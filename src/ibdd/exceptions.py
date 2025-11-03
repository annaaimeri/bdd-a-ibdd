"""
Excepciones personalizadas para el módulo IBDD
"""


class IBDDException(Exception):
    """Excepción base para errores IBDD"""
    pass


class IBDDParseException(IBDDException):
    """Excepción lanzada cuando falla el parsing de IBDD"""
    pass


class IBDDValidationException(IBDDException):
    """Excepción lanzada cuando la validación de IBDD falla"""
    pass


class IBDDTransformException(IBDDException):
    """Excepción lanzada cuando la transformación de IBDD falla"""
    pass