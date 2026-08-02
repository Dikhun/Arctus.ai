from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from arctus_simulation_engine.primitives import SimState, SimulationTime, Duration
from arctus_simulation_engine.events import SimulationEvent
from arctus_simulation_engine.ports import EventBus, Telemetry, HealthMonitor, HealthStatus, CheckpointService, ConfigurationManager
from arctus_simulation_engine.core.virtual_time import VirtualTime
from arctus_simulation_engine.core.scheduler import DiscreteEventScheduler
from arctus_simulation_engine.core.entity_lifecycle import EntityLifecycleManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeConfig:
    max_events_per_step: int = 1
    checkpoint_interval: Duration | None = None
    enable_telemetry: bool = True


class SimulationRuntime:
    def __init__(
        self,
        runtime_id: str,
        virtual_time: VirtualTime,
        scheduler: DiscreteEventScheduler,
        entities: EntityLifecycleManager,
        event_bus: EventBus,
        telemetry: Telemetry,
        health_monitor: HealthMonitor,
        checkpoint_service: CheckpointService,
        config_manager: ConfigurationManager,
    ) -> None:
        self._id = runtime_id
        self._state = SimState.IDLE
        self._virtual_time = virtual_time
        self._scheduler = scheduler
        self._entities = entities
        self._event_bus = event_bus
        self._telemetry = telemetry
        self._health_monitor = health_monitor
        self._checkpoint_service = checkpoint_service
        self._config_manager = config_manager
        self._config = RuntimeConfig()
        self._lock = asyncio.Lock()
        self._step_count = 0
        self._running_task: asyncio.Task[Any] | None = None
        self._stop_requested = False
        self._last_checkpoint_time = SimulationTime(0)

    @property
    def state(self) -> SimState:
        return self._state

    @property
    def current_time(self) -> SimulationTime:
        return self._virtual_time.now

    async def initialize(self) -> None:
        async with self._lock:
            if self._state != SimState.IDLE:
                raise RuntimeError(f"Cannot initialize from state {self._state}")
 self._state = SimState.INITIALIZING
            try:
                cfg = await self._config_manager.get("simulation.runtime.config")
                if isinstance(cfg, dict):
                    self._config = RuntimeConfig(
                        max_events_per_step=cfg.get("max_events_per_step", 1),
                        checkpoint_interval=Duration(cfg["checkpoint_interval"]) if cfg.get("checkpoint_interval") else None,
                        enable_telemetry=cfg.get("enable_telemetry", True),
                    )
                self._state = SimState.PAUSED
                await self._event_bus.publish(SimulationEvent(
                    event_type="runtime.initialized",
                    timestamp=self._virtual_time.now,
                    source=self._id,
                    payload={"runtime_id": self._id},
                ))
                if self._config.enable_telemetry:
                    await self._telemetry.emit("simulation.runtime.initialized", 1.0, "counter")
            except Exception as exc:
                self._state = SimState.ERROR
                await self._health_monitor.report(self._id, HealthStatus.UNHEALTHY, {"error": str(exc)})
                raise

    async def start(self) -> None:
        async with self._lock:
            if self._state not in (SimState.PAUSED, SimState.STEPPING):
                raise RuntimeError(f"Cannot start from state {self._state}")
            self._state = SimState.RUNNING
            self._stop_requested = False
            await self._event_bus.publish(SimulationEvent(
                event_type="runtime.started",
                timestamp=self._virtual_time.now,
                source=self._id,
                payload={"runtime_id": self._id},
            ))
        self._running_task = asyncio.create_task(self._run_loop())

    async def pause(self) -> None:
        async with self._lock:
            if self._state != SimState.RUNNING:
                return
            self._stop_requested = True
            if self._running_task and not self._running_task.done():
                try:
                    await asyncio.wait_for(self._running_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._running_task.cancel()
                    try:
                        await self._running_task
                    except asyncio.CancelledError:
                        pass
            self._state = SimState.PAUSED
            self._stop_requested = False
            await self._event_bus.publish(SimulationEvent(
                event_type="runtime.paused",
                timestamp=self._virtual_time.now,
                source=self._id,
                payload={"runtime_id": self._id},
            ))

    async def step(self, steps: int = 1) -> None:
        for _ in range(steps):
            await self._scheduler.step()
            self._step_count += 1

    async def stop(self) -> None:
        async with self._lock:
            self._stop_requested = True
            if self._running_task and not self._running_task.done():
                self._running_task.cancel()
                try:
                    await self._running_task
                except asyncio.CancelledError:
 pass
            self._scheduler.stop()
            self._state = SimState.STOPPED
            await self._event_bus.publish(SimulationEvent(
                event_type="runtime.stopped",
                timestamp=self._virtual_time.now,
                source=self._id,
                payload={"runtime_id": self._id, "total_steps": self._step_count},
            ))

    async def reset(self) -> None:
        async with self._lock:
            if self._state == SimState.RUNNING:
                await self.stop()
            self._scheduler.clear()
            for entity in self._entities.list_active():
                await self._entities.destroy(entity.entity_id)
            self._virtual_time.set(SimulationTime(0))
            self._step_count = 0
            self._state = SimState.IDLE
            await self._event_bus.publish(SimulationEvent(
                event_type="runtime.reset",
                timestamp=self._virtual_time.now,
                source=self._id,
                payload={"runtime_id": self._id},
            ))

    async def health(self) -> dict[str, Any]:
        status = HealthStatus.HEALTHY if self._state in (SimState.RUNNING, SimState.PAUSED, SimState.IDLE) else HealthStatus.UNHEALTHY
        details = {
            "state": self._state.value,
            "virtual_time_nanos": self._virtual_time.now.nanos,
            "pending_events": self._scheduler.event_count,
            "active_entities": len(self._entities.list_active()),
            "steps": self._step_count,
        }
        await self._health_monitor.report(self._id, status, details)
        return {"status": status.value, "checks": {self._id: details}}

    async def checkpoint(self) -> str:
        snapshot = {
            "runtime_id": self._id,
            "virtual_time_nanos": self._virtual_time.now.nanos,
            "step_count": self._step_count,
            "state": self._state.value,
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "state": e.state.value,
                    "metadata": e.metadata,
                }
                for e in self._entities.list_active()
            ],
            "pending_events": self._scheduler.event_count,
        }
        data = json.dumps(snapshot).encode()
        checkpoint_id = f"checkpoint-{self._id}-{self._virtual_time.now.nanos}"
        await self._checkpoint_service.save(checkpoint_id, data)
        self._last_checkpoint_time = self._virtual_time.now
        await self._event_bus.publish(SimulationEvent(
            event_type="runtime.checkpoint_created",
            timestamp=self._virtual_time.now,
            source=self._id,
            payload={"checkpoint_id": checkpoint_id},
        ))
        if self._config.enable_telemetry:
            await self._telemetry.emit("simulation.checkpoint.created", 1.0, "counter")
        return checkpoint_id

    async def restore(self, checkpoint_id: str) -> None:
        data = await self._checkpoint_service.load(checkpoint_id)
        if data is None:
            raise FileNotFoundError(f"Checkpoint {checkpoint_id} not found")
        snapshot = json.loads(data.decode())
        if snapshot["runtime_id"] != self._id:
            raise ValueError("Checkpoint runtime ID mismatch")
        self._virtual_time.set(SimulationTime(snapshot["virtual_time_nanos"]))
        self._step_count = snapshot["step_count"]
        self._scheduler.clear()
        await self._event_bus.publish(SimulationEvent(
            event_type="runtime.restored",
            timestamp=self._virtual_time.now,
            source=self._id,
            payload={"checkpoint_id": checkpoint_id},
        ))

    async def _run_loop(self) -> None:
        try:
            while not self._stop_requested:
                if self._state != SimState.RUNNING:
                    break has_more = await self._scheduler.step()
                if self._state != SimState.RUNNING:
                    break
                if has_more:
                    self._step_count += 1
                    if self._config.checkpoint_interval and (self._virtual_time.now - self._last_checkpoint_time) >= self._config.checkpoint_interval:
                        await self.checkpoint()
                else:
                    self._state = SimState.STOPPED
                    break
        except Exception as exc:
 logger.exception("Runtime run loop failed")
            self._state = SimState.ERROR
            await self._health_monitor.report(self._id, HealthStatus.UNHEALTHY, {"error": str(exc)})
            await self._event_bus.publish(SimulationEvent(
                event_type="runtime.error",
                timestamp=self._virtual_time.now,
                source=self._id,
                payload={"error": str(exc)},
            ))
