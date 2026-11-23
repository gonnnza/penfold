"""Tests del esquema YAML, validación de grafos y persistencia."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError as PydanticValidationError

from penfold.models.workflow import WorkflowDefinition
from penfold.services.validator import cyclic_edges, validate_workflow
from penfold.services.workflow_store import WorkflowStore
from penfold.services.workflow_templates import default_workflows


def _issues(workflow, **kwargs):
    return validate_workflow(workflow, **kwargs)


def test_default_workflows_are_valid() -> None:
    for workflow in default_workflows():
        assert [issue for issue in _issues(workflow) if issue.severity == "error"] == []


def test_duplicate_node_ids_rejected() -> None:
    raw = default_workflows()[0].model_dump(mode="json")
    raw["nodes"][1]["id"] = raw["nodes"][0]["id"]
    with pytest.raises(PydanticValidationError, match="ID duplicado"):
        WorkflowDefinition.model_validate(raw)


def test_unknown_agent_and_disconnected_node_are_errors() -> None:
    raw = default_workflows()[0].model_dump(mode="json")
    raw["nodes"][1]["agent"] = "no-existe"
    raw["nodes"].append(
        {
            "id": "orphan",
            "type": "command",
            "position": {"x": 0, "y": 0},
            "config": {"command": "echo hola"},
        }
    )
    workflow = WorkflowDefinition.model_validate(raw)
    messages = " ".join(issue.message for issue in _issues(workflow, agent_ids={"product-analyst"}))
    assert "Agente inexistente" in messages
    assert "Nodo desconectado" in messages


def test_cycle_without_limit_is_error() -> None:
    raw = default_workflows()[1].model_dump(mode="json")
    loop_edge = next(edge for edge in raw["edges"] if edge["source_handle"] == "fail")
    loop_edge["config"] = {}
    workflow = WorkflowDefinition.model_validate(raw)
    assert cyclic_edges(workflow)
    messages = " ".join(issue.message for issue in _issues(workflow))
    assert "ciclo" in messages.lower()


def test_bad_operator_and_unknown_reference_are_errors() -> None:
    raw = default_workflows()[1].model_dump(mode="json")
    condition = next(node for node in raw["nodes"] if node["type"] == "condition")
    condition["config"]["expression"]["op"] = "eval"
    condition["config"]["inputs"]["passed"] = "$nodes.no_existe.output.passed"
    messages = " ".join(issue.message for issue in _issues(WorkflowDefinition.model_validate(raw)))
    assert "Operador inválido" in messages
    assert "Referencia de nodo inexistente" in messages


def test_position_does_not_change_execution_order() -> None:
    raw = default_workflows()[0].model_dump(mode="json")
    a = WorkflowDefinition.model_validate(raw)
    moved = copy.deepcopy(raw)
    for node in moved["nodes"]:
        node["position"] = {"x": 9999 - node["position"]["x"], "y": 9999}
    b = WorkflowDefinition.model_validate(moved)
    assert [(edge.source, edge.target) for edge in a.edges] == [
        (edge.source, edge.target) for edge in b.edges
    ]


def test_workflow_store_roundtrip(project) -> None:
    store = WorkflowStore(project)
    workflow = store.get("simple")
    workflow.metadata.name = "Renombrado"
    store.save(workflow)
    assert store.get("simple").metadata.name == "Renombrado"
    assert (project.workflows_dir / "simple.yaml").is_file()
