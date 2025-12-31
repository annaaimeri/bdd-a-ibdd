#!/usr/bin/env python3
"""
Agente Explicador de Errores IBDD
Analiza errores del parser y proporciona explicaciones detalladas para su corrección.
"""
import json
import os
import sys
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv


class IBDDErrorExplainer:
    """
    Agente que analiza errores de parsing IBDD y proporciona explicaciones detalladas
    para ayudar al traductor a corregir los problemas.
    """

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Inicializa el agente explicador.

        Args:
            openai_api_key: Clave API de OpenAI (opcional, usa variable de entorno OPENAI_API_KEY por defecto)
        """
        load_dotenv()

        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Se requiere una clave API de OpenAI. Proporciónala como argumento o configura la variable OPENAI_API_KEY.")

        self.model = "gpt-4o-2024-08-06"
        self.api_endpoint = "https://api.openai.com/v1/chat/completions"

        self.system_prompt = self._load_system_prompt()

    @staticmethod
    def _load_system_prompt() -> str:
        """Carga el prompt del sistema para el agente explicador"""
        return """Eres un experto analizador de sintaxis IBDD (Intermediate Behavior-Driven Development).

                Tu rol es analizar errores de parsing en representaciones IBDD y proporcionar explicaciones claras y accionables para ayudar a corregirlos.
                
                ## Referencia de Gramática IBDD:
                
                ```
                Scenario ::= Given When Then
                Given    ::= 'GIVEN' Declaration '[' Guard ']'
                Declaration ::= lv1, ..., lvn
                Guard    ::= P | Guard '∧' Guard
                When     ::= 'WHEN' Switch+
                Switch   ::= Interaction '[' Condition ']' Assignment
                Interaction ::= g. iv1, ..., ivn
                Condition ::= B
                Assignment ::= A
                Then     ::= 'THEN' Switch* '[' Guard ']'
                ```
                
                ## Patrones de Error Comunes:
                
                1. **Corchetes faltantes en guardas**: Las guardas DEBEN estar encerradas en `[...]`
                2. **Corchetes faltantes en condiciones**: Cada switch DEBE tener condición en `[...]`
                3. **Sintaxis de gate incorrecta**: Los gates deben comenzar con `!` (salida) o `?` (entrada)
                4. **Asignaciones faltantes**: Cada switch necesita una asignación (o `true`)
                5. **Expresiones mal formadas**: Revisar operadores, nombres de variables, llamadas a funciones
                6. **Saltos de línea incorrectos**: Cada switch debe estar en línea separada
                7. **Postcondición faltante**: La cláusula THEN debe terminar con `[...]`
                
                ## Tu Tarea:
                
                Cuando se te proporcione un error de parsing, debes:
                1. Identificar la ubicación exacta y naturaleza del error
                2. Explicar qué esperaba el parser vs qué encontró
                3. Proporcionar sugerencias específicas de corrección
                4. Referenciar el escenario BDD original para asegurar corrección semántica
                
                Sé preciso, conciso y accionable en tus explicaciones."""

    def explain_error(
        self,
        case_id: str,
        original_bdd: Dict[str, str],
        generated_ibdd: str,
        parse_error: str
    ) -> Dict[str, Any]:
        """
        Analiza un error de parsing y genera una explicación detallada.

        Args:
            case_id: ID del caso que falló
            original_bdd: Escenario BDD original (given, when, then)
            generated_ibdd: La representación IBDD que falló al parsear
            parse_error: Mensaje de error del parser

        Returns:
            Diccionario con análisis y sugerencias de corrección
        """
        print(f"\n[Explainer] Analizando error para caso {case_id}...")

        # Preparar el prompt de análisis
        analysis_prompt = self._create_analysis_prompt(
            case_id, original_bdd, generated_ibdd, parse_error
        )

        # Llamar a la API de OpenAI
        response = self._call_openai_api(analysis_prompt)

        if response:
            return {
                "case_id": case_id,
                "success": True,
                "original_bdd": original_bdd,  # Incluir escenario BDD completo
                "previous_translation": generated_ibdd,  # Incluir traducción que falló
                "parse_error": parse_error,  # Incluir error del parser
                "explanation": response.get("explanation", ""),
                "error_type": response.get("error_type", "unknown"),
                "error_location": response.get("error_location", ""),
                "correction_suggestion": response.get("correction_suggestion", ""),
                "hints": response.get("hints", [])
            }
        else:
            return {
                "case_id": case_id,
                "success": False,
                "original_bdd": original_bdd,  # Incluir incluso en caso de falla
                "previous_translation": generated_ibdd,
                "parse_error": parse_error,
                "error": "No se pudo generar la explicación"
            }

    def _create_analysis_prompt(
        self,
        case_id: str,
        original_bdd: Dict[str, str],
        generated_ibdd: str,
        parse_error: str
    ) -> str:
        """Crea el prompt para el análisis de errores"""

        prompt = f"""Analiza este error de parsing IBDD y proporciona una explicación detallada.

## ID del Caso: {case_id}

## Escenario BDD Original:
**Given**: {original_bdd.get('given', 'N/A')}
**When**: {original_bdd.get('when', 'N/A')}
**Then**: {original_bdd.get('then', 'N/A')}

