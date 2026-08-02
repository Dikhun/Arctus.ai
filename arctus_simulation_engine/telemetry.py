from __future__ import annotations

from dataclasses import dataclass

from arctus_simulation_engine.ports import Telemetry


@dataclass(slots=True)
class TelemetryAdapter:
    _telemetry: Telemetry

    async def emit_counter(self, name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
        await self._telemetry.emit(name, value, "counter", tags)

    async def emit_gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        await self._telemetry.emit(name, value, "gauge", tags)

    async def emit_histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        await self._telemetry.emit(name, value, "histogram", tags)
