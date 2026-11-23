"""Modelos de estado de ejecución (persistidos y expuestos por la API)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class RunStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class NodeStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED,
            NodeStatus.SKIPPED,
            NodeStatus.CANCELLED,
        }


class NodeState(BaseModel):
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    iteration: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    runtime: str | None = None
    simulated: bool = False


class ApprovalInfo(BaseModel):
    node_id: str
    title: str
    data: Any = None


class RunDetail(BaseModel):
    id: str
    workflow_id: str
    workflow_version: int = 1
    status: RunStatus = RunStatus.CREATED
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] | None = None
    approval: ApprovalInfo | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utcnow)
    started_at: str | None = None
    finished_at: str | None = None
    nodes: list[NodeState] = Field(default_factory=list)

    def node(self, node_id: str) -> NodeState | None:
        return next((state for state in self.nodes if state.node_id == node_id), None)


class RunSummary(BaseModel):
    id: str
    workflow_id: str
    status: RunStatus
    created_at: str
    finished_at: str | None = None
    node_count: int = 0


class RunEvent(BaseModel):
    id: int = 0
    run_id: str
    seq: int = 0
    type: str
    level: Literal["info", "success", "warning", "error"] = "info"
    node_id: str | None = None
    message: str
    data: dict[str, Any] | None = None
    timestamp: str = Field(default_factory=utcnow)


class StartRunRequest(BaseModel):
    workflow_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject", "modify", "cancel"]
    data: Any = None
    note: str | None = None
