"""CLI de Penfold: punto de entrada principal y mecanismo de automatización."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from penfold import __version__
from penfold.config.paths import ProjectPaths, find_project
from penfold.errors import PenfoldError
from penfold.models.execution import RunStatus
from penfold.services.agent_store import AgentStore
from penfold.services.approval import ConsoleApprovalGate
from penfold.services.events import EventBus
from penfold.services.git import GitService
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.validator import validate_workflow
from penfold.services.workflow_editor import WorkflowEditor
from penfold.services.workflow_store import WorkflowStore
from penfold.services.workflow_templates import install_default_workflows
from penfold.tui import run_dashboard
from penfold.tui.diagram import build_diagram
from penfold.views.auth import new_token

app = typer.Typer(
    name="penfold",
    help="Penfold — orquestador visual local de agentes de IA para desarrollo de software.",
    no_args_is_help=True,
    add_completion=True,
)
workflow_app = typer.Typer(help="Gestionar workflows.")
agent_app = typer.Typer(help="Gestionar agentes.")
git_app = typer.Typer(help="Consultar el repositorio Git del proyecto.")
app.add_typer(workflow_app, name="workflow")
app.add_typer(agent_app, name="agent")
app.add_typer(git_app, name="git")
console = Console()

# Lo fija la opción global --project; None = buscar hacia arriba desde el cwd.
PROJECT_ROOT: Path | None = None


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=code)


def _initialize(paths: ProjectPaths, *, name: str | None = None, force: bool = False) -> None:
    """Crea la estructura .orchestrator/ y sus definiciones por defecto."""
    paths.init(name=name, force=force)
    n_workflows = install_default_workflows(paths)
    RunRepository(paths.db_path)
    console.print(f"[green]✓[/green] Proyecto inicializado en {paths.base}")
    console.print(f"  Workflows creados: {n_workflows}")
    console.print("  Agentes: crea tus definiciones en .orchestrator/agents/*.yaml")
    console.print("  Base de datos: " + str(paths.db_path))


def _components(paths: ProjectPaths | None = None):
    paths = paths or find_project(PROJECT_ROOT)
    try:
        config = paths.require_project()
    except PenfoldError as exc:
        _fail(str(exc))
    agents = AgentStore(paths)
    workflows = WorkflowStore(paths)
    repository = RunRepository(paths.db_path)
    events = EventBus()
    manager = RunManager(paths, config, workflows, agents, repository, events)
    manager.recover_interrupted()
    return paths, config, agents, workflows, repository, events, manager


def _parse_inputs(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            _fail(f"Entrada inválida {item!r}. Usa el formato clave=valor.")
        key, value = item.split("=", 1)
        result[key] = value
    return result


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Mostrar la versión."),
    project: Path | None = typer.Option(
        None,
        "--project",
        help=(
            "Directorio del proyecto Penfold. Por defecto se usa el directorio actual "
            "o el primero hacia arriba que contenga .orchestrator/."
        ),
    ),
) -> None:
    global PROJECT_ROOT
    PROJECT_ROOT = project
    if version:
        console.print(f"penfold {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print("Usa `penfold --help` para ver los comandos disponibles.")


@app.command()
def init(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Directorio del proyecto."),
    name: str | None = typer.Option(None, "--name", help="Nombre del proyecto."),
    force: bool = typer.Option(False, "--force", help="Permitir reinicializar la configuración."),
) -> None:
    """Inicializar la configuración de Penfold en el proyecto actual."""
    try:
        paths = ProjectPaths(PROJECT_ROOT or path)
        _initialize(paths, name=name, force=force)
    except PenfoldError as exc:
        _fail(str(exc))
    console.print("\nSiguiente paso: [cyan]penfold start[/cyan] o [cyan]penfold tui[/cyan]")


@app.command(".")
def open_here() -> None:
    """Inicializar la carpeta actual si hace falta y abrir el dashboard de terminal."""
    root = PROJECT_ROOT or Path.cwd()
    paths = find_project(root)
    if not paths.exists():
        try:
            _initialize(paths)
        except PenfoldError as exc:
            _fail(str(exc))
    console.print(f"[dim]Proyecto:[/dim] {paths.root}")
    run_dashboard(paths.root)


@app.command()
def doctor() -> None:
    """Diagnosticar la instalación y las dependencias del entorno."""
    ok = True
    table = Table(title="Penfold doctor", title_style="bold cyan")
    table.add_column("Comprobación")
    table.add_column("Estado")
    table.add_column("Detalle")

    def add(label: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and passed
        table.add_row(label, "[green]OK[/green]" if passed else "[yellow]FALTA[/yellow]", detail)

    add("Python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    for module in ("fastapi", "typer", "pydantic", "sqlalchemy", "yaml", "jsonschema", "uvicorn"):
        add(f"Python: {module}", importlib.util.find_spec(module) is not None, "importable")
    import shutil

    add("Git", shutil.which("git") is not None, shutil.which("git") or "no encontrado")
    try:
        _components()
        add("Proyecto inicializado", True, "config.yaml encontrado")
    except PenfoldError as exc:
        add("Proyecto inicializado", False, str(exc)[:80])

    try:
        config = find_project(PROJECT_ROOT).load_config()
        with socket.socket() as sock:
            sock.bind((config.server.host, config.server.port))
        add(f"Puerto {config.server.port}", True, "disponible")
    except (OSError, PenfoldError) as exc:
        add("Puerto del servidor", False, str(exc)[:80])

    console.print(table)
    if not ok:
        _fail("Hay comprobaciones pendientes. Revisa los detalles anteriores.")
    console.print("[green]Entorno listo.[/green]")


@app.command()
def start(
    no_browser: bool = typer.Option(False, "--no-browser", help="No abrir el navegador."),
    host: str | None = typer.Option(
        None, "--host", help="Sobrescribe server.host (solo loopback)."
    ),
    port: int | None = typer.Option(None, "--port", help="Sobrescribe server.port."),
) -> None:
    """Iniciar el servidor local (API REST y SSE)."""
    import uvicorn

    paths, config, *_ = _components()
    if host:
        config.server.host = host
    if port:
        config.server.port = port
    token = paths.read_token() or new_token()
    paths.write_token(token)
    from penfold.views.app import create_app

    application = create_app(paths, config, token=token)
    base_url = f"http://{config.server.host}:{config.server.port}"
    console.print(f"[bold cyan]Penfold[/bold cyan] {__version__} en {base_url}")
    console.print(f"Token local: [yellow]{token}[/yellow]")
    console.print("El token también se guardó en " + str(paths.token_path))
    console.print("Pulsa Ctrl+C para detener el servidor.")
    if config.server.auto_open_browser and not no_browser:
        threading.Timer(0.8, webbrowser.open, args=[f"{base_url}/?token={token}"]).start()
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host=config.server.host,
            port=config.server.port,
            log_level="warning",
            access_log=False,
        )
    )
    server.run()


@app.command()
def tui() -> None:
    """Abrir el dashboard interactivo de terminal (equivalente al panel web)."""
    run_dashboard(PROJECT_ROOT)


@app.command()
def run(
    workflow_id: str = typer.Argument(..., help="ID del workflow a ejecutar."),
    input_: list[str] = typer.Option(
        [], "--input", "-i", help="Entrada clave=valor (se puede repetir)."
    ),
    watch: bool = typer.Option(False, "--watch", help="Mostrar eventos hasta que termine."),
) -> None:
    """Ejecutar un workflow directamente desde la CLI."""
    paths, config, agents, workflows, repository, events, manager = _components()

    async def execute() -> None:
        run_detail = None
        try:
            run_detail = await manager.start(
                workflow_id, _parse_inputs(input_), gate=ConsoleApprovalGate()
            )
        except PenfoldError as exc:
            _fail(str(exc))
        assert run_detail is not None
        console.print(f"Ejecución [cyan]{run_detail.id}[/cyan] iniciada.")
        if watch:

            async def follow() -> None:
                last = 0
                while True:
                    for event in repository.list_events(run_detail.id, after=last):
                        last = event.seq
                        console.print(
                            f"  [dim]{event.timestamp[11:19]}[/dim] [{event.level}] {event.message}"
                        )
                    final = await manager.wait(run_detail.id, timeout=0.5)
                    if final.status.terminal or final.status == RunStatus.PAUSED:
                        return

            await follow()
        final = await manager.wait(run_detail.id)
        _print_run(final.model_dump(mode="json"))

    asyncio.run(execute())


@app.command()
def runs(
    workflow_id: str | None = typer.Option(None, "--workflow", help="Filtrar por workflow."),
    limit: int = typer.Option(20, "--limit", help="Máximo de ejecuciones."),
) -> None:
    """Listar ejecuciones recientes."""
    *_, manager = _components()
    table = Table(title="Ejecuciones")
    table.add_column("ID")
    table.add_column("Workflow")
    table.add_column("Estado")
    table.add_column("Creada")
    table.add_column("Nodos")
    for item in manager.list(workflow_id, limit):
        style = (
            "green"
            if item.status == RunStatus.COMPLETED
            else "red"
            if item.status
            in {
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            }
            else "yellow"
        )
        table.add_row(
            item.id,
            item.workflow_id,
            f"[{style}]{item.status.value}[/{style}]",
            item.created_at,
            str(item.node_count),
        )
    console.print(table)


@app.command()
def inspect(run_id: str = typer.Argument(..., help="ID de la ejecución.")) -> None:
    """Inspeccionar el estado detallado de una ejecución."""
    *_, manager = _components()
    try:
        detail = manager.get(run_id)
    except PenfoldError as exc:
        _fail(str(exc))
    _print_run(detail.model_dump(mode="json"))


def _print_run(detail: dict[str, Any]) -> None:
    console.print(
        f"\n[bold]Ejecución[/bold] {detail['id']} · workflow={detail['workflow_id']} · "
        f"estado=[cyan]{detail['status']}[/cyan]"
    )
    if detail.get("error"):
        console.print(f"[red]Error:[/red] {detail['error']}")
    table = Table(title="Nodos")
    table.add_column("Nodo")
    table.add_column("Estado")
    table.add_column("Intentos")
    table.add_column("Iter.")
    table.add_column("Tiempo (ms)")
    table.add_column("Runtime")
    colors = {
        "succeeded": "green",
        "failed": "red",
        "running": "cyan",
        "waiting_approval": "yellow",
        "skipped": "dim",
        "cancelled": "yellow",
    }
    for node in detail.get("nodes", []):
        status = node["status"]
        table.add_row(
            node["node_id"],
            f"[{colors.get(status, 'white')}]{status}[/{colors.get(status, 'white')}]",
            str(node.get("attempts", 0)),
            str(node.get("iteration", 0)),
            str(node.get("duration_ms") or ""),
            str(node.get("runtime") or ""),
        )
    console.print(table)
    if detail.get("outputs"):
        console.print("[bold]Salida:[/bold]")
        console.print_json(data=detail["outputs"])


@app.command()
def logs(
    run_id: str = typer.Argument(..., help="ID de la ejecución."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Seguir nuevos eventos."),
) -> None:
    """Consultar los eventos de una ejecución."""
    *_, manager = _components()

    async def show() -> None:
        last = 0
        try:
            while True:
                batch = manager.events(run_id, after=last)
                for event in batch:
                    last = event.seq
                    color = {"error": "red", "warning": "yellow", "success": "green"}.get(
                        event.level, "white"
                    )
                    node = f"[{event.node_id}] " if event.node_id else ""
                    console.print(
                        f"[dim]{event.timestamp[11:19]}[/dim] [{color}]{event.type}[/{color}] "
                        f"{node}{event.message}"
                    )
                if not follow:
                    return
                detail = manager.get(run_id)
                if detail.status.terminal and not batch:
                    return
                await asyncio.sleep(0.6)
        except PenfoldError as exc:
            _fail(str(exc))

    asyncio.run(show())


@app.command()
def cancel(run_id: str = typer.Argument(..., help="ID de la ejecución.")) -> None:
    """Cancelar una ejecución en curso."""
    *_, manager = _components()
    try:
        manager.cancel(run_id)
    except PenfoldError as exc:
        _fail(str(exc))
    console.print(f"[yellow]Cancelación solicitada[/yellow] para {run_id}.")


@app.command()
def resume(run_id: str = typer.Argument(..., help="ID de la ejecución pausada.")) -> None:
    """Reanudar una ejecución pausada desde su checkpoint."""
    *_, manager = _components()

    async def execute() -> None:
        try:
            await manager.resume(run_id)
        except PenfoldError as exc:
            _fail(str(exc))
        console.print(f"Ejecución [cyan]{run_id}[/cyan] reanudada.")

    asyncio.run(execute())


@workflow_app.command("list")
def workflow_list() -> None:
    """Listar los workflows del proyecto."""
    _, _, _, workflows, *_ = _components()
    table = Table(title="Workflows")
    table.add_column("ID")
    table.add_column("Nombre")
    table.add_column("Nodos")
    table.add_column("Descripción")
    for item in workflows.list():
        table.add_row(
            item.metadata.id, item.metadata.name, str(len(item.nodes)), item.metadata.description
        )
    console.print(table)


@workflow_app.command("diagram")
def workflow_diagram(workflow_id: str = typer.Argument(..., help="ID del workflow.")) -> None:
    """Dibujar el grafo del workflow en la terminal."""
    _, _, _, workflows, *_ = _components()
    try:
        definition = workflows.get(workflow_id)
    except PenfoldError as exc:
        _fail(str(exc))
    console.print(build_diagram(definition))


def _parse_value(raw: str | None) -> object:
    """Interpreta JSON cuando puede; si no, deja la cadena tal cual."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _edit(workflow_id: str, action) -> None:
    """Aplica una edición, muestra el resultado y deja el YAML guardado."""
    _, _, _, workflows, *_ = _components()
    try:
        definition = action(WorkflowEditor(workflows))
    except PenfoldError as exc:
        _fail(str(exc))
    console.print(
        f"[green]✓[/green] Guardado .orchestrator/workflows/{definition.metadata.id}.yaml"
    )
    console.print(build_diagram(definition))


