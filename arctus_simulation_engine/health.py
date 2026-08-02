from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from arctus_simulation_engine.ports import HealthStatus

CheckFn = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


class HealthReporter:
    def __init__(self) -> None:
        self._checks: dict[str, CheckFn] = {}

    def register(self, name: str, check: CheckFn) -> None:
        self._checks[name] = check

    def unregister(self, name: str) -> None:
        self._checks.pop(name, None)

    async def check(self) -> dict[str, Any]:
        results: list[HealthCheckResult] = []
        overall = HealthStatus.HEALTHY
        for name, check in self._checks.items():
            start = time.monotonic()
            try:
                details = await check()
                status = HealthStatus.HEALTHY
            except Exception as exc:
                details = {"error": str(exc)}
                status = HealthStatus.UNHEALTHY
            latency = (time.monotonic() - start) * 1000.0
            results.append(HealthCheckResult(name=name, status=status, details=details, latency_ms=latency))
            if status == HealthStatus.UNHEALTHY:
                overall = HealthStatus.UNHEALTHY
            elif status == HealthStatus.DEGRADED and overall == HealthStatus.HEALTHY:
                overall = HealthStatus.DEGRADED
        return {
            "status": overall.value,
            "checks": {
                r.name: {"status": r.status.value, "details": r.details, "latency_ms": r.latency_ms}
                for r in results
            },
        }
