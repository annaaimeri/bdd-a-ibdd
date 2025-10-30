#!/usr/bin/env python3
"""
IBDD Validator - Loads JSON with IBDD cases and validates them using the IBDD Parser
"""

import json
import sys
import os
from typing import List, Dict, Any, Optional
import pandas as pd

# Import the parser from the first document
from lark import Lark, Transformer, v_args
from typing import List, Optional, Dict, Any, Union, Tuple
from dataclasses import dataclass, field
import re


# Include the parser code here (it's too long to paste directly in this display)
# Importing the parser class from the file
# The parser code is already included in the documents provided by the user

@dataclass
class IBDDExpression:
    """Expresión IBDD"""
    expr_type: str
    value: str
    args: List[Any] = field(default_factory=list)

    def __repr__(self):
        if self.expr_type == 'true':
            return 'true'
        elif self.expr_type == 'false':
            return 'false'
        elif self.expr_type == 'function':
            args_str = ', '.join(str(arg) for arg in self.args)
            return f"{self.value}({args_str})"
        elif self.expr_type == 'comparison':
            return f"{self.args[0]} {self.value} {self.args[1]}"
        elif self.expr_type == 'conjunction':
            return f"{self.args[0]} ∧ {self.args[1]}"
        elif self.expr_type == 'disjunction':
            return f"{self.args[0]} || {self.args[1]}"
        elif self.expr_type == 'property':
            return f"{self.args[0]}.{self.args[1]}"
        elif self.expr_type == 'number':
            return self.value
        elif self.expr_type == 'negative':
            return f"-{self.args[0]}"
        elif self.expr_type == 'variable':
            return self.value
        elif self.expr_type == 'sum':
            return f"{self.args[0]} + {self.args[1]}"
        elif self.expr_type == 'subtraction':
            return f"{self.args[0]} - {self.args[1]}"
        elif self.expr_type == 'multiplication':
            return f"{self.args[0]} * {self.args[1]}"
        elif self.expr_type == 'division':
            return f"{self.args[0]} / {self.args[1]}"
        elif self.expr_type == 'modulo':
            return f"{self.args[0]} % {self.args[1]}"
        elif self.expr_type == 'power':
            return f"{self.args[0]} ^ {self.args[1]}"
        elif self.expr_type == 'paren_expr':
            return f"({self.args[0]})"
        elif self.expr_type == 'not':
            return f"!{self.args[0]}"
        else:
            return self.value


@dataclass
class IBDDInteraction:
    """Interacción IBDD"""
    gate: str
    variables: List[str] = field(default_factory=list)

    def __repr__(self):
        if self.variables:
            return f"{self.gate}.{','.join(self.variables)}"
        return self.gate


@dataclass
class IBDDAssignment:
    """Asignación IBDD"""
    target: Union[str, Tuple[str, str]]
    value: Any

    def __repr__(self):
        if isinstance(self.target, tuple):
            return f"{self.target[0]}.{self.target[1]} := {self.value}"
        else:
            return f"{self.target} := {self.value}"


@dataclass
class IBDDSwitch:
    """Switch IBDD"""
    interaction: IBDDInteraction
    condition: IBDDExpression
    assignments: List[IBDDAssignment] = field(default_factory=list)

    def __repr__(self):
        assignments_str = ", ".join(str(a) for a in self.assignments)
        if not assignments_str:
            assignments_str = "true"
        return f"{self.interaction}\n{self.condition}\n{assignments_str}"


@dataclass
class IBDDScenario:
    """Escenario IBDD completo"""
    # GIVEN
    local_vars: List[str] = field(default_factory=list)
    precondition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))

    # WHEN
    when_switches: List[IBDDSwitch] = field(default_factory=list)

    # THEN
    then_switches: List[IBDDSwitch] = field(default_factory=list)
    postcondition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))

    def __repr__(self):
        result = []
        result.append(f"GIVEN {', '.join(self.local_vars) if self.local_vars else ''} [{self.precondition}]")

        # WHEN
        result.append(f"WHEN {len(self.when_switches)} switches")

        # THEN
        if self.then_switches:
            result.append(f"THEN {len(self.then_switches)} switches [{self.postcondition}]")
        else:
            result.append(f"THEN [{self.postcondition}]")

        return "\n".join(result)


