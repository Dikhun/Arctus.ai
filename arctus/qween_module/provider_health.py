"""Arctus AI Orchestration Framework - Provider Health.

Responsible for health monitoring, latency monitoring,
automatic failover, and provider statistics.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from domain_models import ProviderModel, ProviderStatus
from exceptions import ErrorContext, ProviderHealthException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("provider_health")


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    provider: str
    timestamp: datetime
    healthy: bool
        latency_ms: float
    error: Optional[str] = None
    status_code: Optional[int] = None


@dataclass
class ProviderStats:
    """Aggregated provider statistics."""

    provider: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0


class ProviderHealthMonitorImpl:
    """Production provider health monitor with automatic failover.

    Continuously monitors LLM provider health, tracks latency
    statistics, and manages failover decisions.
    """

    DEFAULT_HEALTH_CHECK_INTERVAL = 30.0  # seconds
    DEFAULT_FAILURE_THRESHOLD = 3
    DEFAULT_RECOVERY_THRESHOLD = 2

    def __init__(
        self,
        health_check_interval: float = DEFAULT_HEALTH_CHECK_INTERVAL,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_threshold: int = DEFAULT_RECOVERY_THRESHOLD,
        health_check_fn: Optional[Callable[[str], Any]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.health_check_fn = health_check_fn or self._default_health_check
        self.event_bus = event_bus
        self.logger = get_logger("provider_health")

        self._providers: Dict[str, ProviderModel] = {}
        self._stats: Dict[str, ProviderStats] = {}
        self._history: Dict[str, List[HealthCheckResult]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def register_provider(self, provider: ProviderModel) -> None:
        """Register provider for health monitoring.

        Args:
            provider: Provider to monitor.
        """
        async with self._lock:
            self._providers[provider.name] = provider
            self._stats[provider.name] = ProviderStats(provider=provider.name)
            self._history[provider.name] = []

        self.logger.info("Provider registered", extra={"provider": provider.name})

    async def unregister_provider(self, provider_name: str) -> None:
        """Remove provider from monitoring.

        Args:
            provider_name: Provider to remove.
        """
        async with self._lock:
            self._providers.pop(provider_name, None)
            self._stats.pop(provider_name, None)
            self._history.pop(provider_name, None)

    async def start_monitoring(self) -> None:
        """Start continuous health monitoring."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Health monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.logger.info("Health monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                providers = list(self._providers.values())
                for provider in providers:
                    await self._check_provider(provider)

                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Monitoring loop error", extra={"error": str(e)})
                await asyncio.sleep(self.health_check_interval)

    @async_timed
    async def _check_provider(self, provider: ProviderModel) -> HealthCheckResult:
        """Check single provider health.

        Args:
            provider: Provider to check.

        Returns:
            Health check result.
        """
        start = time.perf_counter()
        try:
            result = await self.health_check_fn(provider.name)
            latency = (time.perf_counter() - start) * 1000

            healthy = bool(result)
            check = HealthCheckResult(
                provider=provider.name,
                timestamp=datetime.utcnow(),
                healthy=healthy,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            check = HealthCheckResult(
                provider=provider.name,
                timestamp=datetime.utcnow(),
                healthy=False,
                latency_ms=latency,
                error=str(e),
            )

        # Update state
        async with self._lock:
            if provider.name not in self._history:
                self._history[provider.name] = []
            self._history[provider.name].append(check)
            # Keep last 100
            if len(self._history[provider.name]) > 100:
                self._history[provider.name] = self._history[provider.name][-100:]

            await self._update_stats(provider.name, check)

        self.logger.debug(
            "Health check complete",
            extra={
                "provider": provider.name,
                "healthy": check.healthy,
                "latency_ms": round(check.latency_ms, 2),
            },
        )

        return check

    async def _update_stats(self, provider_name: str, check: HealthCheckResult) -> None:
        """Update provider statistics.

        Args:
            provider_name: Provider name.
            check: Latest health check.
        """
        stats = self._stats.get(provider_name)
        if not stats:
            return

        stats.total_requests += 1
        if check.healthy:
            stats.successful_requests += 1
            stats.consecutive_failures = 0
        else:
            stats.failed_requests += 1
            stats.consecutive_failures += 1

        stats.last_check = check.timestamp

        # Update latency stats
        history = self._history.get(provider_name, [])
        latencies = [h.latency_ms for h in history if h.healthy]
        if latencies:
            stats.avg_latency_ms = sum(latencies) / len(latencies)
            sorted_lat = sorted(latencies)
            stats.p95_latency_ms = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) > 20 else stats.avg_latency_ms * 1.5
            stats.p99_latency_ms = sorted_lat[int(len(sorted_lat) * 0.99)] if len(sorted_lat) > 100 else stats.avg_latency_ms * 2.0

        # Update uptime
        total = stats.total_requests
        if total > 0:
            stats.uptime_percentage = (stats.successful_requests / total) * 100

        # Update provider status based on failures
        provider = self._providers.get(provider_name)
        if provider:
            if stats.consecutive_failures >= self.failure_threshold:
                if provider.status != ProviderStatus.CIRCUIT_OPEN:
                    provider = provider.model_copy(update={"status": ProviderStatus.UNHEALTHY})
                    self._providers[provider_name] = provider

                    self.logger.warning(
                        "Provider marked unhealthy",
                        extra={
                            "provider": provider_name,
                            "consecutive_failures": stats.consecutive_failures,
                        },
                    )

                    if self.event_bus:
                        await self.event_bus.publish(
                            OrchestrationEvent(
                                event_type="provider_unhealthy",
                                provider=provider_name,
                                payload={
                                    "consecutive_failures": stats.consecutive_failures,
                                    "uptime": stats.uptime_percentage,
                                },
                            )
                        )

            elif stats.consecutive_failures == 0 and provider.status == ProviderStatus.UNHEALTHY:
                # Check if recovered
                recent_success = sum(1 for h in history[-self.recovery_threshold:] if h.healthy)
                if recent_success >= self.recovery_threshold:
                    provider = provider.model_copy(update={"status": ProviderStatus.HEALTHY})
                    self._providers[provider_name] = provider

                    self.logger.info(
                        "Provider recovered",
                        extra={"provider": provider_name},
                    )

                    if self.event_bus:
                        await self.event_bus.publish(
                            OrchestrationEvent(
                                event_type="provider_recovered",
                                provider=provider_name,
                                payload={"uptime": stats.uptime_percentage},
                            )
                        )

    async def check_health(self, provider: ProviderModel) -> bool:
        """Check if provider is healthy.

        Args:
            provider: Provider to check.

        Returns:
            True if healthy.
        """
        stats = self._stats.get(provider.name)
        if not stats:
            # No history, do immediate check
            result = await self._check_provider(provider)
            return result.healthy

        return provider.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)

    async def get_stats(self, provider_name: str) -> Dict[str, Any]:
        """Get provider statistics.

        Args:
            provider_name: Provider identifier.

        Returns:
            Provider statistics dictionary.
        """
        stats = self._stats.get(provider_name)
        if not stats:
            return {}

        return {
            "provider": stats.provider,
            "total_requests": stats.total_requests,
            "successful_requests": stats.successful_requests,
            "failed_requests": stats.failed_requests,
            "avg_latency_ms": round(stats.avg_latency_ms, 2),
            "p95_latency_ms": round(stats.p95_latency_ms, 2),
            "p99_latency_ms": round(stats.p99_latency_ms, 2),
            "uptime_percentage": round(stats.uptime_percentage, 2),
            "consecutive_failures": stats.consecutive_failures,
            "last_check": stats.last_check.isoformat() if stats.last_check else None,
        }

    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all providers.

        Returns:
            Dictionary of provider statistics.
        """
        result: Dict[str, Dict[str, Any]] = {}
        for name in self._providers:
            result[name] = await self.get_stats(name)
        return result

    async def get_healthy_providers(self) -> List[str]:
        """Get list of currently healthy providers.

        Returns:
            List of healthy provider names.
        """
        healthy = []
        for name, provider in self._providers.items():
            if provider.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED):
                healthy.append(name)
        return healthy

    async def get_failover_recommendation(
        self,
        failed_provider: str,
    ) -> Optional[str]:
        """Get recommended failover provider.

        Args:
            failed_provider: Provider that failed.

        Returns:
            Recommended alternative provider name.
        """
        failed_stats = self._stats.get(failed_provider)
        if failed_stats:
            failed_p95 = failed_stats.p95_latency_ms or 1000.0

        best: Optional[str] = None
        best_score = -1.0

        for name, stats in self._stats.items():
            if name == failed_provider:
                continue
            if stats.uptime_percentage < 95:
                continue

            # Score by uptime and low latency
            score = (stats.uptime_percentage / 100.0) * 0.5
            if stats.avg_latency_ms > 0:
                latency_score = max(0, 1.0 - (stats.avg_latency_ms / 5000.0))
                score += latency_score * 0.5

            if score > best_score:
                best_score = score
                best = name

        return best

    async def _default_health_check(self, provider_name: str) -> bool:
        """Default health check implementation.

        In production, would make actual API call.
        For now, simulates based on provider status.

        Args:
            provider_name: Provider to check.

        Returns:
            Simulated health status.
        """
        # Simulate: random health with bias toward healthy
        import random
        return random.random() > 0.1  # 90% healthy

    async def force_status_update(
        self,
        provider_name: str,
        status: ProviderStatus,
    ) -> None:
        """Manually force provider status update.

        Args:
            provider_name: Provider to update.
            status: New status.
        """
        async with self._lock:
            provider = self._providers.get(provider_name)
            if provider:
                self._providers[provider_name] = provider.model_copy(update={"status": status})

        self.logger.info(
            "Provider status forced",
            extra={"provider": provider_name, "status": status.name},
        )


# Factory
async def create_provider_health_monitor(
    health_check_interval: float = 30.0,
    health_check_fn: Optional[Callable[[str], Any]] = None,
    event_bus: Optional[Any] = None,
) -> ProviderHealthMonitorImpl:
    """Factory for creating configured health monitor.

    Args:
        health_check_interval: Seconds between checks.
        health_check_fn: Custom health check function.
        event_bus: Optional event bus.

    Returns:
        Configured ProviderHealthMonitorImpl.
    """
    return ProviderHealthMonitorImpl(
        health_check_interval=health_check_interval,
        health_check_fn=health_check_fn,
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
