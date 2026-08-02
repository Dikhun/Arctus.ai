from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import structlog

logger = structlog.get_logger()


class HealthCheck(Protocol):
    name: str
    async def check(self) -> bool: ...
class HealthMonitor:
    def __init__(self):
        self.checks: list[HealthCheck] = []
        self.last_results: dict[str, tuple[bool, datetime]] = {}

    def register(self, check: HealthCheck) -> None:
        self.checks.append(check)

    async def check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        outputs = await asyncio.gather(
            *[self._run_check(c) for c in self.checks],
            return_exceptions=True,
        )
        for c, out in zip(self.checks, outputs):
            if isinstance(out, Exception):
                results[c.name] = False
                logger.warning("health_check_failed", check=c.name, error=str(out))
            else:
                results[c.name] = out
                self.last_results[c.name] = (out, datetime.utcnow())
        return results

    async def _run_check(self, check: HealthCheck) -> bool:
        try:
            return await asyncio.wait_for(check.check(), timeout=10.0)
        except asyncio.TimeoutError:
            return False
