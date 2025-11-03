"""
Definición de la gramática IBDD usando Lark
"""

IBDD_GRAMMAR = r"""
    // Estructura principal: GIVEN WHEN THEN
    ?start: scenario

    scenario: given when then

    // GIVEN section: variables locales y precondición
    given: "GIVEN" [vars] guard
    vars: var ("," var)*

    // WHEN section: una serie de switches
    when: "WHEN" switch+

    // THEN section: switches opcionales y postcondición
    then: "THEN" switch* guard

    // Switch: más flexible para manejar diferentes formatos
    switch: interaction (expr | assignment)*

    // Interacción
    interaction: gate ("." var_list)?
    gate: /[!?][a-zA-Z][a-zA-Z0-9_]*/
    var_list: var ("," var)*

    // Guardián (condición)
    guard: "[" expr "]"

    // Expresión (condición o parte de asignación)
    expr: or_expr

    or_expr: and_expr ("||" and_expr)*
    and_expr: not_expr (("&&" | "∧") not_expr)*
    not_expr: "!" comparison | comparison | neg comparison

    // Comparación
    comparison: sum (op sum)?
    op: "=" | "==" | "!=" | "<" | ">" | "<=" | ">=" | "≥" | "≤" | "≠"

    // Operaciones matemáticas
    sum: product (("+"|"-") product)*
    product: power (("*"|"/"|"%") power)*
    power: atom ("^" atom)?
    sqrt: "√" atom
    neg: "¬" atom

    // Átomo (unidad básica de expresión)
    atom: literal
        | var
        | func_call
        | prop_access
        | neg_number
        | "(" expr ")"

    // Número negativo
    neg_number: "-" NUMBER

    // Valores literales - definirlos como tokens explícitos
    literal: TRUE -> true_val
           | FALSE -> false_val
           | NUMBER -> number

    TRUE: "true"
    FALSE: "false"

    // Llamada a función
    func_call: func_name "(" [arg_list] ")"
    func_name: /[a-zA-Z][a-zA-Z0-9_]*/
    arg_list: expr ("," expr)*

    // Acceso a propiedad
    prop_access: var "." var

    // Asignación
    assignment: TRUE -> true_assignment
              | assignment_list

    assignment_list: assignment_expr ("," assignment_expr)*
    assignment_expr: assign_target ":=" expr
    assign_target: var | prop_access

    // Variable
    var: /[A-Za-z][A-Za-z0-9_]*/

    // Terminales
    NUMBER: /[0-9]+(\.[0-9]+)?/
    NL: /\r?\n/

    %import common.WS
    %ignore WS    
"""