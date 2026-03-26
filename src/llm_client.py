#!/usr/bin/env python3
"""
Abstracción de cliente LLM basada en LangChain.

- OpenAI: usa `json_schema` con salidas estructuradas cuando está disponible.
- Local (Ollama): salida JSON en mejor esfuerzo con validación opcional de esquema.
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
except Exception:  # pragma: no cover - dependencia opcional
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
        request_timeout_s: int = 120,
    ) -> None:
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "openai")).lower()
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.temperature = temperature
        self.max_retries = max_retries
        self.request_timeout_s = request_timeout_s
        self._thread_local = threading.local()

    def _get_llm(self):
        """Crea un cliente LLM por hilo para evitar problemas de concurrencia."""
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
                    "Se requiere clave de OpenAI para provider=openai. "
                    "Definí OPENAI_API_KEY o pasá api_key."
                )

            return ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self.temperature,
                request_timeout=self.request_timeout_s,
            )

        if self.provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
                format="json",
            )

        raise ValueError(f"Proveedor LLM no soportado: {self.provider}")

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
                except Exception as e:
                    if attempt < self.max_retries:
                        delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                        time.sleep(delay)
                    else:
                        print(
                            f"[LLMClient] OpenAI generate_json failed after {self.max_retries} intentos: "
                            f"{type(e).__name__}: {e}"
                        )
                        print(
                            "[LLMClient] Reintentando con JSON en mejor esfuerzo y validacion local."
                        )
                        return self._generate_json_best_effort(messages, schema)

        return self._generate_json_best_effort(messages, schema)

    def _generate_json_best_effort(
        self,
        messages: List[Union[SystemMessage, HumanMessage]],
        schema: Dict[str, Any],
    ) -> Optional[Union[Dict[str, Any], List[Any]]]:
        # JSON en mejor esfuerzo para modelos locales o fallback de OpenAI
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
                parsed = self._normalize_singleton_items_wrapper(parsed, schema)
                parsed = self._normalize_known_schema_shapes(parsed, schema)

                if jsonschema_validate:
                    jsonschema_validate(instance=parsed, schema=schema)

                return parsed
            except (json.JSONDecodeError, JsonSchemaValidationError, Exception) as e:
                if attempt < self.max_retries:
                    delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                else:
                    print(
                        f"[LLMClient] JSON best-effort generate_json failed after {self.max_retries} intentos: "
                        f"{type(e).__name__}: {e}"
                    )
                    return None
        return None

    @staticmethod
    def _normalize_singleton_items_wrapper(
        parsed: Union[Dict[str, Any], List[Any]],
        schema: Dict[str, Any],
    ) -> Union[Dict[str, Any], List[Any]]:
        """Adapta respuestas de un solo objeto a un schema envuelto en {"items": [...]}."""
        if not isinstance(parsed, dict):
            return parsed

        if schema.get("type") != "object":
            return parsed

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        items_schema = properties.get("items")

        if "items" not in required or not isinstance(items_schema, dict):
            return parsed

        if items_schema.get("type") != "array":
            return parsed

        if "items" in parsed:
            return parsed

        item_schema = items_schema.get("items", {})
        item_properties = item_schema.get("properties", {})
        if item_schema.get("type") != "object" or not item_properties:
            return parsed

        if set(parsed.keys()).issubset(set(item_properties.keys())):
            return {"items": [parsed]}

        return parsed

    @staticmethod
    def _normalize_known_schema_shapes(
        parsed: Union[Dict[str, Any], List[Any]],
        schema: Dict[str, Any],
    ) -> Union[Dict[str, Any], List[Any]]:
        """Normaliza campos conocidos cuando modelos locales respetan la semantica pero no el tipo exacto."""
        if not isinstance(parsed, dict):
            return parsed

        properties = schema.get("properties", {})

        error_location_schema = properties.get("error_location")
        error_location = parsed.get("error_location")
        if (
            isinstance(error_location_schema, dict)
            and error_location_schema.get("type") == "string"
            and isinstance(error_location, dict)
        ):
            line = error_location.get("line")
            column = error_location.get("column")
            parts = []
            if line is not None:
                parts.append(f"line {line}")
            if column is not None:
                parts.append(f"column {column}")
            parsed["error_location"] = ", ".join(parts) if parts else json.dumps(error_location, ensure_ascii=False)

        return parsed
