"""Interfaz full-screen estilo lazygit/lazydocker.

PanelesLaterales, navegación con j/k y barra de atajos. Se activa solo en TTY;
con entrada redirigida se usa el dashboard clásico por prompts.
"""

from __future__ import annotations

import asyncio
import sys
import termios
import tty
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from penfold import __version__
from penfold.config.paths import ProjectPaths, find_project
from penfold.errors import PenfoldError
from penfold.models.workflow import WorkflowDefinition, WorkflowInput
from penfold.services.agent_store import AgentStore
from penfold.services.events import EventBus
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.workflow_store import WorkflowStore
from penfold.tui.diagram import build_diagram

console = Console()

KEY_HELP = (
    "[bold cyan]j/k[/bold cyan] navegar  "
    "[bold cyan]Enter[/bold cyan] ejecutar  "
    "[bold cyan]n[/bold cyan] nuevo  "
    "[bold cyan]d[/bold cyan] diagrama  "
    "[bold cyan]r[/bold cyan] runs  "
    "[bold cyan]f[/bold cyan] refrescar  "
    "[bold cyan]q[/bold cyan] salir"
)


def _read_key() -> str:
    """Lee una tecla sin esperar a Enter (modo raw temporal)."""
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x1b":
            key += sys.stdin.read(2)
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


