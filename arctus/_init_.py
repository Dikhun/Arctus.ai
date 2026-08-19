#!/usr/bin/env python3
"""
Arctus AI — __init__.py
Package root exposing public API surface. All internal modules are lazy-loaded
to minimize import overhead for CLI entry points.

Architecture alignment:
    arctus/
    ├── __init__.py      (this file — public API facade)
    ├── config.py
    ├── orchestrator.py
    ├── agents.py
    ├── rate_limit.py
    ├── session.py
    ├── mcp.py
    ├── consortium.py
    ├── dcr.py
    ├── sandbox.py
    ├── presets.py
    ├── sandbox_runner.py
    ├── guardrail.py
    └── computer_use.py
"""

from __future__ import annotations

import sys
import logging
from typing import TYPE_CHECKING, Any

# ── Version & Metadata ──────────────────────────────────────────────────
__version__: str = "1.0.0"
__author__: str = "Arctus.ai"
__license__: str = "MIT"

# ── Logging Configuration ───────────────────────────────────────────────────
logger = logging.getLogger("arctus")
logger.addHandler(logging.NullHandler())

def configure_logging(level: int = logging.INFO) -> None:
    """Configure Arctus root logger with a standard stream handler."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)

# ── Lazy Import Helpers ──────────────────────────────────────────────────────
if TYPE_CHECKING:
    from .orchestrator import Orchestrator
    from .agents import Agent, AgentRoster
    from .mcp import MCPClient, MCPServer
    from .consortium import Consortium
    from .session import SessionManager
    from .guardrail import Guardrail
    from .config import ArctusConfig

# ── Public API Exports ──────────────────────────────────────────────────────
__all__: list[str] = [
    "__version__",
    "configure_logging",
    "ArctusConfig",
    "Orchestrator",
    "Agent",
    "AgentRoster",
    "MCPClient",
    "MCPServer",
    "Consortium",
    "SessionManager",
    "Guardrail",
    "create_orchestrator",
]

# ── Factory Functions ───────────────────────────────────────────────────────
def create_orchestrator(
    llm_provider: str = "ollama",
    model: str | None = None,
    mcp_servers: list[str] | None = None,
    max_agents: int = 100,
    handoff_cycle: float = 0.8,
    **kwargs: Any,
) -> "Orchestrator":
    """
    Factory: build a production-ready Orchestrator with sane defaults.

    Args:
        llm_provider: One of "ollama", "openrouter", "openai", "runpod",
                      "huggingface", "omniroute".
        model: Model identifier (provider-specific).
        mcp_servers: List of MCP server URIs or command strings.
        max_agents: Roster ceiling (default 100).
        handoff_cycle: Target handoff ratio [0.0–1.0] (default 0.8 = 80%).
        **kwargs: Forwarded to ArctusConfig.

    Returns:
        Configured Orchestrator instance.
    """
    from .config import ArctusConfig
    from .orchestrator import Orchestrator

    config = ArctusConfig(
        llm_provider=llm_provider,
        model=model,
        mcp_servers=mcp_servers or [],
        max_agents=max_agents,
        handoff_cycle=handoff_cycle,
        **kwargs,
    )
    return Orchestrator(config=config)
