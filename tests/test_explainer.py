#!/usr/bin/env python3
"""
Script para probar el explainer con múltiples casos de error
"""
import json
import sys
from pathlib import Path

# Agregar directorio raíz al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.explainer import IBDDErrorExplainer
from src.parser import IBDDParser  # Usar el parser directamente, sin fallback


def test_explainer_with_errors(file: str):
    """Prueba el explainer con casos que contienen errores"""

    # Cargar casos de prueba
    print(f"Cargando casos de prueba desde: {file}")
    with open(file, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)

    print(f"Se cargaron {len(test_cases)} casos de prueba\n")
    print("=" * 80)

    # Inicializar explainer y parser
    explainer = IBDDErrorExplainer()
    parser = IBDDParser(debug=False)  # Parser sin fallback

    results = []

    for i, case in enumerate(test_cases, 1):
        case_id = case.get('id', f'case_{i}')
        title = case.get('title', 'Sin título')
        ibdd = case.get('ibdd_representation', '')

        print(f"\n[{i}/{len(test_cases)}] Caso: {case_id} - {title}")
        print("-" * 80)

        # Intentar parsear (sin fallback para detectar errores reales)
        try:
            parser.parse_text(ibdd)
            print(f"✓ Parseo exitoso (no hay error para analizar)")
            continue
        except Exception as e:
            error_msg = str(e)
            print(f"✗ Error de parsing detectado:")
            print(f"  {error_msg[:150]}...")

            # Analizar el error con el explainer
            print(f"\n🔍 Analizando error con el Explainer...")

            original_bdd = {
                'given': case.get('given', ''),
                'when': case.get('when', ''),
                'then': case.get('then', '')
            }

            explanation = explainer.explain_error(
                case_id=case_id,
                original_bdd=original_bdd,
                generated_ibdd=ibdd,
                parse_error=error_msg
            )

            if explanation.get('success'):
                print(f"\n📋 Tipo de Error: {explanation['error_type']}")
                print(f"📍 Ubicación: {explanation['error_location']}")
                print(f"\n💡 Explicación:")
                print(f"  {explanation['explanation'][:200]}...")
                print(f"\n✅ Sugerencia de Corrección:")
                suggestion = explanation['correction_suggestion']
                for line in suggestion.split('\n')[:3]:
                    print(f"  {line}")
                if len(suggestion.split('\n')) > 3:
                    print(f"  ...")
                print(f"\n🎯 Pistas:")
                for hint in explanation['hints'][:2]:
                    print(f"  • {hint}")

                results.append({
                    'case_id': case_id,
                    'title': title,
                    'error_detected': True,
                    'explanation': explanation
                })
            else:
                print(f"⚠️  No se pudo generar explicación")
                results.append({
                    'case_id': case_id,
                    'title': title,
                    'error_detected': True,
                    'explanation_failed': True
                })

    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN")
    print("=" * 80)
    print(f"Total de casos: {len(test_cases)}")
    print(f"Casos con errores analizados: {len(results)}")

    # Guardar resultados
    output_file = 'test_explainer_results.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados guardados en: {output_file}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        json_file = 'test_errors.json'

    test_explainer_with_errors(json_file)
