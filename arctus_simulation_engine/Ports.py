from __future__ import annotations

import enum
from typing import Any, Protocolfrom arctus_simulation_engine.events import SimulationEvent


class HealthStatus(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class EventBus(Protocol):
    async def publish(self, event: SimulationEvent) -> None:
        ...

    async def subscribe(self, event_type: str, handler: Any) -> Any:
        ...
class PersistentMemory(Protocol):
    async def store(self, key: str, value: bytes) -> None:
        ...

    async def load(self, key: str) -> bytes | None:
        ...

    async def delete(self, key: str) -> None:
        ...


class KnowledgeGraph(Protocol):
    async def add_triple(self, subject: str, predicate: str, obj: str, metadata: dict[str, Any] | None = None) -> None:
        ...

    async def query(self, query: str) -> list[dict[str, Any]]:
        ...


class Telemetry(Protocol):
    async def emit(self, metric_name: str, value: float, metric_type: str, tags: dict[str, str] | None = None) -> None:
        ...


class HealthMonitor(Protocol):
    async def report(self, component: str, status: HealthStatus, details: dict[str, Any]) -> None:
        ...


class CheckpointService(Protocol):
    async def save(self, checkpoint_id: str, data: bytes) -> None:
        ...

    async def load(self, checkpoint_id: str) -> bytes | None:
        ...

    async def list_checkpoints(self) -> list[str]:
        ...


class SecretManager(Protocol):
    async def get(self, key: str) -> str:
        ...


class ConfigurationManager(Protocol):
    async def get(self, key: str) -> Any:
        ...
class ModelGateway(Protocol):
    async def infer(self, model_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        ...


class VectorDatabase(Protocol):
    async def search(self, collection: str, vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        ...
class RelationalDatabase(Protocol):
    async def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        ...
