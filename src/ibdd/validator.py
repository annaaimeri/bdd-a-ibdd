"""
Validador de casos IBDD
Contiene lógica para validar y procesar casos IBDD desde archivos JSON
"""
import json
from typing import Optional, List, Dict, Any
import pandas as pd
from .parser import IBDDParser
from .exceptions import IBDDValidationException


class IBDDValidator:
    """Validador para casos IBDD"""

    def __init__(self, debug=False):
        """
        Inicializa el validador

        Args:
            debug: Si True, habilita modo debug
        """
        self.parser = IBDDParser(debug=debug)
        self.results: List[Dict[str, Any]] = []

    def validate_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida un caso IBDD individual

        Args:
            case: Diccionario con información del caso

        Returns:
            Dict con resultado de validación
        """
        case_id = case.get('id', 'unknown')
        domain = case.get('domain', 'unknown')
        title = case.get('title', f'Case {case_id}')
        ibdd_text = case.get('ibdd_representation', '')

        # Si no hay representación IBDD
        if not ibdd_text:
            return {
                'id': case_id,
                'domain': domain,
                'title': title,
                'valid': False,
                'error': 'Sin representación IBDD'
            }

        ibdd_text = ibdd_text.replace('\\n', '\n')

        try:
            # Intentar parsear
            scenario = self.parser.parse_text(ibdd_text)

            return {
                'id': case_id,
                'domain': domain,
                'title': title,
                'valid': True,
                'error': None,
                'parsed_result': str(scenario)
            }

        except Exception as e:
            return {
                'id': case_id,
                'domain': domain,
                'title': title,
                'valid': False,
                'error': str(e),
                'parsed_result': None
            }

    def validate_cases(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Valida múltiples casos IBDD

        Args:
            cases: Lista de casos a validar

        Returns:
            Lista de resultados de validación
        """
        self.results = []

        for case in cases:
            result = self.validate_case(case)
            self.results.append(result)

        return self.results

    def get_summary(self) -> Dict[str, Any]:
        """
        Obtiene un resumen de los resultados

        Returns:
            Diccionario con estadísticas
        """
        if not self.results:
            return {'total': 0, 'valid': 0, 'invalid': 0, 'percentage': 0.0}

        valid_count = sum(1 for r in self.results if r['valid'])
        total_count = len(self.results)

        return {
            'total': total_count,
            'valid': valid_count,
            'invalid': total_count - valid_count,
            'percentage': (valid_count / total_count * 100) if total_count > 0 else 0.0
        }

    def print_summary(self):
        """Imprime un resumen de los resultados"""
        summary = self.get_summary()
        print(f"\nResumen: {summary['valid']} de {summary['total']} casos válidos ({summary['percentage']:.1f}%)")

    def save_results_json(self, output_file: str):
        """
        Guarda los resultados en JSON

        Args:
            output_file: Ruta del archivo de salida
        """
        if not self.results:
            raise IBDDValidationException("No hay resultados para guardar")

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

    def save_results_csv(self, output_file: str):
        """
        Guarda los resultados en CSV

        Args:
            output_file: Ruta del archivo de salida
        """
        if not self.results:
            raise IBDDValidationException("No hay resultados para guardar")

        df = pd.DataFrame(self.results)
        df.to_csv(output_file, index=False)


def validate_ibdd_cases(json_file_path: str, output_file: Optional[str] = None) -> None:
    """
    Valida casos IBDD de un archivo JSON y genera un informe

    Args:
        json_file_path: Ruta al archivo JSON con los casos IBDD
        output_file: Ruta al archivo de salida (opcional)
    """
    try:
        # Cargar los datos JSON
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Crear validador
        validator = IBDDValidator(debug=False)

        print(f"Validando {len(data)} casos IBDD...")

        # Validar cada caso
        validator.validate_cases(data)

        # Imprimir resultados por consola
        for result in validator.results:
            status = "Válido ✓" if result['valid'] else f"Inválido ✗"
            print(f"Caso {result['id']}: {result['title']} - {status}")
            if not result['valid']:
                print(f"  Error: {result['error']}")

        # Imprimir resumen
        validator.print_summary()

        # Guardar resultados si se especifica archivo de salida
        if output_file:
            validator.save_results_json(output_file)

            # También generar un CSV
            csv_file = output_file.replace('.json', '.csv')
            validator.save_results_csv(csv_file)

            print(f"Resultados guardados en {output_file}")
            print(f"Resultados en CSV guardados en {csv_file}")

    except Exception as e:
        print(f"Error al procesar el archivo: {e}")
        import traceback
        traceback.print_exc()