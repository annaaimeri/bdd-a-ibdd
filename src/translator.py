#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        workers: Optional[int] = None,
    ):
        """
        Inicializa el servicio de traducción.

        Args:
            api_key: Clave API (opcional, usa OPENAI_API_KEY por defecto)
            provider: Proveedor LLM (openai, ollama)
            model: Identificador del modelo
            base_url: URL base opcional del proveedor
            workers: Cantidad de workers paralelos
        """
        load_dotenv()

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o")
        self.provider = provider or os.environ.get("LLM_PROVIDER", "openai")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        env_workers = os.environ.get("LLM_WORKERS")
        if workers is not None:
            self.workers = max(1, int(workers))
        elif env_workers:
            self.workers = max(1, int(env_workers))
        else:
            self.workers = 1
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
        Lee y parsea un archivo JSON.

        Args:
            json_file_path: Ruta al archivo JSON

        Returns:
            Datos JSON parseados
        """
        try:
            print(f"Leyendo archivo JSON: {json_file_path}")
            with open(json_file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            if isinstance(data, list):
                print(f"JSON cargado correctamente (arreglo con {len(data)} elementos)")
            else:
                print(f"JSON cargado correctamente (objeto con {len(data)} claves)")
            return data
        except Exception as e:
            print(f"Error al leer el archivo JSON: {e}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def read_prompt_file(prompt_file_path: str) -> str:
        """
        Lee el prompt desde archivo.

        Args:
            prompt_file_path: Ruta al archivo de prompt

        Returns:
            Contenido del prompt
        """
        try:
            print(f"Leyendo prompt: {prompt_file_path}")
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            print(f"Error al leer el prompt: {e}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def prepare_prompt(json_data: Union[Dict[str, Any], List[Any]], prompt_template: str) -> str:
        """
        Prepara el prompt combinando la plantilla con los datos JSON.

        Args:
            json_data: Datos JSON parseados
            prompt_template: Plantilla del prompt

        Returns:
            Prompt final a enviar al proveedor
        """
        print("Preparando prompt con datos JSON...")
        json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
        final_prompt = f"{prompt_template}\n\nJSON Data:\n{json_str}"
        return final_prompt

    @staticmethod
    def create_response_schema(json_data: Union[Dict[str, Any], List[Any]]) -> Dict[str, Any]:
        """
        Crea un esquema JSON a partir de la estructura del JSON de entrada.

        Args:
            json_data: JSON de entrada

        Returns:
            JSON Schema para salida estructurada (siempre envuelto en objeto)
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
                # Asegura que el campo de salida exista en el esquema
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
        Invoca al LLM con el prompt preparado y salida estructurada.

        Args:
            prompt: Prompt a enviar
            json_data: JSON original para inferencia del esquema

        Returns:
            Respuesta del proveedor como dict/list o `None` en caso de fallo
        """
        schema = self.create_response_schema(json_data)
        is_array_input = isinstance(json_data, list)

        print(f"Llamando al proveedor LLM: {self.provider} | modelo: {self.model}")
        print("Usando Structured Outputs con JSON Schema cuando esté disponible")

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
        Traduce un caso BDD individual a IBDD.

        Args:
            case: Caso individual con `id`, `given`, `when`, `then`
            prompt_template: Plantilla de prompt a utilizar

        Returns:
            Caso traducido con métricas, o `None` si falla
        """
        start_time = time.time()

        # Preparar prompt para este caso individual
        final_prompt = self.prepare_prompt([case], prompt_template)

        # Invocar al proveedor
        response = self.call_llm_api(final_prompt, [case])

        elapsed_time = time.time() - start_time

        if response and isinstance(response, list) and len(response) > 0:
            translated_case = response[0]
            # Registrar métricas del caso para análisis posterior
            translated_case['_metrics'] = {
                'translation_time': round(elapsed_time, 2),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            return translated_case

        return None

    @staticmethod
    def save_response(response: Union[Dict[str, Any], List[Any]], output_file_path: str) -> None:
        """
        Guarda la respuesta en archivo.

        Args:
            response: Respuesta del proveedor
            output_file_path: Ruta de salida
        """
        try:
            print(f"Guardando traducción en: {output_file_path}")
            with open(output_file_path, 'w', encoding='utf-8') as file:
                json.dump(response, file, indent=2, ensure_ascii=False)
            print("Traducción guardada correctamente")
        except Exception as e:
            print(f"Error al guardar la respuesta: {e}", file=sys.stderr)

    def translate(
        self,
        json_file_path: str,
        prompt_file_path: str,
        output_file_path: str,
        workers: Optional[int] = None,
    ) -> None:
        """
        Flujo completo de traducción desde JSON hacia salida mediante LLM.
        Procesa casos de forma individual con guardado incremental y seguimiento.

        Args:
            json_file_path: Ruta al archivo JSON
            prompt_file_path: Ruta al prompt
            output_file_path: Ruta de salida de traducciones
            workers: Número de workers (usa `self.workers` por defecto)
        """
        print("=" * 80)
        print("Iniciando traducción individual de casos...")
        print("=" * 80)
        translation_start = time.time()

        # Cargar insumos
        json_data = self.read_json_file(json_file_path)
        prompt_template = self.read_prompt_file(prompt_file_path)

        # El dataset debe ser un arreglo de casos
        if not isinstance(json_data, list):
            print("Error: el dataset debe ser un arreglo JSON de casos", file=sys.stderr)
            sys.exit(1)

        total_cases = len(json_data)
        workers = max(1, int(workers if workers is not None else self.workers))
        print(f"\nProcesando {total_cases} casos de forma individual...")
        print(f"Workers paralelos: {workers}")
        print(f"La salida se guardará incrementalmente en: {output_file_path}")
        print("-" * 80)

        # Estructuras para resultados y métricas
        translated_cases = []
        failed_cases = []
        total_time = 0

        case_order = [case.get('id', idx) for idx, case in enumerate(json_data)]
        translated_map = {}

        def save_incremental() -> None:
            ordered_cases = [translated_map[cid] for cid in case_order if cid in translated_map]
            self.save_response(ordered_cases, output_file_path)

        def build_failed_case(case: Dict[str, Any], reason: str) -> Dict[str, Any]:
            failed_case = dict(case)
            failed_case['ibdd_representation'] = ''
            failed_case['_metrics'] = {
                'translation_time': 0.0,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'translation_failed': True,
                'failure_reason': reason,
            }
            return failed_case

        if workers == 1:
            # Modo secuencial
            for case in tqdm(json_data, desc="Translating", unit="case"):
                case_id = case.get('id', 'unknown')

                try:
                    translated_case = self.translate_single_case(case, prompt_template)

                    if translated_case:
                        translated_map[case_id] = translated_case
                        translated_cases.append(translated_case)
                        if '_metrics' in translated_case:
                            total_time += translated_case['_metrics'].get('translation_time', 0)
                        save_incremental()
                    else:
                        failed_case = build_failed_case(case, 'La API devolvió None')
                        translated_map[case_id] = failed_case
                        failed_cases.append({
                            'id': case_id,
                            'reason': 'La API devolvió None'
                        })
                        save_incremental()
                        print(f"\n⚠ Advertencia: el caso {case_id} no pudo traducirse", file=sys.stderr)

                except Exception as e:
                    failed_case = build_failed_case(case, str(e))
                    translated_map[case_id] = failed_case
                    failed_cases.append({
                        'id': case_id,
                        'reason': str(e)
                    })
                    save_incremental()
                    print(f"\n✗ Error al traducir el caso {case_id}: {e}", file=sys.stderr)
                    # Continuar con el siguiente caso evita abortar todo el lote
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                case_by_id = {case.get('id', 'unknown'): case for case in json_data}
                future_to_case_id = {
                    executor.submit(self.translate_single_case, case, prompt_template): case.get('id', 'unknown')
                    for case in json_data
                }
                for future in tqdm(as_completed(future_to_case_id), total=total_cases, desc="Translating", unit="case"):
                    case_id = future_to_case_id[future]
                    try:
                        translated_case = future.result()
                        if translated_case:
                            translated_map[case_id] = translated_case
                            translated_cases.append(translated_case)
                            if '_metrics' in translated_case:
                                total_time += translated_case['_metrics'].get('translation_time', 0)
                            save_incremental()
                        else:
                            source_case = case_by_id.get(case_id, {'id': case_id})
                            failed_case = build_failed_case(source_case, 'La API devolvió None')
                            translated_map[case_id] = failed_case
                            failed_cases.append({
                                'id': case_id,
                                'reason': 'La API devolvió None'
                            })
                            save_incremental()
                            print(f"\n⚠ Advertencia: el caso {case_id} no pudo traducirse", file=sys.stderr)
                    except Exception as e:
                        source_case = case_by_id.get(case_id, {'id': case_id})
                        failed_case = build_failed_case(source_case, str(e))
                        translated_map[case_id] = failed_case
                        failed_cases.append({
                            'id': case_id,
                            'reason': str(e)
                        })
                        save_incremental()
                        print(f"\n✗ Error al traducir el caso {case_id}: {e}", file=sys.stderr)

        # Guardado final en el orden original del dataset
        save_incremental()

        # Resumen final de la etapa
        print("\n" + "=" * 80)
        print("Resumen de traducción")
        print("=" * 80)
        print(f"Casos totales:          {total_cases}")
        print(f"Traducidos correctamente: {len(translated_cases)}")
        print(f"Fallidos:               {len(failed_cases)}")
        print(f"Tasa de éxito:          {len(translated_cases)/total_cases*100:.1f}%")
        print(f"Tiempo total (wall):    {time.time() - translation_start:.1f}s")
        print(f"Tiempo acumulado del modelo: {total_time:.1f}s")
        print(f"Promedio por caso:      {total_time/len(translated_cases):.1f}s" if translated_cases else "N/A")
        print(f"Salida guardada en:     {output_file_path}")

        if failed_cases:
            print("\nCasos fallidos:")
            for failed in failed_cases:
                print(f"  - Caso {failed['id']}: {failed['reason']}")

        print("=" * 80)

        if not translated_cases:
            print("\n✗ No se pudo traducir ningún caso", file=sys.stderr)
            sys.exit(1)

    def retry_failed_translations(
        self,
        error_explanations: List[Dict[str, Any]],
        retry_prompt_path: str = "docs/PROMPT_EN_RETRY.md",
        workers: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Reintenta la traducción de casos que fallaron el parsing usando análisis de error.
        Procesa cada caso de forma individual.

        Args:
            error_explanations: Lista de explicaciones de error
            retry_prompt_path: Ruta al prompt de reintento
            workers: Número de workers (usa `self.workers` por defecto)

        Returns:
            Lista de traducciones corregidas (mismo formato que la salida original)
        """
        from src.explainer import IBDDErrorExplainer

        print(f"\n[Retry] Intentando corregir {len(error_explanations)} traducción(es) fallida(s)...")
        print("-" * 80)

        # Leer plantilla del prompt de reintento
        retry_prompt_template = self.read_prompt_file(retry_prompt_path)

        # Estructuras de resultados
        corrected_cases = []
        retry_failed_cases = []

        workers = max(1, int(workers if workers is not None else self.workers))

        def process_retry_case(error_exp: Dict[str, Any]):
            case_id = error_exp.get('case_id', 'unknown')
            if not error_exp.get('success', False):
                return case_id, None, 'falló la explicación del error'

            original_bdd = error_exp.get('original_bdd', {})
            case_data = {
                'id': case_id,
                'given': original_bdd.get('given', ''),
                'when': original_bdd.get('when', ''),
                'then': original_bdd.get('then', '')
            }

            error_analysis_text = IBDDErrorExplainer.format_error_analysis_for_retry(error_exp)
            case_retry_prompt = retry_prompt_template.replace('{error_analysis}', error_analysis_text)
            corrected_case = self.translate_single_case(case_data, case_retry_prompt)
            if corrected_case:
                return case_id, corrected_case, None
            return case_id, None, 'La API devolvió None'

        if workers == 1:
            # Modo secuencial
            for error_exp in tqdm(error_explanations, desc="Retrying", unit="case"):
                case_id = error_exp.get('case_id', 'unknown')
                try:
                    _, corrected_case, reason = process_retry_case(error_exp)
                    if corrected_case:
                        corrected_cases.append(corrected_case)
                    else:
                        print(f"\n⚠ Advertencia: falló el reintento para el caso {case_id}: {reason}")
                        retry_failed_cases.append(case_id)
                except Exception as e:
                    print(f"\n✗ Error al reintentar el caso {case_id}: {e}", file=sys.stderr)
                    retry_failed_cases.append(case_id)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_case_id = {
                    executor.submit(process_retry_case, error_exp): error_exp.get('case_id', 'unknown')
                    for error_exp in error_explanations
                }
                for future in tqdm(as_completed(future_to_case_id), total=len(error_explanations), desc="Retrying", unit="case"):
                    case_id = future_to_case_id[future]
                    try:
                        _, corrected_case, reason = future.result()
                        if corrected_case:
                            corrected_cases.append(corrected_case)
                        else:
                            print(f"\n⚠ Advertencia: falló el reintento para el caso {case_id}: {reason}")
                            retry_failed_cases.append(case_id)
                    except Exception as e:
                        print(f"\n✗ Error al reintentar el caso {case_id}: {e}", file=sys.stderr)
                        retry_failed_cases.append(case_id)

        # Resumen de reintentos
        print("\n" + "-" * 80)
        print("Resumen de reintentos:")
        print(f"  Intentados:   {len(error_explanations)}")
        print(f"  Corregidos:   {len(corrected_cases)}")
        print(f"  Aún fallidos: {len(retry_failed_cases)}")
        if retry_failed_cases:
            print(f"  IDs fallidos: {retry_failed_cases}")
        print("-" * 80)

        return corrected_cases


def main():
    parser = argparse.ArgumentParser(description='Traduce contenido JSON usando LLM con Structured Outputs')
    parser.add_argument('json_file', help='Ruta al archivo JSON')
    parser.add_argument('prompt_file', help='Ruta al archivo de prompt (.md)')
    parser.add_argument('-o', '--output', help='Ruta del archivo de salida (default: translation_output.json)')
    parser.add_argument('-k', '--api-key', help='Clave API (opcional, puede usar OPENAI_API_KEY)')
    parser.add_argument('-m', '--model', help='Modelo a usar (ej.: gpt-4o, llama3.3:70b)')
    parser.add_argument('-r', '--max-retries', type=int, help='Máximo de reintentos de API (default: 5)')
    parser.add_argument('-w', '--workers', type=int, default=1, help='Workers paralelos para API (default: 1)')
    parser.add_argument('--provider', default=None, help='Proveedor LLM: openai u ollama (default: openai)')
    parser.add_argument('--base-url', default=None, help='URL base opcional del proveedor LLM')

    args = parser.parse_args()

    output_file = args.output or 'translation_output.json'

    service = TranslationService(
        args.api_key,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        workers=args.workers,
    )
    if args.max_retries:
        service.max_retries = args.max_retries
        service.llm_client.max_retries = args.max_retries

    service.translate(args.json_file, args.prompt_file, output_file, workers=args.workers)


if __name__ == '__main__':
    main()
