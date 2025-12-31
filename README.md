# BDD to IBDD Translation using NLP

Sistema de traducción automática de escenarios BDD (Behavior-Driven Development) a representación IBDD (Intermediate Behavior-Driven Development) utilizando modelos de lenguaje.

## Descripción

Este proyecto implementa un pipeline completo para la traducción automática de escenarios de prueba escritos en lenguaje natural (formato BDD) a una representación formal intermedia (IBDD). El sistema incluye:

- **Traductor**: Convierte escenarios BDD a IBDD usando la API de OpenAI
- **Parser**: Valida y parsea la sintaxis IBDD generada
- **Explicador**: Analiza errores de parsing y proporciona explicaciones detalladas para corrección

## Requisitos

- Python 3.8 o superior
- API key de OpenAI
- Dependencias listadas en `requirements.txt`

## Instalación

1. Clonar el repositorio:
```bash
git clone <repository-url>
cd bdd-to-ibdd-nlp
```

2. Crear y activar entorno virtual:
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar credenciales de OpenAI:
```bash
# Crear archivo .env en la raíz del proyecto
echo "OPENAI_API_KEY=tu-api-key" > .env
```

## Uso

### Pipeline Completo

Ejecutar la traducción, validación y explicación de errores completa:

```bash
python src/main.py data/Dataset.json docs/PROMPT_EN.md
```

Opciones adicionales:

```bash
python src/main.py data/Dataset.json docs/PROMPT_EN.md \
  -t data/mi_traduccion.json \
  -v data/mi_validacion.json \
  -k sk-tu-api-key \
  -m gpt-4o-2024-08-06
```

Argumentos:
- `dataset`: Ruta al archivo JSON con escenarios BDD
- `prompt`: Ruta al archivo de prompt template (.md)
- `-t, --translation-output`: Ruta para guardar la traducción (default: data/output.json)
- `-v, --validation-output`: Ruta para guardar validación (default: data/parsed_ibdd_results.json)
- `-k, --api-key`: API key de OpenAI (opcional si está en .env)
- `-m, --model`: Modelo de OpenAI a usar (default: gpt-4o)

### Módulos Individuales

#### Solo Traducción

```bash
python -c "from src.translator import TranslationService; \
  service = TranslationService(); \
  service.translate('data/Dataset.json', 'docs/PROMPT_EN.md', 'output.json')"
```

#### Solo Validación

```bash
python -c "from src.parser import validate_ibdd_cases; \
  validate_ibdd_cases('data/output.json', 'results.json')"
```

#### Solo Explicación de Errores

```bash
python tests/test_explainer.py data/tests/test_errors.json
```

## Estructura del Proyecto

```
bdd-to-ibdd-nlp/
│
├── src/                          # Código fuente principal
│   ├── __init__.py
│   ├── main.py                   # Orquestador del pipeline completo
│   ├── translator.py             # Servicio de traducción BDD→IBDD
│   ├── explainer.py              # Agente explicador de errores
│   └── parser.py                 # Parser y validador de sintaxis IBDD
│
├── tests/                        # Tests y scripts de prueba
│   ├── __init__.py
│   └── test_explainer.py         # Test del explicador de errores
│
├── data/                         # Datos y resultados
│   ├── Dataset.json              # Dataset principal de entrada
│   ├── output.json               # Resultado de traducción (default)
│   ├── parsed_ibdd_results.json  # Resultado de validación (default)
│   ├── error_explanations.json   # Explicaciones de errores (si hay)
│   │
│   ├── examples/                 # Datasets de ejemplo
│   │   ├── small_dataset.json    # Dataset pequeño (3 casos)
│   │   └── medium_dataset.json   # Dataset mediano (23 casos)
│   │
│   └── tests/                    # Datos para testing
│       ├── test_errors.json
│       └── test_explainer_results.json
│
├── docs/                         # Documentación y prompts
│   ├── PROMPT_EN.md              # Template de prompt en inglés (ACTIVO)
│   └── PROMPT_ES.md              # Template de prompt en español (referencia)
│
├── _deprecated/                  # Archivos obsoletos (eliminar después)
│   ├── README.md
│   ├── old_versions/
│   └── unused_modules/
│
├── .env                          # Configuración (crear manualmente)
├── requirements.txt              # Dependencias de Python
└── README.md                     # Este archivo
```

