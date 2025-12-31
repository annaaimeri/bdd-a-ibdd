#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import time
from typing import Dict, Any, Optional, Union, List

import requests
from dotenv import load_dotenv


class TranslationService:
    def __init__(self, openai_api_key: str = None):
        """
        Initialize the translation service.

        Args:
            openai_api_key: OpenAI API key (optional, defaults to OPENAI_API_KEY env variable)
        """
        load_dotenv()

        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Provide it as an argument or set OPENAI_API_KEY environment variable.")

        self.model = "gpt-4o-2024-08-06"
        self.api_endpoint = "https://api.openai.com/v1/chat/completions"
        self.max_retries = 5
        self.base_delay = 1

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

        def infer_type(value):
            if isinstance(value, str):
                return {"type": "string"}
            elif isinstance(value, bool):
                return {"type": "boolean"}
            elif isinstance(value, int):
                return {"type": "integer"}
            elif isinstance(value, float):
                return {"type": "number"}
            elif isinstance(value, list):
                if value:
                    return {
                        "type": "array",
                        "items": infer_type(value[0])
                    }
                return {"type": "array", "items": {"type": "string"}}
            elif isinstance(value, dict):
                properties = {}
                required = []
                for k, v in value.items():
                    properties[k] = infer_type(v)
                    required.append(k)
                return {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False
                }
            elif value is None:
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

    def call_openai_api(self, prompt: str, json_data: Union[Dict[str, Any], List[Any]]) -> Optional[
        Union[Dict[str, Any], List[Any]]]:
        """
        Call OpenAI API with the prepared prompt and structured output.

        Args:
            prompt: The prompt to send to OpenAI
            json_data: Original JSON data for schema inference

        Returns:
            API response as dict/list or None on failure
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        schema = self.create_response_schema(json_data)
        is_array_input = isinstance(json_data, list)

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a translation assistant. Translate the provided JSON content according to the instructions. Maintain the exact same structure as the input."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "translation_response",
                    "strict": True,
                    "schema": schema
                }
            },
            "temperature": 0.7
        }

        print(f"Calling OpenAI API with model: {self.model}")
        print("Using Structured Outputs with JSON Schema")

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(self.api_endpoint, headers=headers, json=data)

                if response.status_code == 200:
                    print("Translation completed successfully")
                    response_data = response.json()

                    message = response_data["choices"][0]["message"]

                    if message.get("refusal"):
                        print(f"API refused the request: {message['refusal']}", file=sys.stderr)
                        return None

                    content = message["content"]
                    parsed_content = json.loads(content)

                    if is_array_input and isinstance(parsed_content, dict) and "items" in parsed_content:
                        return parsed_content["items"]

                    return parsed_content

                elif response.status_code == 429:
                    print(response.text)
                    if attempt < self.max_retries:
                        delay = self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                        print(f"Rate limit exceeded. Waiting {delay:.2f} seconds before retry...")
                        time.sleep(delay)
                    else:
                        print("Max retries reached. Rate limit still exceeded.", file=sys.stderr)
                        return None

                else:
                    print(f"API error: {response.status_code} - {response.text}", file=sys.stderr)
                    if attempt < self.max_retries:
                        delay = self.base_delay * (2 ** (attempt - 1))
                        print(f"Retrying in {delay:.2f} seconds...")
                        time.sleep(delay)
                    else:
                        return None

            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}", file=sys.stderr)
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    print(f"Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    return None
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}", file=sys.stderr)
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    print(f"Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    return None

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
        Complete translation workflow from JSON to output via GPT.

        Args:
            json_file_path: Path to the JSON file
            prompt_file_path: Path to the prompt template file
            output_file_path: Path where to save the translation
        """
        print("Starting translation process...")

        json_data = self.read_json_file(json_file_path)
        prompt_template = self.read_prompt_file(prompt_file_path)
        final_prompt = self.prepare_prompt(json_data, prompt_template)
        response = self.call_openai_api(final_prompt, json_data)

        if response:
            self.save_response(response, output_file_path)
            print("Translation process completed")
        else:
            print("Failed to get translation from OpenAI API", file=sys.stderr)
            sys.exit(1)

    def retry_failed_translations(
        self,
        error_explanations: List[Dict[str, Any]],
        retry_prompt_path: str = "docs/PROMPT_EN_RETRY.md"
    ) -> List[Dict[str, Any]]:
        """
        Retry translation for cases that failed parsing, using error analysis.

        Args:
            error_explanations: List of error explanation dicts (from IBDDErrorExplainer)
            retry_prompt_path: Path to the retry prompt template

        Returns:
            List of corrected translations (same format as original translation output)
        """
        from src.explainer import IBDDErrorExplainer

        print(f"\n[Retry] Attempting to correct {len(error_explanations)} failed translation(s)...")

        # Read retry prompt template
        retry_prompt_template = self.read_prompt_file(retry_prompt_path)

        # Build JSON data with only failed cases (using original BDD)
        failed_cases_json = []
        error_analysis_sections = []

        for error_exp in error_explanations:
            if not error_exp.get('success', False):
                print(f"⚠ Skipping case {error_exp.get('case_id')} - error explanation failed")
                continue

            # Build the case JSON from original BDD
            original_bdd = error_exp.get('original_bdd', {})
            case_data = {
                'id': error_exp.get('case_id'),
                'given': original_bdd.get('given', ''),
                'when': original_bdd.get('when', ''),
                'then': original_bdd.get('then', '')
            }
            failed_cases_json.append(case_data)

            # Format error analysis for this case
            error_analysis_text = IBDDErrorExplainer.format_error_analysis_for_retry(error_exp)
            error_analysis_sections.append(error_analysis_text)

        if not failed_cases_json:
            print("⚠ No valid cases to retry")
            return []

        # Combine all error analyses
        combined_error_analysis = "\n\n" + "="*80 + "\n\n".join(error_analysis_sections)

        # Replace placeholder in retry prompt
        final_retry_prompt = retry_prompt_template.replace(
            '{error_analysis}',
            combined_error_analysis
        )

        # Prepare final prompt with JSON data
        final_prompt = self.prepare_prompt(failed_cases_json, final_retry_prompt)

        # Call OpenAI API
        print(f"[Retry] Calling OpenAI API to correct {len(failed_cases_json)} case(s)...")
        response = self.call_openai_api(final_prompt, failed_cases_json)

        if response:
            print(f"✓ Retry completed successfully for {len(response)} case(s)")
            return response
        else:
            print("✗ Retry failed - could not get corrected translations", file=sys.stderr)
            return []


def main():
    parser = argparse.ArgumentParser(description='Translate JSON content using GPT with Structured Outputs')
    parser.add_argument('json_file', help='Path to the JSON file')
    parser.add_argument('prompt_file', help='Path to the prompt template file (.md)')
    parser.add_argument('-o', '--output', help='Path to the output file (default: translation_output.json)')
    parser.add_argument('-k', '--api-key', help='OpenAI API key (optional, can use OPENAI_API_KEY env variable)')
    parser.add_argument('-m', '--model', help=f'OpenAI model to use (default: gpt-4o-2024-08-06)')
    parser.add_argument('-r', '--max-retries', type=int, help=f'Maximum number of retries (default: 5)')

    args = parser.parse_args()

    output_file = args.output or 'translation_output.json'

    service = TranslationService(args.api_key)

    if args.model:
        service.model = args.model
    if args.max_retries:
        service.max_retries = args.max_retries

    service.translate(args.json_file, args.prompt_file, output_file)


if __name__ == '__main__':
    main()