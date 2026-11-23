"""Edición de workflows desde la terminal.

Toda la lógica de mutación vive en el service; la CLI y la TUI solo presentan
el resultado. Cada cambio se valida y se persiste como YAML versionable.
"""

from __future__ import annotations

from typing import Any, get_args

from penfold.errors import ValidationError
from penfold.models.workflow import (
    EdgeConfig,
    Handle,
    NodeType,
    Position,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowNode,
)
from penfold.services.workflow_store import WorkflowStore


class WorkflowEditor:
    def __init__(self, store: WorkflowStore):
        self.store = store

    def _reload(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        """Revalida el objeto completo (detecta ids duplicados) antes de guardar."""
        data = workflow.model_dump(mode="json", exclude_none=True)
        saved = WorkflowDefinition.model_validate(data)
        self.store.save(saved)
        return saved

    def create(
        self, workflow_id: str, *, name: str | None = None, description: str = ""
    ) -> WorkflowDefinition:
        if self.store.exists(workflow_id):
            raise ValidationError(f"El workflow {workflow_id!r} ya existe.")
        workflow = WorkflowDefinition(
            metadata=WorkflowMetadata(
                id=workflow_id, name=name or workflow_id, description=description
            ),
            nodes=[
                WorkflowNode(
                    id="start", type="input", label="Entrada", position=Position(x=0, y=0)
                ),
                WorkflowNode(
                    id="end", type="output", label="Resultado", position=Position(x=240, y=0)
                ),
            ],
            edges=[WorkflowEdge(id="e1", source="start", target="end")],
        )
        return self._reload(workflow)

    def add_node(
        self,
        workflow_id: str,
        node_id: str,
        node_type: str,
        *,
        label: str | None = None,
        agent: str | None = None,
        description: str | None = None,
    ) -> WorkflowDefinition:
        if node_type not in get_args(NodeType):
            raise ValidationError(
                f"Tipo {node_type!r} no válido. Usa: {', '.join(get_args(NodeType))}."
            )
        workflow = self.store.get(workflow_id)
        if any(node.id == node_id for node in workflow.nodes):
            raise ValidationError(f"Ya existe el nodo {node_id!r}.")
        if node_type == "agent" and agent is None:
            raise ValidationError("Un nodo agent necesita --agent.")
        workflow.nodes.append(
            WorkflowNode(
                id=node_id,
                type=node_type,  # type: ignore[arg-type]
                label=label,
                agent=agent,
                description=description,
            )
        )
        return self._reload(workflow)

    def connect(
        self,
        workflow_id: str,
        source: str,
        target: str,
        *,
        handle: str = "default",
        label: str | None = None,
        loop: bool = False,
        max_iterations: int | None = None,
    ) -> WorkflowDefinition:
        if handle not in get_args(Handle):
            raise ValidationError(
                f"Handle {handle!r} no válido. Usa: {', '.join(get_args(Handle))}."
            )
        workflow = self.store.get(workflow_id)
        ids = {node.id for node in workflow.nodes}
        if source not in ids or target not in ids:
            raise ValidationError(f"Nodos inexistentes: {source!r} → {target!r}.")
        number = len(workflow.edges) + 1
        while f"e{number}" in {edge.id for edge in workflow.edges}:
            number += 1
        workflow.edges.append(
            WorkflowEdge(
                id=f"e{number}",
                source=source,
                target=target,
                source_handle=handle,  # type: ignore[arg-type]
                label=label,
                config=EdgeConfig(loop=loop, max_iterations=max_iterations),
            )
        )
        return self._reload(workflow)

    def set_config(
        self, workflow_id: str, node_id: str, key: str, value: Any
    ) -> WorkflowDefinition:
        workflow = self.store.get(workflow_id)
        node = next((node for node in workflow.nodes if node.id == node_id), None)
        if node is None:
            raise ValidationError(f"Nodo {node_id!r} no encontrado.")
        node.config[key] = value
        return self._reload(workflow)

    def add_input(
        self,
        workflow_id: str,
        input_id: str,
        *,
        input_type: str = "string",
        required: bool = True,
        default: Any = None,
    ) -> WorkflowDefinition:
        workflow = self.store.get(workflow_id)
        if any(item.id == input_id for item in workflow.inputs):
            raise ValidationError(f"Ya existe la entrada {input_id!r}.")
        workflow.inputs.append(
            WorkflowInput(id=input_id, type=input_type, required=required, default=default)
        )
        return self._reload(workflow)

    def remove_node(self, workflow_id: str, node_id: str) -> WorkflowDefinition:
        workflow = self.store.get(workflow_id)
        if not any(node.id == node_id for node in workflow.nodes):
            raise ValidationError(f"Nodo {node_id!r} no encontrado.")
        workflow.nodes = [node for node in workflow.nodes if node.id != node_id]
        workflow.edges = [
            edge for edge in workflow.edges if edge.source != node_id and edge.target != node_id
        ]
        return self._reload(workflow)

    def remove_edge(self, workflow_id: str, edge_id: str) -> WorkflowDefinition:
        workflow = self.store.get(workflow_id)
        if not any(edge.id == edge_id for edge in workflow.edges):
            raise ValidationError(f"Arista {edge_id!r} no encontrada.")
        workflow.edges = [edge for edge in workflow.edges if edge.id != edge_id]
        return self._reload(workflow)
