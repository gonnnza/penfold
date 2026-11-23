"""Registro de runtimes disponibles."""

from __future__ import annotations

from collections.abc import Callable

from penfold.errors import ExecutionError
from penfold.runtimes.base import AgentRuntime
from penfold.runtimes.command import CommandRuntime
from penfold.runtimes.mock import MockRuntime

Factory = Callable[[], AgentRuntime]

_REGISTRY: dict[str, Factory] = {
    MockRuntime.name: MockRuntime,
    CommandRuntime.name: CommandRuntime,
}


def register_runtime(name: str, factory: Factory) -> None:
    """Registra (o reemplaza) un runtime. Útil para extensiones y tests."""
    _REGISTRY[name] = factory


def get_runtime(name: str) -> AgentRuntime:
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ExecutionError(
            f"Runtime {name!r} no registrado. Disponibles: {', '.join(sorted(_REGISTRY))}"
        )
    return factory()


def available_runtimes() -> list[str]:
    return sorted(_REGISTRY)
