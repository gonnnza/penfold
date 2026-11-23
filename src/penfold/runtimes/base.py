"""Contrato de runtime de agentes.

El motor solo conoce este contrato: no sabe si el trabajo lo hace un mock, una
CLI externa o un modelo local. Cada integración concreta valida sus propios
parámetros, mensajes de autenticación y formatos de salida.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from penfold.agents.models import AgentDefinition


class RuntimeContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    node_id: str
    agent: AgentDefinition | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    workspace: Path
    timeout: int = 300
    options: dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1
    cancel_event: asyncio.Event | None = None


class RuntimeResult(BaseModel):
    output: dict[str, Any]
    logs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


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
