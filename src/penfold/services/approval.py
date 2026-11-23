"""Puerta de aprobación humana (human-in-the-loop)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from penfold.errors import ExecutionError
from penfold.models.approval import ApprovalDecision


class ApprovalGate(ABC):
    @abstractmethod
    async def request(
        self,
        run_id: str,
        node_id: str,
        title: str,
        message: str,
        data: Any,
    ) -> ApprovalDecision: ...

    def cancel(self, run_id: str) -> None:
        """Libera las esperas pendientes de una ejecución cancelada."""

    def shutdown(self, run_id: str) -> None:
        """Limpia estructuras cuando la ejecución termina."""


class AutoApproveGate(ApprovalGate):
    """Solo para tests: aprueba automáticamente sin simulación de interfaz."""

    async def request(self, run_id, node_id, title, message, data) -> ApprovalDecision:
        return ApprovalDecision(decision="approve", note="auto-aprobado en test")


class QueueApprovalGate(ApprovalGate):
    """Usada por el servidor: la API resuelve la espera con POST /approve."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ApprovalDecision]] = {}

    def has_pending(self, run_id: str) -> bool:
        future = self._pending.get(run_id)
        return future is not None and not future.done()

    def submit(self, run_id: str, decision: ApprovalDecision) -> bool:
        future = self._pending.get(run_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    async def request(self, run_id, node_id, title, message, data) -> ApprovalDecision:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._pending[run_id] = future
        try:
            return await future
        finally:
            if self._pending.get(run_id) is future:
                self._pending.pop(run_id, None)

    def cancel(self, run_id: str) -> None:
        self.submit(run_id, ApprovalDecision(decision="cancel"))

    def shutdown(self, run_id: str) -> None:
        future = self._pending.pop(run_id, None)
        if future is not None and not future.done():
            future.cancel()


class ConsoleApprovalGate(ApprovalGate):
    """Aprobación por terminal para ejecuciones CLI interactivas."""

    async def request(self, run_id, node_id, title, message, data) -> ApprovalDecision:

        print(f"\n[Aprobación requerida] {title}")

        if message:
            print(message)

        try:
            answer = await asyncio.to_thread(input, "¿Aprobar? [s/n]: ")
        except EOFError as e:
            raise ExecutionError(
                "Se requiere aprobación humana pero la terminal no es interactiva. "
                "Usa el servidor local y la interfaz para aprobar."
            ) from e
        if answer.strip().lower() in {"s", "si", "sí", "y", "yes"}:
            return ApprovalDecision(decision="approve")
        return ApprovalDecision(decision="reject", note="rechazado desde la terminal")
