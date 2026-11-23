"""Validación estática de workflows: esquema, grafo, referencias y ciclos.

El motor confía en esta validación antes de ejecutar. Las posiciones del canvas
nunca influyen en el orden de ejecución.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from penfold.workflows.models import WorkflowDefinition, WorkflowEdge

VALID_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "exists"}


class ValidationIssue(BaseModel):
    path: str
    message: str
    severity: str = "error"


def _error(path: str, message: str) -> ValidationIssue:
    return ValidationIssue(path=path, message=message, severity="error")


def _warning(path: str, message: str) -> ValidationIssue:
    return ValidationIssue(path=path, message=message, severity="warning")


def _walk(value: Any):
    """Recorre recursivamente dicts y listas devolviendo strings."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def cyclic_edges(workflow: WorkflowDefinition) -> set[str]:
    """Devuelve los IDs de aristas que forman parte de algún ciclo (DFS con colores)."""
    adjacency: dict[str, list[WorkflowEdge]] = {node.id: [] for node in workflow.nodes}
    for edge in workflow.edges:
        adjacency.setdefault(edge.source, []).append(edge)

    color: dict[str, int] = {node_id: 0 for node_id in adjacency}
    stack_edges: list[str] = []
    found: set[str] = set()

    def visit(node_id: str) -> None:
        color[node_id] = 1
        for edge in adjacency.get(node_id, []):
            target = edge.target
            if target not in color:
                continue
            if color[target] == 0:
                stack_edges.append(edge.id)
                visit(target)
                stack_edges.pop()
            elif color[target] == 1:
                # Arista de retroceso: desde el objetivo en la pila hasta aquí.
                if edge.id not in stack_edges:
                    found.add(edge.id)
                if edge.id in stack_edges:
                    found.update(stack_edges[stack_edges.index(edge.id) :])
                else:
                    found.add(edge.id)
        color[node_id] = 2

    for node_id in list(color):
        if color[node_id] == 0:
            visit(node_id)
    return found


