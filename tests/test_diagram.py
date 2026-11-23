"""Tests del renderizador de diagramas en terminal."""

from rich.console import Console

from penfold.models.workflow import (
    EdgeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowMetadata,
    WorkflowNode,
)
from penfold.tui.diagram import _levels, build_diagram


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        metadata=WorkflowMetadata(id="demo", name="Demo diagram"),
        nodes=[
            WorkflowNode(id="start", type="input", label="Entrada"),
            WorkflowNode(id="analyst", type="agent", label="Analista"),
            WorkflowNode(id="check", type="condition", label="¿Pasa?"),
            WorkflowNode(id="end", type="output", label="Resultado"),
        ],
        edges=[
            WorkflowEdge(id="e1", source="start", target="analyst"),
            WorkflowEdge(id="e2", source="analyst", target="check"),
            WorkflowEdge(id="e3", source="check", target="end", source_handle="pass", label="PASS"),
            WorkflowEdge(
                id="e4",
                source="check",
                target="analyst",
                source_handle="fail",
                label="FAIL",
                config=EdgeConfig(loop=True, max_iterations=3),
            ),
        ],
    )


def _render(workflow: WorkflowDefinition) -> str:
    console = Console(record=True, width=80)
    console.print(build_diagram(workflow))
    return console.export_text()


def test_diagrama_muestra_nodos_y_aristas() -> None:
    text = _render(_workflow())
    assert "Workflow: Demo diagram" in text
    assert "INPUT" in text
    assert "AGENTE" in text
    assert "CONDI" in text
    assert "OUTPUT" in text
    assert "▶" in text


def test_diagrama_respeta_orden_topologico() -> None:
    level = _levels(_workflow())
    assert level["start"] < level["analyst"] < level["check"] < level["end"]


def test_diagrama_muestra_bucles() -> None:
    text = _render(_workflow())
    assert "Bucles / retornos" in text
    assert "FAIL" in text
    assert "max 3" in text
