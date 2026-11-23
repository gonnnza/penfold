"""Motor de ejecución de grafos.

Interpreta la definición del workflow, resuelve dependencias, ejecuta nodos,
aplica contratos, evalúa condiciones, limita ciclos y persiste checkpoints.
No conoce React, FastAPI ni proveedores concretos de IA.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError as SchemaValidationError
from jsonschema import validate as validate_schema

from penfold.agents.store import AgentStore
from penfold.config.models import ProjectConfig
from penfold.config.paths import ProjectPaths
from penfold.errors import (
    CancelledError,
    ContextResolutionError,
    ContractError,
    ExecutionError,
    PermissionDeniedError,
    ValidationError,
)
from penfold.execution.approval import ApprovalDecision, ApprovalGate
from penfold.execution.context import ContextResolver
from penfold.execution.events import EventBus
from penfold.execution.models import (
    ApprovalInfo,
    NodeState,
    NodeStatus,
    RunDetail,
    RunEvent,
    RunStatus,
    utcnow,
)
from penfold.execution.repository import RunRepository
from penfold.runtimes.base import RuntimeContext, RuntimeResult
from penfold.runtimes.registry import get_runtime
from penfold.runtimes.secrets import redact
from penfold.workflows.models import WorkflowDefinition, WorkflowEdge, WorkflowNode
from penfold.workflows.validator import cyclic_edges

RETRYABLE = (ExecutionError, ContractError, ContextResolutionError, ValidationError)


@dataclass
class EngineContext:
    workflow: WorkflowDefinition
    run: RunDetail
    paths: ProjectPaths
    config: ProjectConfig
    agents: AgentStore
    repository: RunRepository
    events: EventBus
    gate: ApprovalGate


class GraphWorkflowEngine:
    """Ejecutor nativo del grafo, detrás del protocolo ``ExecutionEngine``."""

    def __init__(self, context: EngineContext):
        self.ctx = context
        self.run = context.run
        self.workflow = context.workflow
        self.nodes: dict[str, WorkflowNode] = {node.id: node for node in self.workflow.nodes}
        self.incoming: dict[str, list[WorkflowEdge]] = defaultdict(list)
        self.outgoing: dict[str, list[WorkflowEdge]] = defaultdict(list)
        for edge in self.workflow.edges:
            if edge.source in self.nodes and edge.target in self.nodes:
                self.outgoing[edge.source].append(edge)
                self.incoming[edge.target].append(edge)
        self.cyclic = cyclic_edges(self.workflow)
        self.depths = self._compute_depths()
        self.states: dict[str, NodeState] = {state.node_id: state for state in self.run.nodes}
        for node in self.workflow.nodes:
            self.states.setdefault(node.id, NodeState(node_id=node.id))
        self.run.nodes = [self.states[node.id] for node in self.workflow.nodes]
        self.cancel_event = asyncio.Event()
        self._blocked_edges: set[str] = set()
        self._loop_limits: list[str] = []

    # ---------- preparación ----------

    def _compute_depths(self) -> dict[str, int]:
        forward = [edge for edge in self.workflow.edges if edge.id not in self.cyclic]
        indegree: dict[str, int] = {node_id: 0 for node_id in self.nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in forward:
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        depth = {node_id: 0 for node_id in self.nodes}
        while queue:
            current = queue.popleft()
            for target in adjacency[current]:
                depth[target] = max(depth[target], depth[current] + 1)
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        return depth

    def prepare_resume(self) -> None:
        """Reanuda desde checkpoints sin repetir nodos ya exitosos."""
        for state in self.states.values():
            if state.status in {NodeStatus.RUNNING, NodeStatus.WAITING_APPROVAL, NodeStatus.READY}:
                state.status = NodeStatus.PENDING
                state.started_at = None
                state.finished_at = None
                state.output = None
                state.error = None
                self._persist_state(state)
        self.run.approval = None
        self.run.status = RunStatus.RUNNING
        self.ctx.repository.save_run(self.run)
        self._emit("run_resumed", "Ejecución reanudada desde checkpoint.")

    # ---------- bucle principal ----------

    async def execute(self) -> RunDetail:
        self.run.status = RunStatus.RUNNING
        self.run.started_at = self.run.started_at or utcnow()
        self.run.error = None
        self.ctx.repository.save_run(self.run)
        self._emit(
            "run_started",
            f"Workflow {self.run.workflow_id} iniciado.",
            data={"run_id": self.run.id},
        )

        try:
            while True:
                if self._is_cancelled():
                    self._cancel_remaining()
                    break

                ready = self._ready_nodes()
                if not ready:
                    if all(state.status.terminal for state in self.states.values()):
                        break
                    blocked = ", ".join(
                        state.node_id for state in self.states.values() if not state.status.terminal
                    )
                    raise ExecutionError(f"El grafo quedó bloqueado en: {blocked}")

                batch = ready[: self.ctx.config.execution.max_concurrency]
                await asyncio.gather(*(self._execute_node(node) for node in batch))
                executed = {node.id for node in batch}
                self._process_loop_retriggers(executed)

            if self._is_cancelled():
                self.run.status = RunStatus.CANCELLED
                self.run.error = "Ejecución cancelada por el usuario."
            elif self._loop_limits:
                self.run.status = RunStatus.FAILED
                self.run.error = "; ".join(self._loop_limits)
            elif any(state.status == NodeStatus.FAILED for state in self.states.values()):
                self.run.status = RunStatus.FAILED
                self.run.error = "Uno o más nodos fallaron. Consulta los logs para el detalle."
            else:
                self.run.status = RunStatus.COMPLETED
        except CancelledError as exc:
            self.run.status = RunStatus.CANCELLED
            self.run.error = str(exc)
            self._cancel_remaining()
        except Exception as exc:  # fallo estructural del motor
            self.run.status = RunStatus.FAILED
            self.run.error = f"Fallo del motor: {exc}"
            self._emit("engine_error", self.run.error, level="error")
        finally:
            self.run.finished_at = utcnow()
            self.run.approval = None
            self.ctx.repository.save_run(self.run)
            self._emit(
                "run_finished",
                f"Ejecución {self.run.status.value}",
                level="success" if self.run.status == RunStatus.COMPLETED else "info",
                data={"status": self.run.status.value, "error": self.run.error},
            )
            self.ctx.gate.shutdown(self.run.id)
        return self.run

    def cancel(self) -> None:
        self.cancel_event.set()
        self.ctx.gate.cancel(self.run.id)

    def _is_cancelled(self) -> bool:
        return self.cancel_event.is_set() or self.ctx.repository.is_cancel_requested(self.run.id)

    def _cancel_remaining(self) -> None:
        for state in self.states.values():
            if not state.status.terminal:
                state.status = NodeStatus.CANCELLED
                state.finished_at = utcnow()
                self._persist_state(state)
        self.run.status = RunStatus.CANCELLED
        self.ctx.repository.save_run(self.run)
        self.ctx.gate.cancel(self.run.id)

    def _ready_nodes(self) -> list[WorkflowNode]:
        ready: list[WorkflowNode] = []
        for node in self.workflow.nodes:
            state = self.states[node.id]
            if state.status.terminal or state.status in {
                NodeStatus.RUNNING,
                NodeStatus.WAITING_APPROVAL,
            }:
                continue
            edges = self.incoming.get(node.id, [])
            if not edges:
                ready.append(node)
                continue
            active: list[WorkflowEdge] = []
            pending_source = False
            future_loop_source = False
            for edge in edges:
                source_state = self.states[edge.source]
                if not source_state.status.terminal:
                    # Una arista de retroceso aún no activada no bloquea la
                    # primera ejecución del nodo; solo importa en el ciclo.
                    if (
                        edge.id in self.cyclic
                        or self.depths[edge.source] >= self.depths[edge.target]
                    ):
                        future_loop_source = True
                    else:
                        pending_source = True
                    continue
                if edge.id in self._blocked_edges or source_state.status in {
                    NodeStatus.SKIPPED,
                    NodeStatus.CANCELLED,
                }:
                    continue
                source_node = self.nodes[edge.source]
                if source_node.type == "condition" and source_state.status == NodeStatus.SUCCEEDED:
                    branch = (source_state.output or {}).get("branch")
                    if branch is not None and edge.source_handle != branch:
                        continue
                active.append(edge)
            # Sincronización explícita: una unión espera a TODOS sus predecesores.
            if pending_source or (not active and future_loop_source):
                continue
            if not active:
                if not pending_source:
                    state.status = NodeStatus.SKIPPED
                    state.finished_at = utcnow()
                    self._persist_state(state)
                    self._emit(
                        "node_skipped",
                        f"Nodo {node.id} omitido: ninguna rama entrante activa.",
                        node_id=node.id,
                    )
                continue
            if any(self.states[edge.source].status == NodeStatus.FAILED for edge in active):
                state.status = NodeStatus.SKIPPED
                state.finished_at = utcnow()
                self._persist_state(state)
                self._emit(
                    "node_skipped",
                    f"Nodo {node.id} omitido: un predecesor falló.",
                    level="warning",
                    node_id=node.id,
                )
                continue
            ready.append(node)
        return ready

    # ---------- ejecución de nodos ----------

    async def _execute_node(self, node: WorkflowNode) -> None:
        state = self.states[node.id]
        state.status = NodeStatus.RUNNING
        state.started_at = utcnow()
        state.error = None
        started = time.monotonic()
        self._persist_state(state)
        self._emit(
            "node_started",
            f"Iniciando {node.label or node.id} ({node.type})",
            node_id=node.id,
            data={"type": node.type, "agent": node.agent},
        )
        try:
            if self._is_cancelled():
                raise CancelledError("Ejecución cancelada.")
            resolver = ContextResolver(self.run.inputs, self._outputs(), self._statuses())
            inputs = resolver.resolve_mapping(node.config.get("inputs"))
            state.input = inputs
            output: dict[str, Any]

            if node.type == "input":
                output = {
                    declared.id: self.run.inputs.get(declared.id, declared.default)
                    for declared in self.workflow.inputs
                }
            elif node.type == "agent":
                output, runtime_name, simulated = await self._execute_agent(node, state, inputs)
                state.runtime = runtime_name
                state.simulated = simulated
            elif node.type == "command":
                result = await self._execute_command(node, state, inputs)
                output = result.output
                state.runtime = "command"
            elif node.type == "condition":
                output = self._evaluate_condition(node, inputs)
            elif node.type == "approval":
                output = await self._execute_approval(node, state, inputs)
            elif node.type == "output":
                output = {
                    "format": node.config.get("format", "json"),
                    "data": inputs,
                }
                self.run.outputs = output
            else:  # pragma: no cover - validado por Pydantic
                raise ExecutionError(f"Tipo de nodo no soportado: {node.type}")

            state.output = output
            state.status = NodeStatus.SUCCEEDED
            self._emit(
                "node_succeeded",
                f"Completado {node.label or node.id}",
                level="success",
                node_id=node.id,
                data=self._summary(output),
            )
        except CancelledError as exc:
            state.status = NodeStatus.CANCELLED
            state.error = str(exc)
            self._emit("node_cancelled", str(exc), level="warning", node_id=node.id)
        except Exception as exc:
            state.status = NodeStatus.FAILED
            state.error = redact(str(exc))
            self._emit(
                "node_failed",
                f"Falló {node.label or node.id}: {state.error}",
                level="error",
                node_id=node.id,
                data={"error_type": type(exc).__name__},
            )
        finally:
            state.finished_at = utcnow()
            state.duration_ms = int((time.monotonic() - started) * 1000)
            self._persist_state(state)
            self.ctx.repository.save_run(self.run)

    async def _execute_agent(
        self, node: WorkflowNode, state: NodeState, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], str, bool]:
        if not node.agent:
            raise ValidationError(f"El nodo {node.id} no declara un agente.")
        agent = self.ctx.agents.get(node.agent)
        runtime = get_runtime(agent.runtime.type)
        await runtime.validate()
        options: dict[str, Any] = {
            "delay_seconds": agent.mock.delay_seconds,
            "max_output_chars": self.ctx.config.execution.max_output_chars,
        }
        max_retries = int(node.config.get("retries", agent.retries))
        max_retries = min(max_retries, self.ctx.config.execution.max_retries)
        timeout = int(node.config.get("timeout", agent.timeout))
        result = await self._with_retries(
            runtime,
            RuntimeContext(
                run_id=self.run.id,
                node_id=node.id,
                agent=agent,
                inputs=inputs,
                workspace=self.ctx.paths.root,
                timeout=timeout,
                options=options,
                cancel_event=self.cancel_event,
            ),
            max_retries=max_retries,
            state=state,
            validate_output=agent.outputs.json_schema if agent.outputs.format == "json" else None,
        )
        output = dict(result.output)
        return (
            output,
            f"{runtime.name}:{agent.id}",
            bool(runtime.simulated or output.get("_simulated")),
        )

    async def _execute_command(
        self, node: WorkflowNode, state: NodeState, inputs: dict[str, Any]
    ) -> RuntimeResult:
        runtime = get_runtime("command")
        timeout = int(node.config.get("timeout", self.ctx.config.execution.default_timeout_seconds))
        options = {
            "command": node.config.get("command"),
            "cwd": node.config.get("cwd", "."),
            "max_output_chars": self.ctx.config.execution.max_output_chars,
            "artifacts_dir": self.ctx.paths.artifacts_dir / self.run.id,
            "permissions": {
                "mode": self.ctx.config.security.default_permission_mode,
                "allowed_commands": node.config.get("allowed_commands", []),
            },
        }
        return await self._with_retries(
            runtime,
            RuntimeContext(
                run_id=self.run.id,
                node_id=node.id,
                inputs=inputs,
                workspace=self.ctx.paths.root,
                timeout=timeout,
                options=options,
                cancel_event=self.cancel_event,
            ),
            max_retries=min(
                int(node.config.get("retries", 0)), self.ctx.config.execution.max_retries
            ),
            state=state,
            validate_output=None,
        )

    async def _with_retries(
        self,
        runtime: Any,
        context: RuntimeContext,
        *,
        max_retries: int,
        state: NodeState,
        validate_output: dict[str, Any] | None,
    ) -> RuntimeResult:
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 2):
            if self._is_cancelled():
                raise CancelledError("Ejecución cancelada.")
            context.attempt = attempt
            state.attempts += 1
            try:
                result: RuntimeResult = await runtime.execute(context)
                if validate_output:
                    try:
                        validate_schema(instance=result.output, schema=validate_output)
                    except SchemaValidationError as exc:
                        raise ContractError(
                            f"La salida de {context.node_id} no cumple el contrato JSON Schema: "
                            f"{exc.message} (ruta: {'/'.join(map(str, exc.absolute_path))})"
                        ) from exc
                return result
            except (CancelledError, PermissionDeniedError):
                raise
            except RETRYABLE as exc:
                last_error = exc
                if attempt > max_retries:
                    raise
                self._emit(
                    "node_retry",
                    f"Reintentando {context.node_id} ({attempt}/{max_retries}): {exc}",
                    level="warning",
                    node_id=context.node_id,
                )
                await asyncio.sleep(0.15 * attempt)
        raise ExecutionError(f"Agotados los reintentos: {last_error}")

    # ---------- lógica ----------

    def _evaluate_condition(self, node: WorkflowNode, inputs: dict[str, Any]) -> dict[str, Any]:
        expression = node.config.get("expression")
        if not isinstance(expression, dict):
            raise ValidationError("La condición no tiene una expresión válida.")
        field = expression.get("field")
        op = expression.get("op")
        expected = expression.get("value")
        actual = inputs.get(str(field))
        if op == "eq":
            result = actual == expected
        elif op == "ne":
            result = actual != expected
        elif op == "gt":
            result = actual is not None and actual > expected
        elif op == "gte":
            result = actual is not None and actual >= expected
        elif op == "lt":
            result = actual is not None and actual < expected
        elif op == "lte":
            result = actual is not None and actual <= expected
        elif op == "contains":
            result = actual is not None and expected in actual
        elif op == "in":
            result = isinstance(expected, list) and actual in expected
        elif op == "exists":
            result = actual is not None
        else:
            raise ValidationError(f"Operador de condición no soportado: {op!r}")
        return {
            "result": bool(result),
            "branch": "pass" if result else "fail",
            "field": field,
            "actual": actual,
            "expected": expected,
        }

    async def _execute_approval(
        self, node: WorkflowNode, state: NodeState, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        title = str(node.config.get("title") or node.label or f"Aprobación: {node.id}")
        message = str(node.config.get("message") or "")
        state.status = NodeStatus.WAITING_APPROVAL
        self.run.status = RunStatus.WAITING_APPROVAL
        self.run.approval = ApprovalInfo(node_id=node.id, title=title, data=inputs)
        self._persist_state(state)
        self.ctx.repository.save_run(self.run)
        self._emit(
            "approval_requested",
            f"Aprobación pendiente: {title}",
            level="warning",
            node_id=node.id,
        )
        decision: ApprovalDecision = await self.ctx.gate.request(
            self.run.id, node.id, title, message, inputs
        )
        self.run.approval = None
        self.run.status = RunStatus.RUNNING
        self.ctx.repository.save_run(self.run)
        self.ctx.repository.record_approval(
            self.run.id, node.id, decision.decision, decision.data, decision.note, utcnow()
        )
        if decision.decision == "cancel":
            raise CancelledError("Aprobación cancelada por el usuario.")
        if decision.decision == "reject":
            raise ExecutionError(f"Aprobación rechazada. {decision.note or ''}".strip())
        data = (
            decision.data if decision.decision == "modify" and decision.data is not None else inputs
        )
        self._emit(
            "approval_resolved",
            f"Aprobación resuelta: {decision.decision}",
            node_id=node.id,
        )
        return {"decision": decision.decision, "data": data, "note": decision.note}

    def _process_loop_retriggers(self, executed: set[str]) -> None:
        for edge in self.workflow.edges:
            if edge.source not in executed or edge.id not in self.cyclic:
                continue
            if edge.id in self._blocked_edges:
                continue
            source_state = self.states[edge.source]
            if source_state.status != NodeStatus.SUCCEEDED:
                continue
            branch = (source_state.output or {}).get("branch")
            if edge.source_handle not in {"fail", "default"} or (
                branch and branch != edge.source_handle
            ):
                continue
            target = self.states[edge.target]
            if edge.target in executed or not target.status.terminal:
                continue
            limit = int(
                edge.config.max_iterations
                or self.nodes[edge.target].config.get("max_iterations", 0)
                or self.ctx.config.execution.max_iterations
            )
            limit = min(limit, 10)
            next_iteration = target.iteration + 1
            if next_iteration > limit:
                message = (
                    f"Límite de iteraciones alcanzado ({limit}) en el ciclo "
                    f"{edge.source} -> {edge.target}."
                )
                self._loop_limits.append(message)
                self._emit("loop_limit", message, level="error", node_id=edge.target)
                self._blocked_edges.add(edge.id)
                continue
            self._reset_subgraph(edge.target)
            self._emit(
                "loop_iteration",
                f"Nueva iteración {next_iteration}/{limit} en {edge.target}",
                level="warning",
                node_id=edge.target,
                data={"iteration": next_iteration, "limit": limit},
            )

    def _reset_subgraph(self, root_id: str) -> None:
        queue = deque([root_id])
        visited: set[str] = set()
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            state = self.states[node_id]
            if state.status.terminal:
                state.status = NodeStatus.PENDING
                state.iteration += 1
                state.started_at = None
                state.finished_at = None
                state.output = None
                state.input = None
                state.error = None
                self._persist_state(state)
            for edge in self.outgoing.get(node_id, []):
                if edge.target not in visited and edge.id not in self._blocked_edges:
                    queue.append(edge.target)

    # ---------- helpers ----------

    def _outputs(self) -> dict[str, Any]:
        return {
            node_id: state.output
            for node_id, state in self.states.items()
            if state.status == NodeStatus.SUCCEEDED
        }

    def _statuses(self) -> dict[str, str]:
        result = {node_id: state.status.value for node_id, state in self.states.items()}
        for node_id, state in self.states.items():
            if state.error:
                result[f"{node_id}:error"] = state.error
        return result

    def _persist_state(self, state: NodeState) -> None:
        self.ctx.repository.save_node_state(self.run.id, state)

    @staticmethod
    def _summary(output: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for key, value in output.items():
            if isinstance(value, str):
                summary[key] = value[:300]
            elif isinstance(value, (list, dict)):
                summary[key] = f"<{type(value).__name__} de {len(value)} elementos>"
            else:
                summary[key] = value
        return summary

    def _emit(
        self,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        node_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = RunEvent(
            run_id=self.run.id,
            type=event_type,
            level=level,  # type: ignore[arg-type]
            node_id=node_id,
            message=redact(message),
            data=data,
        )
        stored = self.ctx.repository.append_event(event)
        self.ctx.events.publish(stored)
        try:
            target_dir = self.ctx.paths.runs_dir / self.run.id
            target_dir.mkdir(parents=True, exist_ok=True)
            with (target_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(stored.model_dump_json() + "\n")
        except OSError:  # pragma: no cover
            pass
