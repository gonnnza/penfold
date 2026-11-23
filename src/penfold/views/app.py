"""Aplicación FastAPI local: API REST, SSE y archivos estáticos del editor."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from penfold import __version__
from penfold.config.paths import ProjectPaths
from penfold.errors import (
    NotFoundError,
    PenfoldError,
    PermissionDeniedError,
    ProjectError,
    ValidationError,
)
from penfold.models.agent import AgentDefinition
from penfold.models.config import ProjectConfig
from penfold.models.execution import ApprovalRequest, RunEvent, StartRunRequest
from penfold.models.workflow import WorkflowDefinition
from penfold.services.agent_store import AgentStore
from penfold.services.events import EventBus
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.validator import validate_workflow
from penfold.services.workflow_store import WorkflowStore
from penfold.views.auth import TokenMiddleware

STATUS_BY_ERROR: dict[type[Exception], int] = {
    NotFoundError: 404,
    ValidationError: 422,
    PermissionDeniedError: 403,
    ProjectError: 400,
}


def create_app(paths: ProjectPaths, config: ProjectConfig, *, token: str) -> FastAPI:
    agents = AgentStore(paths)
    workflows = WorkflowStore(paths)
    repository = RunRepository(paths.db_path)
    events = EventBus()
    manager = RunManager(paths, config, workflows, agents, repository, events)

    app = FastAPI(title="Penfold API", version=__version__, docs_url=None, redoc_url=None)
    app.state.paths = paths
    app.state.config = config
    app.state.manager = manager
    app.state.events = events
    app.state.token = token
    app.state.workflows = workflows
    app.state.agents = agents
    manager.recover_interrupted()

    app.add_middleware(TokenMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PenfoldError)
    async def penfold_error_handler(_request: Request, exc: PenfoldError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/config")
    async def get_config() -> dict:
        return {
            "project": config.project,
            "defaults": {"runtime": config.defaults.runtime},
            "execution": {
                "max_concurrency": config.execution.max_concurrency,
                "default_timeout_seconds": config.execution.default_timeout_seconds,
                "max_retries": config.execution.max_retries,
                "max_iterations": config.execution.max_iterations,
            },
            "security": {"default_permission_mode": config.security.default_permission_mode},
        }

    @app.get("/api/workflows")
    async def list_workflows() -> list[dict]:
        result = []
        for workflow in workflows.list():
            result.append(
                {
                    "id": workflow.metadata.id,
                    "name": workflow.metadata.name,
                    "description": workflow.metadata.description,
                    "node_count": len(workflow.nodes),
                    "updated_at": None,
                }
            )
        return result

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> WorkflowDefinition:
        return workflows.get(workflow_id)

    @app.put("/api/workflows/{workflow_id}")
    async def save_workflow(workflow_id: str, workflow: WorkflowDefinition) -> dict:
        if workflow.metadata.id != workflow_id:
            raise ValidationError("metadata.id debe coincidir con el ID de la URL.")
        workflows.save(workflow)
        issues = validate_workflow(
            workflow,
            agent_ids={agent.id for agent in agents.list()},
            max_iterations_limit=10,
        )
        return {
            "ok": True,
            "id": workflow_id,
            "issues": [issue.model_dump() for issue in issues],
        }

    @app.post("/api/workflows/validate")
    async def validate(workflow: WorkflowDefinition) -> dict:
        issues = validate_workflow(
            workflow,
            agent_ids={agent.id for agent in agents.list()},
            max_iterations_limit=10,
        )
        return {
            "valid": all(issue.severity != "error" for issue in issues),
            "issues": [issue.model_dump() for issue in issues],
        }

    @app.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str) -> dict:
        workflows.delete(workflow_id)
        return {"ok": True}

    @app.get("/api/agents")
    async def list_agents() -> list[AgentDefinition]:
        return agents.list()

    @app.get("/api/agents/{agent_id}")
    async def get_agent(agent_id: str) -> AgentDefinition:
        return agents.get(agent_id)

    @app.put("/api/agents/{agent_id}")
    async def save_agent(agent_id: str, agent: AgentDefinition) -> dict:
        if agent.id != agent_id:
            raise ValidationError("El id del agente debe coincidir con el ID de la URL.")
        agents.save(agent)
        return {"ok": True, "id": agent_id}

    @app.get("/api/runs")
    async def list_runs(workflow_id: str | None = None, limit: int = 50) -> list[dict]:
        return [run.model_dump(mode="json") for run in manager.list(workflow_id, limit)]

    @app.post("/api/runs", status_code=201)
    async def start_run(request: StartRunRequest) -> dict:
        run = await manager.start(request.workflow_id, request.inputs)
        return run.model_dump(mode="json")

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        return manager.get(run_id).model_dump(mode="json")

    @app.get("/api/runs/{run_id}/events")
    async def get_events(run_id: str, after: int = 0) -> list[dict]:
        return [event.model_dump(mode="json") for event in manager.events(run_id, after)]

    @app.get("/api/runs/{run_id}/stream")
    async def stream_events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
        manager.get(run_id)
        queue = events.subscribe(run_id)

        async def generator():
            last = after
            try:
                for event in repository.list_events(run_id, after=last):
                    last = event.seq
                    yield f"data: {event.model_dump_json()}\n\n"
                while True:
                    try:
                        event: RunEvent = await asyncio.wait_for(queue.get(), timeout=15)
                        if event.seq > last:
                            last = event.seq
                            yield f"data: {event.model_dump_json()}\n\n"
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": keep-alive\n\n"
            finally:
                events.unsubscribe(run_id, queue)

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict:
        manager.cancel(run_id)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str) -> dict:
        run = await manager.resume(run_id)
        return {"ok": True, "status": run.status.value}

    @app.post("/api/runs/{run_id}/approve")
    async def approve_run(run_id: str, request: ApprovalRequest) -> dict:
        manager.approve(run_id, request)
        return {"ok": True}

    @app.get("/api/artifacts/{run_id}/{name:path}")
    async def get_artifact(run_id: str, name: str) -> FileResponse:
        root = (paths.artifacts_dir / run_id).resolve()
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise NotFoundError("Artefacto no encontrado.")
        return FileResponse(target)

    static_dir = paths.static_dir
    if (static_dir / "index.html").is_file():

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        if (static_dir / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> FileResponse:
            candidate = (static_dir / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")
    else:

        @app.get("/")
        async def not_built() -> HTMLResponse:
            return HTMLResponse(
                "<h1>Penfold</h1>"
                "<p>El servidor está activo, pero el frontend aún no está compilado.</p>"
                "<p>Compílalo con <code>cd web &amp;&amp; pnpm build</code></p>"
                "<p>y reinicia el servidor.</p>"
                "<p><a href='/api/health'>/api/health</a></p>"
            )

    return app