@workflow_app.command("new")
def workflow_new(
    workflow_id: str = typer.Argument(..., help="ID del nuevo workflow."),
    name: str | None = typer.Option(None, "--name", help="Nombre legible."),
    description: str = typer.Option("", "--description", help="Descripción."),
) -> None:
    """Crear un workflow con nodos Input y Output ya conectados."""
    _edit(
        workflow_id,
        lambda editor: editor.create(workflow_id, name=name, description=description),
    )


@workflow_app.command("add-node")
def workflow_add_node(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    node_id: str = typer.Argument(..., help="ID del nodo."),
    node_type: str = typer.Argument(..., help="input|agent|command|condition|approval|output."),
    label: str | None = typer.Option(None, "--label", help="Etiqueta visible."),
    agent: str | None = typer.Option(None, "--agent", help="Agente (obligatorio si type=agent)."),
) -> None:
    """Añadir un nodo al grafo."""
    _edit(
        workflow_id,
        lambda editor: editor.add_node(workflow_id, node_id, node_type, label=label, agent=agent),
    )


@workflow_app.command("connect")
def workflow_connect(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    source: str = typer.Argument(..., help="Nodo origen."),
    target: str = typer.Argument(..., help="Nodo destino."),
    handle: str = typer.Option("default", "--handle", help="default|pass|fail."),
    label: str | None = typer.Option(None, "--label", help="Etiqueta de la arista."),
    loop: bool = typer.Option(False, "--loop", help="Marcar como arista de retorno."),
    max_iterations: int | None = typer.Option(None, "--max-iterations", help="Límite del bucle."),
) -> None:
    """Conectar dos nodos."""
    _edit(
        workflow_id,
        lambda editor: editor.connect(
            workflow_id,
            source,
            target,
            handle=handle,
            label=label,
            loop=loop,
            max_iterations=max_iterations,
        ),
    )


