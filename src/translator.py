#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import time
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv


class TranslationService:
    def __init__(self, openai_api_key: str = None):
        """
        Initialize the translation service.

        Args:
            openai_api_key: OpenAI API key (optional, defaults to OPENAI_API_KEY env variable)
        """
        # Load environment variables from .env file if exists
        load_dotenv()

        # Use provided API key or get from environment
        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Provide it as an argument or set OPENAI_API_KEY environment variable.")

        # Default model
        self.model = "gpt-4o"

        # OpenAI API endpoint
        self.api_endpoint = "https://api.openai.com/v1/chat/completions"

        # Retry configuration
        self.max_retries = 5
        self.base_delay = 1  # Base delay in seconds

    @staticmethod
    def read_json_file(json_file_path: str) -> Dict[str, Any]:
        """
        Read and parse JSON file.

        Args:
            json_file_path: Path to the JSON file

        Returns:
            Parsed JSON data
        """
        try:
            with open(json_file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
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
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            print(f"Error reading prompt file: {e}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def prepare_prompt(json_data: Dict[str, Any], prompt_template: str) -> str:
        """
        Prepare the prompt by combining the template with JSON data.
        This method can be customized based on how the JSON data should be incorporated.

        Args:
            json_data: Parsed JSON data
            prompt_template: The prompt template

        Returns:
            Final prompt to send to the API
        """
        # Default implementation: Include the JSON data as context
        # Modify this based on your specific needs
        json_str = json.dumps(json_data, indent=2)

        # Combine template with JSON data
        # This assumes the prompt template has a placeholder for the JSON data
        # If not, you might need to adjust this logic
        final_prompt = f"{prompt_template}\n\nJSON Data:\n{json_str}"

        return final_prompt

    def call_openai_api(self, prompt: str) -> Optional[str]:
        """
        Call OpenAI API with the prepared prompt and handle retries.

        Args:
            prompt: The prompt to send to OpenAI

        Returns:
            API response text or None on failure
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"API call attempt {attempt}/{self.max_retries}...")
                response = requests.post(self.api_endpoint, headers=headers, json=data)

                if response.status_code == 200:
                    response_data = response.json()
                    return response_data["choices"][0]["message"]["content"]

                elif response.status_code == 429:
                    print(response.text)
                    # Rate limit hit - implement exponential backoff
                    if attempt < self.max_retries:
                        # Calculate delay with jitter to avoid thundering herd
                        delay = self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                        print(f"Rate limit exceeded. Retrying in {delay:.2f} seconds...")
                        time.sleep(delay)
                    else:
                        print("Max retries reached. Rate limit still exceeded.", file=sys.stderr)
                        return None

                else:
                    # Other errors
                    print(f"API returned error: {response.status_code} - {response.text}", file=sys.stderr)
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

        return None

    @staticmethod
    def save_response(response: str, output_file_path: str) -> None:
        """
        Save the API response to a file.

        Args:
            response: The response from the API
            output_file_path: Path where to save the response
        """
        try:
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]  # Remover ```json
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]  # Remover ```

            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]  # Remover ``` final

            cleaned_response = cleaned_response.strip()

            with open(output_file_path, 'w', encoding='utf-8') as file:
                file.write(cleaned_response)
            print(f"Translation saved to {output_file_path}")
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
        # Read input files
        json_data = self.read_json_file(json_file_path)
        prompt_template = self.read_prompt_file(prompt_file_path)

        # Prepare the prompt
        final_prompt = self.prepare_prompt(json_data, prompt_template)

        # Call OpenAI API
        response = self.call_openai_api(final_prompt)

        if response:
            # Save the response
            self.save_response(response, output_file_path)
        else:
            print("Failed to get translation from OpenAI API", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Translate JSON content using GPT')
    parser.add_argument('json_file', help='Path to the JSON file')
    parser.add_argument('prompt_file', help='Path to the prompt template file (.md)')
    parser.add_argument('-o', '--output', help='Path to the output file (default: translation_output.json)')
    parser.add_argument('-k', '--api-key', help='OpenAI API key (optional, can use OPENAI_API_KEY env variable)')
    parser.add_argument('-m', '--model', help=f'OpenAI model to use (default: gpt-4o)')
    parser.add_argument('-r', '--max-retries', type=int, help=f'Maximum number of retries (default: 5)')

    args = parser.parse_args()

    output_file = args.output or 'translation_output.json'

    # Create translation service
    service = TranslationService(args.api_key)

    # Override defaults if provided
    if args.model:
        service.model = args.model
    if args.max_retries:
        service.max_retries = args.max_retries

    service.translate(args.json_file, args.prompt_file, output_file)


if __name__ == '__main__':
    main()