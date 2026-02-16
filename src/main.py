#!/usr/bin/env python3
"""
Main orchestration script for BDD to IBDD translation workflow.
This script coordinates the complete pipeline:
1. Translate BDD scenarios to IBDD via LLM
2. Parse and validate IBDD syntax
3. Iterative correction loop (explain errors → retry → re-validate)
4. Final summary with metrics
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.translator import TranslationService
from src.parser import validate_ibdd_cases
from src.explainer import IBDDErrorExplainer


class BDDToIBDDPipeline:
    """Orchestrates the complete BDD to IBDD translation and validation pipeline"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        workers: int = 1,
    ):
        """
        Initialize the pipeline.

        Args:
            api_key: API key (optional, defaults to OPENAI_API_KEY env variable)
            provider: LLM provider (openai, ollama)
            model: Model identifier
            base_url: Optional base URL for the LLM provider
            workers: Number of parallel workers for LLM API calls
        """
        self.translation_service = TranslationService(
            api_key,
            provider=provider,
            model=model,
            base_url=base_url,
            workers=workers,
        )
        self.error_explainer = IBDDErrorExplainer(
            api_key,
            provider=provider,
            model=model,
            base_url=base_url,
        )

    @staticmethod
    def _detect_retry_prompt_path(prompt_path: str) -> str:
        """
        Auto-detect the retry prompt path based on the main prompt language.

        If the main prompt contains '_ES' in its filename, the Spanish retry
        prompt is used; otherwise the English one is used.
        """
        prompt_dir = os.path.dirname(prompt_path)
        prompt_name = os.path.basename(prompt_path).upper()

        if '_ES' in prompt_name:
            retry_name = 'PROMPT_ES_RETRY.md'
        else:
            retry_name = 'PROMPT_EN_RETRY.md'

        retry_path = os.path.join(prompt_dir, retry_name)
        if os.path.exists(retry_path):
            return retry_path

        # Fallback to English
        fallback = os.path.join(prompt_dir, 'PROMPT_EN_RETRY.md')
        if os.path.exists(fallback):
            return fallback

        raise FileNotFoundError(
            f"Retry prompt not found. Tried: {retry_path}, {fallback}"
        )

    @staticmethod
    def _get_validation_summary(
            validation_output_path: str
    ) -> Dict[str, Any]:
        """Load validation results and return a summary dict."""
        with open(validation_output_path, 'r', encoding='utf-8') as f:
            results = json.load(f)

        total = len(results)
        passed = sum(1 for r in results if r.get('valid', True))
        failed_ids = [r['id'] for r in results if not r.get('valid', True)]

        return {
            'total': total,
            'passed': passed,
            'failed': total - passed,
            'failed_case_ids': failed_ids,
        }

    def run(
        self,
        dataset_path: str,
        prompt_path: str,
        translation_output_path: str = "data/output.json",
        validation_output_path: str = "data/parsed_ibdd_results.json",
        explanations_output_path: str = "data/error_explanations.json",
        max_rounds: int = 3,
    ) -> Dict[str, Any]:
        """
        Run the complete pipeline with iterative correction.

        Pipeline:
            1. Translate BDD → IBDD via LLM
            2. Validate syntax (Lark parser)
            3. Iterative correction loop (up to max_rounds):
               explain errors → retry translation → re-validate
            4. Final summary

        Args:
            dataset_path: Path to the input dataset JSON file
            prompt_path: Path to the prompt template file (.md)
            translation_output_path: Path where translated IBDD will be saved
            validation_output_path: Path where validation results will be saved
            explanations_output_path: Path where error explanations will be saved
            max_rounds: Maximum number of correction rounds (0 = no retries)

        Returns:
            Dict with pipeline results and per-round metrics
        """
        pipeline_start = time.time()
        retry_prompt_path = self._detect_retry_prompt_path(prompt_path)

        print("=" * 80)
        print("BDD to IBDD Translation Pipeline")
        print(f"Max correction rounds: {max_rounds}")
        print("=" * 80)

        # ── Step 1: Translate BDD to IBDD ──────────────────────────────
        print("\n[Step 1/4] Translating BDD scenarios to IBDD...")
        print("-" * 80)
        try:
            self.translation_service.translate(
                json_file_path=dataset_path,
                prompt_file_path=prompt_path,
                output_file_path=translation_output_path,
                workers=self.translation_service.workers,
            )
            print(f"✓ Translation completed: {translation_output_path}")
        except Exception as e:
            print(f"✗ Translation failed: {e}", file=sys.stderr)
            sys.exit(1)

        # ── Step 2: Validate syntax ────────────────────────────────────
        print("\n[Step 2/4] Parsing and validating IBDD syntax...")
        print("-" * 80)
        try:
            validate_ibdd_cases(
                json_file_path=translation_output_path,
                output_destination=validation_output_path
            )
            print(f"✓ Syntax validation completed: {validation_output_path}")
        except Exception as e:
            print(f"✗ Validation failed: {e}", file=sys.stderr)
            sys.exit(1)

        # Record initial validation results
        initial_summary = self._get_validation_summary(validation_output_path)
        print(f"\n   Initial result: {initial_summary['passed']}/{initial_summary['total']} "
              f"passed ({initial_summary['passed']/initial_summary['total']*100:.1f}%)")

        # ── Step 3: Iterative correction loop ──────────────────────────
        print("\n[Step 3/4] Iterative correction loop...")
        print("-" * 80)

        round_metrics: List[Dict[str, Any]] = []
        all_explanations: List[Dict[str, Any]] = []

        for round_num in range(1, max_rounds + 1):
            round_start = time.time()

            # Collect failed cases
            failed_cases = self._collect_failed_cases(
                translation_output_path,
                validation_output_path
            )

            if not failed_cases:
                print(f"\n✓ All cases passed — no correction needed"
                      + (f" (converged at round {round_num - 1})" if round_num > 1 else ""))
                break

            print(f"\n── Round {round_num}/{max_rounds}: "
                  f"{len(failed_cases)} case(s) still failing ──")

            # Explain errors
            try:
                explanations = self.error_explainer.explain_multiple_errors(failed_cases)
                all_explanations.extend(explanations)
            except Exception as e:
                print(f"⚠ Error explanation failed: {e}", file=sys.stderr)
                round_metrics.append({
                    'round': round_num,
                    'error': str(e),
                })
                break

            # Retry translations with error feedback
            corrected_ids = []
            try:
                corrected = self.translation_service.retry_failed_translations(
                    error_explanations=explanations,
                    retry_prompt_path=retry_prompt_path,
                    workers=self.translation_service.workers,
                )

                if corrected:
                    corrected_ids = [c['id'] for c in corrected]

                    # Merge corrected translations
                    updated = self._merge_translations(
                        translation_output_path, corrected
                    )
                    with open(translation_output_path, 'w', encoding='utf-8') as f:
                        json.dump(updated, indent=2, ensure_ascii=False, fp=f)

                    # Re-validate
                    validate_ibdd_cases(
                        json_file_path=translation_output_path,
                        output_destination=validation_output_path
                    )
            except Exception as e:
                print(f"⚠ Retry failed: {e}", file=sys.stderr)

            # Gather post-round summary
            post_summary = self._get_validation_summary(validation_output_path)
            round_time = time.time() - round_start

            round_metrics.append({
                'round': round_num,
                'failed_before': len(failed_cases),
                'failed_case_ids_before': [c['case_id'] for c in failed_cases],
                'corrected_case_ids': corrected_ids,
                'passed_after': post_summary['passed'],
                'failed_after': post_summary['failed'],
                'failed_case_ids_after': post_summary['failed_case_ids'],
                'round_time': round(round_time, 2),
            })

            print(f"   Round {round_num} result: {post_summary['passed']}/{post_summary['total']} "
                  f"passed ({post_summary['passed']/post_summary['total']*100:.1f}%) "
                  f"[{round_time:.1f}s]")

            if post_summary['failed'] == 0:
                print(f"\n✓ All cases passed — converged at round {round_num}")
                break
        else:
            if max_rounds > 0:
                print(f"\n⚠ Max correction rounds ({max_rounds}) reached")

        # Save all error explanations
        if all_explanations:
            with open(explanations_output_path, 'w', encoding='utf-8') as f:
                json.dump(all_explanations, indent=2, ensure_ascii=False, fp=f)

        # ── Step 4: Final Summary ──────────────────────────────────────
        pipeline_time = time.time() - pipeline_start
        final_summary = self._get_validation_summary(validation_output_path)

        print("\n[Step 4/4] Final Summary")
        print("=" * 80)

        print(f"Translation output:   {translation_output_path}")
        print(f"Syntax validation:    {validation_output_path}")
        if all_explanations:
            print(f"Error explanations:   {explanations_output_path}")

        print(f"\nSyntax Validation: {final_summary['passed']}/{final_summary['total']} "
              f"passed ({final_summary['passed']/final_summary['total']*100:.1f}%)")
        if final_summary['failed_case_ids']:
            print(f"Still failing: {final_summary['failed_case_ids']}")

        print(f"Correction rounds used: {len(round_metrics)}/{max_rounds}")
        print(f"Total pipeline time: {pipeline_time:.1f}s")
        print("=" * 80)
        print()

        # Build and save pipeline metrics
        pipeline_metrics = {
            'model': self.translation_service.model,
            'provider': self.translation_service.provider,
            'prompt': prompt_path,
            'dataset': dataset_path,
            'max_rounds': max_rounds,
            'initial_passed': initial_summary['passed'],
            'initial_failed': initial_summary['failed'],
            'initial_failed_case_ids': initial_summary['failed_case_ids'],
            'final_passed': final_summary['passed'],
            'final_failed': final_summary['failed'],
            'final_failed_case_ids': final_summary['failed_case_ids'],
            'total_cases': final_summary['total'],
            'rounds': round_metrics,
            'total_pipeline_time': round(pipeline_time, 2),
        }

        metrics_path = translation_output_path.replace('.json', '_metrics.json')
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump(pipeline_metrics, indent=2, ensure_ascii=False, fp=f)
        print(f"Pipeline metrics saved: {metrics_path}")

        return pipeline_metrics

    @staticmethod
    def _merge_translations(
            original_translations_path: str,
        corrected_translations: list
    ) -> list:
        """
        Merge corrected translations with original successful translations.

        Args:
            original_translations_path: Path to the original translation output file
            corrected_translations: List of corrected translations from retry

        Returns:
            Updated list of translations with corrections applied
        """
        # Load original translations
        with open(original_translations_path, 'r', encoding='utf-8') as f:
            original_translations = json.load(f)

        # Create a map of case_id to corrected translation
        corrected_map = {case['id']: case for case in corrected_translations}

        # Update original translations with corrections
        updated_translations = []
        for original in original_translations:
            case_id = original['id']
            if case_id in corrected_map:
                # Use corrected version
                updated_translations.append(corrected_map[case_id])
                print(f"  → Case {case_id}: Using corrected translation")
            else:
                # Keep original
                updated_translations.append(original)

        return updated_translations

    @staticmethod
    def _collect_failed_cases(
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

  # Run with Spanish prompt (retry prompt auto-detected)
  python src/main.py data/Dataset.json docs/PROMPT_ES.md

  # Run with more correction rounds
  python src/main.py data/Dataset.json docs/PROMPT_EN.md --max-rounds 5

  # Run with a specific model via Ollama
  python src/main.py data/Dataset.json docs/PROMPT_EN.md \\
    --provider ollama -m llama3.3:70b
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
        help='API key (optional, can use OPENAI_API_KEY env variable)'
    )
    parser.add_argument(
        '-m', '--model',
        help='Model to use (e.g., gpt-4o, llama3.3:70b)'
    )
    parser.add_argument(
        '--provider',
        default=None,
        help='LLM provider: openai or ollama (default: openai)'
    )
    parser.add_argument(
        '--base-url',
        default=None,
        help='Optional base URL for LLM provider'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=3,
        help='Maximum number of correction rounds (default: 3, 0 = no retries)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Parallel workers for LLM API calls (default: 1)'
    )
    # TODO: Add a CLI flag for translation temperature to make performance
    # and quality comparisons reproducible across runs.

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
    pipeline = BDDToIBDDPipeline(
        api_key=args.api_key,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        workers=args.workers,
    )

    # Display configuration
    print(f"Provider: {pipeline.translation_service.provider}")
    print(f"Model:    {pipeline.translation_service.model}")
    print(f"Workers:  {pipeline.translation_service.workers}")
    print()

    # Run the pipeline
    pipeline.run(
        dataset_path=args.dataset,
        prompt_path=args.prompt,
        translation_output_path=args.translation_output,
        validation_output_path=args.validation_output,
        max_rounds=args.max_rounds,
    )


if __name__ == '__main__':
    main()
