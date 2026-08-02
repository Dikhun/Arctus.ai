"""Metrics façade that adapts to the injected ITelemetry."""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import ITelemetry

class AWSMetrics:
    __slots__ = ("_telemetry",)

    def __init__(self, telemetry: Optional[ITelemetry] = None) -> None:
        self._telemetry = telemetry

    def _tags(self, service: str, operation: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        tags: Dict[str, str] = {"service": service, "operation": operation}
        if extra:
            tags.update(extra)
        return tags

    async def record_counter(
        self, name: str, value: int, *, service: str, operation: str, tags: Optional[Dict[str, str]] = None
    ) -> None:
        if self._telemetry is None:
            return
        await self._telemetry.emit_counter(name, value, tags=self._tags(service, operation, tags))

    async def record_latency(
        self, name: str, seconds: float, *, service: str, operation: str, tags: Optional[Dict[str, str]] = None
    ) -> None:
        if self._telemetry is None:
            return
        await self._telemetry.emit_histogram(name, seconds, tags=self._tags(service, operation, tags))

    async def record_gauge(
        self, name: str, value: float, *, service: str, operation: str, tags: Optional[Dict[str, str]] = None
    ) -> None:
        if self._telemetry is None:
            return
        await self._telemetry.emit_gauge(name, value, tags=self._tags(service, operation, tags))
