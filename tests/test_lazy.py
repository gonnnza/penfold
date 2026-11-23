"""Tests de la interfaz full-screen (sin depender de un TTY real)."""

from rich.console import Console

from penfold.services.workflow_store import WorkflowStore
from penfold.tui.lazy import LazyDashboard


def _render(app: LazyDashboard) -> str:
    console = Console(record=True, width=100, height=40)
    console.print(app._compose())
    return console.export_text()


def test_interfaz_muestra_paneles_y_atajos(components) -> None:
    paths = components[0]
    app = LazyDashboard(paths)

    text = _render(app)

    assert "Workflows" in text
    assert "Atajos" in text
    assert "j/k" in text
    assert "Penfold" in text


def test_navegacion_y_cambio_de_vista(components) -> None:
    app = LazyDashboard(components[0])
    assert app.current is not None

    assert app._handle_key("j") is True
    assert app.selected == 1
    assert app._handle_key("k") is True
    assert app.selected == 0

    assert app._handle_key("r") is True
    assert app.right_mode == "runs"
    assert app._handle_key("d") is True
    assert app.right_mode == "diagram"
    assert app._handle_key("q") is False


def test_atajo_n_crea_workflow_con_entrada_inline(components) -> None:
    paths = components[0]
    app = LazyDashboard(paths)

    assert app._handle_key("n") is True
    assert app.prompt is not None
    for char in "nuevo":
        app._handle_key(char)
    assert app._handle_key("\r") is True

    assert WorkflowStore(paths).exists("nuevo")
    assert app.current is not None
    assert app.current.metadata.id == "nuevo"
