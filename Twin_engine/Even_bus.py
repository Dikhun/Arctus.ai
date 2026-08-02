from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from .models import ChangeEvent
logger = structlog.get_logger()


class EventBus:
    """
    Async publish-subscribe pipeline for ChangeEvents.
    Subscribers are async callables; delivery is concurrent.
    """

    def __init__(self, maxsize: int = 10_000):
        self._queue: asyncio.Queue[ChangeEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: list[Callable[[ChangeEvent], Coroutine[Any, Any, None]]] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, handler: Callable[[ChangeEvent], Coroutine[Any, Any, None]]) -> None:
        self._subscribers.append(handler)

    async def emit(self, event: ChangeEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("event_queue_overflow", dropped_event=event.event_id)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await self._dispatch(event)
            self._queue.task_done()

    async def _dispatch(self, event: ChangeEvent) -> None:
        if not self._subscribers:
            return
        results = await asyncio.gather(
            *[self._safe_call(h, event) for h in self._subscribers],
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, Exception):
                logger.error("event_handler_failed", exception=str(exc))

    async def _safe_call(self, handler: Callable, event: ChangeEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.error("subscriber_error", handler=handler.__name__, error=str(exc))
