from __future__ import annotations

from typing import Any

from arctus_simulation_engine.di import DIContainer
from arctus_simulation_engine.discovery import ServiceDiscovery
from arctus_simulation_engine.core import SimulationRuntime, VirtualTime, DiscreteEventScheduler, EntityLifecycleManager
from arctus_simulation_engine.health import HealthReporter


class AutonomousRuntime:
    def __init__(self, runtime_id: str, container: DIContainer | None = None) -> None:
        self._id = runtime_id
        self._container = container or DIContainer()
        self._discovery = ServiceDiscovery(self._container)
        self._runtime: SimulationRuntime | None = None
        self._health = HealthReporter()

    async def bootstrap(self) -> SimulationRuntime:
        self._discovery.bind_all_defaults()
        event_bus = await self._discovery.event_bus()
        telemetry = await self._discovery.telemetry()
        health_monitor = await self._discovery.health_monitor()
        checkpoint = await self._discovery.checkpoint_service()
        config = await self._discovery.configuration_manager()

        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, event_bus)
        entities = EntityLifecycleManager(event_bus, vt)

        self._runtime = SimulationRuntime(
            runtime_id=self._id,
            virtual_time=vt,
            scheduler=sched,
            entities=entities,
            event_bus=event_bus,
            telemetry=telemetry,
            health_monitor=health_monitor,
            checkpoint_service=checkpoint,
            config_manager=config,
        )

        self._health.register("simulation_runtime", self._runtime.health)
        return self._runtime

    async def health(self) -> dict[str, Any]:
        return await self._health.check()
