"""
Parser principal para IBDD
Contiene la lógica de parsing reutilizable
"""
import re
from lark import Lark
from .models import IBDDScenario, IBDDExpression, IBDDInteraction, IBDDSwitch
from .transformer import IBDDTransformer
from .grammar import IBDD_GRAMMAR
from .exceptions import IBDDParseException


class IBDDParser:
    """Parser principal para IBDD"""

    def __init__(self, debug=False):
        """
        Inicializa el parser IBDD

        Args:
            debug: Si True, habilita modo debug en Lark
        """
        try:
            self.parser = Lark(
                IBDD_GRAMMAR,
                start='start',
                parser='earley',
                debug=debug,
                propagate_positions=True,
                ambiguity='resolve'
            )
            self.transformer = IBDDTransformer()
        except Exception as e:
            raise IBDDParseException(f"Error al inicializar parser: {e}")

    def parse_text(self, text: str) -> IBDDScenario:
        """
        Parsea un texto IBDD y devuelve un IBDDScenario

        Args:
            text: Texto IBDD a parsear

        Returns:
            IBDDScenario: Escenario IBDD parseado

        Raises:
            IBDDParseException: Si hay error en el parsing
        """
        try:
            # Preprocesar el texto
            text = self._preprocess_text(text)

            # Parsear
            tree = self.parser.parse(text)

            # Transformar
            result = self.transformer.transform(tree)

            return result

        except Exception as e:
            raise IBDDParseException(f"Error al parsear IBDD: {e}")

    def validate(self, text: str) -> bool:
        """
        Valida si el texto es IBDD válido

        Args:
            text: Texto IBDD a validar

        Returns:
            bool: True si es válido, False si no
        """
        try:
            self.parse_text(text)
            return True
        except Exception:
            return False

    @staticmethod
    def _preprocess_text(text: str) -> str:
        """
        Preprocesamiento de texto IBDD

        Args:
            text: Texto a preprocesar

        Returns:
            str: Texto preprocesado
        """
        # Reemplazar saltos de línea escapados
        text = text.replace('\\n', '\n')

        # Normalizar y agregar saltos de línea entre secciones
        text = re.sub(r'(GIVEN|WHEN|THEN)', r'\n\1', text)

        # Separar partes del switch con saltos de línea si no los hay
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Si es un switch, verificar si necesita ser reformateado
            if re.match(r'[!?][a-zA-Z][a-zA-Z0-9_]*', line):
                # Es un gate, formatear como switch
                parts = re.split(r'(\s+)', line, 2)
                if len(parts) > 2:
                    # Separar en líneas
                    gate = parts[0]
                    rest = parts[2] if len(parts) > 2 else ""
                    lines.append(gate)
                    if rest:
                        lines.append(rest)
                else:
                    lines.append(line)
            else:
                lines.append(line)

        # Normalizar espacios en blanco y operadores
        text = '\n'.join(lines)
        text = re.sub(r'\s+', ' ', text)

        # Asegurar espacios adecuados alrededor de tokens clave
        text = re.sub(r'GIVEN\s+', 'GIVEN ', text)
        text = re.sub(r'WHEN\s+', 'WHEN ', text)
        text = re.sub(r'THEN\s+', 'THEN ', text)
        text = re.sub(r'\s+\[', ' [', text)
        text = re.sub(r']\s+', '] ', text)

        # Dividir en líneas y normalizar de nuevo
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line:
                lines.append(line)

        return '\n'.join(lines)

    @staticmethod
    def parse_ibdd_fallback(text: str) -> IBDDScenario:
        """
        Parser alternativo para casos muy difíciles

        Args:
            text: Texto IBDD a parsear

        Returns:
            IBDDScenario: Escenario IBDD parseado (fallback)
        """
        scenario = IBDDScenario()

        # Normalizar el texto
        text = text.replace('\\n', '\n').strip()
        text = re.sub(r'\s+', ' ', text)

        # Extraer secciones principales
        given_match = re.search(r'GIVEN\s+(.*?)\s*\[(.*?)]\s*WHEN', text, re.DOTALL)
        when_then_text = text.split('WHEN', 1)[1] if 'WHEN' in text else ""
        when_then_parts = when_then_text.split('THEN', 1)

        when_text = when_then_parts[0].strip() if len(when_then_parts) > 0 else ""
        then_text = when_then_parts[1].strip() if len(when_then_parts) > 1 else ""

        # Procesar GIVEN
        if given_match:
            vars_text = given_match.group(1).strip()
            precond_text = given_match.group(2).strip()

            # Procesar variables
            if vars_text:
                vars_list = [v.strip() for v in vars_text.split(',')]
                scenario.local_vars = [v for v in vars_list if v]

            # Procesar precondición
            if precond_text:
                scenario.precondition = IBDDExpression('variable', precond_text)

        # Procesar WHEN (switches)
        if when_text:
            # Extraer switches (simplificado)
            switch_texts = re.findall(r'([?!][a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_,]+)?)', when_text)
            for switch_text in switch_texts:
                gate_parts = switch_text.split('.', 1)
                gate = gate_parts[0]
                variables = []
                if len(gate_parts) > 1:
                    variables = [v.strip() for v in gate_parts[1].split(',')]

                interaction = IBDDInteraction(gate, variables)
                scenario.when_switches.append(IBDDSwitch(interaction))

        # Procesar THEN
        then_match = re.search(r'\[(.*?)]', then_text)
        if then_match:
            postcond_text = then_match.group(1).strip()
            scenario.postcondition = IBDDExpression('variable', postcond_text)

        return scenario