"""Tests for RetryController and CircuitBreaker."""

from __future__ import annotations

import asyncioimport pytest

from arctus_aws._core import CircuitBreaker, RetryController
from arctus_aws.config import RetryConfig
from arctus_aws.exceptions import CircuitBreakerOpenError

pytestmark = pytest.mark.asyncio


async def test_retry_succeeds_first_try() -> None:
 retry = RetryController(RetryConfig(max_attempts=3))
    result = await retry.execute("ok", lambda: asyncio.sleep(0) or "done")
    assert result == "done"

async def test_retry_exhausts_on_permanent_failure() -> None:
 retry = RetryController(RetryConfig(max_attempts=2, base_delay_seconds=0.01))

    with pytest.raises(RuntimeError):
        await retry.execute("fail", lambda: (_ for _ in ()).throw(RuntimeError("bad")))

async def test_circuit_opens_after_threshold() -> None:
 cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)

    async def boom() -> None:
        raise ConnectionError("network")

    with pytest.raises(ConnectionError):
        await cb.call(boom)
    with pytest.raises(ConnectionError):
        await cb.call(boom)
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(boom)

async def test_circuit_closes_on_success() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
    result = await cb.call(lambda: asyncio.sleep(0) or "ok")
    assert result == "ok"
    assert cb._state == "closed"
