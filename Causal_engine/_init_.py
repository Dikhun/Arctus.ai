"""Arctus Causal Engine — Autonomous Setup & Orchestration."""

__version__ = "1.0.0"

from .bootstrap import CausalEngineBootstrap
from .types import SystemInfo, ServiceStatus, CapabilityMeta

__all__ = [
    "CausalEngineBootstrap",
    "SystemInfo",
    "ServiceStatus",
    "CapabilityMeta",
    "__version__",
]
