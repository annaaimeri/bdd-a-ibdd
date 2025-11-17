#!/usr/bin/env python3
"""
Parser IBDD que maneja correctamente todos los casos del dataset
"""
import re
from dataclasses import dataclass, field
from typing import List, Any, Union, Tuple, Optional
import sys
import json
import pandas as pd
import time

from lark import Lark, Transformer, v_args

# Gramática IBDD mejorada
IBDD_GRAMMAR = r"""
    // Estructura principal: GIVEN WHEN THEN
    ?start: scenario

    scenario: given when then

    // GIVEN section: variables locales y precondición
    given: "GIVEN" [vars] guard
    vars: var (COMMA var)*

    // WHEN section: una serie de switches
    when: "WHEN" switch+

    // THEN section: switches opcionales y postcondición
    then: "THEN" switch* guard

    // Switch: más flexible para manejar diferentes formatos
    switch: interaction (expr | assignment)*

    // Interacción
    interaction: gate (DOT var_list)?
    gate: /[!?][a-zA-Z][a-zA-Z0-9_]*/
    var_list: var (COMMA var)*

    // Guardián (condición)
    guard: LBRACKET expr RBRACKET

    // Expresión (condición o parte de asignación)
    expr: or_expr

    or_expr: and_expr (OR and_expr)*
    and_expr: not_expr ((AND | AND_SYMBOL) not_expr)*
    not_expr: (NOT | NOT_SYMBOL) not_expr | comparison

    // Comparación
    comparison: sum (op sum)?
    op: EQ | EQEQ | NEQ | LT | GT | LEQ | GEQ | GEQ_SYMBOL | LEQ_SYMBOL | NEQ_SYMBOL

    // Operaciones matemáticas
    sum: product ((PLUS|MINUS) product)*
    product: power ((STAR|SLASH|PERCENT) power)*
    power: atom (CIRCUMFLEX atom)?
    sqrt: SQRT atom

    // Átomo (unidad básica de expresión)
    atom: literal
        | var
        | func_call
        | prop_access
        | neg_number
        | LPAR expr RPAR

    // Número negativo
    neg_number: MINUS NUMBER

    // Valores literales
    literal: TRUE -> true_val
           | FALSE -> false_val
           | NUMBER -> number

    TRUE: "true"
    FALSE: "false"

    // Llamada a función
    func_call: func_name LPAR [arg_list] RPAR
    func_name: /[a-zA-Z][a-zA-Z0-9_]*/
    arg_list: expr (COMMA expr)*

    // Acceso a propiedad
    prop_access: var DOT var

    // Asignación
    assignment: TRUE -> true_assignment
              | assignment_list

    assignment_list: assignment_expr (COMMA assignment_expr)*
    assignment_expr: assign_target ASSIGN expr
    assign_target: var | prop_access

    // Variable
    var: /[A-Za-z][A-Za-z0-9_]*/

    // Terminales con nombres descriptivos
    LPAR: "("
    RPAR: ")"
    LBRACKET: "["
    RBRACKET: "]"
    COMMA: ","
    DOT: "."
    ASSIGN: ":="

    // Operadores lógicos
    OR: "||"
    AND: "&&"
    AND_SYMBOL: "∧"
    NOT: "!"
    NOT_SYMBOL: "¬"

    // Operadores de comparación
    EQ: "="
    EQEQ: "=="
    NEQ: "!="
    NEQ_SYMBOL: "≠"
    LT: "<"
    GT: ">"
    LEQ: "<="
    LEQ_SYMBOL: "≤"
    GEQ: ">="
    GEQ_SYMBOL: "≥"

    // Operadores matemáticos
    PLUS: "+"
    MINUS: "-"
    STAR: "*"
    SLASH: "/"
    PERCENT: "%"
    CIRCUMFLEX: "^"
    SQRT: "√"

    // Números
    NUMBER: /[0-9]+(\.[0-9]+)?/
    NL: /\r?\n/

    %import common.WS
    %ignore WS    
"""


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
        elif self.expr_type == 'sqrt':
            return f"√{self.args[0]}"
        elif self.expr_type == 'neg' or self.expr_type == 'not':
            return f"¬{self.args[0]}"
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
    condition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))
    assignments: List[IBDDAssignment] = field(default_factory=list)

    def __repr__(self):
        assignments_str = ", ".join(str(a) for a in self.assignments)
        if not assignments_str:
            assignments_str = "true"
        return f"{self.interaction}\n{self.condition}\n{assignments_str}"


