"""Per-session rolling 60-second rate limiting + monthly tier quotas.

The rolling 60s window is in-memory. Monthly run caps and token metering
are durable (persisted via the session store).
"""
from __future__ import annotations

import time
import calendar
from dataclasses import dataclass
from typing import Dict, Any

from .config import TIER_QUOTAS


@dataclass
class RateLimitConfig:
    max_requests_per_minute: int = 30
    max_tokens_per_minute: int = 250_000
    enforce_strict_quota: bool = True


class RateLimitError(RuntimeError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason  # "requests" | "tokens" | "monthly_runs"
        self.detail = detail


_BUCKETS: Dict[str, dict] = {}


def check_and_update(
    session_id: str,
    config: RateLimitConfig,
    estimated_tokens: int = 1000,
) -> None:
    """Rolling 60s window. Raises RateLimitError if the quota is exceeded."""
    now = time.time()
    bucket = _BUCKETS.get(session_id)
    if not bucket or now - bucket["window_start"] > 60:
        bucket = {"tokens": 0, "requests": 0, "window_start": now}

    if config.enforce_strict_quota:
        if bucket["requests"] >= config.max_requests_per_minute:
            raise RateLimitError(
                "requests",
                f"Rate limit exceeded: Max {config.max_requests_per_minute} requests/min reached.",
            )
        if bucket["tokens"] + estimated_tokens > config.max_tokens_per_minute:
            raise RateLimitError(
                "tokens",
                f"Token rate limit exceeded: Max {config.max_tokens_per_minute} tokens/min reached.",
            )

    bucket["requests"] += 1
    bucket["tokens"] += estimated_tokens
    _BUCKETS[session_id] = bucket


def clear(session_id: str) -> None:
    _BUCKETS.pop(session_id, None)


def estimate_tokens(text: str) -> int:
    """Rough heuristic: ~4 chars/token. Good enough for pre-flight checks."""
    return max(1, len(text) // 4)


# ── Monthly tier quota enforcement ────────────────────────────────────────

def check_monthly_quota(session_id: str, tier_name: str, monthly_usage: Dict[str, Any]) -> None:
    """Enforce the monthly run cap for a subscription tier.

    Raises RateLimitError(reason="monthly_runs") if the cap is exceeded.
    Uses the usage dict from session.monthly_usage() which is persisted.
    """
    if tier_name not in TIER_QUOTAS:
        return  # unknown tier → no quota enforcement
    quota = TIER_QUOTAS[tier_name]
    max_runs = quota.get("monthly_runs", float("inf"))
    used = monthly_usage.get("runs", 0)
    if max_runs != float("inf") and used >= max_runs:
        raise RateLimitError(
            "monthly_runs",
            f"Monthly run limit reached ({used}/{int(max_runs)} for {quota['label']}). "
            "Upgrade your subscription tier for more capacity.",
        )


def compute_monthly_cost(tier_name: str, in_tokens: int, out_tokens: int) -> float:
    """Estimate USD cost for a single run based on tier pricing."""
    if tier_name not in TIER_QUOTAS:
        return 0.0
    quota = TIER_QUOTAS[tier_name]
    token_price = quota.get("token_price_usd", 0.0)
    total_tokens = in_tokens + out_tokens
    return (total_tokens / 1_000_000) * token_price