# Gramática IBDD mejorada con soporte para matemáticas y corchetes
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

    // Switch: gate + variables, condición y asignación
    switch: interaction NL expr NL assignment NL?

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
    not_expr: "!" comparison | comparison

    // Comparación
    comparison: sum (op sum)?
    op: "=" | "==" | "!=" | "<" | ">" | "<=" | ">="

    // Operaciones matemáticas
    sum: product (("+"|"-") product)*
    product: power (("*"|"/"|"%") power)*
    power: atom ("^" atom)?

    // Átomo (unidad básica de expresión)
    atom: literal
        | var
        | func_call
        | prop_access
        | neg_number
        | "(" expr ")"

    // Número negativo
    neg_number: "-" NUMBER

    // Valores literales
    literal: "true" -> true_val
           | "false" -> false_val
           | NUMBER -> number

    // Llamada a función
    func_call: func_name "(" [arg_list] ")"
    func_name: /[a-zA-Z][a-zA-Z0-9_]*/
    arg_list: expr ("," expr)*

    // Acceso a propiedad
    prop_access: var "." var

    // Asignación
    assignment: "true" -> true_assignment
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

@v_args(inline=True)
class IBDDTransformer(Transformer):
    """Transforma el árbol de parsing a objetos IBDD"""

    # Estructura principal
    def scenario(self, given, when, then):
        scenario = IBDDScenario()

        # GIVEN
        if given:
            vars, precondition = given
            scenario.local_vars = vars if vars else []
            scenario.precondition = precondition if precondition else IBDDExpression('true', 'true')

        # WHEN
        if when:
            scenario.when_switches = when

        # THEN
        if then:
            switches, postcondition = then
            scenario.then_switches = switches if switches else []
            scenario.postcondition = postcondition if postcondition else IBDDExpression('true', 'true')

        return scenario

    # GIVEN
    def given(self, vars, guard):
        return (vars or [], guard)

    def vars(self, *args):
        return list(str(arg) for arg in args)

    # WHEN
    def when(self, *switches):
        return list(switches)

    # THEN
    def then(self, *args):
        # Separar switches de la postcondición
        switches = []
        postcondition = None

        for arg in args:
            if isinstance(arg, IBDDSwitch):
                switches.append(arg)
            else:
                postcondition = arg

        return (switches, postcondition)

    # Guard (precondición/postcondición)
    def guard(self, expr):
        return expr

    # SWITCH
    def switch(self, interaction, condition, assignment):
        assignments = []
        if isinstance(assignment, list):
            assignments = assignment

        return IBDDSwitch(interaction, condition, assignments)

    # INTERACTION
    def interaction(self, gate, var_list=None):
        variables = var_list if var_list else []
        return IBDDInteraction(gate, variables)

    def gate(self, token):
        return str(token)

    def var_list(self, *args):
        return list(str(arg) for arg in args)

    # EXPRESIONES
    def expr(self, expr):
        return expr

    def or_expr(self, left, *args):
        if not args:
            return left

        result = left
        for i in range(0, len(args), 2):
            right = args[i + 1]
            result = IBDDExpression('disjunction', '||', [result, right])

        return result

    def and_expr(self, left, *args):
        if not args:
            return left

        result = left
        for i in range(0, len(args), 2):
            op = args[i]
            right = args[i + 1]
            result = IBDDExpression('conjunction', '∧', [result, right])

        return result

    def not_expr(self, *args):
        if len(args) == 2:  # "!" comparison
            return IBDDExpression('not', '!', [args[1]])
        return args[0]  # comparison

    def comparison(self, left, op=None, right=None):
        if op is None or right is None:
            return left
        return IBDDExpression('comparison', str(op), [left, right])

    def op(self, op):
        return str(op)

    # Operaciones matemáticas
    def sum(self, left, *args):
        if not args:
            return left

        result = left
        for i in range(0, len(args), 2):
            op = args[i]
            right = args[i + 1]
            if op == '+':
                result = IBDDExpression('sum', '+', [result, right])
            else:  # '-'
                result = IBDDExpression('subtraction', '-', [result, right])

        return result

    def product(self, left, *args):
        if not args:
            return left

        result = left
        for i in range(0, len(args), 2):
            op = args[i]
            right = args[i + 1]
            if op == '*':
                result = IBDDExpression('multiplication', '*', [result, right])
            elif op == '/':  # '/'
                result = IBDDExpression('division', '/', [result, right])
            else:  # '%'
                result = IBDDExpression('modulo', '%', [result, right])

        return result

    def power(self, base, exponent=None):
        if exponent is None:
            return base
        return IBDDExpression('power', '^', [base, exponent])

    def atom(self, value):
        return value

    def neg_number(self, number):
        return IBDDExpression('negative', '-', [number])

    # LITERALES
    def true_val(self, _):
        """El argumento _ es necesario aunque no se use"""
        return IBDDExpression('true', 'true')

    def false_val(self, _):
        """El argumento _ es necesario aunque no se use"""
        return IBDDExpression('false', 'false')

    def number(self, token):
        """El token es usado para obtener el valor"""
        return IBDDExpression('number', str(token))

    # LLAMADA A FUNCIÓN
    def func_call(self, name, args=None):
        if args is None:
            return IBDDExpression('function', str(name), [])
        return IBDDExpression('function', str(name), args if isinstance(args, list) else [args])

    def func_name(self, name):
        return str(name)

    def arg_list(self, *args):
        return list(args)

    # ACCESO A PROPIEDAD
    def prop_access(self, obj, prop):
        return IBDDExpression('property', f"{obj}.{prop}", [obj, prop])

    # ASIGNACIÓN
    def true_assignment(self, _):
        return []

    def assignment(self, value):
        return value

    def assignment_list(self, *assignments):
        return list(assignments)

    def assignment_expr(self, target, expr):
        if isinstance(target, IBDDExpression) and target.expr_type == 'property':
            # Acceso a propiedad como objetivo
            obj, prop = target.args
            return IBDDAssignment((obj, prop), expr)
        else:
            # Variable como objetivo
            return IBDDAssignment(str(target), expr)

    def assign_target(self, target):
        return target

    # VARIABLE
    def var(self, token):
        return IBDDExpression('variable', str(token))

    # TERMINALES
    def NL(self, nl):
        pass  # Ignorar saltos de línea


