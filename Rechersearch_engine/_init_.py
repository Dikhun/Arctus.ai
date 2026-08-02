# arctus_research_engine/__init__.py
"""Arctus Research Engine — Cognitive subsystem for autonomous scientific discovery."""

from arctus_research_engine.engine import ResearchEngine
from arctus_research_engine.interfaces import (
    IEventBus,
    IAgentMesh,
    IHttpClient,
    IKnowledgeGraph,
    ILockProvider,
    IModelGateway,
    IPersistentMemory,
    IPluginLoader,
    ISecretResolver,
    ITelemetry,
)
from arctus_research_engine.models import (
    AnalysisReport,
    Citation,
    EvidenceRecord,
    RankedEvidenceCollection,
    ResearchDirective,
    ResearchEvent,
    ResearchReport,
    WorkflowManifest,
)
from arctus_research_engine.plugins.base import (
    AnalysisStrategy,
    BasePlugin,
    CitationFormatter,
    ExecutionContext,
    PlanningStrategy,
    RankingStrategy,
    RetrievalAdapter,
    SynthesisStrategy,
)

__all__ = [
    "ResearchEngine",
    "IEventBus",
    "IAgentMesh",
    "IHttpClient",
    "IKnowledgeGraph",
    "ILockProvider",
    "IModelGateway",
    "IPersistentMemory",
    "IPluginLoader",
    "ISecretResolver",
    "ITelemetry",
    "AnalysisReport",
    "Citation",
    "EvidenceRecord",
    "RankedEvidenceCollection",
    "ResearchDirective",
    "ResearchEvent",
    "ResearchReport",
    "WorkflowManifest",
    "AnalysisStrategy",
    "BasePlugin",
    "CitationFormatter",
    "ExecutionContext",
    "PlanningStrategy",
    "RankingStrategy",
    "RetrievalAdapter",
    "SynthesisStrategy",
]
