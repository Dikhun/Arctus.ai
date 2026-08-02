"""Health-check registry for AWS service integrations."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

class HealthRegistry:
    __slots__ = ("_checks", "_lock")

    def __init__(self) -> None:
        self._checks: Dict[str, Callable[[], Awaitable[Dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def register(self, name: str, check: Callable[[], Awaitable[Dict[str, Any]]]) -> None:
        async with self._lock:
            self._checks[name] = check

    async def unregister(self, name: str) -> None:
        async with self._lock:
            self._checks.pop(name, None)

    async def evaluate(self) -> Dict[str, Any]:
        async with self._lock:
            snapshot = dict(self._checks)
        results: Dict[str, Any] = {}
        coros = [self._safely(name, fn) for name, fn in snapshot.items()]
        outs = await asyncio.gather(*coros, return_exceptions=True)
        for name, out in zip(snapshot.keys(), outs):
            if isinstance(out, Exception):
                results[name] = {"status": "unhealthy", "error": str(out)}
            else:
                results[name] = out
        overall = "healthy" if all(r.get("status") == "healthy" for r in results.values()) else "degraded"
        return {"status": overall, "checks": results}

    async def _safely(self, name: str, fn: Callable[[], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
        try:
            return await fn()
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}
