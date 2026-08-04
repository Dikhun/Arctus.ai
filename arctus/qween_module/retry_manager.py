"""Arctus AI Orchestration Framework - Retry Manager.

Responsible for retry logic, backoff, circuit breaker,
and recovery mechanisms.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type, Union

from exceptions import (
    CircuitBreakerException,
    ErrorContext,
    RetryExhaustedException,
)
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("retry_manager")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing, reject requests
    HALF_OPEN = auto()   # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)


class CircuitBreaker:
    """Per-provider circuit breaker implementation."""

    def __init__(
        self,
        provider: str,
        config: CircuitBreakerConfig,
    ) -> None:
        self.provider = provider
        self.config = config
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.successes = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(
        self,
        operation: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute operation through circuit breaker.

        Args:
            operation: Async callable.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Operation result.

        Raises:
            CircuitBreakerException: If circuit is open.
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(
                        "Circuit half-open",
                        extra={"provider": self.provider},
                    )
                else:
                    raise CircuitBreakerException(
                        f"Circuit breaker open for {self.provider}",
                        provider=self.provider,
                        open_duration=time.time() - (self.last_failure_time or 0),
                        context=ErrorContext(
                            module="retry_manager",
                            operation="circuit_breaker.call",
                            provider=self.provider,
                        ),
                    )

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerException(
                        f"Circuit half-open call limit reached for {self.provider}",
                        provider=self.provider,
                        context=ErrorContext(
                            module="retry_manager",
                            operation="circuit_breaker.call",
                            provider=self.provider,
                        ),
                    )
                self.half_open_calls += 1

        # Execute operation
        try:
            result = await operation(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try recovery."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.successes += 1
                if self.successes >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failures = 0
                    self.successes = 0
                    logger.info(
                        "Circuit closed",
                        extra={"provider": self.provider},
                    )
            else:
                self.failures = max(0, self.failures - 1)

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.half_open_calls = 0
                logger.warning(
                    "Circuit re-opened",
                    extra={"provider": self.provider, "failures": self.failures},
                )
            elif self.failures >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit opened",
                    extra={"provider": self.provider, "failures": self.failures},
                )

    async def get_state(self) -> Dict[str, Any]:
        """Get current circuit state.

        Returns:
            State dictionary.
        """
        return {
            "provider": self.provider,
            "state": self.state.name,
            "failures": self.failures,
            "successes": self.successes,
            "last_failure": self.last_failure_time,
        }


class RetryManagerImpl:
    """Production retry manager with circuit breakers and backoff.

    Coordinates retry policies, circuit breaker patterns,
    and recovery strategies across all providers.
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_config: Optional[CircuitBreakerConfig] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.retry_config = retry_config or RetryConfig()
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        self.event_bus = event_bus
        self.logger = get_logger("retry_manager")

        self._circuits: Dict[str, CircuitBreaker] = {}
        self._circuit_lock = asyncio.Lock()

    async def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """Get or create circuit breaker for provider.

        Args:
            provider: Provider name.

        Returns:
            Circuit breaker instance.
        """
        async with self._circuit_lock:
            if provider not in self._circuits:
                self._circuits[provider] = CircuitBreaker(
                    provider=provider,
                    config=self.circuit_config,
                )
            return self._circuits[provider]

    @async_timed
    async def execute_with_retry(
        self,
        operation: Callable[..., Coroutine[Any, Any, Any]],
        max_retries: Optional[int] = None,
        exceptions: Optional[tuple] = None,
        provider: Optional[str] = None,
        operation_name: str = "unknown",
    ) -> Any:
        """Execute operation with retry logic and circuit breaker.

        Args:
            operation: Async callable to execute.
            max_retries: Override max retries.
            exceptions: Override retryable exceptions.
            provider: Provider for circuit breaker.
            operation_name: Operation identifier.

        Returns:
            Operation result.

        Raises:
            RetryExhaustedException: If all retries fail.
            CircuitBreakerException: If circuit is open.
        """
        retries = max_retries if max_retries is not None else self.retry_config.max_retries
        exc_types = exceptions if exceptions is not None else self.retry_config.retryable_exceptions

        # Circuit breaker
        if provider:
            circuit = await self.get_circuit_breaker(provider)
            # Wrap operation through circuit
            async def circuit_operation(*args: Any, **kwargs: Any) -> Any:
                return await self._retry_loop(operation, retries, exc_types, operation_name)
            return await circuit.call(circuit_operation)

        return await self._retry_loop(operation, retries, exc_types, operation_name)

    async def _retry_loop(
        self,
        operation: Callable[..., Coroutine[Any, Any, Any]],
        max_retries: int,
        exceptions: tuple,
        operation_name: str,
    ) -> Any:
        """Core retry loop.

        Args:
            operation: Operation to retry.
            max_retries: Maximum retries.
            exceptions: Retryable exceptions.
            operation_name: Operation name.

        Returns:
            Operation result.

        Raises:
            RetryExhaustedException: If retries exhausted.
        """
        last_exception: Optional[BaseException] = None

        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except exceptions as e:
                last_exception = e

                if attempt < max_retries:
                    delay = self._calculate_delay(attempt)

                    self.logger.warning(
                        "Operation failed, retrying",
                        extra={
                            "operation": operation_name,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay": delay,
                            "error": str(e),
                        },
                    )

                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        "Operation failed after all retries",
                        extra={
                            "operation": operation_name,
                            "attempts": max_retries + 1,
                            "last_error": str(e),
                        },
                    )

        raise RetryExhaustedException(
            f"Operation '{operation_name}' failed after {max_retries + 1} attempts",
            max_retries=max_retries,
            context=ErrorContext(
                module="retry_manager",
                operation="execute_with_retry",
            ),
            cause=last_exception,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate backoff delay with optional jitter.

        Args:
            attempt: Retry attempt number (0-indexed).

        Returns:
            Delay in seconds.
        """
        delay = min(
            self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
            self.retry_config.max_delay,
        )

        if self.retry_config.jitter:
            delay *= (0.5 + random.random() * 0.5)  # 50-100% of calculated delay

        return delay

    async def reset_circuit(self, provider: str) -> bool:
        """Manually reset circuit breaker.

        Args:
            provider: Provider to reset.

        Returns:
            True if reset succeeded.
        """
        async with self._circuit_lock:
            if provider in self._circuits:
                self._circuits[provider] = CircuitBreaker(
                    provider=provider,
                    config=self.circuit_config,
                )
                self.logger.info("Circuit reset", extra={"provider": provider})
                return True
            return False

    async def get_all_circuits(self) -> List[Dict[str, Any]]:
        """Get status of all circuit breakers.

        Returns:
            List of circuit states.
        """
        async with self._circuit_lock:
            states = []
            for circuit in self._circuits.values():
                states.append(await circuit.get_state())
            return states


# Factory
async def create_retry_manager(
    max_retries: int = 3,
    base_delay: float = 1.0,
    circuit_failure_threshold: int = 5,
    event_bus: Optional[Any] = None,
) -> RetryManagerImpl:
    """Factory for creating configured retry manager.

    Args:
        max_retries: Default max retries.
        base_delay: Base backoff delay.
        circuit_failure_threshold: Circuit breaker threshold.
        event_bus: Optional event bus.

    Returns:
        Configured RetryManagerImpl.
    """
    return RetryManagerImpl(
        retry_config=RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
        ),
        circuit_config=CircuitBreakerConfig(
            failure_threshold=circuit_failure_threshold,
        ),
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
