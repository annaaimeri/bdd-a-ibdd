# Prompt para Traducción BDD → IBDD (MODO REINTENTO)

## ⚠️ MODO REINTENTO ACTIVO

Estás intentando corregir una traducción previa que falló al parsearse correctamente.

### Resumen del Intento Anterior:
{error_analysis}

### Tu Tarea:
Revisa cuidadosamente el análisis de error anterior y genera una **traducción IBDD corregida** que:
1. Corrija los errores de parsing específicos identificados
2. Siga todas las reglas gramaticales estrictamente
3. Mantenga alineación semántica con el escenario BDD original

**PRESTA ESPECIAL ATENCIÓN A:**
- Colocación de corchetes: Todos los guards y condiciones DEBEN estar en `[...]`
- Sintaxis de gates: Usa `!` para salida del sistema, `?` para entrada
- Formato de asignaciones: Sigue el patrón `var := expresión`
- Saltos de línea: Cada switch en una línea separada

---

## Contexto

Vas a traducir escenarios escritos en formato Gherkin a un lenguaje intermedio llamado IBDD (Intermediate Behavior-Driven Development). IBDD mantiene la estructura Given-When-Then pero añade precisión formal mediante Symbolic Transition Systems (STS).

## 1. Definición de IBDD

### Gramática (EBNF):

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

### Elementos clave:

- **Variables locales (lv)**: Declaradas en GIVEN, visibles en todo el escenario
- **Variables globales**: Estado persistente del sistema (ej: SJL = Scheduled Jobs List)
- **Variables de interacción (iv)**: Comunicación entre sistema y entorno
- **Gates**:
  - `!` = output del sistema
  - `?` = input desde el entorno
- **Guards**: Condiciones booleanas
- **Assignments**: Asignaciones (var := expresión)

---

## 2. Ejemplos de Traducción

### Ejemplo 1: Escenario Simple (Solo Given con Variable Local)

**Escenario Gherkin:**
```json
{
  "id": 1,
  "domain": "printer",
  "title": "Submit job to printer",
  "given": "a job file",
  "when": "the operator submits the job file using Submission method",
  "then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type"
}
```

**Traducción IBDD (una línea):**
```
GIVEN JF [true] WHEN ?submit.jf,sm [true] JF := jf THEN !append.cj,sjl [cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)] CJ := cj, SJL := add(CJ, SJL) [is_in_list(CJ, SJL) ∧ CJ.type = JT]
```

**Traducción IBDD (formateada con \n):**
```
GIVEN JF [true]
WHEN ?submit.jf,sm [true] JF := jf
THEN !append.cj,sjl [cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)] CJ := cj, SJL := add(CJ, SJL)
[is_in_list(CJ, SJL) ∧ CJ.type = JT]
```

**Razonamiento:**
- Given: Solo declara variable local `JF` (job file), sin precondiciones → `[true]`
- When: Gate de input `?submit` con variables de interacción `jf`, `sm`, condición `[true]`, asignación `JF := jf`
- Then: Gate de output `!append` con condición y asignación, postcondición verificando inclusión

---

### Ejemplo 2: Escenario con Variables Locales y Guards

**Escenario Gherkin:**
```json
{
  "id": 2,
  "domain": "printer",
  "title": "Move production job to printed jobs",
  "given": "a controller job is in the scheduled jobs AND the controller job is a production job",
  "when": "the printer starts printing the controller job AND the printer completes printing the controller job",
  "then": "the controller job is in the printed jobs"
}
```

**Traducción IBDD (formateada con \n):**
```
GIVEN CJ [is_in_list(CJ, SJL) ∧ CJ.type = Production]
WHEN !printstart.cj [cj.id = CJ.id ∧ cj.state = Printing] CJ.state := cj.state
!printcomplete.cj [cj.id = CJ.id ∧ cj.state = Completed] CJ.state := cj.state, PJL := add(CJ, PJL)
THEN [is_in_list(CJ, PJL)]
```

**Razonamiento:**
- Given: Variable local `CJ` con guard que verifica: está en `SJL` Y es de tipo Production
- When: Dos switches secuenciales (!printstart, !printcomplete) cada uno con condición entre corchetes y asignaciones
- Then: Sin switches, solo postcondición verificando que `CJ` está en `PJL`

---

### Ejemplo 3: Escenario con Solo Guard (Sin Variables Locales)

**Escenario Gherkin:**
```json
{
  "id": 3,
  "domain": "printer",
  "title": "Clean up printed jobs on restart",
  "given": "the printer controller is running",
  "when": "the operator restarts the printer controller",
  "then": "the printed jobs clean up is executed"
}
```

**Traducción IBDD (formateada con \n):**
```
GIVEN [is_running(CTRL)]
WHEN ?restart [true] true
THEN !cleanup [true] PJL := empty(PJL)
[is_empty(PJL)]
```

**Razonamiento:**
- Given: No hay variables locales, solo guard verificando que el controlador está corriendo
- When: Gate de input `?restart` con condición `[true]` y asignación `true` (sin cambio de estado)
- Then: Gate de output `!cleanup` que limpia lista, postcondición verifica que está vacía

---

### Ejemplo 4: Escenario con Múltiples Variables de Interacción

**Escenario Gherkin:**
```json
{
  "id": 4,
  "domain": "ecommerce",
  "title": "Add product to cart",
  "given": "a product with price and a shopping cart",
  "when": "the user adds the product to the cart with quantity",
  "then": "the cart contains the product AND the total price is updated"
}
```

