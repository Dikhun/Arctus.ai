"""Arctus AI Orchestration Framework - Shared Infrastructure.

Logging, event bus, dependency injection, and utility functions used
across all Queen Module components.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from domain_models import OrchestrationEvent

# ─── Structured Logging ───────────────────────────────────────────────────────

class StructuredLogFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.thread,
        }
        if hasattr(record, "extra"):
            log_obj.update(record.extra)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get configured structured logger.

    Args:
        name: Logger name, typically module __name__.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class LogContext:
    """Context manager for adding structured fields to log records."""

    _context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})

    def __init__(self, **kwargs: Any) -> None:
        self.extra = kwargs
        self.token: Optional[Any] = None

    def __enter__(self) -> LogContext:
        current = self._context.get().copy()
        current.update(self.extra)
        self.token = self._context.set(current)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.token:
            self._context.reset(self.token)

    @classmethod
    def get_current(cls) -> Dict[str, Any]:
        """Get current log context."""
        return cls._context.get().copy()


def log_extra(**kwargs: Any) -> Dict[str, Any]:
    """Build extra dict for structured logging with context."""
    extra = LogContext.get_current()
    extra.update(kwargs)
    return {"extra": extra}


# ─── Event Bus ────────────────────────────────────────────────────────────────

@dataclass
class EventBus:
    """In-memory async event bus for module communication.

    Implements publish-subscribe pattern with typed event routing.
    """

    _subscribers: Dict[str, List[Callable[[OrchestrationEvent], Coroutine[Any, Any, None]]]] = field(
        default_factory=lambda: {}
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def publish(self, event: OrchestrationEvent) -> None:
        """Publish event to all subscribers.

        Args:
            event: Event to publish.
        """
        async with self._lock:
            handlers = self._subscribers.get(event.event_type, []).copy()

        if not handlers:
            return

        await asyncio.gather(
            *[self._safe_call(handler, event) for handler in handlers],
            return_exceptions=True,
        )

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[OrchestrationEvent], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to event type.

        Args:
            event_type: Event type to subscribe to.
            handler: Async handler callable.
        """
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    async def unsubscribe(
        self,
        event_type: str,
        handler: Callable[[OrchestrationEvent], Coroutine[Any, Any, None]],
    ) -> None:
        """Unsubscribe handler from event type.

        Args:
            event_type: Event type.
            handler: Handler to remove.
        """
        async with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]

    @staticmethod
    async def _safe_call(
        handler: Callable[[OrchestrationEvent], Coroutine[Any, Any, None]],
        event: OrchestrationEvent,
    ) -> None:
        """Safely invoke handler with exception isolation."""
        try:
            await handler(event)
        except Exception:
            logger = get_logger("event_bus")
            logger.exception("Event handler failed", extra={"event_type": event.event_type})


# ─── Dependency Injection Container ───────────────────────────────────────────

T = TypeVar("T")


@dataclass
class ServiceRegistration:
    """Registration metadata for a service."""

    interface: Type[Any]
    implementation: Type[Any]
    instance: Optional[Any] = None
    factory: Optional[Callable[..., Any]] = None
    singleton: bool = True
    kwargs: Dict[str, Any] = field(default_factory=dict)


