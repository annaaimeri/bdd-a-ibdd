# BDD to IBDD NLP

Este repositorio acompaña la implementación de mi trabajo final para la Licenciatura en Ciencias de la Computación de la Facultad de Matemática, Astronomía, Física y Computación en la Universidad Nacional de Córdoba. El objetivo es traducir escenarios BDD expresados en JSON a representaciones IBDD usando un LLM, validar la sintaxis de las traducciones y registrar los resultados del proceso.

El pipeline principal:

1. lee un dataset de escenarios BDD
2. genera una traducción IBDD para cada caso
3. valida la sintaxis de la salida
4. si hay errores, intenta corregirlos en rondas sucesivas
5. guarda traducciones, validaciones y métricas en archivos JSON

## Requisitos

- Python 3.10 o superior
- Un proveedor LLM configurado:
  - `openai` con `OPENAI_API_KEY`, o
  - `ollama` corriendo localmente

## Preparar el entorno

```bash
git clone <URL_DEL_REPO>
cd bdd-to-ibdd-nlp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuración

### OpenAI

Podés exportar la variable:

```bash
export OPENAI_API_KEY="tu_api_key"
```

O usar un archivo `.env` en la raíz del proyecto:

```env
OPENAI_API_KEY=tu_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

### Ollama

Ejemplo de `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.3:70b
LLM_BASE_URL=http://localhost:11434
```

## Datasets incluidos

Para probar una ejecución recomiendo usar los ejemplos chicos:

- `data/examples/small_dataset.json`
- `data/examples/medium_dataset.json`

El repositorio también incluye otros datasets más amplios usados durante el desarrollo y la evaluación.

También se incluyen ejemplos de salida para inspección rápida:

- `data/examples/translation_output_example.json`
- `data/examples/error_explanations_example.json`
- `data/examples/retry_cycle_example.json`

## Ejecutar el pipeline completo

### Primera corrida recomendada

```bash
python3 src/main.py data/examples/small_dataset.json docs/PROMPT_EN.md
```

Este comando usa por defecto:

- traducciones en `data/output.json`
- validación en `data/parsed_ibdd_results.json`
- explicaciones de error en `data/error_explanations.json`

### Guardar los resultados en archivos propios

```bash
python3 src/main.py data/examples/small_dataset.json docs/PROMPT_EN.md \
  -t data/mi_traduccion.json \
  -v data/mi_validacion.json \
  --max-rounds 2 \
  --workers 1
```

En este caso, además, se genera:

- `data/mi_traduccion_metrics.json`

### Correr el ejemplo mediano

```bash
python3 src/main.py data/examples/medium_dataset.json docs/PROMPT_EN.md
```

### Correr con Ollama

```bash
python3 src/main.py data/examples/small_dataset.json docs/PROMPT_EN.md \
  --provider ollama \
  --model llama3.3:70b \
  --base-url http://localhost:11434
```

## Dónde revisar los resultados

Los archivos principales son:

- `data/output.json`: traducciones IBDD generadas
- `data/parsed_ibdd_results.json`: resultado de validación por caso
- `data/error_explanations.json`: explicación de los errores detectados, si hubo fallos

Si querés ver ejemplos de salida sin ejecutar el pipeline, podés revisar:

- `data/examples/translation_output_example.json`
- `data/examples/error_explanations_example.json`
- `data/examples/retry_cycle_example.json`

Si usaste `-t data/mi_traduccion.json`, también conviene revisar:

- `data/mi_traduccion_metrics.json`: tiempos, rondas y resumen de la corrida

## Qué contiene cada salida

En el archivo de traducción, cada caso conserva su estructura original y agrega:

- `ibdd_representation`: traducción IBDD generada
- `_metrics`: tiempo y metadatos de la traducción

En el archivo de validación, cada caso incluye:

- `valid`: indica si la traducción pasó la validación
- `error`: mensaje de error, si falló

## Prompts disponibles

- `docs/PROMPT_EN.md`
- `docs/PROMPT_ES.md`
- `docs/PROMPT_EN_RETRY.md`
- `docs/PROMPT_ES_RETRY.md`

El pipeline detecta automáticamente el prompt de reintento según el idioma del prompt principal.

## Parámetros principales de `src/main.py`

- `dataset`: ruta al dataset JSON de entrada
- `prompt`: ruta al prompt principal
- `-t`, `--translation-output`: archivo de salida de traducciones
- `-v`, `--validation-output`: archivo de salida de validación
- `-k`, `--api-key`: clave API opcional
- `--provider`: `openai` u `ollama`
- `--model`: modelo a utilizar
- `--base-url`: URL base opcional del proveedor
- `--max-rounds`: máximo de rondas de corrección
- `--workers`: cantidad de workers para llamadas al LLM

## Ejecutar módulos por separado

### Solo traducción

```bash
python3 src/translator.py data/examples/small_dataset.json docs/PROMPT_EN.md \
  -o data/solo_traduccion.json
```

### Solo validación

```bash
python3 src/parser.py data/solo_traduccion.json data/solo_validacion.json
```

### Evaluación

```bash
python3 src/evaluate.py \
  --runs 3 \
  --max-rounds 2 \
  --workers 1 \
  --provider openai \
  --model gpt-4o \
  --configs EN-EN
```
