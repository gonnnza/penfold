"""Dashboard interactivo de terminal, equivalente al panel de la UI web.

Muestra workflows, agentes e historial de runs; lanza ejecuciones y sigue sus
eventos en vivo. No hay servidor HTTP ni token: se conecta directamente a los
services, igual que lo hace la vista web a través de la API.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from penfold import __version__
from penfold.config.paths import ProjectPaths, find_project
from penfold.errors import PenfoldError
from penfold.models.execution import ApprovalRequest, RunDetail, RunEvent, RunStatus
from penfold.models.workflow import WorkflowDefinition
from penfold.services.agent_store import AgentStore
from penfold.services.events import EventBus
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.workflow_editor import WorkflowEditor
from penfold.services.workflow_store import WorkflowStore
from penfold.tui.diagram import build_diagram

console = Console()

RUN_STYLES: dict[RunStatus, str] = {
    RunStatus.CREATED: "dim",
    RunStatus.VALIDATING: "yellow",
    RunStatus.RUNNING: "cyan bold",
    RunStatus.WAITING_APPROVAL: "magenta bold",
    RunStatus.PAUSED: "yellow",
    RunStatus.COMPLETED: "green bold",
    RunStatus.FAILED: "red bold",
    RunStatus.CANCELLED: "dim red",
}
NODE_STYLES: dict[str, str] = {
    "pending": "dim",
    "ready": "yellow",
    "running": "cyan bold",
    "waiting_approval": "magenta bold",
    "succeeded": "green",
    "failed": "red bold",
    "skipped": "dim",
    "cancelled": "dim red",
}
LEVEL_STYLES: dict[str, str] = {
    "info": "white",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
}


def _style(status: Any, styles: dict[Any, str]) -> str:
    return styles.get(status, "white")


def render_workflows_table(workflows: list[WorkflowDefinition]) -> Table:
    table = Table(title="Workflows", expand=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Nombre")
    table.add_column("Nodos", justify="right")
    table.add_column("Descripción", style="dim")
    for workflow in workflows:
        table.add_row(
            workflow.metadata.id,
            workflow.metadata.name,
            str(len(workflow.nodes)),
            workflow.metadata.description,
        )
    return table


def render_runs_table(runs: list[Any]) -> Table:
    table = Table(title="Ejecuciones", expand=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Workflow")
    table.add_column("Estado")
    table.add_column("Nodos", justify="right")
    table.add_column("Creado", style="dim")
    for run in runs:
        table.add_row(
            run.id,
            run.workflow_id,
            Text(run.status.value, style=_style(run.status, RUN_STYLES)),
            str(run.node_count),
            run.created_at[11:19],
        )
    return table


def render_agents_table(agents: list[Any]) -> Table:
    table = Table(title="Agentes", expand=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Rol")
    table.add_column("Runtime")
    table.add_column("Permisos")
    table.add_column("Descripción", style="dim")
    for agent in agents:
        table.add_row(
            agent.id,
            agent.role,
            agent.runtime.type,
            agent.permissions.mode,
            agent.description or "",
        )
    return table


def build_run_view(
    run: RunDetail,
    workflow: WorkflowDefinition | None,
    events: list[RunEvent],
) -> Group:
    """Construye la vista en vivo de un run (nodos + eventos + aprobación)."""
    labels = {node.id: node.label or node.id for node in workflow.nodes} if workflow else {}

    nodes = Table(title=f"Run {run.id} — {run.workflow_id}", expand=True)
    nodes.add_column("Nodo")
    nodes.add_column("Estado")
    nodes.add_column("Intentos", justify="right")
    nodes.add_column("Tiempo", justify="right")
    nodes.add_column("Detalle", style="dim")
    for state in run.nodes:
        detail = state.error or (state.runtime or "")
        nodes.add_row(
            labels.get(state.node_id, state.node_id),
            Text(state.status.value, style=_style(state.status.value, NODE_STYLES)),
            str(state.attempts),
            f"{state.duration_ms} ms" if state.duration_ms is not None else "-",
            detail[:60],
        )

    log = Table.grid(padding=(0, 1))
    for event in events[-12:]:
        time = Text(event.timestamp[11:19], style="dim")
        message = Text(event.message, style=_style(event.level, LEVEL_STYLES))
        log.add_row(time, Text(f"#{event.seq}", style="dim"), message)

    parts: list[RenderableType] = [
        Panel(
            Text(
                f"{run.status.value.upper()}  ·  entradas: "
                f"{json.dumps(run.inputs, ensure_ascii=False)}"
                + (f"\nERROR: {run.error}" if run.error else ""),
                style=_style(run.status, RUN_STYLES),
            ),
            title="Estado",
        ),
        nodes,
        Panel(log, title="Eventos", height=15),
    ]

    if run.status == RunStatus.WAITING_APPROVAL and run.approval is not None:
        approval = run.approval
        data = json.dumps(approval.data, ensure_ascii=False, indent=2, default=str)
        parts.append(
            Panel(
                Text(f"{approval.message or approval.title}\n{data[:600]}", style="magenta"),
                title=f"Aprobación pendiente: {approval.title}",
                border_style="magenta",
            )
        )

    return Group(*parts)


async def ask(
    prompt: str,
    *,
    default: str | None = None,
    choices: list[str] | None = None,
) -> str:
    """Prompt de Rich en un hilo, para no bloquear el event loop del motor."""
    return await asyncio.to_thread(
        Prompt.ask,
        prompt,
        default=default,
        choices=choices,
        show_choices=choices is not None,
    )


def _header(title: str) -> None:
    console.rule(f"[bold cyan]Penfold {__version__}[/bold cyan] · {title}")


async def _monitor_run(
    manager: RunManager,
    repository: RunRepository,
    run_id: str,
    workflow: WorkflowDefinition | None,
) -> RunDetail:
    """Sigue un run hasta que termina, resolviendo aprobaciones desde la terminal."""
    last_seq = 0
    recent: list[RunEvent] = []
    approval_asked = False

    while True:
        with Live(console=console, refresh_per_second=4, screen=False) as live:
            while True:
                for event in repository.list_events(run_id, after=last_seq):
                    last_seq = event.seq
                    recent.append(event)
                recent = recent[-12:]
                run = manager.get(run_id)
                live.update(build_run_view(run, workflow, recent))

                if run.status == RunStatus.WAITING_APPROVAL:
                    break
                if run.status.terminal or run.status == RunStatus.PAUSED:
                    return run
                await asyncio.sleep(0.25)

        if not approval_asked:
            approval_asked = True
            run = manager.get(run_id)
            approval = run.approval
            console.print(
                Panel(
                    f"[bold]{approval.title if approval else 'Aprobación requerida'}[/bold]\n"
                    f"{approval.message if approval else ''}",
                    border_style="magenta",
                    title="Revisión humana",
                )
            )
            decision = await ask(
                "¿Aprobar, rechazar o modificar?",
                choices=["approve", "reject", "modify", "cancel"],
            )
            data = None
            note: str | None = None
            if decision == "modify":
                raw = await ask("Nuevos datos (JSON, o vacío):", default="")
                try:
                    data = json.loads(raw) if raw.strip() else None
                except json.JSONDecodeError as exc:
                    console.print(f"[red]JSON inválido:[/red] {exc}")
                    data = None
            if decision in {"reject", "modify"}:
                note = await ask("Nota (opcional):", default="")
            try:
                manager.approve(
                    run_id, ApprovalRequest(decision=decision, data=data, note=note or None)
                )
            except PenfoldError as exc:
                console.print(f"[yellow]No se pudo aprobar:[/yellow] {exc}")
            approval_asked = False


async def _launch(manager: RunManager, repository: RunRepository, workflows: WorkflowStore) -> None:
    definitions = workflows.list()
    if not definitions:
        console.print("[yellow]No hay workflows. Usa `penfold init` o crea uno en la UI.[/yellow]")
        return
    _header("Ejecutar workflow")
    console.print(render_workflows_table(definitions))
    selected = await ask("ID del workflow (Enter para volver):", default="")
    if not selected:
        return
    try:
        workflow = workflows.get(selected)
    except PenfoldError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return

    values: dict[str, Any] = {}
    for declared in workflow.inputs:
        default = "" if declared.default is None else str(declared.default)
        answer = await ask(f"{declared.id} ({declared.type})", default=default)
        if answer:
            values[declared.id] = answer

    try:
        run = await manager.start(selected, values)
    except PenfoldError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return

    final = await _monitor_run(manager, repository, run.id, workflow)
    console.print(
        Panel(
            f"Estado: {final.status.value}\nSalidas: "
            f"{json.dumps(final.outputs, ensure_ascii=False, default=str)}",
            title=f"Run {final.id} finalizado",
            border_style=_style(final.status, RUN_STYLES),
        )
    )


async def _runs_menu(
    manager: RunManager, repository: RunRepository, workflows: WorkflowStore
) -> None:
    while True:
        _header("Historial de ejecuciones")
        runs = manager.list(limit=20)
        console.print(render_runs_table(runs))
        choice = await ask("[1] Ver detalle  [2] Cancelar  [3] Reanudar  [0] Volver", default="0")
        if choice == "0":
            return
        run_id = await ask("ID del run:", default="")
        if not run_id:
            continue
        try:
            if choice == "1":
                run = manager.get(run_id)
                definition = None
                for candidate in workflows.list():
                    if candidate.metadata.id == run.workflow_id:
                        definition = candidate
                        break
                events = manager.events(run_id)
                console.print(build_run_view(run, definition, events))
            elif choice == "2":
                manager.cancel(run_id)
                console.print("[yellow]Cancelación solicitada.[/yellow]")
            elif choice == "3":
                await manager.resume(run_id)
                await _monitor_run(manager, repository, run_id, None)
        except PenfoldError as exc:
            console.print(f"[red]Error:[/red] {exc}")


async def _edit_menu(workflows: WorkflowStore) -> None:
    """Editor interactivo de workflows: crea nodos, aristas y configura."""
    editor = WorkflowEditor(workflows)
    node_types = ["input", "agent", "command", "condition", "approval", "output"]

    while True:
        _header("Editar workflow")
        console.print(render_workflows_table(workflows.list()))
        choice = await ask(
            "[1] Nuevo  [2] Añadir nodo  [3] Conectar  [4] Configurar  "
            "[5] Añadir entrada  [6] Borrar  [0] Volver",
            default="0",
        )
        if choice == "0":
            return

        try:
            if choice == "1":
                workflow_id = await ask("ID del nuevo workflow:", default="")
                name = await ask("Nombre:", default=workflow_id)
                definition = editor.create(workflow_id, name=name or None)
            else:
                workflow_id = await ask("ID del workflow:", default="")
                if not workflow_id:
                    continue
                if choice == "2":
                    node_id = await ask("ID del nodo:", default="")
                    node_type = await ask("Tipo:", choices=node_types)
                    label = await ask("Etiqueta:", default="")
                    agent = await ask("Agente:", default="") if node_type == "agent" else None
                    definition = editor.add_node(
                        workflow_id, node_id, node_type, label=label or None, agent=agent or None
                    )
                elif choice == "3":
                    source = await ask("Nodo origen:", default="")
                    target = await ask("Nodo destino:", default="")
                    handle = await ask("Handle:", choices=["default", "pass", "fail"])
                    loop = (await ask("¿Bucle?", choices=["no", "si"], default="no")) == "si"
                    maximum = await ask("max_iterations (vacío = ninguno):", default="")
                    definition = editor.connect(
                        workflow_id,
                        source,
                        target,
                        handle=handle,
                        loop=loop,
                        max_iterations=int(maximum) if maximum.isdigit() else None,
                    )
                elif choice == "4":
                    node_id = await ask("ID del nodo:", default="")
                    key = await ask("Clave de config:", default="")
                    raw = await ask("Valor (JSON o texto):", default="")
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError:
                        value = raw
                    definition = editor.set_config(workflow_id, node_id, key, value)
                elif choice == "5":
                    input_id = await ask("Nombre de la entrada:", default="")
                    input_type = await ask("Tipo:", default="string")
                    answer = await ask("¿Obligatoria?", choices=["si", "no"], default="si")
                    required = answer == "si"
                    default = await ask("Valor por defecto (JSON o texto):", default="")
                    try:
                        parsed = json.loads(default) if default else None
                    except json.JSONDecodeError:
                        parsed = default
                    definition = editor.add_input(
                        workflow_id,
                        input_id,
                        input_type=input_type,
                        required=required,
                        default=parsed,
                    )
                elif choice == "6":
                    kind = await ask("¿Nodo o arista?", choices=["nodo", "arista"])
                    item_id = await ask("ID:", default="")
                    definition = (
                        editor.remove_node(workflow_id, item_id)
                        if kind == "nodo"
                        else editor.remove_edge(workflow_id, item_id)
                    )
                else:
                    continue
            console.print(f"[green]✓[/green] Guardado {definition.metadata.id}.yaml")
            console.print(build_diagram(definition))
        except (PenfoldError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
        await ask("Enter para continuar...", default="")


async def _session(paths: ProjectPaths) -> None:
    config = paths.require_project()
    agents = AgentStore(paths)
    workflows = WorkflowStore(paths)
    repository = RunRepository(paths.db_path)
    events = EventBus()
    manager = RunManager(paths, config, workflows, agents, repository, events)
    manager.recover_interrupted()

    try:
        while True:
            _header("Dashboard")
            console.print(
                f"[dim]Proyecto:[/dim] {paths.root}  [dim]Workflows:[/dim] "
                f"{len(workflows.list())}  [dim]Agentes:[/dim] {len(agents.list())}"
            )
            choice = await ask(
                "[1] Workflows  [2] Ejecutar  [3] Runs  [4] Agentes  "
                "[5] Diagrama  [6] Editar  [0] Salir",
                default="0",
            )
            if choice == "0":
                return
            if choice == "1":
                _header("Workflows")
                console.print(render_workflows_table(workflows.list()))
                await ask("Enter para continuar...", default="")
            elif choice == "2":
                await _launch(manager, repository, workflows)
            elif choice == "3":
                await _runs_menu(manager, repository, workflows)
            elif choice == "4":
                _header("Agentes")
                console.print(render_agents_table(agents.list()))
                await ask("Enter para continuar...", default="")
            elif choice == "5":
                _header("Diagrama")
                workflow_id = await ask("ID del workflow:", default="")
                if workflow_id:
                    try:
                        console.print(build_diagram(workflows.get(workflow_id)))
                    except PenfoldError as exc:
                        console.print(f"[red]Error:[/red] {exc}")
                await ask("Enter para continuar...", default="")
            elif choice == "6":
                await _edit_menu(workflows)
    finally:
        for task in list(manager.tasks.values()):
            if not task.done():
                task.cancel()
        if manager.tasks:
            await asyncio.gather(*manager.tasks.values(), return_exceptions=True)


def run_dashboard(project: Path | None = None) -> None:
    """Punto de entrada síncrono para el comando `penfold tui`.

    ``project`` permite apuntar a cualquier carpeta; si es None se busca
    ``.orchestrator/`` hacia arriba desde el directorio actual.
    """
    try:
        paths = find_project(project)
        paths.require_project()
    except PenfoldError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc
    asyncio.run(_session(paths))
