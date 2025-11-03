"""
CLI principal para el módulo IBDD
Maneja argumentos de línea de comandos y orquestación

Uso:
    python3 cli.py data.json
    python3 cli.py data.json output_results.json
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.ibdd.validator import validate_ibdd_cases

def main():
    """Función principal del CLI"""

    if len(sys.argv) < 2:
        print("Uso: python cli.py <archivo_json> [archivo_salida]")
        print("\nEjemplos:")
        print("  python cli.py data.json")
        print("  python cli.py data.json output_results.json")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        validate_ibdd_cases(json_file, output_file)
        print("\n✅ Proceso completado exitosamente")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()