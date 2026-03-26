# BDD to IBDD NLP

Guía para levantar el proyecto localmente y ejecutar el pipeline completo de traducción BDD -> IBDD.

## Objetivo

Tomar un dataset JSON con escenarios BDD (`given`, `when`, `then`), traducirlo a IBDD con un LLM, validar la sintaxis con el parser y guardar resultados intermedios/finales en JSON.

## Requisitos

- Tener Python 3.10+ instalado
- Tener acceso a un proveedor LLM:
  - `openai` con `OPENAI_API_KEY`, o
  - `ollama` corriendo localmente con un modelo descargado.

## Instalar dependencias

1. Clonar el repositorio.
2. Entrar al directorio del proyecto.
3. Crear entorno virtual.
4. Activar entorno virtual.
5. Instalar dependencias.

```bash
git clone <URL_DEL_REPO>
cd bdd-to-ibdd-nlp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configurar credenciales / proveedor

### Opción A: OpenAI

Definir `OPENAI_API_KEY` por variable de entorno:

```bash
export OPENAI_API_KEY="tu_api_key"
```

O crear `.env` en la raíz del proyecto:

```env
OPENAI_API_KEY=tu_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

### Opción B: Ollama

Tener Ollama levantado y un modelo disponible. Definir proveedor/modelo por CLI o `.env`.

Ejemplo `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.3:70b
LLM_BASE_URL=http://localhost:11434
```

## Preparar dataset de entrada (JSON)

El pipeline espera un arreglo JSON de casos. Cada caso debe tener, como mínimo:

- `id`
- `domain`
- `title`
- `given`
- `when`
- `then`

Se puede agregar `complexity` u otros metadatos; el traductor los preserva.

### Ejemplo mínimo de dataset

```json
[
  {
    "id": 1,
    "domain": "printer",
    "title": "Submit job to printer",
    "given": "a job file",
    "when": "the operator submits the job file using Submission method",
    "then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type",
    "complexity": "medium"
  }
]
```

Archivos de ejemplo ya incluidos:

- `data/Dataset.json`
- `data/Dataset_20.json`
- `data/Dataset_ES.json`

## Ejecutar pipeline completo (recomendado)

Usar `src/main.py` desde la raíz del repo.

### Ejecución básica

```bash
python3 src/main.py data/Dataset_20.json docs/PROMPT_EN.md
```

Eso ejecuta:

1. Traducción BDD -> IBDD
2. Validación sintáctica
3. Ciclo de corrección iterativa
4. Guardado de métricas

### Ejecución indicando salidas

```bash
python3 src/main.py data/Dataset_20.json docs/PROMPT_EN.md \
  -t data/mi_traduccion.json \
  -v data/mi_validacion.json \
  --max-rounds 2 \
  --workers 1
```

### Ejecución con Ollama

```bash
python3 src/main.py data/Dataset_20.json docs/PROMPT_EN.md \
  --provider ollama \
  --model llama3.3:70b \
  --base-url http://localhost:11434
```

## Parámetros principales de `src/main.py`

- `dataset` (posicional): ruta al dataset JSON.
- `prompt` (posicional): ruta al prompt (`.md`).
- `-t`, `--translation-output`: JSON de traducciones (default `data/output.json`).
- `-v`, `--validation-output`: JSON de validación (default `data/parsed_ibdd_results.json`).
- `-k`, `--api-key`: clave API (opcional).
- `-m`, `--model`: modelo a usar.
- `--provider`: `openai` u `ollama`.
- `--base-url`: URL base opcional del proveedor.
- `--max-rounds`: cantidad máxima de rondas de corrección.
- `--workers`: paralelismo para llamadas al LLM.

## Archivos que genera el pipeline

### 1. Traducciones (`translation-output`)

Archivo JSON con la estructura original + `ibdd_representation` + `_metrics`.

Ejemplo:

