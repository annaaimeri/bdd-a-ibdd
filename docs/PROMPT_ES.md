# Prompt para Traducción BDD → IBDD

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
Switch   ::= Interaction Condition Assignment
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

**Traducción IBDD:**
```
GIVEN JF [true]
WHEN ?submit.jf,sm
  true
  JF := jf
THEN !append.cj,sjl
  cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)
  CJ := cj, SJL := add(CJ, SJL)
  [is_in_list(CJ, SJL) ∧ CJ.type = JT]
```

**Razonamiento:**
- Given: Solo declara variable local `JF` (job file), sin precondiciones → `[true]`
- When: Gate de input `?submit` con variables de interacción `jf`, `sm`
- Then: Gate de output `!append` que añade job a lista, con postcondición verificando inclusión

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

**Traducción IBDD:**
```
GIVEN CJ [is_in_list(CJ, SJL) ∧ CJ.type = Production]
WHEN !printstart.cj
  cj.id = CJ.id ∧ cj.state = Printing
  CJ.state := cj.state
!printcomplete.cj
  cj.id = CJ.id ∧ cj.state = Completed
  CJ.state := cj.state, PJL := add(CJ, PJL)
THEN [is_in_list(CJ, PJL)]
```

**Razonamiento:**
- Given: Variable local `CJ` con guard que verifica: está en `SJL` Y es de tipo Production
- When: Dos switches secuenciales (!printstart, !printcomplete) que actualizan estado
- Then: Postcondición verifica que `CJ` está en `PJL` (Printed Jobs List)

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

**Traducción IBDD:**
```
GIVEN [is_running(CTRL)]
WHEN ?restart
  true
  (no assignment)
THEN !cleanup
  true
  PJL := empty(PJL)
  [is_empty(PJL)]
```

**Razonamiento:**
- Given: No hay variables locales, solo guard verificando estado del controlador
- When: Input gate simple sin condiciones ni asignaciones relevantes
- Then: Output gate que limpia lista y verifica que quede vacía

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

**Traducción IBDD:**
```
GIVEN P, SC [P.price > 0 ∧ is_valid(SC)]
WHEN ?add_to_cart.p,sc,qty
  p.id = P.id ∧ sc.id = SC.id ∧ qty > 0
  SC.items := add(p, SC.items), SC.total := SC.total + (p.price * qty)
THEN [is_in_list(P, SC.items) ∧ SC.total = calculate_total(SC.items)]
```

**Razonamiento:**
- Given: Dos variables locales (`P`, `SC`) con guards verificando precio válido y carrito válido
- When: Gate con múltiples variables de interacción (producto, carrito, cantidad)
- Then: Postcondición verifica inclusión del producto y actualización correcta del total

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

### 4.2 When Clause
- Acciones del usuario → gates de input (`?`)
- Acciones del sistema → gates de output (`!`)
- Múltiples acciones con "AND" → múltiples switches secuenciales
- Identifica variables de interacción necesarias para la comunicación

### 4.3 Then Clause
- Verifica estado final en postcondición (guard final)
- Si hay acciones explícitas del sistema → switches con gates de output
- Postcondición siempre entre corchetes `[]`

### 4.4 Convenciones de Nombres
- Variables locales: Abreviaturas en mayúsculas (CJ, JF, P, SC)
- Variables globales: Descriptivas en mayúsculas (SJL, PJL, CTRL)
- Variables de interacción: Minúsculas, relacionadas con las locales (cj, jf, p, sc)
- Gates: Verbos descriptivos en minúsculas (submit, printstart, add_to_cart)

---

## 5. Instrucción Final

Procesa el JSON de entrada y devuelve el mismo JSON con el campo `"ibdd_representation"` añadido a cada escenario. 

**IMPORTANTE**: 
- NO incluyas explicaciones, comentarios o markdown
- SOLO devuelve el JSON resultante
- Mantén exactamente la misma estructura del JSON de entrada
- La representación IBDD debe ser un string con saltos de línea (`\n`)