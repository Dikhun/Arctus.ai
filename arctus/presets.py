"""Tier presets for common providers."""
from __future__ import annotations

import os
from typing import Dict

from .config import Config, Tier, load_config, save_config


PRESETS: Dict[str, Dict[str, str]] = {
    "openrouter_free": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "api_key_env": "OPENROUTER_API_KEY",
        "applies_to": "fast",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3.5-sonnet",
        "api_key_env": "OPENROUTER_API_KEY",
        "applies_to": "strong",
    },
    "omniroute_local": {
        "base_url": "http://localhost:20128/v1",
        "model": "llama3.2",
        "api_key_env": "ARCTUS_OMNIROUTE_KEY",
        "applies_to": "fast",
    },
    "omniroute_remote": {
        "base_url": "https://api.omniroute.ai/v1",
        "model": "llama3.2",
        "api_key_env": "OMNIROUTE_API_KEY",
        "applies_to": "fast",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5-coder:32b",
        "api_key_env": "",
        "applies_to": "fast",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "builder_model": "gpt-4o-mini",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "applies_to": "strong",
    },
    "anthropic_via_openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3.5-sonnet",
        "api_key_env": "OPENROUTER_API_KEY",
        "applies_to": "strong",
    },
}


def apply_preset(name: str, cfg: Config | None = None) -> Config:
    """Apply a named preset to the relevant tier. Returns the updated config."""
    if name not in PRESETS:
        raise KeyError(f"Unknown preset {name!r}. Known: {list(PRESETS)}")
    p = PRESETS[name]
    cfg = cfg or load_config()
    api_key = os.environ.get(p["api_key_env"], "") if p["api_key_env"] else ""
    new_tier = Tier(
        base_url=p["base_url"],
        model=p["model"],
        api_key=api_key,
        temperature=0.3,
    )
    setattr(cfg, p["applies_to"], new_tier)
    save_config(cfg)
    return cfg


def apply_preset_silent(name: str, cfg: Config | None = None) -> Config:
    """Apply a named preset without persisting to disk. Used by tier resolver."""
    if name not in PRESETS:
        return cfg or load_config()
    p = PRESETS[name]
    cfg = cfg or load_config()
    api_key = os.environ.get(p["api_key_env"], "") if p["api_key_env"] else ""
    new_tier = Tier(
        base_url=p["base_url"],
        model=p["model"],
        api_key=api_key,
        temperature=0.3,
    )
    setattr(cfg, p["applies_to"], new_tier)
    return cfg


def list_presets() -> Dict[str, Dict[str, str]]:
    return PRESETS
    