## Flujo del Sistema

El sistema implementa un pipeline de 3 pasos:

```
1. TRADUCCIÓN (Translator)
   Dataset BDD (JSON) → OpenAI API → IBDD (JSON)

2. VALIDACIÓN (Parser)
   IBDD (JSON) → Parser Lark → Resultados de validación (JSON + CSV)

3. EXPLICACIÓN (Explainer - solo si hay errores)
   Casos con errores → OpenAI API → Explicaciones detalladas (JSON)
```

### Paso 1: Traducción

- Lee escenarios BDD del archivo de entrada
- Usa el prompt especificado
- Envía cada escenario a OpenAI para traducción
- Guarda resultados en formato JSON con:
  - ID, dominio, título
  - Cláusulas BDD originales (given, when, then)
  - Representación IBDD generada
  - Metadatos (complejidad, notas)

### Paso 2: Validación

- Parsea cada representación IBDD usando gramática Lark
- Valida sintaxis y estructura
- Genera reporte con:
  - Estado de validación (válido/inválido)
  - Mensajes de error detallados si falla
  - Resultado parseado si es exitoso
- Exporta a JSON y CSV

### Paso 3: Explicación de Errores

- Se ejecuta automáticamente si hay casos con errores
- Para cada error:
  - Analiza el escenario BDD original
  - Examina el IBDD generado
  - Identifica el tipo y ubicación del error
  - Proporciona sugerencias de corrección
- Guarda explicaciones en data/error_explanations.json

## Gramática IBDD

La gramática IBDD soportada incluye:

### Estructura Básica
```
GIVEN <variables> [<precondición>]
WHEN <switch>+
THEN <switch>* [<postcondición>]
```

### Switch
```
<interaction> [<condición>] <asignación>
```

Donde:
- `<interaction>`: Gate (entrada/salida) con variables (ej: `?input.x,y` o `!output.result`)
- `<condición>`: Expresión lógica opcional entre corchetes
- `<asignación>`: Asignaciones de variables (ej: `x := 5`) o `true`

### Expresiones Soportadas

- Literales: `true`, `false`, números
- Variables: identificadores alfanuméricos
- Operadores lógicos: `∧` (AND), `||` (OR), `!` (NOT)
- Operadores de comparación: `=`, `==`, `!=`, `<`, `>`, `<=`, `>=`
- Operadores aritméticos: `+`, `-`, `*`, `/`, `%`, `^`
- Funciones: `nombre(arg1, arg2, ...)`
- Acceso a propiedades: `objeto.propiedad`

## Desarrollo

### Agregar Nuevos Casos de Prueba

Editar `data/Dataset.json` con el siguiente formato:

```json
{
  "id": 1,
  "domain": "nombre_dominio",
  "title": "Título del caso",
  "given": "condición inicial",
  "when": "acción del usuario",
  "then": "resultado esperado",
  "complexity": "simple|medium|complex",
  "notes": "notas adicionales opcionales"
}
```

### Modificar el Prompt

TODO: cambiar esto
Editar `docs/PROMPT_EN.md` para ajustar las instrucciones de traducción enviadas al LLM.

## Resultados y Métricas

El sistema genera automáticamente:

- **Tasa de éxito**: Porcentaje de casos que pasan validación
- **Reporte CSV**: Resumen de resultados en formato tabular
- **Explicaciones**: Análisis detallado de cada error encontrado

Ubicación de resultados:
- `data/output.json` - Traducciones generadas
- `data/parsed_ibdd_results.json` - Resultados de validación
- `data/parsed_ibdd_results.csv` - Resultados en formato CSV
- `data/error_explanations.json` - Explicaciones de errores (si aplica)

## Notas Técnicas

- El parser usa la biblioteca Lark con estrategia Earley para manejar ambigüedades
- Las traducciones usan Structured Outputs de OpenAI para garantizar formato JSON válido
- El explainer usa el modelo gpt-4o con temperatura 0.3
- Todos los módulos soportan tanto ejecución independiente como integrada

## Contacto

annaaimeri@mi.unc.edu.ar