@workflow_app.command("set")
def workflow_set(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    node_id: str = typer.Argument(..., help="ID del nodo."),
    key: str = typer.Argument(..., help="Clave de config (p. ej. command, inputs)."),
    value: str = typer.Argument(..., help="Valor JSON o texto."),
) -> None:
    """Asignar una clave de config a un nodo."""
    _edit(
        workflow_id,
        lambda editor: editor.set_config(workflow_id, node_id, key, _parse_value(value)),
    )


@workflow_app.command("add-input")
def workflow_add_input(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    input_id: str = typer.Argument(..., help="Nombre de la entrada."),
    input_type: str = typer.Option("string", "--type", help="Tipo declarado."),
    required: bool = typer.Option(True, "--required/--no-required", help="Obligatoria."),
    default: str | None = typer.Option(None, "--default", help="Valor por defecto (JSON o texto)."),
) -> None:
    """Declarar una entrada del workflow."""
    _edit(
        workflow_id,
        lambda editor: editor.add_input(
            workflow_id,
            input_id,
            input_type=input_type,
            required=required,
            default=_parse_value(default),
        ),
    )


@workflow_app.command("rm-node")
def workflow_remove_node(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    node_id: str = typer.Argument(..., help="ID del nodo a borrar."),
) -> None:
    """Borrar un nodo y sus aristas."""
    _edit(workflow_id, lambda editor: editor.remove_node(workflow_id, node_id))


