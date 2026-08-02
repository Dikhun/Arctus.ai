from __future__ import annotations

import asyncio
import copy
from typing import Any, Callable

from arctus_simulation_engine.events import SimulationEvent
from arctus_simulation_engine.ports import HealthStatus


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Any]] = {}
        self._history: list[SimulationEvent] = []

    async def publish(self, event: SimulationEvent) -> None:
        self._history.append(event)
        for handler in self._subscriptions.get(event.event_type, []):
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

    async def subscribe(self, event_type: str, handler: Callable[..., Any]) -> None:
        self._subscriptions.setdefault(event_type, []).append(handler)


class InMemoryPersistentMemory:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def store(self, key: str, value: bytes) -> None:
        self._store[key] = copy.copy(value)

    async def load(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class InMemoryTelemetry:
    def __init__(self) -> None:
        self._metrics: list[dict[str, Any]] = []

    async def emit(self, metric_name: str, value: float, metric_type: str, tags: dict[str, str] | None = None) -> None:
        self._metrics.append({
            "name": metric_name,
            "value": value,
            "type": metric_type,
            "tags": tags or {},
        })


class InMemoryHealthMonitor:
    def __init__(self) -> None:
        self._reports: list[dict[str, Any]] = []

    async def report(self, component: str, status: HealthStatus, details: dict[str, Any]) -> None:
        self._reports.append({"component": component, "status": status, "details": details})


class InMemoryCheckpointService:
    def __init__(self) -> None:
        self._checkpoints: dict[str, bytes] = {}

    async def save(self, checkpoint_id: str, data: bytes) -> None:
        self._checkpoints[checkpoint_id] = copy.copy(data)

    async def load(self, checkpoint_id: str) -> bytes | None:
        return self._checkpoints.get(checkpoint_id)

    async def list_checkpoints(self) -> list[str]:
        return list(self._checkpoints.keys())


class InMemoryConfigurationManager:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._config.get(key)

    async def set(self, key: str, value: Any) -> None:
        self._config[key] = value
