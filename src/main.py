#!/usr/bin/env python3
"""
Script principal de orquestación del flujo BDD -> IBDD.

Coordina el pipeline completo:
1. Traducción de escenarios BDD a IBDD con LLM
2. Análisis y validación sintáctica de IBDD
3. Ciclo de corrección iterativa (explicación -> reintento -> revalidación)
4. Resumen final con métricas
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
    """Orquesta el pipeline completo de traducción y validación BDD -> IBDD."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        workers: int = 1,
    ):
        """
        Inicializa el pipeline.

        Args:
            api_key: Clave de API (opcional, usa OPENAI_API_KEY por defecto)
            provider: Proveedor de LLM (openai, ollama)
            model: Identificador del modelo
            base_url: URL base opcional del proveedor
            workers: Cantidad de workers paralelos para llamadas al LLM
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
        Detecta automáticamente el prompt de reintento según el idioma del prompt base.

        Si el nombre del archivo contiene `_ES`, usa el prompt de reintento en
        español; en caso contrario usa el de inglés.
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

        # Respaldo en inglés si no existe el prompt específico
        fallback = os.path.join(prompt_dir, 'PROMPT_EN_RETRY.md')
        if os.path.exists(fallback):
            return fallback

        raise FileNotFoundError(
            f"No se encontró el prompt de reintento. Se intentó con: {retry_path}, {fallback}"
        )

    @staticmethod
    def _get_validation_summary(
            validation_output_path: str
    ) -> Dict[str, Any]:
        """Carga los resultados de validación y devuelve un resumen."""
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
        Ejecuta el pipeline completo con corrección iterativa.

        Pipeline:
            1. Traducción BDD -> IBDD con LLM
            2. Validación sintáctica (parser de Lark)
            3. Ciclo de corrección iterativa (hasta `max_rounds`)
            4. Resumen final

        Args:
            dataset_path: Ruta al dataset JSON de entrada
            prompt_path: Ruta al archivo de prompt (.md)
            translation_output_path: Ruta de salida de traducciones IBDD
            validation_output_path: Ruta de salida de validación sintáctica
            explanations_output_path: Ruta de salida de explicaciones de error
            max_rounds: Máximo de rondas de corrección (0 = sin reintentos)

        Returns:
            Diccionario con resultados del pipeline y métricas por ronda
        """
        pipeline_start = time.time()
        retry_prompt_path = self._detect_retry_prompt_path(prompt_path)

        print("=" * 80)
        print("Pipeline de Traducción BDD -> IBDD")
        print(f"Máximo de rondas de corrección: {max_rounds}")
        print("=" * 80)

        # Paso 1: traducción BDD -> IBDD
        print("\n[Paso 1/4] Traduciendo escenarios BDD a IBDD...")
        print("-" * 80)
        try:
            self.translation_service.translate(
                json_file_path=dataset_path,
                prompt_file_path=prompt_path,
                output_file_path=translation_output_path,
                workers=self.translation_service.workers,
            )
            print(f"✓ Traducción completada: {translation_output_path}")
        except Exception as e:
            print(f"✗ Falló la traducción: {e}", file=sys.stderr)
            sys.exit(1)

        # Paso 2: validación sintáctica
        print("\n[Paso 2/4] Analizando y validando sintaxis IBDD...")
        print("-" * 80)
        try:
            validate_ibdd_cases(
                json_file_path=translation_output_path,
                output_destination=validation_output_path
            )
            print(f"✓ Validación sintáctica completada: {validation_output_path}")
        except Exception as e:
            print(f"✗ Falló la validación: {e}", file=sys.stderr)
            sys.exit(1)

        # Registrar resultados iniciales de validación
        initial_summary = self._get_validation_summary(validation_output_path)
        print(f"\n   Initial result: {initial_summary['passed']}/{initial_summary['total']} "
              f"passed ({initial_summary['passed']/initial_summary['total']*100:.1f}%)")

        # Paso 3: ciclo de corrección iterativa
        print("\n[Paso 3/4] Ciclo de corrección iterativa...")
        print("-" * 80)

        round_metrics: List[Dict[str, Any]] = []
        all_explanations: List[Dict[str, Any]] = []

        for round_num in range(1, max_rounds + 1):
            round_start = time.time()

            # Recolectar casos fallidos
            failed_cases = self._collect_failed_cases(
                translation_output_path,
                validation_output_path
            )

            if not failed_cases:
                print(f"\n✓ Todos los casos pasaron; no se requiere corrección"
                      + (f" (converged at round {round_num - 1})" if round_num > 1 else ""))
                break

            print(f"\n── Round {round_num}/{max_rounds}: "
                  f"{len(failed_cases)} case(s) still failing ──")

            # Explicar errores
            try:
                explanations = self.error_explainer.explain_multiple_errors(failed_cases)
                all_explanations.extend(explanations)
            except Exception as e:
                print(f"⚠ Falló la explicación de errores: {e}", file=sys.stderr)
                round_metrics.append({
                    'round': round_num,
                    'error': str(e),
                })
                break

            # Reintentar traducciones con retroalimentación del error
            corrected_ids = []
            try:
                corrected = self.translation_service.retry_failed_translations(
                    error_explanations=explanations,
                    retry_prompt_path=retry_prompt_path,
                    workers=self.translation_service.workers,
                )

                if corrected:
                    corrected_ids = [c['id'] for c in corrected]

                    # Fusionar correcciones sin sobrescribir casos correctos
                    updated = self._merge_translations(
                        translation_output_path, corrected
                    )
                    with open(translation_output_path, 'w', encoding='utf-8') as f:
                        json.dump(updated, indent=2, ensure_ascii=False, fp=f)

                    # Revalidar después de aplicar correcciones
                    validate_ibdd_cases(
                        json_file_path=translation_output_path,
                        output_destination=validation_output_path
                    )
            except Exception as e:
                print(f"⚠ Falló el reintento: {e}", file=sys.stderr)

            # Consolidar resumen de la ronda
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

            print(f"   Resultado ronda {round_num}: {post_summary['passed']}/{post_summary['total']} "
                  f"passed ({post_summary['passed']/post_summary['total']*100:.1f}%) "
                  f"[{round_time:.1f}s]")

            if post_summary['failed'] == 0:
                print(f"\n✓ Todos los casos pasaron; convergió en la ronda {round_num}")
                break
        else:
            if max_rounds > 0:
                print(f"\n⚠ Se alcanzó el máximo de rondas de corrección ({max_rounds})")

        # Guardar explicaciones de error acumuladas
        if all_explanations:
            with open(explanations_output_path, 'w', encoding='utf-8') as f:
                json.dump(all_explanations, indent=2, ensure_ascii=False, fp=f)

        # Paso 4: resumen final
        pipeline_time = time.time() - pipeline_start
        final_summary = self._get_validation_summary(validation_output_path)

        print("\n[Paso 4/4] Resumen final")
        print("=" * 80)

        print(f"Salida de traducción: {translation_output_path}")
        print(f"Validación sintáctica:{' '}{validation_output_path}")
        if all_explanations:
            print(f"Explicaciones de error: {explanations_output_path}")

        print(f"\nValidación sintáctica: {final_summary['passed']}/{final_summary['total']} "
              f"passed ({final_summary['passed']/final_summary['total']*100:.1f}%)")
        if final_summary['failed_case_ids']:
            print(f"Casos aún fallando: {final_summary['failed_case_ids']}")

        print(f"Rondas de corrección usadas: {len(round_metrics)}/{max_rounds}")
        print(f"Tiempo total del pipeline: {pipeline_time:.1f}s")
        print("=" * 80)
        print()

        # Construir y guardar métricas del pipeline
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
        print(f"Métricas del pipeline guardadas: {metrics_path}")

        return pipeline_metrics

    @staticmethod
    def _merge_translations(
            original_translations_path: str,
        corrected_translations: list
    ) -> list:
        """
        Fusiona traducciones corregidas con las traducciones originales exitosas.

        Args:
            original_translations_path: Ruta al archivo de traducciones original
            corrected_translations: Lista de traducciones corregidas

        Returns:
            Lista actualizada con las correcciones aplicadas
        """
        # Cargar traducciones originales
        with open(original_translations_path, 'r', encoding='utf-8') as f:
            original_translations = json.load(f)

        # Indexar correcciones por `case_id` para reemplazo directo
        corrected_map = {case['id']: case for case in corrected_translations}

        # Reemplazar solo los casos corregidos y preservar el resto
        updated_translations = []
        for original in original_translations:
            case_id = original['id']
            if case_id in corrected_map:
                # Usar versión corregida
                updated_translations.append(corrected_map[case_id])
                print(f"  → Caso {case_id}: usando traducción corregida")
            else:
                # Mantener versión original
                updated_translations.append(original)

        return updated_translations

    @staticmethod
    def _collect_failed_cases(
            translation_output_path: str,
        validation_output_path: str
    ) -> list:
        """
        Recolecta los casos que fallaron el parsing para enviarlos al explicador.

        Args:
            translation_output_path: Ruta al archivo de traducciones
            validation_output_path: Ruta al archivo de validación

        Returns:
            Lista de casos fallidos con la información necesaria para explicar el error
        """
        # Cargar traducciones (BDD original + IBDD generado)
        with open(translation_output_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)

        # Cargar resultados de validación (éxito/fallo + error)
        with open(validation_output_path, 'r', encoding='utf-8') as f:
            validations = json.load(f)

        # Crear un mapa por ID para cruzar traducciones y validaciones
        translation_map = {case['id']: case for case in translations}

        # Recolectar casos fallidos con el contexto necesario
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
                        'parse_error': validation.get('error', 'Error desconocido')
                    })

        return failed_cases


