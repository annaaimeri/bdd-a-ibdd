# Prompt para Traducción BDD → IBDD

## Contexto
Vas a traducir escenarios escritos en formato Gherkin a un lenguaje intermedio llamado IBDD (Intermediate Behavior-Driven Development). IBDD mantiene la estructura Given-When-Then pero añade precisión formal mediante Symbolic Transition Systems (STS).

## 1. Definición de IBDD

### Gramática (EBNF):
* Scenario ::= Given When Then
* Given ::= 'GIVEN' Declaration '[' Guard ']'
* Declaration ::= lv1, ..., lvn  
* Guard ::= P | Guard '∧' Guard
* When ::= 'WHEN' Switch+
* Switch ::= Interaction Condition Assignment
* Interaction ::= g. iv1, ..., ivn
* Condition ::= B
* Assignment ::= A
* Then ::= 'THEN' Switch* '[' Guard ']'

### Elementos clave:
* Variables locales (lv): Declaradas en GIVEN, visibles en todo el escenario. 
* Variables globales: Estado persistente del sistema (ej: SJL = Scheduled Jobs List). 
* Variables de interacción (iv): Comunicación entre sistema y entorno. 
* Gates: 
   * ! = output del sistema 
   * ? = input desde el entorno 
* Guards: Condiciones booleanas.
* Assignments: Asignaciones (var := expresión).

## 2. Formato de Entrada y Salida

### Formato de Entrada:
Recibirás un JSON que contiene una lista de escenarios en formato Gherkin, cada uno con:
- id: Identificador único del escenario
- domain: Dominio al que pertenece el escenario
- title: Título descriptivo del escenario
- given: Condiciones iniciales (Given en Gherkin)
- when: Acciones (When en Gherkin)
- then: Resultados esperados (Then en Gherkin)
- complexity: Nivel de complejidad del escenario

### Formato de Salida:
Deberás devolver el mismo JSON de entrada, pero añadiendo un campo "ibdd_representation" a cada escenario con la traducción IBDD.

## 3. Instrucciones para la Traducción

Para cada escenario en el JSON:

1. Analiza las secciones given, when y then
2. Identifica variables locales, globales y de interacción apropiadas
3. Determina los gates (? para input, ! para output)
4. Define guards y assignments coherentes con el escenario
5. Estructura el resultado en formato IBDD (GIVEN, WHEN, THEN)
6. Asegúrate de que la traducción sea precisa y refleje el comportamiento descrito

## 4. Ejemplo de Traducción

### Escenario Gherkin:
{
"id": 1,
"domain": "printer",
"title": "Submit job to printer",
"given": "a job file",
"when": "the operator submits the job file using Submission method",
"then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type"
}

### Traducción IBDD esperada:
{
"id": 1,
"domain": "printer",
"title": "Submit job to printer",
"given": "a job file",
"when": "the operator submits the job file using Submission method",
"then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type",
"ibdd_representation": "GIVEN JF [true]\nWHEN ?submit.jf,sm\n    true\n    JF := jf\nTHEN !append.cj,sjl\n    cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)\n    CJ := cj, SJL := add(CJ, SJL)\n    [is_in_list(CJ, SJL) ∧ CJ.type = JT]"
}

## 5. Consideraciones Adicionales

- Mantén consistencia en el estilo de representación IBDD
- Usa abreviaturas apropiadas para las variables (ej. P para Product, SC para ShoppingCart)
- Las variables globales deben representarse en mayúsculas
- Incluye condiciones de guardia adecuadas según el contexto
- Captura fielmente la lógica del escenario en la representación IBDD

### Instrucción Final:
Procesa el JSON de entrada y devuelve el mismo JSON con el campo "ibdd_representation" añadido a cada escenario con su traducción IBDD correspondiente. NO incluyas explicaciones o comentarios adicionales, SOLO devuelve el JSON resultante.