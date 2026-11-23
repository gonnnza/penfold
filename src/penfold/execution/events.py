"""Bus de eventos en memoria, alimentado por el motor y consumido por SSE/CLI."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from penfold.execution.models import RunEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent]]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent]:
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent]) -> None:
        subscribers = self._subscribers.get(run_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    def publish(self, event: RunEvent) -> None:
        for queue in list(self._subscribers.get(event.run_id, ())):
            queue.put_nowait(event)

    def publish_all(self, run_id: str, event: RunEvent) -> None:
        self.publish(event)