**Traducción IBDD (formateada con \n):**
```
GIVEN P, SC [P.price > 0 ∧ is_valid(SC)]
WHEN ?add_to_cart.p,sc,qty [p.id = P.id ∧ sc.id = SC.id ∧ qty > 0] SC.items := add(p, SC.items), SC.total := SC.total + (p.price * qty)
THEN [is_in_list(P, SC.items) ∧ SC.total = calculate_total(SC.items)]
```

**Razonamiento:**
- Given: Dos variables locales (`P`, `SC`) con guards verificando precio válido y carrito válido
- When: Gate con múltiples variables de interacción, condición entre corchetes, múltiples asignaciones
- Then: Sin switches, solo postcondición verificando inclusión del producto y actualización correcta del total

---

## 3. Formato de Entrada y Salida

### Formato de Entrada:
```json
[
    {
      "id": "<número>",
      "domain": "<dominio>",
      "title": "<título>",
      "given": "<condiciones iniciales>",
      "when": "<acciones>",
      "then": "<resultados esperados>"
    }
]
```

### Formato de Salida:
```json
[
    {
      "id": "<número>",
      "domain": "<dominio>",
      "title": "<título>",
      "given": "<condiciones iniciales>",
      "when": "<acciones>",
      "then": "<resultados esperados>",
      "ibdd_representation": "<traducción IBDD>"
    }
]
```

---

## 4. Reglas de Traducción

### 4.1 Given Clause
- Identifica si hay variables locales mencionadas ("a job", "a product" → variables locales)
- Si solo describe estado del sistema → solo guard, sin declaration
- Combina múltiples condiciones con `∧`
- El guard DEBE estar entre corchetes `[...]`

### 4.2 When Clause
- Acciones del usuario → gates de input (`?`)
- Acciones del sistema → gates de output (`!`)
- Múltiples acciones con "AND" → múltiples switches secuenciales
- Identifica variables de interacción necesarias para la comunicación
- **CRÍTICO: Cada switch DEBE tener condición entre corchetes `[...]`**
- Las asignaciones siguen a la condición

### 4.3 Then Clause
- Verifica estado final en postcondición (guard final)
- Si hay acciones explícitas del sistema → switches con gates de output
- **Cada switch DEBE tener condición entre corchetes `[...]`**
- La postcondición (guard final) DEBE estar entre corchetes `[...]`

### 4.4 Convenciones de Nombres
- Variables locales: Abreviaturas en mayúsculas (CJ, JF, P, SC)
- Variables globales: Descriptivas en mayúsculas (SJL, PJL, CTRL)
- Variables de interacción: Minúsculas, relacionadas con las locales (cj, jf, p, sc)
- Gates: Verbos descriptivos en minúsculas (submit, printstart, add_to_cart)

---

## 5. RECORDATORIOS CRÍTICOS PARA MODO REINTENTO

**ANTES DE GENERAR LA TRADUCCIÓN:**
1. ✓ Revisa el análisis de error anterior cuidadosamente
2. ✓ Identifica la ubicación exacta y naturaleza del error
3. ✓ Verifica la sugerencia de corrección proporcionada
4. ✓ Aplica la corrección manteniendo la corrección semántica

**ERRORES COMUNES A EVITAR:**
- Corchetes faltantes alrededor de guards o condiciones
- Sintaxis de gate incorrecta (usando dirección equivocada)
- Asignaciones faltantes después de condiciones
- Saltos de línea incorrectos (todos los switches deben estar en líneas separadas)
- Expresiones o llamadas a funciones mal formadas

---

## 6. Instrucción Final

Procesa el JSON de entrada y devuelve el mismo JSON con el campo `"ibdd_representation"` conteniendo tu traducción IBDD **CORREGIDA** para cada escenario.

**IMPORTANTE**:
- NO incluyas explicaciones, comentarios o markdown
- SOLO devuelve el JSON resultante
- Mantén exactamente la misma estructura del JSON de entrada
- **CRÍTICO**: Coloca tu traducción IBDD en el campo `"ibdd_representation"` (sobrescribe el valor existente si está presente)
- Deja el campo `"notes"` sin cambios si existe
- La representación IBDD debe ser un string con saltos de línea (`\n`)
- **TODAS las condiciones en Switch deben estar entre corchetes `[...]`**
- **TODOS los guards deben estar entre corchetes `[...]`**

**REGLAS CRÍTICAS DE FORMATO:**
1. Cláusula GIVEN: Una sola línea
2. Cada switch WHEN: Línea separada con formato: `<gate>.<vars> [<condición>] <asignación>`
3. Cada switch THEN: Línea separada con el mismo formato
4. Guard final THEN: Línea separada con formato: `[<postcondición>]`

**Ejemplo de formato correcto:**
```
GIVEN CJ [is_in_list(CJ, SJL)]
WHEN !printstart.cj [cj.id = CJ.id] CJ.state := cj.state
!printcomplete.cj [cj.id = CJ.id] CJ.state := cj.state
THEN [is_in_list(CJ, PJL)]
```

**SIEMPRE separa cada switch con `\n` (carácter de salto de línea en el string JSON)**

---

## 7. VERIFICACIÓN FINAL MODO REINTENTO

Antes de enviar tu traducción, verifica:
- [ ] El error específico mencionado arriba ha sido corregido
- [ ] Todos los corchetes están en su lugar para guards y condiciones
- [ ] Todos los gates tienen sintaxis correcta (`!` o `?`)
- [ ] Todas las asignaciones siguen el formato correcto
- [ ] Los saltos de línea están correctamente colocados
- [ ] La traducción es semánticamente correcta respecto al BDD original