@workflow_app.command("rm-edge")
def workflow_remove_edge(
    workflow_id: str = typer.Argument(..., help="ID del workflow."),
    edge_id: str = typer.Argument(..., help="ID de la arista a borrar."),
) -> None:
    """Borrar una arista."""
    _edit(workflow_id, lambda editor: editor.remove_edge(workflow_id, edge_id))


@workflow_app.command("validate")
def workflow_validate(workflow_id: str = typer.Argument(..., help="ID del workflow.")) -> None:
    """Validar la estructura y las referencias de un workflow."""
    _, _, agents, workflows, *_ = _components()
    try:
        definition = workflows.get(workflow_id)
    except PenfoldError as exc:
        _fail(str(exc))
    issues = validate_workflow(
        definition,
        agent_ids={agent.id for agent in agents.list()},
        max_iterations_limit=10,
    )
    if not issues:
        console.print(f"[green]✓[/green] Workflow {workflow_id} válido.")
        return
    for issue in issues:
        color = "red" if issue.severity == "error" else "yellow"
        console.print(f"[{color}]{issue.severity}[/{color}] {issue.path}: {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        raise typer.Exit(code=1)


@agent_app.command("list")
def agent_list() -> None:
    """Listar los agentes configurados."""
    _, _, agents, *_ = _components()
    table = Table(title="Agentes")
    table.add_column("ID")
    table.add_column("Nombre")
    table.add_column("Runtime")
    table.add_column("Permisos")
    table.add_column("Salida")
    for item in agents.list():
        table.add_row(
            item.id, item.name, item.runtime.type, item.permissions.mode, item.outputs.format
        )
    console.print(table)


def _git_service(path: Path) -> GitService:
    """Adaptador CLI: resuelve el service y convierte sus errores en salida CLI."""
    try:
        return GitService(path)
    except PenfoldError as exc:
        _fail(str(exc))


@git_app.command("status")
def git_status(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Directorio del repositorio."),
) -> None:
    """Mostrar rama, limpieza y archivos modificados del repositorio."""
    info = _git_service(path).info()
    table = Table(title="Repositorio Git")
    table.add_column("Raíz")
    table.add_column("Rama", style="cyan")
    table.add_column("Estado")
    table.add_column("Archivos modificados")
    table.add_row(
        str(info.root),
        info.branch,
        "[green]limpio[/green]" if info.clean else "[yellow]con cambios[/yellow]",
        "\n".join(info.changed_files) or "—",
    )
    console.print(table)


@git_app.command("diff")
def git_diff(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Directorio del repositorio."),
    staged: bool = typer.Option(False, "--staged", help="Mostrar los cambios en el índice."),
) -> None:
    """Mostrar el diff del repositorio en formato estadístico."""
    output = _git_service(path).diff(staged=staged).strip()
    console.print(output or "Sin diferencias.")


@git_app.command("worktrees")
def git_worktrees(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Directorio del repositorio."),
) -> None:
    """Listar los worktrees del repositorio."""
    lines = _git_service(path).worktrees()
    if not lines:
        console.print("No hay worktrees.")
        return
    for line in lines:
        console.print(line)
