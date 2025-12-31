#!/usr/bin/env python3
"""
Main orchestration script for BDD to IBDD translation workflow.
This script coordinates the complete pipeline:
1. Load dataset JSON
2. Translate BDD scenarios to IBDD using OpenAI
3. Parse and validate IBDD results
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.translator import TranslationService
from src.parser import validate_ibdd_cases
from src.explainer import IBDDErrorExplainer


class BDDToIBDDPipeline:
    """Orchestrates the complete BDD to IBDD translation and validation pipeline"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the pipeline.

        Args:
            api_key: OpenAI API key (optional, defaults to OPENAI_API_KEY env variable)
        """
        self.translation_service = TranslationService(api_key)
        self.error_explainer = IBDDErrorExplainer(api_key)

    def run(
        self,
        dataset_path: str,
        prompt_path: str,
        translation_output_path: str = "data/output.json",
        validation_output_path: str = "data/parsed_ibdd_results.json",
        explanations_output_path: str = "data/error_explanations.json"
    ) -> None:
        """
        Run the complete pipeline: dataset → translation → parsing/validation → error explanation (if needed)

        Args:
            dataset_path: Path to the input dataset JSON file
            prompt_path: Path to the prompt template file (.md)
            translation_output_path: Path where translated IBDD will be saved
            validation_output_path: Path where validation results will be saved
            explanations_output_path: Path where error explanations will be saved (if errors exist)
        """
        print("=" * 80)
        print("BDD to IBDD Translation Pipeline")
        print("=" * 80)

        # Step 1: Translate BDD to IBDD
        print("\n[Step 1/3] Translating BDD scenarios to IBDD...")
        print("-" * 80)
        try:
            self.translation_service.translate(
                json_file_path=dataset_path,
                prompt_file_path=prompt_path,
                output_file_path=translation_output_path
            )
            print(f"✓ Translation completed: {translation_output_path}")
        except Exception as e:
            print(f"✗ Translation failed: {e}", file=sys.stderr)
            sys.exit(1)

        # Step 2: Parse and validate IBDD
        print("\n[Step 2/3] Parsing and validating IBDD scenarios...")
        print("-" * 80)
        try:
            validate_ibdd_cases(
                json_file_path=translation_output_path,
                output_file=validation_output_path
            )
            print(f"✓ Validation completed: {validation_output_path}")
        except Exception as e:
            print(f"✗ Validation failed: {e}", file=sys.stderr)
            sys.exit(1)

        # Step 3: Explain errors if any cases failed
        print("\n[Step 3/3] Checking for parsing errors...")
        print("-" * 80)
        try:
            failed_cases = self._collect_failed_cases(
                translation_output_path,
                validation_output_path
            )

            if failed_cases:
                print(f"⚠ Found {len(failed_cases)} case(s) with parsing errors")
                print("Generating error explanations...")

                explanations = self.error_explainer.explain_multiple_errors(failed_cases)

                # Save explanations
                with open(explanations_output_path, 'w', encoding='utf-8') as f:
                    json.dump(explanations, indent=2, ensure_ascii=False, fp=f)

                print(f"✓ Error explanations saved: {explanations_output_path}")
            else:
                print("✓ All cases parsed successfully - no errors to explain")
        except Exception as e:
            print(f"⚠ Error explanation step failed (non-critical): {e}", file=sys.stderr)
            print("Pipeline will continue despite explanation failure")

        # Summary
        print("\n" + "=" * 80)
        print("Pipeline completed successfully!")
        print("=" * 80)
        print(f"Translation output: {translation_output_path}")
        print(f"Validation output:  {validation_output_path}")
        print(f"Validation CSV:     {validation_output_path.replace('.json', '.csv')}")

        # Check if there were errors
        if os.path.exists(explanations_output_path):
            print(f"Error explanations: {explanations_output_path}")
            with open(validation_output_path, 'r', encoding='utf-8') as f:
                validation_results = json.load(f)
                total = len(validation_results)
                failed = sum(1 for r in validation_results if not r.get('valid', True))
                print(f"\nValidation Summary: {total - failed}/{total} cases passed, {failed} failed")
        print()

    def _collect_failed_cases(
        self,
        translation_output_path: str,
        validation_output_path: str
    ) -> list:
        """
        Collect all cases that failed parsing for error explanation.

        Args:
            translation_output_path: Path to the translation output file
            validation_output_path: Path to the validation results file

        Returns:
            List of failed cases with all necessary information for explanation
        """
        # Load translation results (original BDD + generated IBDD)
        with open(translation_output_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)

        # Load validation results (parsing success/failure + errors)
        with open(validation_output_path, 'r', encoding='utf-8') as f:
            validations = json.load(f)

        # Create a mapping of case ID to translation data
        translation_map = {case['id']: case for case in translations}

        # Collect failed cases
        failed_cases = []
        for validation in validations:
            if not validation.get('valid', True):
                case_id = validation['id']
                translation = translation_map.get(case_id)

                if translation:
                    failed_cases.append({
                        'case_id': case_id,
                        'original_bdd': {
                            'given': translation.get('given', ''),
                            'when': translation.get('when', ''),
                            'then': translation.get('then', '')
                        },
                        'generated_ibdd': translation.get('ibdd_representation', ''),
                        'parse_error': validation.get('error', 'Unknown error')
                    })

        return failed_cases


def main():
    """Main entry point for the pipeline"""
    parser = argparse.ArgumentParser(
        description='Complete BDD to IBDD translation and validation pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default paths
  python src/main.py data/Dataset.json docs/PROMPT_EN.md

  # Run with custom output paths
  python src/main.py data/Dataset.json docs/PROMPT_EN.md \\
    -t data/my_translation.json \\
    -v data/my_validation.json

  # Run with custom API key
  python src/main.py data/Dataset.json docs/PROMPT_EN.md -k sk-...
        """
    )

    parser.add_argument(
        'dataset',
        help='Path to the input dataset JSON file'
    )
    parser.add_argument(
        'prompt',
        help='Path to the prompt template file (.md)'
    )
    parser.add_argument(
        '-t', '--translation-output',
        default='data/output.json',
        help='Path for translation output (default: data/output.json)'
    )
    parser.add_argument(
        '-v', '--validation-output',
        default='data/parsed_ibdd_results.json',
        help='Path for validation output (default: data/parsed_ibdd_results.json)'
    )
    parser.add_argument(
        '-k', '--api-key',
        help='OpenAI API key (optional, can use OPENAI_API_KEY env variable)'
    )
    parser.add_argument(
        '-m', '--model',
        help='OpenAI model to use (default: gpt-4o-2024-08-06)'
    )

    args = parser.parse_args()

    # Validate input files exist
    if not os.path.exists(args.dataset):
        print(f"Error: Dataset file not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.prompt):
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    # Create output directories if needed
    os.makedirs(os.path.dirname(args.translation_output) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(args.validation_output) or '.', exist_ok=True)

    # Initialize and run pipeline
    pipeline = BDDToIBDDPipeline(api_key=args.api_key)

    # Set custom model if provided
    if args.model:
        pipeline.translation_service.model = args.model

    # Run the pipeline
    pipeline.run(
        dataset_path=args.dataset,
        prompt_path=args.prompt,
        translation_output_path=args.translation_output,
        validation_output_path=args.validation_output
    )


if __name__ == '__main__':
    main()
