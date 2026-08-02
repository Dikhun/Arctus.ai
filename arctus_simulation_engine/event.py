from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from arctus_simulation_engine.primitives import SimulationTime


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    event_type: str
    timestamp: SimulationTime
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class EventBus(Protocol):
    async def publish(self, event: SimulationEvent) -> None:
        ...

    async def subscribe(self, event_type: str, handler: Any) -> Any:
        ...