@dataclass
class IBDDScenario:
    """Escenario IBDD completo"""
    local_vars: List[str] = field(default_factory=list)
    precondition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))
    when_switches: List[IBDDSwitch] = field(default_factory=list)
    then_switches: List[IBDDSwitch] = field(default_factory=list)
    postcondition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))

    def __repr__(self):
        result = [f"GIVEN {', '.join(self.local_vars) if self.local_vars else ''} [{self.precondition}]",
                  f"WHEN {len(self.when_switches)} switches"]

        if self.then_switches:
            result.append(f"THEN {len(self.then_switches)} switches [{self.postcondition}]")
        else:
            result.append(f"THEN [{self.postcondition}]")

        return "\n".join(result)


@v_args(inline=False)
class IBDDTransformer(Transformer):
    """Transforma el árbol de parsing a objetos IBDD"""

    @staticmethod
    def scenario(children):
        scenario = IBDDScenario()

        if children and len(children) >= 1:
            given_result = children[0]
            if given_result and len(given_result) == 2:
                scenario.local_vars = given_result[0] or []
                scenario.precondition = given_result[1] if given_result[1] else IBDDExpression('true', 'true')

        if children and len(children) >= 2:
            when_result = children[1]
            scenario.when_switches = when_result or []

        if children and len(children) >= 3:
            then_result = children[2]
            if then_result and len(then_result) == 2:
                scenario.then_switches = then_result[0] or []
                scenario.postcondition = then_result[1] if then_result[1] else IBDDExpression('true', 'true')

        return scenario

    @staticmethod
    def given(children):
        vars_result = []
        guard_result = None

        for child in children:
            if isinstance(child, list):
                vars_result = child
            else:
                guard_result = child

        return vars_result, guard_result

    @staticmethod
    def vars(children):
        return [str(child) for child in children if child]

    @staticmethod
    def when(children):
        return [child for child in children if child]

    @staticmethod
    def then(children):
        switches = []
        guard = None

        for child in children:
            if isinstance(child, IBDDSwitch):
                switches.append(child)
            else:
                guard = child

        return switches, guard

    @staticmethod
    def guard(children):
        if not children:
            return IBDDExpression('true', 'true')
        return children[0] if len(children) > 0 else IBDDExpression('true', 'true')

    @staticmethod
    def switch(children):
        if not children:
            return None

        interaction = None
        condition = IBDDExpression('true', 'true')
        assignments = []

        for child in children:
            if isinstance(child, IBDDInteraction):
                interaction = child
            elif isinstance(child, IBDDExpression):
                condition = child
            elif isinstance(child, list):
                assignments = child

        if not interaction:
            return None

        return IBDDSwitch(interaction, condition, assignments)

    @staticmethod
    def interaction(children):
        gate = None
        variables = []

        for child in children:
            if isinstance(child, str):
                gate = child
            elif isinstance(child, list):
                variables = child

        return IBDDInteraction(gate or "", variables)

    @staticmethod
    def gate(children):
        return str(children[0]) if children else ""

    @staticmethod
    def var_list(children):
        return [str(child) for child in children if child]

    @staticmethod
    def expr(children):
        return children[0] if children else IBDDExpression('true', 'true')

    @staticmethod
    def or_expr(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        result = children[0]
        for i in range(1, len(children), 2):
            if i + 1 < len(children):
                result = IBDDExpression('disjunction', '||', [result, children[i + 1]])

        return result

    @staticmethod
    def and_expr(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        result = children[0]
        for i in range(1, len(children), 2):
            if i + 1 < len(children):
                result = IBDDExpression('conjunction', '∧', [result, children[i + 1]])

        return result

    @staticmethod
    def not_expr(children):
        if not children:
            return IBDDExpression('true', 'true')
        if len(children) == 2 and str(children[0]) == '!':
            return IBDDExpression('not', '!', [children[1]])
        return children[0]

    @staticmethod
    def comparison(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        if len(children) >= 3:
            left, op, right = children[0], children[1], children[2]
            return IBDDExpression('comparison', str(op), [left, right])

        return children[0]

    @staticmethod
    def op(children):
        return str(children[0]) if children else "="

    @staticmethod
    def sum(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        result = children[0]
        for i in range(1, len(children), 2):
            if i + 1 < len(children):
                op = str(children[i])
                right = children[i + 1]
                if op == '+':
                    result = IBDDExpression('sum', '+', [result, right])
                else:
                    result = IBDDExpression('subtraction', '-', [result, right])

        return result

    @staticmethod
    def product(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        result = children[0]
        for i in range(1, len(children), 2):
            if i + 1 < len(children):
                op = str(children[i])
                right = children[i + 1]
                if op == '*':
                    result = IBDDExpression('multiplication', '*', [result, right])
                elif op == '/':
                    result = IBDDExpression('division', '/', [result, right])
                else:
                    result = IBDDExpression('modulo', '%', [result, right])

        return result

    @staticmethod
    def power(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        if len(children) == 1:
            return children[0]

        return IBDDExpression('power', '^', [children[0], children[1]])

    @staticmethod
    def sqrt(children):
        if not children or len(children) == 0:
            return IBDDExpression('number', '0')
        return IBDDExpression('sqrt', '√', [children[0]])

    @staticmethod
    def neg(children):
        if not children or len(children) == 0:
            return IBDDExpression('true', 'true')
        return IBDDExpression('not', '¬', [children[0]])

    @staticmethod
    def atom(children):
        return children[0] if children else IBDDExpression('true', 'true')

    @staticmethod
    def neg_number(children):
        return IBDDExpression('negative', '-', [children[1]]) if len(children) > 1 else IBDDExpression('number', '0')

    @staticmethod
    def true_val(children):
        return IBDDExpression('true', 'true')

    @staticmethod
    def false_val(children):
        return IBDDExpression('false', 'false')

    @staticmethod
    def number(children):
        return IBDDExpression('number', str(children[0])) if children else IBDDExpression('number', '0')

    @staticmethod
    def func_call(children):
        if not children:
            return IBDDExpression('function', "", [])

        name = children[0] if len(children) > 0 else ""
        args = children[1] if len(children) > 1 else []

        return IBDDExpression('function', str(name), args if isinstance(args, list) else [args])

    @staticmethod
    def func_name(children):
        return str(children[0]) if children else ""

    @staticmethod
    def arg_list(children):
        return list(children) if children else []

    @staticmethod
    def prop_access(children):
        if not children or len(children) < 2:
            return IBDDExpression('variable', str(children[0]) if children else "")

        obj, prop = children[0], children[1]
        return IBDDExpression('property', f"{obj}.{prop}", [obj, prop])

    @staticmethod
    def true_assignment():
        return []

    @staticmethod
    def assignment(children):
        if not children:
            return []
        return children[0]

    @staticmethod
    def assignment_list(children):
        return list(children) if children else []

    @staticmethod
    def assignment_expr(children):
        if not children or len(children) < 2:
            return IBDDAssignment("", IBDDExpression('true', 'true'))

        target, expr = children[0], children[1]

        if isinstance(target, IBDDExpression) and target.expr_type == 'property':
            obj, prop = target.args
            return IBDDAssignment((obj, prop), expr)
        else:
            return IBDDAssignment(str(target), expr)

    @staticmethod
    def assign_target(children):
        return children[0] if children else ""

    @staticmethod
    def var(children):
        return IBDDExpression('variable', str(children[0])) if children else IBDDExpression('variable', "")

    @staticmethod
    def NL(self, children):
        pass


class IBDDParser:
    """Parser para IBDD"""

    def __init__(self, debug=False):
        self.parser = Lark(IBDD_GRAMMAR, start='start', parser='earley', debug=debug,
                           propagate_positions=True, ambiguity='resolve')
        self.transformer = IBDDTransformer()

    def parse_text(self, text: str) -> IBDDScenario:
        """Parsea un texto IBDD y devuelve un IBDDScenario"""
        text = self._preprocess_text(text)
        tree = self.parser.parse(text)
        result = self.transformer.transform(tree)
        return result

    @staticmethod
    def _preprocess_text(text: str) -> str:
        """Preprocesamiento de texto IBDD"""
        text = text.replace('\\n', '\n')
        text = re.sub(r'(GIVEN|WHEN|THEN)', r'\n\1', text)
        text = re.sub(r'([!?][a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_,]+)?)\s*∧\s*([!?][a-zA-Z][a-zA-Z0-9_]*)',
                      r'\1\n\2', text)

        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            if re.match(r'[!?][a-zA-Z][a-zA-Z0-9_]*', line):
                parts = re.split(r'(\s+)', line)
                if len(parts) > 2:
                    gate = parts[0]
                    rest = parts[2] if len(parts) > 2 else ""
                    lines.append(gate)
                    if rest:
                        lines.append(rest)
                else:
                    lines.append(line)
            else:
                lines.append(line)

        text = '\n'.join(lines)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'GIVEN\s+', 'GIVEN ', text)
        text = re.sub(r'WHEN\s+', 'WHEN ', text)
        text = re.sub(r'THEN\s+', 'THEN ', text)
        text = re.sub(r'\s+\[', ' [', text)
        text = re.sub(r']\s+', '] ', text)

        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line:
                lines.append(line)

        return '\n'.join(lines)

    def validate(self, text: str) -> bool:
        """Valida si el texto es IBDD válido"""
        try:
            self.parse_text(text)
            return True
        except Exception:
            return False

    @staticmethod
    def parse_ibdd_fallback(text: str) -> IBDDScenario:
        """Parser alternativo para casos difíciles"""
        scenario = IBDDScenario()

        text = text.replace('\\n', '\n').strip()
        text = re.sub(r'\s+', ' ', text)

        given_match = re.search(r'GIVEN\s+(.*?)\s*\[(.*?)]\s*WHEN', text, re.DOTALL)
        when_then_text = text.split('WHEN', 1)[1] if 'WHEN' in text else ""
        when_then_parts = when_then_text.split('THEN', 1)

        when_text = when_then_parts[0].strip() if len(when_then_parts) > 0 else ""
        then_text = when_then_parts[1].strip() if len(when_then_parts) > 1 else ""

        if given_match:
            vars_text = given_match.group(1).strip()
            precond_text = given_match.group(2).strip()

            if vars_text:
                vars_list = [v.strip() for v in vars_text.split(',')]
                scenario.local_vars = [v for v in vars_list if v]

            if precond_text:
                scenario.precondition = IBDDExpression('variable', precond_text)

        if when_text:
            switch_texts = re.findall(r'([?!][a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_,]+)?)', when_text)
            for switch_text in switch_texts:
                gate_parts = switch_text.split('.', 1)
                gate = gate_parts[0]
                variables = []
                if len(gate_parts) > 1:
                    variables = [v.strip() for v in gate_parts[1].split(',')]

                interaction = IBDDInteraction(gate, variables)
                scenario.when_switches.append(IBDDSwitch(interaction))

        then_match = re.search(r'\[(.*?)]', then_text)
        if then_match:
            postcond_text = then_match.group(1).strip()
            scenario.postcondition = IBDDExpression('variable', postcond_text)

        return scenario


def parse_ibdd(text: str) -> IBDDScenario:
    """Parsea un texto IBDD y devuelve un escenario IBDD"""
    parser = IBDDParser(debug=False)
    try:
        return parser.parse_text(text)
    except Exception:
        print(f"Using fallback parser...")
        return parser.parse_ibdd_fallback(text)


def validate_ibdd_cases(json_file_path: str, output_file: Optional[str] = None) -> None:
    """
    Valida casos IBDD de un archivo JSON y genera un informe

    Args:
        json_file_path: Ruta al archivo JSON con los casos IBDD
        output_file: Ruta al archivo de salida (opcional)
    """
    try:
        print(f"Loading JSON file: {json_file_path}")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"Initializing IBDD parser...")
        parser = IBDDParser(debug=False)
        results = []

        print(f"Validating {len(data)} IBDD cases...\n")

        for i, case in enumerate(data, 1):
            case_id = case.get('id', i)
            domain = case.get('domain', 'unknown')
            title = case.get('title', f'Case {case_id}')
            ibdd_text = case.get('ibdd_representation', '')

            if not ibdd_text:
                print(f"\033[91m✗\033[0m Case {case_id}: {title} - No IBDD representation found")
                results.append({
                    'id': case_id,
                    'domain': domain,
                    'title': title,
                    'valid': False,
                    'error': 'No IBDD representation'
                })
                time.sleep(0.3)
                continue

            ibdd_text = ibdd_text.replace('\\n', '\n')

            try:
                scenario = parser.parse_text(ibdd_text)
                valid = True
                error = None
                parsed_result = str(scenario)
                print(f"✓ Case {case_id}: {title} - Valid")

            except Exception as e:
                valid = False
                error_message = str(e)
                parsed_result = None
                print(f"\033[91m✗ Case {case_id}: {title} - Invalid\033[0m")
                print(f"  Error: {error_message}")

                results.append({
                    'id': case_id,
                    'domain': domain,
                    'title': title,
                    'valid': valid,
                    'error': error_message,
                    'parsed_result': parsed_result
                })
                time.sleep(0.3)
                continue

            results.append({
                'id': case_id,
                'domain': domain,
                'title': title,
                'valid': valid,
                'error': error,
                'parsed_result': parsed_result
            })

            time.sleep(0.3)

        valid_count = sum(1 for r in results if r['valid'])
        if len(results) > 0:
            print(f"\nSummary: {valid_count} of {len(results)} valid cases ({valid_count / len(results) * 100:.1f}%)")

        if output_file:
            print(f"\nSaving results to: {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved successfully")

            csv_file = output_file.replace('.json', '.csv')
            print(f"Saving CSV to: {csv_file}")
            df = pd.DataFrame(results)
            df.to_csv(csv_file, index=False)
            print(f"CSV saved successfully")

    except Exception as e:
        print(f"\033[91mError processing file: {e}\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ibdd_parser.py <json_file> [output_file]")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    validate_ibdd_cases(json_file, output_file)