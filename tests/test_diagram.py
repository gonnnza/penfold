"""Tests del renderizador de diagramas en terminal."""

from rich.console import Console

from penfold.services.workflow_templates import default_workflows
from penfold.tui.diagram import _levels, build_diagram


def _render(workflow_id: str) -> str:
    workflow = next(w for w in default_workflows() if w.metadata.id == workflow_id)
    console = Console(record=True, width=80)
    console.print(build_diagram(workflow))
    return console.export_text()


def test_diagrama_simple_muestra_nodos_y_aristas() -> None:
    text = _render("simple")
    assert "Workflow: Simple demo" in text
    assert "INPUT" in text
    assert "AGENTE" in text
    assert "COMANDO" in text
    assert "OUTPUT" in text
    assert "▶" in text


def test_diagrama_respeta_orden_topologico() -> None:
    workflow = next(w for w in default_workflows() if w.metadata.id == "feature-development")
    level = _levels(workflow)
    assert level["start"] < level["analyst"] < level["developer"]
    assert level["developer"] < level["tests"] < level["check"] < level["output"]
    assert "CONDI" in _render("feature-development")


def test_diagrama_muestra_bucles() -> None:
    text = _render("feature-development")
    assert "Bucles / retornos" in text
    assert "FAIL" in text
    assert "max 3" in text
