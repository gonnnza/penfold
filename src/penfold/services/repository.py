"""Persistencia SQLite de ejecuciones, estados, eventos y aprobaciones."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy import (
    event as sa_event,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from penfold.models.execution import (
    ApprovalInfo,
    NodeState,
    RunDetail,
    RunEvent,
    RunSummary,
)

Base = declarative_base()


def _dump(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def _load(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class RunRow(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, nullable=False, index=True)
    workflow_version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, index=True)
    inputs_json = Column(Text, nullable=False, default="{}")
    outputs_json = Column(Text)
    approval_json = Column(Text)
    error = Column(Text)
    created_at = Column(String, nullable=False)
    started_at = Column(String)
    finished_at = Column(String)
    cancel_requested = Column(Integer, nullable=False, default=0)


class NodeStateRow(Base):
    __tablename__ = "node_states"

    run_id = Column(String, ForeignKey("runs.id"), primary_key=True)
    node_id = Column(String, primary_key=True)
    status = Column(String, nullable=False)
    iteration = Column(Integer, nullable=False, default=0)
    started_at = Column(String)
    finished_at = Column(String)
    duration_ms = Column(Integer)
    input_json = Column(Text)
    output_json = Column(Text)
    error = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    runtime = Column(String)
    simulated = Column(Integer, nullable=False, default=0)


class EventRow(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False, default=0)
    type = Column(String, nullable=False)
    level = Column(String, nullable=False, default="info")
    node_id = Column(String)
    message = Column(Text, nullable=False)
    data_json = Column(Text)
    timestamp = Column(String, nullable=False)


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    decision = Column(String)
    data_json = Column(Text)
    note = Column(Text)
    decided_at = Column(String)


Index("ix_events_run_seq", EventRow.run_id, EventRow.seq)


class RunRepository:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )

        @sa_event.listens_for(self.engine, "connect")
        def _pragma(dbapi_connection, _record):  # pragma: no cover - SQLite specifics
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _row_to_run(self, row: RunRow, session: Session) -> RunDetail:
        states = session.scalars(
            select(NodeStateRow).where(NodeStateRow.run_id == row.id).order_by(NodeStateRow.node_id)
        ).all()
        return RunDetail(
            id=row.id,
            workflow_id=row.workflow_id,
            workflow_version=row.workflow_version,
            status=row.status,
            inputs=_load(row.inputs_json, {}),
            outputs=_load(row.outputs_json),
            approval=ApprovalInfo.model_validate(_load(row.approval_json))
            if row.approval_json
            else None,
            error=row.error,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            nodes=[
                NodeState(
                    node_id=state.node_id,
                    status=state.status,
                    iteration=state.iteration,
                    started_at=state.started_at,
                    finished_at=state.finished_at,
                    duration_ms=state.duration_ms,
                    input=_load(state.input_json),
                    output=_load(state.output_json),
                    error=state.error,
                    attempts=state.attempts,
                    runtime=state.runtime,
                    simulated=bool(state.simulated),
                )
                for state in states
            ],
        )

    def create_run(self, run: RunDetail) -> RunDetail:
        with self.Session() as session:
            session.add(
                RunRow(
                    id=run.id,
                    workflow_id=run.workflow_id,
                    workflow_version=run.workflow_version,
                    status=run.status.value,
                    inputs_json=_dump(run.inputs) or "{}",
                    outputs_json=_dump(run.outputs),
                    approval_json=_dump(run.approval.model_dump() if run.approval else None),
                    error=run.error,
                    created_at=run.created_at,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                )
            )
            for state in run.nodes:
                session.add(self._state_row(run.id, state))
            session.commit()
        return run

    @staticmethod
    def _state_row(run_id: str, state: NodeState) -> NodeStateRow:
        return NodeStateRow(
            run_id=run_id,
            node_id=state.node_id,
            status=state.status.value,
            iteration=state.iteration,
            started_at=state.started_at,
            finished_at=state.finished_at,
            duration_ms=state.duration_ms,
            input_json=_dump(state.input),
            output_json=_dump(state.output),
            error=state.error,
            attempts=state.attempts,
            runtime=state.runtime,
            simulated=int(state.simulated),
        )

    def save_run(self, run: RunDetail) -> None:
        with self.Session() as session:
            row = session.get(RunRow, run.id)
            if row is None:
                raise KeyError(f"Run {run.id} no existe")
            row.status = run.status.value
            row.inputs_json = _dump(run.inputs) or "{}"
            row.outputs_json = _dump(run.outputs)
            row.approval_json = _dump(run.approval.model_dump() if run.approval else None)
            row.error = run.error
            row.started_at = run.started_at
            row.finished_at = run.finished_at
            session.commit()

    def save_node_state(self, run_id: str, state: NodeState) -> None:
        with self.Session() as session:
            row = session.get(NodeStateRow, (run_id, state.node_id))
            if row is None:
                session.add(self._state_row(run_id, state))
            else:
                for column, value in {
                    "status": state.status.value,
                    "iteration": state.iteration,
                    "started_at": state.started_at,
                    "finished_at": state.finished_at,
                    "duration_ms": state.duration_ms,
                    "input_json": _dump(state.input),
                    "output_json": _dump(state.output),
                    "error": state.error,
                    "attempts": state.attempts,
                    "runtime": state.runtime,
                    "simulated": int(state.simulated),
                }.items():
                    setattr(row, column, value)
            session.commit()

    def get_run(self, run_id: str) -> RunDetail | None:
        with self.Session() as session:
            row = session.get(RunRow, run_id)
            return self._row_to_run(row, session) if row is not None else None

    def list_runs(self, workflow_id: str | None = None, limit: int = 50) -> list[RunSummary]:
        with self.Session() as session:
            statement = select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
            if workflow_id:
                statement = statement.where(RunRow.workflow_id == workflow_id)
            rows = session.scalars(statement).all()
            counts = dict(
                session.execute(
                    select(NodeStateRow.run_id, func.count()).group_by(NodeStateRow.run_id)
                ).all()
            )
            return [
                RunSummary(
                    id=row.id,
                    workflow_id=row.workflow_id,
                    status=row.status,
                    created_at=row.created_at,
                    finished_at=row.finished_at,
                    node_count=counts.get(row.id, 0),
                )
                for row in rows
            ]

    def is_cancel_requested(self, run_id: str) -> bool:
        with self.Session() as session:
            row = session.get(RunRow, run_id)
            return bool(row and row.cancel_requested)

    def request_cancel(self, run_id: str) -> None:
        with self.Session() as session:
            row = session.get(RunRow, run_id)
            if row is not None:
                row.cancel_requested = 1
                session.commit()

    def append_event(self, event: RunEvent) -> RunEvent:
        with self.Session() as session:
            seq = session.scalar(
                select(func.coalesce(func.max(EventRow.seq), 0) + 1).where(
                    EventRow.run_id == event.run_id
                )
            )
            row = EventRow(
                run_id=event.run_id,
                seq=seq or 1,
                type=event.type,
                level=event.level,
                node_id=event.node_id,
                message=event.message,
                data_json=_dump(event.data),
                timestamp=event.timestamp,
            )
            session.add(row)
            session.commit()
            return RunEvent(
                id=row.id,
                run_id=row.run_id,
                seq=row.seq,
                type=event.type,
                level=event.level,
                node_id=event.node_id,
                message=event.message,
                data=event.data,
                timestamp=event.timestamp,
            )

    def list_events(self, run_id: str, after: int = 0, limit: int = 1000) -> list[RunEvent]:
        with self.Session() as session:
            rows = session.scalars(
                select(EventRow)
                .where(EventRow.run_id == run_id, EventRow.seq > after)
                .order_by(EventRow.seq)
                .limit(limit)
            ).all()
            return [
                RunEvent(
                    id=row.id,
                    run_id=row.run_id,
                    seq=row.seq,
                    type=row.type,
                    level=row.level,
                    node_id=row.node_id,
                    message=row.message,
                    data=_load(row.data_json),
                    timestamp=row.timestamp,
                )
                for row in rows
            ]

    def record_approval(
        self,
        run_id: str,
        node_id: str,
        decision: str,
        data: Any = None,
        note: str | None = None,
        decided_at: str | None = None,
    ) -> None:
        with self.Session() as session:
            session.add(
                ApprovalRow(
                    run_id=run_id,
                    node_id=node_id,
                    decision=decision,
                    data_json=_dump(data),
                    note=note,
                    decided_at=decided_at,
                )
            )
            session.commit()