class IBDDParser:
    """Parser para IBDD"""

    def __init__(self, debug=False):
        self.parser = Lark(IBDD_GRAMMAR, start='start', parser='earley', debug=debug,
                           propagate_positions=True, ambiguity='resolve')
        self.transformer = IBDDTransformer()

    def parse_text(self, text: str) -> IBDDScenario:
        """Parsea un texto IBDD y devuelve un IBDDScenario"""
        try:
            # Preprocesar el texto
            # text = self._preprocess_text(text)

            # Parsear
            tree = self.parser.parse(text)

            # Transformar
            result = self.transformer.transform(tree)

            return result

        except Exception as e:
            import traceback
            print(f"Error al parsear IBDD: {e}")
            traceback.print_exc()
            raise

    def _preprocess_text(self, text: str) -> str:
        """Preprocesamiento más agresivo para normalizar espacios"""
        # Primero normaliza los saltos de línea
        # text = text.replace("\\n", "\n")

        # Normaliza espacios múltiples a un solo espacio
        # text = re.sub(r'\s+', ' ', text)

        # Casos especiales para asegurar un espacio entre tokens clave
        text = re.sub(r'GIVEN\s+', 'GIVEN ', text)
        text = re.sub(r'\s+\[', ' [', text)
        text = re.sub(r'\]\s+', '] ', text)
        text = re.sub(r'WHEN\s+', 'WHEN ', text)
        text = re.sub(r'THEN\s+', 'THEN ', text)

        # Divide en líneas y las normaliza
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line:  # solo agrega líneas no vacías
                lines.append(line)

        return '\n'.join(lines)

    def validate(self, text: str) -> bool:
        """Valida si el texto es IBDD válido"""
        try:
            self.parse_text(text)
            return True
        except Exception as e:
            print(f"Error de validación: {e}")
            return False


