"""Internal shared utilities for arctus_aws.

Retry logic, circuit-breaker state machine, and async-lazy boto3 client
lifecycle management.  Imported by service modules; must never import
any service module to preserve the acyclic graph.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeVar

from .config import ConfigProvider, RetryConfig
from .exceptions import (
    ArctusAWSException,
    AWSConnectionError,
    AWSTimeoutError,
    CircuitBreakerOpenError,
)

T = TypeVar("T")


class _SessionProvider(Protocol):
    """Duck-type bridge to CredentialsProvider without introducing a
    circular import at runtime."""

    async def session(self) -> Any: ...
class RetryController:
    """Deterministic adaptive retry with exponential backoff and jitter."""

    __slots__ = ("_cfg",)

    def __init__(self, cfg: RetryConfig) -> None:
        self._cfg = cfg

    async def execute(
        self,
        operation: str,
        coro_factory: Callable[[], Awaitable[T]],
        is_retryable: Optional[Callable[[BaseException], bool]] = None,
    ) -> T:
        last_exc: Optional[BaseException] = None
        delay = self._cfg.base_delay_seconds
        for attempt in range(1, self._cfg.max_attempts + 1):
            try:
                return await coro_factory()
            except Exception as exc:
                last_exc = exc
                retryable = False
                if isinstance(exc, ArctusAWSException):
                    retryable = exc.retryable
                elif isinstance(exc, (OSError, ConnectionError, TimeoutError)):
                    retryable = True
                if is_retryable is not None:
                    retryable = is_retryable(exc)
                if not retryable or attempt == self._cfg.max_attempts:
                    raise
                sleep_for = min(delay, self._cfg.max_delay_seconds)
                if self._cfg.jitter:
                    sleep_for *= 0.5 + random.random()
                await asyncio.sleep(sleep_for)
                delay *= self._cfg.exponential_base
        raise last_exc if last_exc is not None else Exception(f"{operation} exhausted retries")


class CircuitBreaker:
    """In-memory circuit breaker for transient AWS partitions."""

    __slots__ = ("_threshold", "_recovery", "_lock", "_failures", "_last_failure", "_state")

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._lock = asyncio.Lock()
        self._failures = 0
        self._last_failure: Optional[float] = None
        self._state = "closed"

    async def call(
        self,
        coro_factory: Callable[[], Awaitable[T]],
        *,
        on_open: Callable[[], Exception] = lambda: CircuitBreakerOpenError("circuit open", service="unknown"),
    ) -> T:
        async with self._lock:
            if self._state == "open":
                if self._last_failure and (time.monotonic() - self._last_failure) > self._recovery:
                    self._state = "half-open"
                    self._failures = 0
                else:
                    raise on_open()
        try:
            result = await coro_factory()
            async with self._lock:
                self._failures = 0
                self._state = "closed"
            return result
        except Exception as exc:
            async with self._lock:
                self._failures += 1
                self._last_failure = time.monotonic()
                if self._failures >= self._threshold:
                    self._state = "open"
            raise


class AsyncBoto3Client:
    """Lazy, thread-safe, async-aware boto3 client lifecycle wrapper."""

    __slots__ = ("_svc", "_cfg_prov", "_cred_prov", "_client", "_lock")

    def __init__(
        self,
        service_name: str,
        config_provider: ConfigProvider,
        credentials_provider: Optional[_SessionProvider] = None,
    ) -> None:
        self._svc = service_name
        self._cfg_prov = config_provider
        self._cred_prov = credentials_provider
        self._client: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def get(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is not None:
                return self._client
            cfg = self._cfg_prov.current()
            import boto3 if self._cred_prov is not None:
                session = await self._cred_prov.session()
                self._client = session.client(
                    self._svc,
                    region_name=cfg.region,
                    endpoint_url=cfg.endpoint_url,
                )
            else:
                self._client = boto3.client(
                    self._svc,
                    region_name=cfg.region,
                    endpoint_url=cfg.endpoint_url,
                )
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