def validate_workflow(
    workflow: WorkflowDefinition,
    *,
    agent_ids: set[str] | None = None,
    max_iterations_limit: int = 10,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    node_ids = {node.id for node in workflow.nodes}
    input_ids = {item.id for item in workflow.inputs}
    edge_ids: set[str] = set()

    if not workflow.nodes:
        issues.append(_error("nodes", "El workflow no tiene nodos."))
    inputs = [node for node in workflow.nodes if node.type == "input"]
    outputs = [node for node in workflow.nodes if node.type == "output"]
    if not inputs:
        issues.append(_error("nodes", "Debe existir al menos un nodo de tipo input."))
    if not outputs:
        issues.append(_error("nodes", "Debe existir al menos un nodo de tipo output."))

    for edge in workflow.edges:
        if edge.id in edge_ids:
            issues.append(_error(f"edges.{edge.id}", f"ID de arista duplicado: {edge.id}"))
        edge_ids.add(edge.id)
        if edge.source not in node_ids:
            issues.append(
                _error(f"edges.{edge.id}.source", f"Nodo source inexistente: {edge.source}")
            )
        if edge.target not in node_ids:
            issues.append(
                _error(f"edges.{edge.id}.target", f"Nodo target inexistente: {edge.target}")
            )
        if edge.source == edge.target:
            issues.append(_error(f"edges.{edge.id}", "Una arista no puede conectarse a sí misma."))
        if (
            edge.config.max_iterations is not None
            and edge.config.max_iterations > max_iterations_limit
        ):
            issues.append(
                _error(
                    f"edges.{edge.id}.config.max_iterations",
                    f"max_iterations no puede superar {max_iterations_limit}.",
                )
            )

    incoming: dict[str, list[WorkflowEdge]] = {node_id: [] for node_id in node_ids}
    outgoing: dict[str, list[WorkflowEdge]] = {node_id: [] for node_id in node_ids}
    for edge in workflow.edges:
        if edge.source in incoming and edge.target in node_ids:
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)

    pairs: set[tuple[str, str, str]] = set()
    for edge in workflow.edges:
        key = (edge.source, edge.target, edge.source_handle)
        if key in pairs:
            issues.append(
                _error(
                    f"edges.{edge.id}",
                    f"Conexión duplicada {edge.source} -> {edge.target} ({edge.source_handle}).",
                )
            )
        pairs.add(key)

    for node in workflow.nodes:
        base = f"nodes.{node.id}"
        if node.type == "input":
            if incoming.get(node.id):
                issues.append(_error(base, "Un nodo input no puede tener aristas entrantes."))
        elif not incoming.get(node.id):
            issues.append(_error(base, f"Nodo desconectado: {node.id} no tiene aristas entrantes."))
        if node.type != "output" and not outgoing.get(node.id):
            issues.append(_warning(base, f"El nodo {node.id} no tiene aristas salientes."))

        if node.type == "agent":
            if not node.agent:
                issues.append(_error(f"{base}.agent", "El nodo agent requiere el campo 'agent'."))
            elif agent_ids is not None and node.agent not in agent_ids:
                issues.append(_error(f"{base}.agent", f"Agente inexistente: {node.agent!r}."))
        if node.type == "command":
            command = node.config.get("command")
            if not isinstance(command, str) or not command.strip():
                issues.append(
                    _error(f"{base}.config.command", "El nodo command requiere un comando.")
                )
        if node.type == "condition":
            expression = node.config.get("expression")
            if not isinstance(expression, dict):
                issues.append(
                    _error(f"{base}.config.expression", "El nodo condition requiere 'expression'.")
                )
            else:
                for key in ("field", "op", "value"):
                    if key not in expression:
                        issues.append(
                            _error(
                                f"{base}.config.expression.{key}", f"Falta '{key}' en la condición."
                            )
                        )
                op = expression.get("op")
                if op is not None and op not in VALID_OPS:
                    issues.append(
                        _error(f"{base}.config.expression.op", f"Operador inválido: {op!r}.")
                    )
            handles = {edge.source_handle for edge in outgoing.get(node.id, [])}
            if not handles:
                issues.append(_error(base, "La condición requiere ramas de salida pass/fail."))
            elif handles == {"pass"} or handles == {"fail"}:
                issues.append(
                    _warning(base, "La condición solo define una rama; la otra se omitirá.")
                )
            for edge in outgoing.get(node.id, []):
                if edge.source_handle == "default":
                    issues.append(
                        _warning(
                            f"edges.{edge.id}.source_handle",
                            "Las aristas de una condición deberían usar source_handle pass o fail.",
                        )
                    )

        for value in _walk(node.config):
            if not isinstance(value, str) or not value.startswith("$"):
                continue
            parts = value.split(".")
            if parts[0] == "$inputs" and len(parts) == 2:
                if parts[1] not in input_ids:
                    issues.append(
                        _error(f"{base}.config", f"Entrada de workflow inexistente: {value}.")
                    )
            elif parts[0] == "$nodes" and len(parts) >= 3:
                ref = parts[1]
                if ref not in node_ids:
                    issues.append(
                        _error(f"{base}.config", f"Referencia de nodo inexistente: {value}.")
                    )
            elif parts[0] in {"$inputs", "$nodes"}:
                issues.append(_error(f"{base}.config", f"Referencia mal formada: {value}."))

    cycles = cyclic_edges(workflow)
    for edge in workflow.edges:
        if edge.id not in cycles:
            continue
        if not edge.config.loop and edge.config.max_iterations is None:
            issues.append(
                _error(
                    f"edges.{edge.id}",
                    "Esta arista forma un ciclo: declara config.loop: true o "
                    "config.max_iterations para limitar las iteraciones.",
                )
            )

    # Nodos inalcanzables desde cualquier input.
    reachable: set[str] = set()
    frontier = [node.id for node in inputs]
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(edge.target for edge in outgoing.get(current, []))
    for node in workflow.nodes:
        if node.id not in reachable:
            issues.append(
                _warning(f"nodes.{node.id}", f"Nodo {node.id} no es alcanzable desde un input.")
            )

    return issues