def main():
    """Punto de entrada principal del pipeline."""
    parser = argparse.ArgumentParser(
        description='Pipeline completo de traducción y validación BDD -> IBDD',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Ejecutar con rutas por defecto
  python src/main.py data/Dataset.json docs/PROMPT_EN.md

  # Ejecutar con prompt en español (retry detectado automáticamente)
  python src/main.py data/Dataset.json docs/PROMPT_ES.md

  # Ejecutar con más rondas de corrección
  python src/main.py data/Dataset.json docs/PROMPT_EN.md --max-rounds 5

  # Ejecutar con un modelo específico vía Ollama
  python src/main.py data/Dataset.json docs/PROMPT_EN.md \\
    --provider ollama -m llama3.3:70b
        """
    )

    parser.add_argument(
        'dataset',
        help='Ruta al archivo JSON del dataset de entrada'
    )
    parser.add_argument(
        'prompt',
        help='Ruta al archivo de prompt (.md)'
    )
    parser.add_argument(
        '-t', '--translation-output',
        default='data/output.json',
        help='Ruta de salida de traducciones (default: data/output.json)'
    )
    parser.add_argument(
        '-v', '--validation-output',
        default='data/parsed_ibdd_results.json',
        help='Ruta de salida de validación (default: data/parsed_ibdd_results.json)'
    )
    parser.add_argument(
        '-k', '--api-key',
        help='Clave API (opcional, puede usar OPENAI_API_KEY)'
    )
    parser.add_argument(
        '-m', '--model',
        help='Modelo a usar (ej.: gpt-4o, llama3.3:70b)'
    )
    parser.add_argument(
        '--provider',
        default=None,
        help='Proveedor LLM: openai u ollama (default: openai)'
    )
    parser.add_argument(
        '--base-url',
        default=None,
        help='URL base opcional del proveedor LLM'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=3,
        help='Máximo de rondas de corrección (default: 3, 0 = sin reintentos)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Workers paralelos para llamadas al LLM (default: 1)'
    )
    args = parser.parse_args()

    # Validar que existan los archivos de entrada
    if not os.path.exists(args.dataset):
        print(f"Error: no se encontró el dataset: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.prompt):
        print(f"Error: no se encontró el prompt: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    # Crear directorios de salida si no existen
    os.makedirs(os.path.dirname(args.translation_output) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(args.validation_output) or '.', exist_ok=True)

    # Inicializar el pipeline
    pipeline = BDDToIBDDPipeline(
        api_key=args.api_key,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        workers=args.workers,
    )

    # Mostrar configuración efectiva
    print(f"Proveedor: {pipeline.translation_service.provider}")
    print(f"Modelo:    {pipeline.translation_service.model}")
    print(f"Workers:  {pipeline.translation_service.workers}")
    print()

    # Ejecutar el pipeline
    pipeline.run(
        dataset_path=args.dataset,
        prompt_path=args.prompt,
        translation_output_path=args.translation_output,
        validation_output_path=args.validation_output,
        max_rounds=args.max_rounds,
    )


if __name__ == '__main__':
    main()
