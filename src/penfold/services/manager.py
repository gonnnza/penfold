"""Ciclo de vida de ejecuciones: crear, cancelar, aprobar, reanudar e inspeccionar."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from penfold.config.paths import ProjectPaths
from penfold.errors import NotFoundError, ValidationError
from penfold.models.config import ProjectConfig
from penfold.models.execution import (
    ApprovalRequest,
    NodeState,
    RunDetail,
    RunEvent,
    RunStatus,
)
from penfold.services.agent_store import AgentStore
from penfold.services.approval import ApprovalDecision, ApprovalGate, QueueApprovalGate
from penfold.services.engine import EngineContext, GraphWorkflowEngine
from penfold.services.events import EventBus
from penfold.services.repository import RunRepository
from penfold.services.validator import validate_workflow
from penfold.services.workflow_store import WorkflowStore
from penfold.utils import utcnow


class RunManager:
    def __init__(
        self,
        paths: ProjectPaths,
        config: ProjectConfig,
        workflows: WorkflowStore,
        agents: AgentStore,
        repository: RunRepository,
        events: EventBus,
    ) -> None:
        self.paths = paths
        self.config = config
        self.workflows = workflows
        self.agents = agents
        self.repository = repository
        self.bus = events
        self.gate = QueueApprovalGate()
        self.tasks: dict[str, asyncio.Task[RunDetail]] = {}

    def recover_interrupted(self) -> int:
        """Tras un reinicio, marca como pausadas las ejecuciones en curso."""
        recovered = 0
        for summary in self.repository.list_runs(limit=500):
            if summary.status != RunStatus.RUNNING:
                continue
            run = self.repository.get_run(summary.id)
            if run is None:
                continue
            run.status = RunStatus.PAUSED
            run.approval = None
            self.repository.save_run(run)
            self._emit(
                run.id, "run_paused", "Ejecución pausada tras reiniciar el servidor.", "warning"
            )
            recovered += 1
        return recovered

    async def start(
        self,
        workflow_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        gate: ApprovalGate | None = None,
    ) -> RunDetail:
        workflow = self.workflows.get(workflow_id)
        issues = validate_workflow(
            workflow,
            agent_ids={agent.id for agent in self.agents.list()},
            max_iterations_limit=10,
        )
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            detail = "; ".join(f"{issue.path}: {issue.message}" for issue in errors)
            raise ValidationError(f"Workflow inválido: {detail}")

        resolved_inputs: dict[str, Any] = {}
        for declared in workflow.inputs:
            value = (inputs or {}).get(declared.id, declared.default)
            if declared.required and value is None:
                raise ValidationError(f"Falta la entrada requerida: {declared.id}")
            resolved_inputs[declared.id] = value
        for key, value in (inputs or {}).items():
            if key not in resolved_inputs:
                resolved_inputs[key] = value

        run = RunDetail(
            id=uuid.uuid4().hex[:12],
            workflow_id=workflow_id,
            inputs=resolved_inputs,
            nodes=[NodeState(node_id=node.id) for node in workflow.nodes],
        )
        self.repository.create_run(run)
        self._emit(run.id, "run_created", f"Ejecución creada para {workflow_id}.")
        task = asyncio.create_task(
            self._execute(run, workflow, gate or self.gate), name=f"penfold-run-{run.id}"
        )
        self.tasks[run.id] = task
        return run

    async def _execute(self, run: RunDetail, workflow: Any, gate: ApprovalGate) -> RunDetail:
        engine = GraphWorkflowEngine(
            EngineContext(
                workflow=workflow,
                run=run,
                paths=self.paths,
                config=self.config,
                agents=self.agents,
                repository=self.repository,
                events=self.bus,
                gate=gate,
            )
        )
        try:
            await engine.execute()
        except Exception as exc:  # pragma: no cover - engine ya maneja sus errores
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.finished_at = utcnow()
            self.repository.save_run(run)
        finally:
            self.tasks.pop(run.id, None)
            gate.shutdown(run.id)
        return run

    async def wait(self, run_id: str, timeout: float | None = None) -> RunDetail:
        task = self.tasks.get(run_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        else:
            # Proceso distinto (CLI siguiendo logs): sondear persistencia.
            async def poll() -> None:
                while True:
                    run = self.repository.get_run(run_id)
                    if run is None or run.status.terminal or run.status == RunStatus.PAUSED:
                        return
                    await asyncio.sleep(0.4)

            await asyncio.wait_for(poll(), timeout=timeout)
        run = self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Ejecución {run_id!r} no encontrada")
        return run

    def get(self, run_id: str) -> RunDetail:
        run = self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Ejecución {run_id!r} no encontrada")
        return run

    def list(self, workflow_id: str | None = None, limit: int = 50) -> list[Any]:
        return self.repository.list_runs(workflow_id=workflow_id, limit=limit)

    def events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        self.get(run_id)
        return self.repository.list_events(run_id, after=after)

    def cancel(self, run_id: str) -> None:
        run = self.get(run_id)
        if run.status.terminal:
            raise ValidationError(f"No se puede cancelar una ejecución {run.status.value}.")
        self.repository.request_cancel(run_id)
        self.gate.cancel(run_id)
        task = self.tasks.get(run_id)
        if task is not None and not task.done():
            # El motor comprueba el flag entre nodos; el gate libera aprobaciones.
            pass
        self._emit(run_id, "cancel_requested", "Cancelación solicitada por el usuario.", "warning")
        run.status = RunStatus.CANCELLED
        run.finished_at = run.finished_at or utcnow()
        self.repository.save_run(run)

    async def resume(self, run_id: str) -> RunDetail:
        run = self.get(run_id)
        if run.status not in {RunStatus.PAUSED, RunStatus.WAITING_APPROVAL}:
            raise ValidationError(
                f"Solo se pueden reanudar ejecuciones pausadas (estado: {run.status.value})."
            )
        workflow = self.workflows.get(run.workflow_id)
        engine = GraphWorkflowEngine(
            EngineContext(
                workflow=workflow,
                run=run,
                paths=self.paths,
                config=self.config,
                agents=self.agents,
                repository=self.repository,
                events=self.bus,
                gate=self.gate,
            )
        )
        engine.prepare_resume()
        task = asyncio.create_task(
            self._execute(run, workflow, self.gate), name=f"penfold-resume-{run.id}"
        )
        self.tasks[run.id] = task
        return run

    def approve(self, run_id: str, request: ApprovalRequest) -> None:
        run = self.get(run_id)
        if run.status != RunStatus.WAITING_APPROVAL or run.approval is None:
            raise ValidationError("La ejecución no tiene una aprobación pendiente.")
        if not self.gate.submit(
            run_id,
            ApprovalDecision(decision=request.decision, data=request.data, note=request.note),
        ):
            raise ValidationError("La aprobación ya fue resuelta o la ejecución ya no está activa.")

    def _emit(self, run_id: str, event_type: str, message: str, level: str = "info") -> None:
        event = self.repository.append_event(
            RunEvent(run_id=run_id, type=event_type, level=level, message=message)  # type: ignore[arg-type]
        )
        self.bus.publish(event)
