"""OpenAI-compatible LLM client.

Talks to whatever endpoints the user configured (fast / strong tiers).
Pure outbound HTTP, no listeners, no tunneling. Uses urllib from the stdlib
so the package has zero third-party runtime dependencies.

Every call is routed through the semantic cache FIRST (Feature 1: exact +
fuzzy match). A cache hit returns immediately with no LLM call and no
billed tokens. The session_id (Feature 4: sticky sessions) is threaded
through so cache keys and provider routing are consistent within a run.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import List, Dict, Any, Optional

from .config import Tier

logger = logging.getLogger("arctus.llm")


class LLMError(RuntimeError):
    pass


def chat(
    tier: Tier,
    messages: List[Dict[str, str]],
    *,
    timeout: int = 120,
    session_id: str = "",
    use_cache: bool = True,
) -> str:
    """Call POST {base_url}/chat/completions and return the assistant message.

    Routes through the semantic cache first (Feature 1). On a cache hit,
    returns immediately — no HTTP call, no tokens billed.

    Args:
        tier: model config (base_url, model, api_key, ...).
        messages: chat messages.
        timeout: HTTP timeout in seconds.
        session_id: sticky session key (Feature 4). When set, included in
            the cache key and sent as X-Session-Id to providers that
            support sticky routing.
        use_cache: set False to bypass the semantic cache (e.g. verifier).
    """
    # Extract the last user message as the cache key.
    prompt_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            prompt_text = m.get("content", "")
            break

    # Feature 1: semantic cache lookup BEFORE the LLM call.
    if use_cache and prompt_text:
        try:
            from .semantic_cache import get_cache
            cache = get_cache()
            cached = cache.get(prompt_text, session_id=session_id)
            if cached is not None:
                logger.info("LLM cache HIT for session=%s model=%s (no call made)", session_id, tier.model)
                return cached
        except Exception as e:
            logger.warning("Semantic cache lookup failed (%s); proceeding to LLM", e)

    # ── LLM HTTP call ──
    url = tier.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": tier.model,
        "messages": messages,
        "temperature": tier.temperature,
        "max_tokens": tier.max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if tier.api_key:
        headers["Authorization"] = f"Bearer {tier.api_key}"
    # Feature 4: sticky session header for providers that support it.
    if session_id:
        headers["X-Session-Id"] = session_id

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = ""
        try:
            text = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        raise LLMError(f"{tier.model} HTTP {e.code}: {text[:400]}") from None
    except urllib.error.URLError as e:
        raise LLMError(f"{tier.model} unreachable: {e.reason}") from None

    # Capture usage for metering (not all providers return this).
    _chat_last_usage = payload.get("usage") or {}

    content: Optional[str] = (
        payload.get("choices", [{}])[0].get("message", {}).get("content")
    )
    if not content:
        raise LLMError(f"{tier.model} returned no content: {json.dumps(payload)[:400]}")

    # Store usage as module-level so callers can read it after chat().
    _store_usage(_chat_last_usage)

    result = content.strip()

    # Feature 1: store the result in the semantic cache.
    if use_cache and prompt_text:
        try:
            from .semantic_cache import get_cache
            cache = get_cache()
            cache.put(prompt_text, result, session_id=session_id, model=tier.model)
        except Exception as e:
            logger.warning("Semantic cache put failed: %s", e)

    return result


# ── Usage metering (module-level side channel) ──────────────────────────────

_chat_usage_state: Dict[str, Any] = {}


def _store_usage(usage: Dict[str, Any]) -> None:
    """Accumulate usage from the latest chat() call."""
    global _chat_usage_state
    _chat_usage_state["prompt_tokens"] = _chat_usage_state.get("prompt_tokens", 0) + int(usage.get("prompt_tokens", 0))
    _chat_usage_state["completion_tokens"] = _chat_usage_state.get("completion_tokens", 0) + int(usage.get("completion_tokens", 0))
    _chat_usage_state["total_tokens"] = _chat_usage_state.get("total_tokens", 0) + int(usage.get("total_tokens", 0))


def pop_usage() -> Dict[str, int]:
    """Return accumulated usage since last pop and reset the counter."""
    global _chat_usage_state
    data = dict(_chat_usage_state)
    _chat_usage_state = {}
    return data



# ── Usage metering (module-level side channel) ──────────────────────────────

_chat_usage_state: Dict[str, Any] = {}


def _store_usage(usage: Dict[str, Any]) -> None:
    """Accumulate usage from the latest chat() call."""
    global _chat_usage_state
    _chat_usage_state["prompt_tokens"] = _chat_usage_state.get("prompt_tokens", 0) + int(usage.get("prompt_tokens", 0))
    _chat_usage_state["completion_tokens"] = _chat_usage_state.get("completion_tokens", 0) + int(usage.get("completion_tokens", 0))
    _chat_usage_state["total_tokens"] = _chat_usage_state.get("total_tokens", 0) + int(usage.get("total_tokens", 0))


def pop_usage() -> Dict[str, int]:
    """Return accumulated usage since last pop and reset the counter."""
    global _chat_usage_state
    data = dict(_chat_usage_state)
    _chat_usage_state = {}
    return data
