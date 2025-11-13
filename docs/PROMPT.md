# Prompt para Traducción BDD → IBDD

## Contexto  
Vas a traducir escenarios escritos en Gherkin a un lenguaje intermedio llamado IBDD (Intermediate Behavior-Driven Development).  IBDD mantiene la estructura Given–When–Then pero añadí precisión formal mediante Symbolic Transition Systems (STS).


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


## 2. Ejemplo de Traducción

### Escenario Gherkin
* Scenario: A controller job is added to the scheduled jobs after a job file has been submitted
* Given a job file
* When the operator submits the job file using Submission method  
* Then the printer appends a new controller job to the scheduled jobs
* And the controller job is of type Job type

### Traducción IBDD esperada
* GIVEN JF [true]
* WHEN ?submit.jf,sm
*     true
*     JF := jf
* THEN !append.cj,sjl
*     cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)
*     CJ := cj, SJL := add(CJ, SJL)
*     [is_in_list(CJ, SJL) ∧ CJ.type = JT]


## 3. Tarea

Traducí el siguiente escenario a IBDD, pero generá 3 opciones distintas, explorando variaciones en el modelado:

### Escenario a traducir (en Gherkin):
* Scenario: A product is added to shopping cart when user selects it
* Given a product is available in inventory
* And the user is logged in
* When the user clicks add to cart button
* And the user specifies quantity  
* Then the product is added to the shopping cart
* And the inventory is updated


## 4. Requisitos de Salida

Para cada traducción:
1. Etiqueta clara: (Opción 1, Opción 2, Opción 3). 
2. Explicación del enfoque: qué varía (granularidad, modelado, nivel de detalle, etc.). 
3. Identificación de variables: locales, globales, de interacción. 
4. Definición de gates: usando ? (input) y ! (output). 
5. Uso de guards y assignments: coherentes con el escenario. 
6. Estructura completa en formato IBDD (GIVEN, WHEN, THEN). 
7. Justificación breve de por qué elegiste ese modelado. 


## 5. Enfoques sugeridos para variar las opciones
* Opción 1: Interacciones atómicas (cada acción del usuario y del sistema separada). 
* Opción 2: Interacción compuesta (modelar el "add to cart" como un evento único que engloba acción + cantidad). 
* Opción 3: Cambio de granularidad en variables (por ejemplo, modelar inventario como entero vs lista de productos). 


### Instrucción Final al LLM:
Generá 3 traducciones del escenario en formato IBDD, cumpliendo con los requisitos anteriores.