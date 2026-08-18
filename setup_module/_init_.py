"""
Arctus AI - Local-first multi-agent orchestration framework.

Provides tiered LLM access:
- fast:    Local Ollama instance
- strong:  OpenRouter API (Claude, GPT-4, etc.)
- free:    Hugging Face Spaces / Inference API
"""

__version__ = "1.0.0"
__all__ = [
    "LLMClient",
    "Orchestrator",
    "Agent",
    "Config",
    "setup_provider",
    "check_status",
]

import os
import sys
from pathlib import Path
from typing import Optional

# ============================================================================
# CONFIGURATION DISCOVERY
# ============================================================================

def get_config_dir() -> Path:
    """Return the user's config directory for Arctus."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        config_dir = base / "arctus"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        config_dir = base / "arctus"
    
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Return the path to config.json."""
    return get_config_dir() / "config.json"


def get_env_path() -> Path:
    """Return the path to .env file."""
    return get_config_dir() / ".env"


# ============================================================================
# LAZY IMPORTS (avoid circular dependencies)
# ============================================================================

def _lazy_import(name: str):
    """Lazy import to avoid circular dependencies during initialization."""
    import importlib
    return importlib.import_module(f"arctus.{name}")


# Public API accessors
def LLMClient(*args, **kwargs):
    from arctus.llm import LLMClient as _LLMClient
    return _LLMClient(*args, **kwargs)


def Orchestrator(*args, **kwargs):
    from arctus.orchestrator import Orchestrator as _Orchestrator
    return _Orchestrator(*args, **kwargs)


def Agent(*args, **kwargs):
    from arctus.agent import Agent as _Agent
    return _Agent(*args, **kwargs)


def Config(*args, **kwargs):
    from arctus.config import Config as _Config
    return _Config(*args, **kwargs)


def setup_provider(provider: str, **kwargs):
    """Configure a provider preset."""
    from arctus.setup import setup_provider as _setup
    return _setup(provider, **kwargs)


def check_status():
    """Check health of all configured providers."""
    from arctus.setup import check_status as _check
    return _check()