class DIContainer:
    """Lightweight dependency injection container with interface resolution.

    Supports singleton and transient lifetimes, factory registration,
    and constructor injection.
    """

    def __init__(self) -> None:
        self._registrations: Dict[Type[Any], ServiceRegistration] = {}
        self._singletons: Dict[Type[Any], Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    def register(
        self,
        interface: Type[T],
        implementation: Optional[Type[T]] = None,
        *,
        instance: Optional[T] = None,
        factory: Optional[Callable[..., T]] = None,
        singleton: bool = True,
        **kwargs: Any,
    ) -> DIContainer:
        """Register service with container.

        Args:
            interface: Abstract interface type.
            implementation: Concrete implementation type.
            instance: Pre-created singleton instance.
            factory: Factory function for creation.
            singleton: Whether to cache instance.
            **kwargs: Constructor arguments.

        Returns:
            Self for chaining.
        """
        impl = implementation or (type(instance) if instance else interface)
        self._registrations[interface] = ServiceRegistration(
            interface=interface,
            implementation=impl,
            instance=instance,
            factory=factory,
            singleton=singleton,
            kwargs=kwargs,
        )
        if instance and singleton:
            self._singletons[interface] = instance
        return self

    async def resolve(self, interface: Type[T]) -> T:
        """Resolve service by interface.

        Args:
            interface: Registered interface type.

        Returns:
            Resolved service instance.

        Raises:
            KeyError: If interface not registered.
        """
        if interface in self._singletons:
            return self._singletons[interface]  # type: ignore[return-value]

        reg = self._registrations.get(interface)
        if not reg:
            raise KeyError(f"No registration for {interface.__name__}")

        async with self._lock:
            # Double-check after acquiring lock
            if reg.singleton and interface in self._singletons:
                return self._singletons[interface]  # type: ignore[return-value]

            instance = await self._create_instance(reg)

            if reg.singleton:
                self._singletons[interface] = instance

            return instance  # type: ignore[return-value]

    async def _create_instance(self, reg: ServiceRegistration) -> Any:
        """Create instance from registration."""
        if reg.factory:
            return reg.factory(**reg.kwargs)

        # Constructor injection
        hints = get_type_hints(reg.implementation.__init__)
        init_args: Dict[str, Any] = {}

        for name, hint in hints.items():
            if name in ("self", "return"):
                continue
            if name in reg.kwargs:
                init_args[name] = reg.kwargs[name]
            elif hint in self._registrations or hint in self._singletons:
                init_args[name] = await self.resolve(hint)

        return reg.implementation(**init_args)

    def build_provider(self) -> Callable[[Type[T]], Coroutine[Any, Any, T]]:
        """Build provider function for FastAPI-style injection.

        Returns:
            Async provider function.
        """
        return lambda iface: self.resolve(iface)


# ─── Async Utilities ────────────────────────────────────────────────────────────

def async_timed(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator to time async function execution."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        logger = get_logger("timing")
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"{func.__name__} took {elapsed:.2f}ms",
                extra={"function": func.__name__, "elapsed_ms": elapsed},
            )

    return wrapper


async def gather_with_concurrency(
    limit: int,
    *coros: Coroutine[Any, Any, T],
) -> List[T]:
    """Gather coroutines with semaphore-based concurrency limit.

    Args:
        limit: Maximum concurrent executions.
        *coros: Coroutines to execute.

    Returns:
        List of results in input order.
    """
    semaphore = asyncio.Semaphore(limit)

    async def sem_coro(coro: Coroutine[Any, Any, T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*[sem_coro(c) for c in coros])


# ─── Thread Safety Utilities ──────────────────────────────────────────────────

class AtomicCounter:
    """Thread-safe atomic counter for metrics and IDs."""

    def __init__(self, initial: int = 0) -> None:
        self._value = initial
        self._lock = asyncio.Lock()

    async def increment(self, delta: int = 1) -> int:
        """Atomically increment and return new value."""
        async with self._lock:
            self._value += delta
            return self._value

    async def get(self) -> int:
        """Get current value."""
        async with self._lock:
            return self._value


# ─── Retry Decorator ────────────────────────────────────────────────────────────

def async_retry(
    max_retries: int = 3,
    exceptions: tuple = (Exception,),
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """Decorator for async retry with exponential backoff.

    Args:
        max_retries: Maximum retry attempts.
        exceptions: Tuple of exceptions to catch.
        backoff_base: Base seconds for backoff.
        backoff_max: Maximum backoff seconds.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Optional[BaseException] = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        break
                    delay = min(backoff_base * (2 ** attempt), backoff_max)
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
