"""Tests del editor de workflows por terminal."""

import pytest

from penfold.errors import ValidationError
from penfold.services.workflow_editor import WorkflowEditor


def test_crear_workflow_con_nodos_base(components) -> None:
    *_, workflows, _, _, _ = components
    editor = WorkflowEditor(workflows)

    definition = editor.create("demo", name="Demo")

    assert [node.id for node in definition.nodes] == ["start", "end"]
    assert [(edge.source, edge.target) for edge in definition.edges] == [("start", "end")]
    assert workflows.get("demo").metadata.name == "Demo"


def test_anadir_nodos_conectar_y_configurar(components) -> None:
    *_, workflows, _, _, _ = components
    editor = WorkflowEditor(workflows)
    editor.create("demo")

    editor.add_node("demo", "analyst", "agent", label="Analista", agent="product-analyst")
    editor.connect("demo", "start", "analyst")
    editor.connect("demo", "analyst", "end")
    editor.set_config("demo", "analyst", "inputs", {"request": "$inputs.request"})
    editor.add_input("demo", "request", input_type="string")

    definition = workflows.get("demo")
    analyst = next(node for node in definition.nodes if node.id == "analyst")
    assert analyst.config["inputs"] == {"request": "$inputs.request"}
    assert definition.inputs[0].id == "request"
    assert len(definition.edges) == 3


def test_borrar_nodo_quita_sus_aristas(components) -> None:
    *_, workflows, _, _, _ = components
    editor = WorkflowEditor(workflows)
    editor.create("demo")
    editor.add_node("demo", "analyst", "agent", agent="product-analyst")
    editor.connect("demo", "start", "analyst")

    definition = editor.remove_node("demo", "analyst")

    assert [node.id for node in definition.nodes] == ["start", "end"]
    assert all(edge.source != "analyst" and edge.target != "analyst" for edge in definition.edges)


def test_rechaza_ids_duplicados_y_tipos_invalidos(components) -> None:
    *_, workflows, _, _, _ = components
    editor = WorkflowEditor(workflows)
    editor.create("demo")

    with pytest.raises(ValidationError):
        editor.add_node("demo", "start", "input")
    with pytest.raises(ValidationError):
        editor.add_node("demo", "other", "teleporter")