def parse_ibdd(text: str) -> IBDDScenario:
    """
    Parsea un texto IBDD y devuelve un escenario IBDD
    """
    parser = IBDDParser(debug=False)
    return parser.parse_text(text)


def validate_ibdd_cases(json_file_path: str, output_file: Optional[str] = None) -> None:
    """
    Valida casos IBDD de un archivo JSON y genera un informe

    Args:
        json_file_path: Ruta al archivo JSON con los casos IBDD
        output_file: Ruta al archivo de salida (opcional, si no se proporciona se imprime por consola)
    """
    try:
        # Cargar los datos JSON
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Inicializar el parser
        parser = IBDDParser(debug=False)

        # Resultados
        results = []

        print(f"Validando {len(data)} casos IBDD...")

        # Validar cada caso
        for i, case in enumerate(data, 1):
            case_id = case.get('id', i)
            domain = case.get('domain', 'unknown')
            title = case.get('title', f'Case {case_id}')
            ibdd_text = case.get('ibdd_representation', '')

            # Si no hay representación IBDD, saltamos
            if not ibdd_text:
                print(f"Caso {case_id}: {title} - Sin representación IBDD")
                results.append({
                    'id': case_id,
                    'domain': domain,
                    'title': title,
                    'valid': False,
                    'error': 'Sin representación IBDD'
                })
                continue

            ibdd_text = ibdd_text.replace('\\n', '\n')

            try:
                # Intentar parsear
                scenario = parser.parse_text(ibdd_text)
                valid = True
                error = None
                parsed_result = str(scenario)

                print(f"Caso {case_id}: {title} - Válido ✓")

            except Exception as e:
                valid = False
                error = str(e)
                parsed_result = None

                print(f"Caso {case_id}: {title} - Inválido ✗ - Error: {error}")
                # si uno falla parar la ejecucion
                break

            # Almacenar resultados
            results.append({
                'id': case_id,
                'domain': domain,
                'title': title,
                'valid': valid,
                'error': error,
                'parsed_result': parsed_result
            })

        # Resumen
        valid_count = sum(1 for r in results if r['valid'])
        if len(results) > 0:
            print(f"\nResumen: {valid_count} de {len(results)} casos válidos ({valid_count / len(results) * 100:.1f}%)")

        # Generar salida
        if output_file:
            # Guardar como JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Resultados guardados en {output_file}")

            # También generar un CSV
            csv_file = output_file.replace('.json', '.csv')
            df = pd.DataFrame(results)
            df.to_csv(csv_file, index=False)
            print(f"Resultados en CSV guardados en {csv_file}")
        else:
            # Imprimir resumen detallado por consola
            print("\nResultados detallados:")
            for res in results:
                status = "Válido ✓" if res['valid'] else f"Inválido ✗ - {res['error']}"
                print(f"{res['id']}: {res['title']} - {status}")

    except Exception as e:
        print(f"Error al procesar el archivo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Verificar argumentos
    if len(sys.argv) < 2:
        print("Uso: python ibdd_validator.py <archivo_json> [archivo_salida]")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    validate_ibdd_cases(json_file, output_file)