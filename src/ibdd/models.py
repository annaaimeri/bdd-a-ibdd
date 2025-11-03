"""
Modelos de datos para IBDD (dataclasses)
Contiene todas las estructuras de datos utilizadas en la representación IBDD
"""
from dataclasses import dataclass, field
from typing import List, Any, Union, Tuple


@dataclass
class IBDDExpression:
    """Expresión IBDD - representa cualquier expresión lógica o matemática"""
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
        else:
            return self.value


@dataclass
class IBDDInteraction:
    """Interacción IBDD - representa una interacción con un gate"""
    gate: str
    variables: List[str] = field(default_factory=list)

    def __repr__(self):
        if self.variables:
            return f"{self.gate}.{','.join(self.variables)}"
        return self.gate


@dataclass
class IBDDAssignment:
    """Asignación IBDD - asignación de valor a una variable"""
    target: Union[str, Tuple[str, str]]
    value: Any

    def __repr__(self):
        if isinstance(self.target, tuple):
            return f"{self.target[0]}.{self.target[1]} := {self.value}"
        else:
            return f"{self.target} := {self.value}"


@dataclass
class IBDDSwitch:
    """Switch IBDD - representa un switch con su interacción, condición y asignaciones"""
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
    """Escenario IBDD completo - estructura principal de un caso IBDD"""
    # GIVEN section
    local_vars: List[str] = field(default_factory=list)
    precondition: IBDDExpression = field(default_factory=lambda: IBDDExpression('true', 'true'))

    # WHEN section
    when_switches: List[IBDDSwitch] = field(default_factory=list)

    # THEN section
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