#!/usr/bin/env python3
"""
Arctus AI — config.py
Central configuration dataclass with persistence to ~/.arctus/config.json.
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("arctus.config")

CONFIG_DIR: Path = Path.home() / ".arctus"
CONFIG_FILE: Path = CONFIG_DIR / "config.json"


@dataclass
class ArctusConfig:
    """
    Production configuration for Arctus AI.
    Environment variables override saved configuration at runtime.
    """
    llm_provider: str = "ollama"
    model: Optional[str] = None
    mcp_servers: list[str] = field(default_factory=list)
    max_agents: int = 100
    handoff_cycle: float = 0.8
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    request_timeout: float = 120.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArctusConfig:
        # Forward-compat: ignore unknown keys
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: Optional[Path] = None) -> None:
        target = path or CONFIG_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Configuration saved to %s", target)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> ArctusConfig:
        target = path or CONFIG_FILE
        if not target.exists():
            logger.debug("No config file at %s; using defaults.", target)
            return cls()
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except json.JSONDecodeError as exc:
            logger.error("Config file corrupt at %s: %s", target, exc)
            return cls()

    def merge_env(self) -> ArctusConfig:
        """Overlay environment variables onto this instance (mutating)."""
        self.llm_provider = os.getenv("ARCTUS_PROVIDER", self.llm_provider)
        self.model = os.getenv("ARCTUS_MODEL", self.model)
        self.api_key = os.getenv("ARCTUS_API_KEY", self.api_key)
        self.base_url = os.getenv("ARCTUS_BASE_URL", self.base_url)
        return self
