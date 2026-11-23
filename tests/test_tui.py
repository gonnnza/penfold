"""Tests del dashboard de terminal (solo render, sin prompts interactivos)."""

from rich.console import Console

from penfold.models.execution import NodeState, NodeStatus, RunDetail, RunEvent, RunStatus
from penfold.services.workflow_templates import default_workflows
from penfold.tui.dashboard import build_run_view, render_workflows_table


def _render(renderable: object) -> str:
    console = Console(record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_render_workflows_table() -> None:
    text = _render(render_workflows_table(default_workflows()))
    assert "simple" in text
    assert "Workflows" in text


def test_build_run_view_muestra_estados_y_eventos() -> None:
    workflow = default_workflows()[0]
    run = RunDetail(
        id="abc123",
        workflow_id=workflow.metadata.id,
        status=RunStatus.RUNNING,
        inputs={"feature_description": "demo"},
        nodes=[
            NodeState(node_id=node.id, status=NodeStatus.SUCCEEDED) for node in workflow.nodes[:-1]
        ]
        + [NodeState(node_id=workflow.nodes[-1].id, status=NodeStatus.RUNNING)],
    )
    event = RunEvent(run_id=run.id, seq=1, type="node_started", message="Nodo iniciado")

    text = _render(build_run_view(run, workflow, [event]))

    assert "abc123" in text
    assert "RUNNING" in text
    assert "Nodo iniciado" in text
    assert "succeeded" in text
