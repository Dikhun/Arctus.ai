from __future__ import annotations

from typing import Any, TypeVar

from arctus_simulation_engine.di import DIContainer
from arctus_simulation_engine.ports import (
    EventBus,
    PersistentMemory,
    Telemetry,
    HealthMonitor,
    CheckpointService,
    ConfigurationManager,
)
from arctus_simulation_engine.adapters import (
    InMemoryEventBus,
    InMemoryPersistentMemory,
    InMemoryTelemetry,
    InMemoryHealthMonitor,
    InMemoryCheckpointService,
    InMemoryConfigurationManager,
)

T = TypeVar("T")


class ServiceDiscovery:
    def __init__(self, container: DIContainer) -> None:
        self._container = container

    async def discover(self, interface: type[T], default: Any | None = None) -> T:
        try:
            return await self._container.resolve(interface)
        except Exception:
            if default is not None:
                return default raise

    async def event_bus(self) -> EventBus:
        return await self.discover(EventBus, InMemoryEventBus())

    async def persistent_memory(self) -> PersistentMemory:
        return await self.discover(PersistentMemory, InMemoryPersistentMemory())

    async def telemetry(self) -> Telemetry:
        return await self.discover(Telemetry, InMemoryTelemetry())

    async def health_monitor(self) -> HealthMonitor:
        return await self.discover(HealthMonitor, InMemoryHealthMonitor())

    async def checkpoint_service(self) -> CheckpointService:
        return await self.discover(CheckpointService, InMemoryCheckpointService())

    async def configuration_manager(self) -> ConfigurationManager:
        return await self.discover(ConfigurationManager, InMemoryConfigurationManager())

    def bind_all_defaults(self) -> None:
        if not self._container.has(EventBus):
            self._container.register_instance(EventBus, InMemoryEventBus())
        if not self._container.has(PersistentMemory):
            self._container.register_instance(PersistentMemory, InMemoryPersistentMemory())
        if not self._container.has(Telemetry):
            self._container.register_instance(Telemetry, InMemoryTelemetry())
        if not self._container.has(HealthMonitor):
            self._container.register_instance(HealthMonitor, InMemoryHealthMonitor())
        if not self._container.has(CheckpointService):
            self._container.register_instance(CheckpointService, InMemoryCheckpointService())
        if not self._container.has(ConfigurationManager):
            self._container.register_instance(ConfigurationManager, InMemoryConfigurationManager())
