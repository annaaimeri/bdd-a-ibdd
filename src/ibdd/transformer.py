"""
Transformer para convertir el árbol de parsing Lark en objetos IBDD
"""
from lark import Transformer, v_args
from .models import (
    IBDDExpression, IBDDInteraction, IBDDAssignment,
    IBDDSwitch, IBDDScenario
)


@v_args(inline=False)
class IBDDTransformer(Transformer):
    """Transforma el árbol de parsing a objetos IBDD"""

    # Estructura principal
    @staticmethod
    def scenario(children):
        scenario = IBDDScenario()

        if children and len(children) >= 1:  # GIVEN
            given_result = children[0]
            if given_result and len(given_result) == 2:
                scenario.local_vars = given_result[0] or []
                scenario.precondition = given_result[1] if given_result[1] else IBDDExpression('true', 'true')

        if children and len(children) >= 2:  # WHEN
            when_result = children[1]
            scenario.when_switches = when_result or []

        if children and len(children) >= 3:  # THEN
            then_result = children[2]
            if then_result and len(then_result) == 2:
                scenario.then_switches = then_result[0] or []
                scenario.postcondition = then_result[1] if then_result[1] else IBDDExpression('true', 'true')

        return scenario

    # GIVEN
    @staticmethod
    def given(children):
        vars_result = []
        guard_result = None

        for child in children:
            if isinstance(child, list):  # Es vars
                vars_result = child
            else:  # Es guard
                guard_result = child

        return vars_result, guard_result

    @staticmethod
    def vars(children):
        return [str(child) for child in children if child]

    # WHEN
    @staticmethod
    def when(children):
        return [child for child in children if child]

    # THEN
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

    # Guard (precondición/postcondición)
    @staticmethod
    def guard(children):
        if not children:
            return IBDDExpression('true', 'true')
        return children[0] if len(children) > 0 else IBDDExpression('true', 'true')

    # SWITCH
    @staticmethod
    def switch(children):
        if not children:
            return None

        interaction = None
        condition = IBDDExpression('true', 'true')  # Default
        assignments = []

        for child in children:
            if isinstance(child, IBDDInteraction):
                interaction = child
            elif isinstance(child, IBDDExpression):
                condition = child
            elif isinstance(child, list):
                assignments = child

        if not interaction:  # Debe haber una interacción para un switch válido
            return None

        return IBDDSwitch(interaction, condition, assignments)

    # INTERACTION
    @staticmethod
    def interaction(children):
        gate = None
        variables = []

        for child in children:
            if isinstance(child, str):  # Es gate
                gate = child
            elif isinstance(child, list):  # Es var_list
                variables = child

        return IBDDInteraction(gate or "", variables)

    @staticmethod
    def gate(children):
        return str(children[0]) if children else ""

    @staticmethod
    def var_list(children):
        return [str(child) for child in children if child]

    # EXPRESIONES
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

    # Operaciones matemáticas
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
                else:  # '-'
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
                else:  # '%'
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

    # LITERALES
    @staticmethod
    def true_val(self):
        return IBDDExpression('true', 'true')

    @staticmethod
    def false_val(self):
        return IBDDExpression('false', 'false')

    @staticmethod
    def number(children):
        return IBDDExpression('number', str(children[0])) if children else IBDDExpression('number', '0')

    # LLAMADA A FUNCIÓN
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

    # ACCESO A PROPIEDAD
    @staticmethod
    def prop_access(children):
        if not children or len(children) < 2:
            return IBDDExpression('variable', str(children[0]) if children else "")

        obj, prop = children[0], children[1]
        return IBDDExpression('property', f"{obj}.{prop}", [obj, prop])

    # ASIGNACIÓN
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

    # VARIABLE
    @staticmethod
    def var(children):
        return IBDDExpression('variable', str(children[0])) if children else IBDDExpression('variable', "")

    # TERMINALES
    @staticmethod
    def NL(self, children):
        pass