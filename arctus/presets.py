#!/usr/bin/env python3
"""
Arctus AI — presets.py
Provider presets, model registries, and environment-aware configuration bundles.
Supports: Ollama, OpenRouter, OmniRoute, RunPod, HuggingFace, OpenAI-compatible.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ProviderPreset:
    """
    Immutable provider configuration template.
    """
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    request_timeout: float = 120.0
    max_retries: int = 3
    retry_backoff: float = 1.5
    supports_streaming: bool = True
    supports_tools: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelPreset:
    """
    Per-model tuning parameters.
    """
    provider: str
    model_id: str
    context_window: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 2048
    system_prompt: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# BUILT-IN PROVIDER PRESETS
# ═══════════════════════════════════════════════════════════════════════════

PROVIDER_REGISTRY: dict[str, ProviderPreset] = {
    "ollama": ProviderPreset(
        name="ollama",
        base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        api_key_env="OLLAMA_API_KEY",  # Usually unused; kept for proxy setups
        default_model="llama3.2",
        request_timeout=300.0,
        max_retries=2,
        supports_streaming=True,
        supports_tools=True,
    ),
    
    "openrouter": ProviderPreset(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        default_model="openai/gpt-4o-mini",
        request_timeout=120.0,
        max_retries=3,
        headers={
            "HTTP-Referer": "https://arctus.ai",
            "X-Title": "Arctus AI Orchestrator",
        },
    ),
    
    "openai": ProviderPreset(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        request_timeout=120.0,
        max_retries=3,
    ),
    
    "runpod": ProviderPreset(
        name="runpod",
        base_url=os.getenv("RUNPOD_BASE_URL", "https://api.runpod.ai/v2"),
        api_key_env="RUNPOD_API_KEY",
        default_model="",
        request_timeout=300.0,
        max_retries=2,
        supports_streaming=True,
        supports_tools=False,  # Serverless endpoints vary; set per-endpoint
    ),
    
    "huggingface": ProviderPreset(
        name="huggingface",
        base_url="https://api-inference.huggingface.co",
        api_key_env="HF_API_TOKEN",  # HuggingFace standard env var
        default_model="meta-llama/Llama-3.2-3B-Instruct",
        request_timeout=300.0,
        max_retries=3,
        supports_streaming=False,
        supports_tools=False,
        headers={"Authorization": "Bearer ${HF_API_TOKEN}"},
    ),
    
    "omniroute": ProviderPreset(
        name="omniroute",
        base_url=os.getenv("OMNIROUTE_BASE_URL", "http://localhost:8080/v1"),
        api_key_env="OMNIROUTE_API_KEY",
        default_model="default",
        request_timeout=120.0,
        max_retries=3,
        supports_streaming=True,
        supports_tools=True,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# MODEL PRESETS ( curated high-performance defaults )
# ═══════════════════════════════════════════════════════════════════════════

MODEL_REGISTRY: dict[str, ModelPreset] = {
    # Ollama family
    "llama3.2": ModelPreset(provider="ollama", model_id="llama3.2", context_window=128000),
    "llama3.1": ModelPreset(provider="ollama", model_id="llama3.1", context_window=128000),
    "mistral": ModelPreset(provider="ollama", model_id="mistral", context_window=32000),
    "qwen2.5": ModelPreset(provider="ollama", model_id="qwen2.5", context_window=128000),
    "phi4": ModelPreset(provider="ollama", model_id="phi4", context_window=16000),
    
    # OpenRouter family
    "gpt-4o": ModelPreset(provider="openrouter", model_id="openai/gpt-4o", context_window=128000),
    "gpt-4o-mini": ModelPreset(provider="openrouter", model_id="openai/gpt-4o-mini", context_window=128000),
    "claude-3.5-sonnet": ModelPreset(provider="openrouter", model_id="anthropic/claude-3.5-sonnet", context_window=200000),
    "gemini-1.5-pro": ModelPreset(provider="openrouter", model_id="google/gemini-1.5-pro", context_window=2000000),
    
    # HuggingFace family
    "hf-llama-3.2-3b": ModelPreset(provider="huggingface", model_id="meta-llama/Llama-3.2-3B-Instruct", context_window=128000),
    "hf-mistral-7b": ModelPreset(provider="huggingface", model_id="mistralai/Mistral-7B-Instruct-v0.3", context_window=32000),
    "hf-qwen-2.5-7b": ModelPreset(provider="huggingface", model_id="Qwen/Qwen2.5-7B-Instruct", context_window=128000),
}


# ═══════════════════════════════════════════════════════════════════════════
# PRESET LOADER / SAVER
# ═══════════════════════════════════════════════════════════════════════════

PRESET_DIR = Path.home() / ".arctus" / "presets"


def load_preset_file(name: str) -> dict[str, Any]:
    """Load a JSON preset from ~/.arctus/presets/{name}.json"""
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_preset_file(name: str, data: dict[str, Any]) -> None:
    """Save a JSON preset to ~/.arctus/presets/{name}.json"""
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESET_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def resolve_preset(
    provider: str | None = None,
    model: str | None = None,
) -> tuple[ProviderPreset, ModelPreset]:
    """
    Resolve provider + model presets from name hints or environment.
    Returns (provider_preset, model_preset).
    """
    # Provider resolution
    if not provider:
        for env_key, prov_name in [
            ("OLLAMA_HOST", "ollama"),
            ("OPENROUTER_API_KEY", "openrouter"),
            ("OPENAI_API_KEY", "openai"),
            ("RUNPOD_API_KEY", "runpod"),
            ("HF_API_TOKEN", "huggingface"),
            ("OMNIROUTE_API_KEY", "omniroute"),
        ]:
            if os.getenv(env_key):
                provider = prov_name
                break
        provider = provider or "ollama"  # ultimate fallback
    
    prov = PROVIDER_REGISTRY.get(provider)
    if not prov:
        raise ValueError(f"Unknown provider '{provider}'. "
                         f"Known: {list(PROVIDER_REGISTRY.keys())}")
    
    # Model resolution
    if not model:
        model = prov.default_model
    
    mod = MODEL_REGISTRY.get(model)
    if not mod:
        # Build ad-hoc model preset from provider defaults
        mod = ModelPreset(provider=provider, model_id=model)
    
    return prov, mod


def get_api_key(preset: ProviderPreset) -> str | None:
    """Retrieve API key from environment per preset's declared env var."""
    if not preset.api_key_env:
        return None
    return os.getenv(preset.api_key_env)


# ═══════════════════════════════════════════════════════════════════════════
# ENVIRONMENT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def detect_available_providers() -> list[str]:
    """Scan environment and return list of providers with credentials."""
    available: list[str] = []
    for name, preset in PROVIDER_REGISTRY.items():
        if name == "ollama":
            # Ollama is available if host responds (lightweight check deferred)
            available.append(name)
            continue
        if get_api_key(preset):
            available.append(name)
    return available


def print_diagnostics() -> None:
    """Print environment diagnostic summary."""
    print("═" * 60)
    print("  Arctus AI — Environment Diagnostics")
    print("═" * 60)
    print(f"Detected providers: {', '.join(detect_available_providers()) or 'None'}")
    print(f"Preset directory:   {PRESET_DIR}")
    for name, preset in PROVIDER_REGISTRY.items():
        key = get_api_key(preset)
        status = "✓ set" if key else "— not set"
        print(f"  [{name:12}] {preset.api_key_env:25} {status}")
    print("═" * 60)
