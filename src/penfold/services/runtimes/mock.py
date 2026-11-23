"""Runtime simulado para tests y demostraciones aisladas.

Nunca se presenta como una ejecución real: la salida incluye una marca y el
campo ``simulated`` viaja hasta la interfaz.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from penfold.errors import CancelledError
from penfold.services.runtimes.base import AgentRuntime, RuntimeContext, RuntimeResult


class MockRuntime(AgentRuntime):
    name = "mock"
    simulated = True

    async def validate(self) -> None:
        return None

    async def healthcheck(self) -> bool:
        return True

    async def execute(self, context: RuntimeContext) -> RuntimeResult:
        delay = float(context.options.get("delay_seconds", 0.0))
        if delay > 0:
            if context.cancel_event is not None:
                try:
                    await asyncio.wait_for(context.cancel_event.wait(), timeout=delay)
                    raise CancelledError("Ejecución cancelada durante la simulación.")
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(delay)

        output: dict[str, Any]
        sequences = context.options.get("mock_outputs")
        if isinstance(sequences, list) and sequences:
            output = copy.deepcopy(sequences[min(context.attempt - 1, len(sequences) - 1)])
        elif context.agent is not None and context.agent.mock.output is not None:
            output = copy.deepcopy(context.agent.mock.output)
        else:
            output = {
                "message": "Ejecución SIMULADA con MockRuntime",
                "agent": context.agent.id if context.agent else None,
                "inputs": copy.deepcopy(context.inputs),
            }
        output.setdefault("_simulated", True)
        return RuntimeResult(
            output=output,
            logs=[f"[MOCK] Nodo {context.node_id}: ejecución SIMULADA (sin agente real)."],
            metadata={"runtime": self.name, "simulated": True},
        )
