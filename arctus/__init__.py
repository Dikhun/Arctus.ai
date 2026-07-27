"""Arctus.ai — local-first multi-agent orchestrator (Python).

Public surface for programmatic use:
    from arctus import Config, QueenAgent, TaskResult, build_roster, ...
"""
from .config import Config, Tier, load_config, save_config  # noqa: F401
from .orchestrator import QueenAgent, TaskResult, Step  # noqa: F401
from .rate_limit import RateLimitConfig, RateLimitError  # noqa: F401
from .agents import AgentSpec, build_roster, roster_summary, pick  # noqa: F401
from . import session  # noqa: F401
from . import mcp  # noqa: F401
from . import consortium  # noqa: F401
from . import dcr  # noqa: F401
from . import sandbox  # noqa: F401
from . import presets  # noqa: F401
from . import sandbox_runner  # noqa: F401
from . import guardrail  # noqa: F401
from . import computer_use  # noqa: F401

__version__ = "1.0.0"
__all__ = [
    "Config", "Tier", "load_config", "save_config",
    "QueenAgent", "TaskResult", "Step",
    "RateLimitConfig", "RateLimitError",
    "AgentSpec", "build_roster", "roster_summary", "pick",
    "session", "mcp", "consortium", "dcr", "sandbox", "presets",
    "sandbox_runner", "guardrail", "computer_use",
    "__version__",
]
