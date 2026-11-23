"""Resolución declarativa de contexto entre nodos (sin evaluar expresiones).

Soporta solamente tres formas: ``$inputs.<id>``, ``$nodes.<id>.output[.<path>]``
y ``$nodes.<id>.status|error``. Cualquier otro string es un literal.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from penfold.errors import ContextResolutionError


class ContextResolver:
    def __init__(
        self,
        run_inputs: Mapping[str, Any],
        node_outputs: Mapping[str, Any],
        node_statuses: Mapping[str, str],
    ) -> None:
        self.run_inputs = dict(run_inputs)
        self.node_outputs = dict(node_outputs)
        self.node_statuses = dict(node_statuses)

    def resolve_mapping(self, mapping: Mapping[str, Any] | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in (mapping or {}).items():
            result[key] = self.resolve(value)
        return result

    def resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        return value

    def _resolve_string(self, value: str) -> Any:
        if not value.startswith("$"):
            return value
        parts = value.split(".")
        if len(parts) == 2 and parts[0] == "$inputs":
            name = parts[1]
            if name not in self.run_inputs:
                raise ContextResolutionError(f"Entrada de workflow no disponible: {value}")
            return self.run_inputs[name]
        if len(parts) < 3 or parts[0] != "$nodes":
            raise ContextResolutionError(f"Referencia de contexto mal formada: {value!r}")
        node_id, field, *path = parts[1:]
        if field == "status":
            if node_id not in self.node_statuses:
                raise ContextResolutionError(f"Nodo no disponible en la referencia: {value}")
            return self.node_statuses[node_id]
        if field == "error":
            return self.node_statuses.get(f"{node_id}:error")
        if field != "output":
            raise ContextResolutionError(
                f"Campo de nodo desconocido en {value!r} (se admite output, status, error)"
            )
        if node_id not in self.node_outputs:
            raise ContextResolutionError(f"El nodo {node_id!r} aún no produjo salida ({value}).")
        current: Any = self.node_outputs[node_id]
        for segment in path:
            if isinstance(current, Mapping):
                if segment not in current:
                    raise ContextResolutionError(
                        f"La salida de {node_id!r} no contiene el campo {segment!r} ({value})."
                    )
                current = current[segment]
            elif isinstance(current, list) and segment.isdigit():
                index = int(segment)
                if index >= len(current):
                    raise ContextResolutionError(f"Índice fuera de rango en {value}.")
                current = current[index]
            else:
                raise ContextResolutionError(f"No se puede recorrer {value} en {segment!r}.")
        return current