```json
[
  {
    "id": 1,
    "domain": "printer",
    "title": "Submit job to printer",
    "given": "a job file",
    "when": "the operator submits the job file using Submission method",
    "then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type",
    "complexity": "medium",
    "ibdd_representation": "GIVEN JF, SM [true]\\nWHEN ?submit.jf,sm [true] JF := jf, SM := sm\\nTHEN [true]",
    "_metrics": {
      "translation_time": 2.98,
      "timestamp": "2026-01-06 16:43:09"
    }
  }
]
```

### 2. Validación sintáctica (`validation-output`)

Archivo JSON con resultado por caso (`valid`, `error`, `parsed_result`).

Ejemplo:

```json
[
  {
    "id": 1,
    "domain": "printer",
    "title": "Submit job to printer",
    "valid": true,
    "error": null,
    "parsed_result": "GIVEN JF, SM [[]\\nWHEN 1 switches\\nTHEN [[]"
  }
]
```

### 3. Explicaciones de error (si hay fallos)

Archivo por defecto: `data/error_explanations.json` (o el que el pipeline use internamente para la corrida).

Ejemplo:

```json
[
  {
    "case_id": 3,
    "success": true,
    "original_bdd": {
      "given": "the printer controller is running",
      "when": "the operator restarts the printer controller",
      "then": "the printed jobs clean up is executed"
    },
    "previous_translation": "GIVEN [is_running(CTRL)]\\nWHEN ?restart ...",
    "parse_error": "No terminal matches ...",
    "explanation": "El parser esperaba ...",
    "error_type": "Asignaciones faltantes",
    "error_location": "Línea 4",
    "correction_suggestion": "Reemplazar ...",
    "hints": [
      "Asegurarse de ..."
    ]
  }
]
```

### 4. Métricas del pipeline

El pipeline genera un archivo adicional junto a la salida de traducción:

- si `-t data/mi_traduccion.json`, genera `data/mi_traduccion_metrics.json`

Incluye resumen inicial/final, rondas, tiempos y casos fallidos.

## Ejecutar módulos por separado (opcional)

### Solo traducción

```bash
python3 src/translator.py data/Dataset_20.json docs/PROMPT_EN.md \
  -o data/solo_traduccion.json \
  --provider openai \
  --model gpt-4o
```

### Solo validación sintáctica

Usar el parser sobre un archivo de traducciones (debe tener `ibdd_representation` en cada caso).

```bash
python3 src/parser.py data/solo_traduccion.json data/solo_validacion.json
```

### Solo evaluación (corridas múltiples)

`src/evaluate.py` ejecuta varias corridas y genera resumen JSON + fragmento LaTeX.

```bash
python3 src/evaluate.py \
  --runs 3 \
  --max-rounds 2 \
  --workers 1 \
  --provider openai \
  --model gpt-4o \
  --configs EN-EN ES-EN \
  --output-dir data/eval_demo \
  --latex-out tesis/07_evaluacion/generated_results.tex
```

## Preparar prompts propios

Para ejecutar el pipeline completo, indicar un prompt `.md` como segundo argumento.

Prompts disponibles:

- `docs/PROMPT_EN.md`
- `docs/PROMPT_ES.md`
- `docs/PROMPT_EN_RETRY.md`
- `docs/PROMPT_ES_RETRY.md`

El pipeline detecta automáticamente el prompt de reintento según el nombre del prompt principal (`_ES` o inglés por defecto).

## Checklist rápido para correr localmente

1. Activar `venv`.
2. Configurar `.env` o variables (`OPENAI_API_KEY` / `LLM_PROVIDER` / `LLM_MODEL`).
3. Elegir dataset (`data/Dataset_20.json` para prueba corta).
4. Elegir prompt (`docs/PROMPT_EN.md` o `docs/PROMPT_ES.md`).
5. Ejecutar `python3 src/main.py ...`.
6. Revisar:
   - traducciones (`*_output.json` o `-t`)
   - validación (`*_validation.json` o `-v`)
   - métricas (`*_metrics.json`)

