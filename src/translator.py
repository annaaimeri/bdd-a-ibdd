#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Optional, Union, List

from dotenv import load_dotenv
from tqdm import tqdm

try:
    from src.llm_client import LLMClient
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from src.llm_client import LLMClient


class TranslationService:
    def __init__(
        self,
        api_key: str = None,
        provider: str = None,
        model: str = None,
        base_url: str = None,
    ):
        """
        Initialize the translation service.

        Args:
            api_key: API key (optional, defaults to OPENAI_API_KEY env variable)
            provider: LLM provider (openai, ollama)
            model: Model identifier
            base_url: Optional base URL for the LLM provider
        """
        load_dotenv()

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o")
        self.provider = provider or os.environ.get("LLM_PROVIDER", "openai")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.max_retries = 5
        self.base_delay = 1

        self.llm_client = LLMClient(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.7,
            max_retries=self.max_retries,
        )

    @staticmethod
    def read_json_file(json_file_path: str) -> Union[Dict[str, Any], List[Any]]:
        """
        Read and parse JSON file.

        Args:
            json_file_path: Path to the JSON file

        Returns:
            Parsed JSON data
        """
        try:
            print(f"Reading JSON file: {json_file_path}")
            with open(json_file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            if isinstance(data, list):
                print(f"Successfully loaded JSON array with {len(data)} items")
            else:
                print(f"Successfully loaded JSON with {len(data)} keys")
            return data
        except Exception as e:
            print(f"Error reading JSON file: {e}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def read_prompt_file(prompt_file_path: str) -> str:
        """
        Read prompt template from file.

        Args:
            prompt_file_path: Path to the prompt file

        Returns:
            Prompt template as string
        """
        try:
            print(f"Reading prompt template: {prompt_file_path}")
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            print(f"Error reading prompt file: {e}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def prepare_prompt(json_data: Union[Dict[str, Any], List[Any]], prompt_template: str) -> str:
        """
        Prepare the prompt by combining the template with JSON data.

        Args:
            json_data: Parsed JSON data
            prompt_template: The prompt template

        Returns:
            Final prompt to send to the API
        """
        print("Preparing prompt with JSON data...")
        json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
        final_prompt = f"{prompt_template}\n\nJSON Data:\n{json_str}"
        return final_prompt

    @staticmethod
    def create_response_schema(json_data: Union[Dict[str, Any], List[Any]]) -> Dict[str, Any]:
        """
        Create a JSON schema based on the input JSON structure.

        Args:
            json_data: The input JSON data

        Returns:
            JSON schema for structured output (always wrapped in object)
        """

        def infer_type(val):
            if isinstance(val, str):
                return {"type": "string"}
            elif isinstance(val, bool):
                return {"type": "boolean"}
            elif isinstance(val, int):
                return {"type": "integer"}
            elif isinstance(val, float):
                return {"type": "number"}
            elif isinstance(val, list):
                if val:
                    return {
                        "type": "array",
                        "items": infer_type(val[0])
                    }
                return {"type": "array", "items": {"type": "string"}}
            elif isinstance(val, dict):
                props = {}
                req = []
                for k, v in val.items():
                    props[k] = infer_type(v)
                    req.append(k)
                return {
                    "type": "object",
                    "properties": props,
                    "required": req,
                    "additionalProperties": False
                }
            elif val is None:
                return {"type": ["string", "null"]}
            else:
                return {"type": "string"}

        if isinstance(json_data, list):
            if json_data:
                item_schema = infer_type(json_data[0])
                # Add ibdd_representation field to the schema if not present
                if item_schema.get("type") == "object":
                    if "ibdd_representation" not in item_schema.get("properties", {}):
                        item_schema["properties"]["ibdd_representation"] = {"type": "string"}
                        if "required" in item_schema:
                            item_schema["required"].append("ibdd_representation")
            else:
                item_schema = {"type": "object", "additionalProperties": True}

            schema = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": item_schema
                    }
                },
                "required": ["items"],
                "additionalProperties": False
            }
        else:
            properties = {}
            required = []

            for key, value in json_data.items():
                properties[key] = infer_type(value)
                required.append(key)

            schema = {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False
            }

        return schema

    def call_llm_api(self, prompt: str, json_data: Union[Dict[str, Any], List[Any]]) -> Optional[
        Union[Dict[str, Any], List[Any]]]:
        """
        Call the LLM with the prepared prompt and structured output.

        Args:
            prompt: The prompt to send
            json_data: Original JSON data for schema inference

        Returns:
            API response as dict/list or None on failure
        """
        schema = self.create_response_schema(json_data)
        is_array_input = isinstance(json_data, list)

        print(f"Calling LLM provider: {self.provider} | model: {self.model}")
        print("Using Structured Outputs with JSON Schema when supported")

        response = self.llm_client.generate_json(
            system_prompt=(
                "You are a translation assistant. Translate the provided JSON content "
                "according to the instructions. Maintain the exact same structure as the input."
            ),
            user_prompt=prompt,
            schema=schema,
        )

        if response is None:
            return None

        if is_array_input and isinstance(response, dict) and "items" in response:
            return response["items"]

        return response

    def translate_single_case(
        self,
        case: Dict[str, Any],
        prompt_template: str
    ) -> Optional[Dict[str, Any]]:
        """
        Translate a single BDD case to IBDD.

        Args:
            case: Single case dict with id, given, when, then
            prompt_template: The prompt template to use

        Returns:
            Translated case with metrics, or None on failure
        """
        start_time = time.time()

        # Prepare prompt for this single case
        final_prompt = self.prepare_prompt([case], prompt_template)

        # Call API
        response = self.call_llm_api(final_prompt, [case])

        elapsed_time = time.time() - start_time

        if response and isinstance(response, list) and len(response) > 0:
            translated_case = response[0]
            # Add metrics to the response
            translated_case['_metrics'] = {
                'translation_time': round(elapsed_time, 2),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            return translated_case

        return None

    @staticmethod
    def save_response(response: Union[Dict[str, Any], List[Any]], output_file_path: str) -> None:
        """
        Save the API response to a file.

        Args:
            response: The response dict/list from the API
            output_file_path: Path where to save the response
        """
        try:
            print(f"Saving translation to: {output_file_path}")
            with open(output_file_path, 'w', encoding='utf-8') as file:
                json.dump(response, file, indent=2, ensure_ascii=False)
            print(f"Translation saved successfully")
        except Exception as e:
            print(f"Error saving response: {e}", file=sys.stderr)

    def translate(self, json_file_path: str, prompt_file_path: str, output_file_path: str) -> None:
        """
        Complete translation workflow from JSON to output via LLM.
        Processes cases individually with incremental saving and progress tracking.

        Args:
            json_file_path: Path to the JSON file
            prompt_file_path: Path to the prompt template file
            output_file_path: Path where to save the translation
        """
        print("=" * 80)
        print("Starting individual case translation process...")
        print("=" * 80)

        # Load data
        json_data = self.read_json_file(json_file_path)
        prompt_template = self.read_prompt_file(prompt_file_path)

        # Ensure json_data is a list
        if not isinstance(json_data, list):
            print("Error: Dataset must be a JSON array of cases", file=sys.stderr)
            sys.exit(1)

        total_cases = len(json_data)
        print(f"\nProcessing {total_cases} cases individually...")
        print(f"Output will be saved incrementally to: {output_file_path}")
        print("-" * 80)

        # Track results and metrics
        translated_cases = []
        failed_cases = []
        total_time = 0

        # Process each case individually with progress bar
        for case in tqdm(json_data, desc="Translating", unit="case"):
            case_id = case.get('id', 'unknown')

            try:
                translated_case = self.translate_single_case(case, prompt_template)

                if translated_case:
                    translated_cases.append(translated_case)
                    if '_metrics' in translated_case:
                        total_time += translated_case['_metrics'].get('translation_time', 0)

                    # Incremental save after each successful translation
                    self.save_response(translated_cases, output_file_path)
                else:
                    failed_cases.append({
                        'id': case_id,
                        'reason': 'API returned None'
                    })
                    print(f"\n⚠ Warning: Case {case_id} failed to translate", file=sys.stderr)

            except Exception as e:
                failed_cases.append({
                    'id': case_id,
                    'reason': str(e)
                })
                print(f"\n✗ Error translating case {case_id}: {e}", file=sys.stderr)
                # Continue with next case instead of failing completely

        # Final save
        self.save_response(translated_cases, output_file_path)

        # Print summary
        print("\n" + "=" * 80)
        print("Translation Summary")
        print("=" * 80)
        print(f"Total cases:        {total_cases}")
        print(f"Successfully translated: {len(translated_cases)}")
        print(f"Failed:            {len(failed_cases)}")
        print(f"Success rate:      {len(translated_cases)/total_cases*100:.1f}%")
        print(f"Total time:        {total_time:.1f}s")
        print(f"Average per case:  {total_time/len(translated_cases):.1f}s" if translated_cases else "N/A")
        print(f"Output saved to:   {output_file_path}")

        if failed_cases:
            print("\nFailed cases:")
            for failed in failed_cases:
                print(f"  - Case {failed['id']}: {failed['reason']}")

        print("=" * 80)

        if not translated_cases:
            print("\n✗ No cases were successfully translated", file=sys.stderr)
            sys.exit(1)

    def retry_failed_translations(
        self,
        error_explanations: List[Dict[str, Any]],
        retry_prompt_path: str = "docs/PROMPT_EN_RETRY.md"
    ) -> List[Dict[str, Any]]:
        """
        Retry translation for cases that failed parsing, using error analysis.
        Processes each failed case individually.

        Args:
            error_explanations: List of error explanation dicts (from IBDDErrorExplainer)
            retry_prompt_path: Path to the retry prompt template

        Returns:
            List of corrected translations (same format as original translation output)
        """
        from src.explainer import IBDDErrorExplainer

        print(f"\n[Retry] Attempting to correct {len(error_explanations)} failed translation(s)...")
        print("-" * 80)

        # Read retry prompt template
        retry_prompt_template = self.read_prompt_file(retry_prompt_path)

        # Track results
        corrected_cases = []
        retry_failed_cases = []

        # Process each failed case individually with progress bar
        for error_exp in tqdm(error_explanations, desc="Retrying", unit="case"):
            case_id = error_exp.get('case_id', 'unknown')

            if not error_exp.get('success', False):
                print(f"\n⚠ Skipping case {case_id} - error explanation failed")
                retry_failed_cases.append(case_id)
                continue

            try:
                # Build the case JSON from original BDD
                original_bdd = error_exp.get('original_bdd', {})
                case_data = {
                    'id': case_id,
                    'given': original_bdd.get('given', ''),
                    'when': original_bdd.get('when', ''),
                    'then': original_bdd.get('then', '')
                }

                # Format error analysis for this specific case
                error_analysis_text = IBDDErrorExplainer.format_error_analysis_for_retry(error_exp)

                # Replace placeholder in retry prompt with this case's error analysis
                case_retry_prompt = retry_prompt_template.replace(
                    '{error_analysis}',
                    error_analysis_text
                )

                # Translate this single case with error context
                corrected_case = self.translate_single_case(case_data, case_retry_prompt)

                if corrected_case:
                    corrected_cases.append(corrected_case)
                else:
                    print(f"\n⚠ Warning: Retry failed for case {case_id}")
                    retry_failed_cases.append(case_id)

            except Exception as e:
                print(f"\n✗ Error retrying case {case_id}: {e}", file=sys.stderr)
                retry_failed_cases.append(case_id)

        # Print summary
        print("\n" + "-" * 80)
        print(f"Retry Summary:")
        print(f"  Attempted:  {len(error_explanations)}")
        print(f"  Corrected:  {len(corrected_cases)}")
        print(f"  Still failed: {len(retry_failed_cases)}")
        if retry_failed_cases:
            print(f"  Failed IDs: {retry_failed_cases}")
        print("-" * 80)

        return corrected_cases


def main():
    parser = argparse.ArgumentParser(description='Translate JSON content using LLM with Structured Outputs')
    parser.add_argument('json_file', help='Path to the JSON file')
    parser.add_argument('prompt_file', help='Path to the prompt template file (.md)')
    parser.add_argument('-o', '--output', help='Path to the output file (default: translation_output.json)')
    parser.add_argument('-k', '--api-key', help='API key (optional, can use OPENAI_API_KEY env variable)')
    parser.add_argument('-m', '--model', help='Model to use (e.g., gpt-4o, llama3.3:70b)')
    parser.add_argument('-r', '--max-retries', type=int, help='Maximum number of API retries (default: 5)')
    parser.add_argument('--provider', default=None, help='LLM provider: openai or ollama (default: openai)')
    parser.add_argument('--base-url', default=None, help='Optional base URL for LLM provider')

    args = parser.parse_args()

    output_file = args.output or 'translation_output.json'

    service = TranslationService(
        args.api_key,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
    )
    if args.max_retries:
        service.max_retries = args.max_retries

    service.translate(args.json_file, args.prompt_file, output_file)


if __name__ == '__main__':
    main()
