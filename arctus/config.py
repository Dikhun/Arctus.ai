"""Configuration for Arctus.ai.

Keys live in the user's environment (or ~/.config/arctus-ai/config.json),
never in the code. Nothing is hardcoded, nothing leaves the machine.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional


CONFIG_DIR = Path.home() / ".config" / "arctus-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"


@dataclass
class Tier:
    """One model tier.

    Works against any OpenAI-compatible /chat/completions endpoint:
    OpenAI, OpenRouter, Ollama (/v1), LM Studio, vLLM, etc.
    """
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096


# ── Subscription tiers ────────────────────────────────────────────────────
# Each tier controls model mix, parallel workers, and monthly quotas.
# Prices are per prompt run for the budget tiers; PAYG is $1/1M tokens.

TIER_NAMES = ("free", "tier1", "tier2", "tier3", "payg")

TIER_QUOTAS: Dict[str, Dict[str, Any]] = {
    "free": {
        "label": "Free",
        "workers": 1,
        "monthly_runs": 50,
        "cost_per_run_usd": 0.0,
        "token_price_usd": 0.0,       # free models via OpenRouter
        "preset": "openrouter_free",
    },
    "tier1": {
        "label": "Tier 1 ($17/mo)",
        "workers": 2,
        "monthly_runs": 1_200,
        "cost_per_run_usd": 0.007,
        "token_price_usd": 1.0,       # $1/1M tokens (input+output)
        "preset": "openrouter",        # Flash planner + mid coder
    },
    "tier2": {
        "label": "Tier 2 ($80/mo)",
        "workers": 4,
        "monthly_runs": 2_650,
        "cost_per_run_usd": 0.015,
        "token_price_usd": 1.0,
        "preset": "openrouter",        # mid-tier coding model
    },
    "tier3": {
        "label": "Tier 3 ($180/mo)",
        "workers": 6,
        "monthly_runs": 2_000,        # heavy complex runs
        "cost_per_run_usd": 0.045,
        "token_price_usd": 1.0,
        "preset": "openrouter",        # deep-reasoning verification judges
    },
    "payg": {
        "label": "Pay As You Go",
        "workers": 2,
        "monthly_runs": float("inf"),  # unlimited by run count
        "cost_per_run_usd": 0.0,
        "token_price_usd": 1.0,        # $1/1M tokens (input+output)
        "preset": "openrouter",
    },
}


@dataclass
class Config:
    # Lightweight tier: formatting, syntax checks, summaries, linting.
    fast: Tier = field(default_factory=lambda: Tier(
        base_url=os.environ.get("ARCTUS_FAST_BASE_URL", "http://localhost:11434/v1"),
        model=os.environ.get("ARCTUS_FAST_MODEL", "llama3.2"),
        api_key=os.environ.get("ARCTUS_FAST_API_KEY", "ollama"),
        temperature=0.2,
    ))
    # Primary tier: refactors, design decisions, multi-file changes.
    strong: Tier = field(default_factory=lambda: Tier(
        base_url=os.environ.get("ARCTUS_STRONG_BASE_URL", "https://api.openai.com/v1"),
        model=os.environ.get("ARCTUS_STRONG_MODEL", "gpt-4o-mini"),
        api_key=os.environ.get("ARCTUS_STRONG_API_KEY", ""),
        temperature=0.4,
    ))
    # Planner uses the strong tier by default.
    planner_uses: str = "strong"
    # Complexity routing threshold (words in prompt).
    complexity_threshold_words: int = 40
    # 80% context-handoff rule.
    agent_context_limit: int = 128_000
    handoff_threshold_ratio: float = 0.80
    # Subscription tier for the current user/session.
    subscription_tier: str = os.environ.get("ARCTUS_TIER", "free")
    # Max parallel workers (controlled by tier).
    max_workers: int = 2
    # Feature 1: Semantic cache (exact + fuzzy match before LLM calls).
    semantic_cache_enabled: bool = os.environ.get("ARCTUS_CACHE_ENABLED", "1") != "0"
    semantic_cache_threshold: float = float(os.environ.get("ARCTUS_CACHE_THRESHOLD", "0.85"))
    semantic_cache_backend: str = os.environ.get("ARCTUS_CACHE_BACKEND", "auto")
    # Feature 4: Sticky sessions — thread session_id into cache key + provider.
    sticky_session_enabled: bool = os.environ.get("ARCTUS_STICKY_SESSION", "1") != "0"


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load from JSON file; fall back to env-derived defaults."""
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            tiers = {}
            for name in ("fast", "strong"):
                if name in raw:
                    tiers[name] = Tier(**raw[name])
            rest = {k: v for k, v in raw.items() if k not in ("fast", "strong")}
            return Config(**tiers, **rest)
        except Exception:
            pass
    return Config()


def save_config(cfg: Config) -> Path:
    ensure_dirs()
    data = asdict(cfg)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CONFIG_FILE


def tier_for(cfg: Config, name: str) -> Tier:
    return getattr(cfg, name)


def resolve_tier_for_config(cfg: Config, tier_name: Optional[str] = None) -> Config:
    """Build a Config override for a given subscription tier.

    Applies the tier's preset (model mix) and sets max_workers. Does NOT
    overwrite the caller's existing env-derived keys unless the preset
    explicitly provides values.

    Returns a *new* Config with tier-appropriate model/preset applied.
    """
    tier_name = (tier_name or cfg.subscription_tier).lower()
    if tier_name not in TIER_QUOTAS:
        tier_name = "free"  # safe fallback
    quota = TIER_QUOTAS[tier_name]

    # Apply the tier's model preset if it has one.
    preset_name = quota.get("preset")
    if preset_name:
        try:
            from .presets import apply_preset_silent
            cfg = apply_preset_silent(preset_name, cfg=cfg)
        except Exception:
            pass  # missing preset — use current config as-is

    cfg.subscription_tier = tier_name
    cfg.max_workers = quota["workers"]
    return cfg
