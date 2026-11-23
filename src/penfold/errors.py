"""Errores de dominio de Penfold.

Todas las excepciones esperadas derivan de ``PenfoldError`` para que la CLI y
la API puedan convertirlas en mensajes descriptivos y códigos de salida.
"""

from __future__ import annotations


class PenfoldError(Exception):
    """Error base de la aplicación."""


class ProjectError(PenfoldError):
    """Proyecto no inicializado o configuración inválida."""


class NotFoundError(PenfoldError):
    """Recurso no encontrado (workflow, agente, ejecución, artefacto)."""


class ValidationError(PenfoldError):
    """Definición inválida (workflow, agente, contrato de datos)."""


class ContextResolutionError(ValidationError):
    """Un mapeo declarativo no pudo resolverse."""


class ContractError(ValidationError):
    """La salida de un nodo no cumple su contrato."""


class ExecutionError(PenfoldError):
    """Fallo durante la ejecución de un nodo."""


class PermissionDeniedError(PenfoldError):
    """Acción no permitida por el modo de permisos configurado."""


class CancelledError(PenfoldError):
    """Ejecución cancelada por el usuario."""
