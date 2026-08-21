#!/usr/bin/env python3
"""
Arctus AI — setup.py
Provider preset management and configuration helpers.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


# ═══════════════════════════════════════════════════════════════════════════
# PRESET DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ModelPreset:
    """Configuration for a specific model."""
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 2048
    context_window: int = 4096


@dataclass
class ProviderPreset:
    """Configuration for an LLM provider."""
    name: str
    base_url: str
    api_key_env: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    extra_body: Dict[str, Any] = field(default_factory=dict)
    request_timeout: float = 120.0
    max_retries: int = 3
    retry_backoff: float = 1.0
    supports_tools: bool = False
    default_model: Optional[ModelPreset] = None


# ═══════════════════════════════════════════════════════════════════════════
# PRESET REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

OLLAMA_PRESET = ProviderPreset(
    name="ollama",
    base_url="http://localhost:11434",
    api_key_env=None,
    request_timeout=300.0,
    max_retries=2,
    supports_tools=True,
    default_model=ModelPreset(
        model_id="llama3.1",
        temperature=0.7,
        max_tokens=2048
    )
)

OPENROUTER_PRESET = ProviderPreset(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    headers={
        "HTTP-Referer": "https://arctus.ai",
        "X-Title": "Arctus AI"
    },
    request_timeout=120.0,
    max_retries=3,
    retry_backoff=2.0,
    supports_tools=True,
    default_model=ModelPreset(
        model_id="anthropic/claude-3.5-sonnet-20241022",
        temperature=0.7,
        max_tokens=4096
    )
)

HUGGINGFACE_PRESET = ProviderPreset(
    name="huggingface",
    base_url="https://api-inference.huggingface.co",
    api_key_env="HF_TOKEN",
    request_timeout=60.0,
    max_retries=3,
    retry_backoff=2.0,
    supports_tools=False,
    default_model=ModelPreset(
        model_id="microsoft/DialoGPT-medium",
        temperature=0.7,
        max_tokens=512
    )
)

RUNPOD_PRESET = ProviderPreset(
    name="runpod",
    base_url="https://api.runpod.ai/v2",
    api_key_env="RUNPOD_API_KEY",
    request_timeout=120.0,
    max_retries=2,
    retry_backoff=3.0,
    supports_tools=False,
    default_model=ModelPreset(
        model_id="runpod-default",
        temperature=0.7,
        max_tokens=2048
    )
)

PRESETS: Dict[str, ProviderPreset] = {
    "ollama": OLLAMA_PRESET,
    "openrouter": OPENROUTER_PRESET,
    "hf": HUGGINGFACE_PRESET,
    "huggingface": HUGGINGFACE_PRESET,
    "runpod": RUNPOD_PRESET,
}

PROVIDER_REGISTRY = PRESETS


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_config_path() -> Path:
    """Return the path to the user configuration file."""
    config_dir = Path.home() / ".config" / "arctus"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def get_api_key(preset: ProviderPreset) -> Optional[str]:
    """Retrieve API key from environment or config."""
    if preset.api_key_env:
        # Check environment first
        key = os.environ.get(preset.api_key_env)
        if key:
            return key
        
        # Fallback to config file
        config_path = get_config_path()
        if config_path.exists():
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                # Try common key names
                key_map = {
                    "OPENROUTER_API_KEY": ["openrouter_api_key", "openrouter_key"],
                    "HF_TOKEN": ["hf_token", "huggingface_token"],
                    "RUNPOD_API_KEY": ["runpod_api_key", "runpod_key"],
                }
                for key_name in key_map.get(preset.api_key_env, [preset.api_key_env.lower()]):
                    if key_name in cfg:
                        return cfg[key_name]
            except (json.JSONDecodeError, IOError):
                pass
    
    return None


def resolve_preset(provider: str) -> ProviderPreset:
    """Resolve a provider name to its preset configuration."""
    provider = provider.lower().strip()
    
    # Handle aliases
    aliases = {
        "omniroute": "openrouter",
        "or": "openrouter",
        "hf": "huggingface",
    }
    provider = aliases.get(provider, provider)
    
    if provider not in PRESETS:
        raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PRESETS.keys())}")
    
    return PRESETS[provider]


def setup_provider(provider: str, **kwargs: Any) -> Path:
    """
    Setup a provider and save configuration.
    
    Args:
        provider: Provider name
        **kwargs: Provider-specific settings
    
    Returns:
        Path to saved config file
    """
    preset = resolve_preset(provider)
    config_path = get_config_path()
    
    # Load existing config
    cfg: Dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
    
    # Update with provider settings
    cfg["default_provider"] = preset.name
    cfg["providers"] = cfg.get("providers", {})
    cfg["providers"][preset.name] = {
        "base_url": kwargs.get("base_url", preset.base_url),
        "model": kwargs.get("model", preset.default_model.model_id if preset.default_model else None),
    }
    
    # Store API key references
    if preset.api_key_env and "api_key" in kwargs:
        key_config_name = preset.api_key_env.lower().replace("_", "_")
        cfg[key_config_name] = kwargs["api_key"]
        # Also set in environment for current session
        os.environ[preset.api_key_env] = kwargs["api_key"]
    
    # Save
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    
    return config_path


def load_config() -> Dict[str, Any]:
    """Load user configuration."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def get_active_preset() -> Optional[ProviderPreset]:
    """Get the currently active provider preset from config."""
    cfg = load_config()
    provider = cfg.get("default_provider")
    if provider:
        try:
            return resolve_preset(provider)
        except ValueError:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
# MODEL PRESET HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_model_preset(provider: str, model_name: Optional[str] = None) -> ModelPreset:
    """Get a model preset, optionally overriding the default."""
    preset = resolve_preset(provider)
    
    if model_name:
        # Return custom model preset
        return ModelPreset(
            model_id=model_name,
            temperature=0.7,
            max_tokens=2048
        )
    
    if preset.default_model:
        return preset.default_model
    
    # Fallback
    return ModelPreset(model_id="unknown")


# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "ModelPreset",
    "ProviderPreset",
    "PRESETS",
    "PROVIDER_REGISTRY",
    "OLLAMA_PRESET",
    "OPENROUTER_PRESET",
    "HUGGINGFACE_PRESET",
    "RUNPOD_PRESET",
    "get_config_path",
    "get_api_key",
    "resolve_preset",
    "setup_provider",
    "load_config",
    "get_active_preset",
    "get_model_preset",
]