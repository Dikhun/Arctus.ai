from __future__ import annotations

import heapq
import uuid
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from arctus_simulation_engine.primitives import SimulationTime, EventId, Duration
from arctus_simulation_engine.events import SimulationEvent
from arctus_simulation_engine.core.virtual_time import VirtualTime
from arctus_simulation_engine.ports import EventBus


@dataclass(slots=True)
class _ScheduledItem:
    time: SimulationTime
    tie_breaker: int
    event_id: EventId
    callback: Callable[[], Awaitable[None]]
    priority: int
    cancelled: bool = False

    def __lt__(self, other: _ScheduledItem) -> bool:
        if self.time != other.time:
            return self.time < other.time
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.tie_breaker < other.tie_breaker


class DiscreteEventScheduler:
    def __init__(self, virtual_time: VirtualTime, event_bus: EventBus) -> None:
        self._queue: list[_ScheduledItem] = []
        self._counter = 0
        self._virtual_time = virtual_time
        self._event_bus = event_bus
        self._running = False

    def schedule_absolute(self, time: SimulationTime, callback: Callable[[], Awaitable[None]], priority: int = 0) -> EventId:
        if time < self._virtual_time.now:
            raise ValueError("Cannot schedule event in the past")
        self._counter += 1
        event_id = EventId(uuid.uuid4().hex)
        item = _ScheduledItem(time, self._counter, event_id, callback, priority)
        heapq.heappush(self._queue, item)
        return event_id

    def schedule_relative(self, delay: Duration, callback: Callable[[], Awaitable[None]], priority: int = 0) -> EventId:
        return self.schedule_absolute(self._virtual_time.now + delay, callback, priority)

    def cancel(self, event_id: EventId) -> bool:
        for item in self._queue:
            if item.event_id == event_id and not item.cancelled:
                item.cancelled = True
                return True
        return False

    async def step(self) -> bool:
        while self._queue:
            item = heapq.heappop(self._queue)
            if item.cancelled:
                continue
            if item.time > self._virtual_time.now:
                self._virtual_time.set(item.time)
            await item.callback()
            await self._event_bus.publish(SimulationEvent(
                event_type="scheduler.event_executed",
                timestamp=self._virtual_time.now,
                source="DiscreteEventScheduler",
                payload={"event_id": item.event_id},
            ))
            return True
        return False

    async def run(self) -> None:
        self._running = True
        try:
            while self._running and await self.step():
                pass
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False

    def clear(self) -> None:
        self._queue.clear()

    @property
    def event_count(self) -> int:
        return sum(1 for item in self._queue if not item.cancelled)
