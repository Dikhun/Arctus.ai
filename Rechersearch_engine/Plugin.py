# arctus_research_engine/plugins/base.py
"""Base classes for research engine plugins."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from arctus_research_engine.interfaces import (
    IHttpClient,
    IModelGateway,
    IPersistentMemory,
    ISecretResolver,
    ITelemetry,
)
from arctus_research_engine.models import (
    AnalysisReport,
    Citation,
    EvidenceRecord,
    ExecutionMode,
    RankedEvidenceCollection,
    RawDocument,
    ReportSection,
    ResearchDirective,
    ResearchPlanStep,
    SearchQuery,
)


class ExecutionContext:
    """Inbound context for every plugin invocation."""

    def __init__(
        self,
        correlation_id: str,
        execution_mode: ExecutionMode,
        telemetry: ITelemetry,
        secret_resolver: ISecretResolver,
 ):
        self.correlation_id = correlation_id
        self.execution_mode = execution_mode
        self.telemetry = telemetry
        self.secret_resolver = secret_resolver


class BasePlugin(ABC):
    """All plugins extend this. Lifecycle managed by framework via IPluginLoader."""

    def __init__(self, name: str, version: str, plugin_type: str):
        self.name = name
        self.version = version
        self.plugin_type = plugin_type

    async def initialize(
        self,
        config: Dict[str, Any],
        secret_resolver: ISecretResolver,
    ) -> None:
        """Called once by the engine after framework instantiation."""

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        ...
class RetrievalAdapter(BasePlugin, ABC):
    """Adapter for external knowledge sources (search APIs, databases, etc.)."""

    @abstractmethod
    async def retrieve(
        self,
        query: SearchQuery,
        http_client: IHttpClient,
        context: ExecutionContext,
    ) -> List[RawDocument]:
        ...
class RankingStrategy(BasePlugin, ABC):
    """Algorithmic reranking of retrieved evidence."""

    @abstractmethod
    async def rank(
        self,
        documents: List[RawDocument],
        query: SearchQuery,
        embedder: IModelGateway,
        context: ExecutionContext,
    ) -> List[EvidenceRecord]:
        ...
class AnalysisStrategy(BasePlugin, ABC):
    """Claim extraction, stance classification, and contradiction detection."""

    @abstractmethod
    async def analyze(
        self,
        evidence: RankedEvidenceCollection,
        directive: ResearchDirective,
        model_gateway: IModelGateway,
        context: ExecutionContext,
    ) -> AnalysisReport:
        ...
class SynthesisStrategy(BasePlugin, ABC):
    """Narrative or quantitative integration of validated evidence."""

    @abstractmethod
    async def synthesize(
        self,
        evidence: RankedEvidenceCollection,
        analysis: AnalysisReport,
        directive: ResearchDirective,
        model_gateway: IModelGateway,
        context: ExecutionContext,
    ) -> List[ReportSection]:
        ...


class CitationFormatter(BasePlugin, ABC):
    """Bibliographic formatting and provenance chain generation."""

    @abstractmethod
    async def format_citations(
        self,
        evidence: RankedEvidenceCollection,
        required_format: str,
        context: ExecutionContext,
    ) -> List[Citation]:
        ...
class PlanningStrategy(BasePlugin, ABC):
    """Research planning and autonomous decomposition."""

    @abstractmethod
    async def create_plan(
        self,
        directive: ResearchDirective,
        model_gateway: IModelGateway,
        context: ExecutionContext,
    ) -> List[ResearchPlanStep]:
        ...

    @abstractmethod
    async def determine_next_action(
        self,
        manifest: "WorkflowManifest",  # noqa: F821
        model_gateway: IModelGateway,
        context: ExecutionContext,
    ) -> Optional[ResearchPlanStep]:
        ...
