"""Contrato de runtime de agentes.

El motor solo conoce este contrato: no sabe si el trabajo lo hace un mock, una
CLI externa o un modelo local. Cada integración concreta valida sus propios
parámetros, mensajes de autenticación y formatos de salida.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from penfold.models.runtime import RuntimeContext, RuntimeResult

__all__ = ["AgentRuntime", "RuntimeContext", "RuntimeResult"]


class AgentRuntime(ABC):
    """Interfaz estable, independiente de proveedores y de LangGraph."""

    name: str = "base"
    simulated: bool = False

    @abstractmethod
    async def execute(self, context: RuntimeContext) -> RuntimeResult:
        """Ejecuta la unidad de trabajo y devuelve una salida estructurada."""

    async def validate(self) -> None:
        """Comprueba que la configuración del runtime sea válida."""

    async def healthcheck(self) -> bool:
        """Comprueba que el runtime esté disponible."""
        return True