class LazyDashboard:
    """Aplicación full-screen con paneles y atajos de una tecla."""

    def __init__(self, paths: ProjectPaths):
        config = paths.require_project()
        self.paths = paths
        self.agents = AgentStore(paths)
        self.workflows = WorkflowStore(paths)
        self.repository = RunRepository(paths.db_path)
        self.events = EventBus()
        self.manager = RunManager(
            paths, config, self.workflows, self.agents, self.repository, self.events
        )
        self.manager.recover_interrupted()

        self.definitions: list[WorkflowDefinition] = []
        self.runs: list[Any] = []
        self.selected = 0
        self.right_mode = "diagram"
        self.message = "Listo"
        self.active_run_id: str | None = None
        self.prompt: str | None = None
        self.buffer = ""
        self.on_submit: Callable[[str], None] | None = None
        self.pending_inputs: list[WorkflowInput] = []
        self.collected: dict[str, Any] = {}
        self._refresh()

    def _refresh(self) -> None:
        self.definitions = self.workflows.list()
        self.runs = self.manager.list(limit=20)
        if self.definitions:
            self.selected = min(self.selected, len(self.definitions) - 1)
        else:
            self.selected = 0

    @property
    def current(self) -> WorkflowDefinition | None:
        return self.definitions[self.selected] if self.definitions else None

    def _start_input(self, prompt: str, callback: Callable[[str], None]) -> None:
        self.prompt = prompt
        self.buffer = ""
        self.on_submit = callback

    def _move(self, delta: int) -> None:
        if self.definitions:
            self.selected = (self.selected + delta) % len(self.definitions)
            self.message = f"Seleccionado: {self.current.metadata.id if self.current else '-'}"

    def _begin_run(self) -> None:
        workflow = self.current
        if workflow is None:
            self.message = "No hay workflows"
            return
        self.pending_inputs = list(workflow.inputs)
        self.collected = {}
        self._next_input()

    def _next_input(self) -> None:
        if self.pending_inputs:
            declared = self.pending_inputs.pop(0)
            default = "" if declared.default is None else str(declared.default)
            self._start_input(
                f"{declared.id} ({declared.type}) [{default}]: ",
                lambda value, d=declared, v=default: self._collect(d.id, value or v),
            )
            return
        self._launch()

    def _collect(self, name: str, value: str) -> None:
        self.collected[name] = value
        self._next_input()

    def _launch(self) -> None:
        workflow = self.current
        if workflow is None:
            return
        try:
            run = asyncio.run(self.manager.start(workflow.metadata.id, self.collected))
            self.active_run_id = run.id
            self.message = f"Run iniciado: {run.id}"
            self.right_mode = "runs"
            self._refresh()
        except PenfoldError as exc:
            self.message = str(exc)

    def _new_workflow(self) -> None:
        self._start_input("ID del nuevo workflow: ", self._create_workflow)

    def _create_workflow(self, value: str) -> None:
        if not value:
            self.message = "Cancelado"
            return
        try:
            from penfold.services.workflow_editor import WorkflowEditor

            WorkflowEditor(self.workflows).create(value.strip())
            created = value.strip()
            self.message = f"Workflow {created} creado"
            self._refresh()
            self.selected = next(
                (
                    index
                    for index, item in enumerate(self.definitions)
                    if item.metadata.id == created
                ),
                0,
            )
        except PenfoldError as exc:
            self.message = str(exc)

    def _handle_key(self, key: str) -> bool:
        """Devuelve False cuando hay que salir."""
        if self.prompt is not None:
            if key in {"\r", "\n"}:
                prompt, callback = self.prompt, self.on_submit
                self.prompt = None
                self.on_submit = None
                if callback:
                    callback(self.buffer)
                self.buffer = ""
                self.message = f"Listo · {prompt.strip()}"
            elif key in {"\x7f", "\b"}:
                self.buffer = self.buffer[:-1]
            elif key == "\x1b":
                self.prompt = None
                self.on_submit = None
                self.buffer = ""
                self.message = "Cancelado"
            elif len(key) == 1 and key.isprintable():
                self.buffer += key
            return True

        if key in {"q", "Q", "\x1b"}:
            return False
        if key in {"j", "\x1b[B"}:
            self._move(1)
        elif key in {"k", "\x1b[A"}:
            self._move(-1)
        elif key in {"\r", "\n"}:
            self._begin_run()
        elif key == "n":
            self._new_workflow()
        elif key == "d":
            self.right_mode = "diagram"
            self.message = "Vista: diagrama"
        elif key == "r":
            self.right_mode = "runs"
            self.message = "Vista: ejecuciones"
        elif key == "f":
            self._refresh()
            self.message = "Actualizado"
        elif key == "?":
            self.message = KEY_HELP
        return True

    def _render_list(self) -> RenderableType:
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2)
        table.add_column(no_wrap=True)
        for index, workflow in enumerate(self.definitions):
            marker = "▶" if index == self.selected else " "
            style = "bold cyan" if index == self.selected else "white"
            table.add_row(
                Text(marker, style=style),
                Text(
                    f"{workflow.metadata.id}  [dim]{workflow.metadata.name}[/dim]",
                    style=style,
                ),
            )
        if not self.definitions:
            table.add_row("", Text("Sin workflows", style="dim"))
        return Panel(table, title="Workflows", border_style="cyan")

    def _render_runs(self) -> RenderableType:
        table = Table.grid(padding=(0, 1))
        for run in self.runs[:15]:
            active = "▶" if run.id == self.active_run_id else " "
            table.add_row(
                Text(active, style="cyan"),
                Text(run.id, style="cyan"),
                Text(run.workflow_id, style="white"),
                Text(run.status.value, style="yellow"),
            )
        if not self.runs:
            table.add_row(Text("Sin ejecuciones", style="dim"))
        return Panel(table, title="Ejecuciones", border_style="yellow")

    def _render_detail(self) -> RenderableType:
        if self.right_mode == "runs":
            return self._render_runs()
        if self.current is None:
            return Panel(Text("Sin workflow seleccionado", style="dim"), title="Diagrama")
        return build_diagram(self.current)

    def _render_header(self) -> RenderableType:
        current = self.current.metadata.id if self.current else "-"
        return Panel(
            f"[bold cyan]Penfold {__version__}[/bold cyan] · "
            f"[dim]{self.paths.root}[/dim] · workflow: [bold]{current}[/bold]",
            style="bold",
        )

    def _render_footer(self) -> RenderableType:
        if self.prompt:
            line = Text(f"{self.prompt}{self.buffer}▌", style="bold yellow")
        else:
            line = Text.from_markup(f"{KEY_HELP}  ·  [green]{self.message}[/green]")
        return Panel(line, title="Atajos", border_style="green")

    def _compose(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="list", ratio=1),
            Layout(name="detail", ratio=2),
        )
        layout["header"].update(self._render_header())
        layout["list"].update(self._render_list())
        layout["detail"].update(self._render_detail())
        layout["footer"].update(self._render_footer())
        return layout

    def run(self) -> None:
        with Live(
            self._compose(),
            console=console,
            screen=True,
            auto_refresh=True,
            refresh_per_second=2,
            redirect_stdout=False,
        ) as live:
            while True:
                key = _read_key()
                if not self._handle_key(key):
                    break
                if self.active_run_id:
                    self._refresh()
                live.update(self._compose())


def run_lazy(project: Path | None = None) -> None:
    """Entrada full-screen; usa el dashboard clásico si no hay TTY."""
    paths = find_project(project)
    try:
        paths.require_project()
    except PenfoldError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc
    if not (console.is_terminal and sys.stdin.isatty()):
        from penfold.tui.dashboard import run_dashboard

        run_dashboard(project)
        return
    try:
        LazyDashboard(paths).run()
    except (KeyboardInterrupt, EOFError):
        pass
    console.print(
        Panel(
            f"Proyecto: [cyan]{paths.root}[/cyan]\n"
            "Sesión terminada. Vuelve a abrir con [bold]penfold .[/bold].",
            title="Penfold",
            border_style="cyan",
        )
    )
