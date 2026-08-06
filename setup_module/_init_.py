"""Arctus AI package initialization."""
from __future__ import annotations

from .config import Config, Tier, RateLimitConfig, load_config, save_config
from .agent import QueenAgent
from . import presets
from . import setup

__version__ = "1.0.0"

__all__ = [
    "Config",
    "Tier",
    "RateLimitConfig",
    "QueenAgent",
    "load_config",
    "save_config",
    "presets",
    "setup",
    "__version__",
]
