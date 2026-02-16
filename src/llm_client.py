#!/usr/bin/env python3
"""
LLM client abstraction using LangChain.

- OpenAI: uses json_schema structured outputs when supported.
- Local (Ollama): best-effort JSON output with optional schema validation.
"""
import json
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import HumanMessage, SystemMessage

try:
    from jsonschema import validate as jsonschema_validate
    from jsonschema import ValidationError as JsonSchemaValidationError
except Exception:  # pragma: no cover - optional dependency
    jsonschema_validate = None
    JsonSchemaValidationError = Exception


class LLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_retries: int = 5,
    ) -> None:
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "openai")).lower()
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.temperature = temperature
        self.max_retries = max_retries
        self._thread_local = threading.local()

    def _get_llm(self):
        """Create one LLM client per thread to avoid concurrency issues."""
        llm = getattr(self._thread_local, "llm", None)
        if llm is None:
            llm = self._build_llm()
            self._thread_local.llm = llm
        return llm

    def _build_llm(self):
        if self.provider == "openai":
            from langchain_openai import ChatOpenAI

            if not self.api_key:
                raise ValueError(
                    "OpenAI API key is required for provider=openai. "
                    "Set OPENAI_API_KEY or pass api_key."
                )

            return ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self.temperature,
            )

        if self.provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
                format="json",
            )

        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
    ) -> Optional[Union[Dict[str, Any], List[Any]]]:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        if self.provider == "openai":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": schema,
                },
            }

            llm = self._get_llm().bind(response_format=response_format)
            for attempt in range(1, self.max_retries + 1):
                try:
                    msg = llm.invoke(messages)
                    return json.loads(msg.content)
                except Exception:
                    if attempt < self.max_retries:
                        delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                        time.sleep(delay)
                    else:
                        return None

        # Best-effort JSON for local models (validate if jsonschema is available)
        schema_hint = (
            "Return ONLY valid JSON that matches this JSON Schema. "
            "Do not include markdown or explanations. "
            f"Schema: {json.dumps(schema, ensure_ascii=False)}"
        )
        messages_with_schema = [
            SystemMessage(content=schema_hint),
            *messages,
        ]
        for attempt in range(1, self.max_retries + 1):
            try:
                msg = self._get_llm().invoke(messages_with_schema)
                content = msg.content
                parsed = json.loads(content)

                if jsonschema_validate:
                    jsonschema_validate(instance=parsed, schema=schema)

                return parsed
            except (json.JSONDecodeError, JsonSchemaValidationError, Exception):
                if attempt < self.max_retries:
                    delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                else:
                    return None
        return None