## IBDD Generado (que falló al parsear):
```
{generated_ibdd}
```

## Error del Parser:
```
{parse_error}
```

## Tu Análisis:

Por favor proporciona un análisis estructurado con:

1. **Tipo de Error**: Clasifica el error (ej: "Corchetes faltantes", "Sintaxis de gate inválida", "Guarda mal formada", etc.)

2. **Ubicación del Error**: Identifica exactamente dónde en el IBDD ocurre el error (qué línea, qué parte)

3. **Explicación**: Explica claramente qué salió mal y por qué el parser falló

4. **Sugerencia de Corrección**: Proporciona el fragmento IBDD corregido o el IBDD completo corregido

Responde en formato JSON."""

        return prompt

    def _call_openai_api(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Llama a la API de OpenAI para analizar el error"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # Definir el schema de respuesta
        response_schema = {
            "type": "object",
            "properties": {
                "error_type": {"type": "string"},
                "error_location": {"type": "string"},
                "explanation": {"type": "string"},
                "correction_suggestion": {"type": "string"},
                "hints": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["error_type", "error_location", "explanation", "correction_suggestion", "hints"],
            "additionalProperties": False
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "error_analysis",
                    "strict": True,
                    "schema": response_schema
                }
            },
            "temperature": 0.3
        }

        try:
            response = requests.post(self.api_endpoint, headers=headers, json=data)

            if response.status_code == 200:
                response_data = response.json()
                message = response_data["choices"][0]["message"]

                if message.get("refusal"):
                    print(f"API refused the request: {message['refusal']}", file=sys.stderr)
                    return None

                content = message["content"]
                parsed_content = json.loads(content)
                return parsed_content

            else:
                print(f"API error: {response.status_code} - {response.text}", file=sys.stderr)
                return None

        except Exception as e:
            print(f"Error calling OpenAI API: {e}", file=sys.stderr)
            return None

    def explain_multiple_errors(self, failed_cases: list) -> list:
        """
        Analiza múltiples errores de parsing en lote.

        Args:
            failed_cases: Lista de diccionarios con case_id, original_bdd, generated_ibdd, parse_error

        Returns:
            Lista de explicaciones para cada caso fallido
        """
        explanations = []

        for case in failed_cases:
            explanation = self.explain_error(
                case_id=case['case_id'],
                original_bdd=case['original_bdd'],
                generated_ibdd=case['generated_ibdd'],
                parse_error=case['parse_error']
            )
            explanations.append(explanation)

        return explanations

    @staticmethod
    def format_error_analysis_for_retry(error_explanation: Dict[str, Any]) -> str:
        """
        Formatea una explicación de error para ser insertada en el prompt de reintentos.

        Args:
            error_explanation: Diccionario con la explicación del error (del método explain_error)

        Returns:
            Texto formateado listo para insertar en el placeholder {error_analysis}
        """
        original_bdd = error_explanation.get('original_bdd', {})

        formatted_text = f"""**Case ID:** {error_explanation.get('case_id', 'Unknown')}
                            
                            **Original BDD Scenario:**
                            - **Given:** {original_bdd.get('given', 'N/A')}
                            - **When:** {original_bdd.get('when', 'N/A')}
                            - **Then:** {original_bdd.get('then', 'N/A')}
                            
                            **Previous Translation (that failed):**
                            ```
                            {error_explanation.get('previous_translation', 'N/A')}
                            ```
                            
                            **Parser Error:**
                            ```
                            {error_explanation.get('parse_error', 'N/A')}
                            ```
                            
                            **Error Analysis:**
                            - **Error Type:** {error_explanation.get('error_type', 'Unknown')}
                            - **Location:** {error_explanation.get('error_location', 'Unknown')}
                            - **Explanation:** {error_explanation.get('explanation', 'No explanation available')}
                            - **Correction Suggestion:** {error_explanation.get('correction_suggestion', 'No suggestion available')}
                            
                            **Hints:**
                            {chr(10).join(f'- {hint}' for hint in error_explanation.get('hints', []))}
                            """
        return formatted_text.strip()


def main():
    """Prueba el explainer de forma independiente"""
    import argparse

    parser = argparse.ArgumentParser(description='Prueba el Explicador de Errores IBDD')
    parser.add_argument('--case-id', default='test_1', help='ID del caso')
    parser.add_argument('--given', required=True, help='Cláusula Given original')
    parser.add_argument('--when', required=True, help='Cláusula When original')
    parser.add_argument('--then', required=True, help='Cláusula Then original')
    parser.add_argument('--ibdd', required=True, help='IBDD generado que falló')
    parser.add_argument('--error', required=True, help='Mensaje de error del parser')

    args = parser.parse_args()

    # Inicializar explainer
    explainer = IBDDErrorExplainer()

    # Preparar BDD original
    original_bdd = {
        'given': args.given,
        'when': args.when,
        'then': args.then
    }

    # Explicar el error
    result = explainer.explain_error(
        case_id=args.case_id,
        original_bdd=original_bdd,
        generated_ibdd=args.ibdd,
        parse_error=args.error
    )

    # Imprimir resultados
    print("\n" + "=" * 80)
    print("Resultado del Análisis de Error")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
