# arctus_research_engine/engine.py
"""Factory and lifecycle facade for the Research Engine subsystem.

The Arctus Agent Orchestration Framework instantiates this class,
injects dependencies, calls start(), and manages shutdown.
"""

from arctus_research_engine.interfaces import (
    IEventBus,
    IPersistentMemory,
    IPluginLoader,
    ITelemetry,
)
from arctus_research_engine.orchestrator import ResearchOrchestrator
from arctus_research_engine.gateway import EventGateway
from arctus_research_engine.planning import PlanningEngine
from arctus_research_engine.pipeline.retrieval import RetrievalSubsystem
from arctus_research_engine.pipeline.analysis import EvidenceAnalysisEngine
from arctus_research_engine.pipeline.synthesis import SynthesisEngine
from arctus_research_engine.pipeline.citation import CitationEngine


class ResearchEngine:
    """Top-level subsystem object. No __main__. No CLI. No env parsing."""

    def __init__(
        self,
        config: Dict[str, Any],
        event_bus: IEventBus,
        persistent_memory: IPersistentMemory,
        plugin_loader: IPluginLoader,
        telemetry: ITelemetry,
    ):
        self._config = config
        self._event_bus = event_bus
        self._memory = persistent_memory
        self._plugins = plugin_loader
        self._telemetry = telemetry
        self._gateway: Optional[EventGateway] = None

    async def start(self) -> None:
        """Wire plugins, build pipeline, open event subscriptions."""
        # Resolve pre-installed plugins via framework registry
        planner_strategy = await self._plugins.load(self._config["planning_strategy"])
        retrieval_adapters = [
            await self._plugins.load(name)
            for name in self._config["retrieval_adapters"]
        ]
        ranking_strategy = await self._plugins.load(self._config["ranking_strategy"])
        analysis_strategy = await self._plugins.load(self._config["analysis_strategy"])
        synthesis_strategy = await self._plugins.load(self._config["synthesis_strategy"])
        citation_formatter = await self._plugins.load(self._config["citation_formatter"])

        # Initialize plugins with secrets injected by framework (via ISecretResolver if needed)
        for plugin in [*retrieval_adapters, planner_strategy, ranking_strategy,
 analysis_strategy, synthesis_strategy, citation_formatter]:
            # In a real system, the framework may have already initialized these.
            # This hook is for engine-specific config only.
            pass

        # Assemble pipeline
        planner = PlanningEngine(planner_strategy, None, self._telemetry)  # model gateway injected by framework later if needed
        retrieval = RetrievalSubsystem(
            adapters=retrieval_adapters,
            ranking_strategy=ranking_strategy,
            embedder=None,  # injected by framework            telemetry=self._telemetry,
        )
        analysis = EvidenceAnalysisEngine(analysis_strategy, None, self._telemetry)
        synthesis = SynthesisEngine(synthesis_strategy, None, self._telemetry)
        citation = CitationEngine(citation_formatter, self._telemetry)

        orchestrator = ResearchOrchestrator(
            persistent_memory=self._memory,
            event_bus=self._event_bus,
            planner=planner,
            retrieval=retrieval,
            analysis=analysis,
            synthesis=synthesis,
            citation=citation,
            telemetry=self._telemetry,
            deterministic_salt=self._config.get("deterministic_salt", "arctus-research-v1"),
        )

        self._gateway = EventGateway(self._event_bus, orchestrator, self._telemetry)
        await self._gateway.start()

    async def stop(self) -> None:
        if self._gateway:
            await self._gateway.stop()
        await self._telemetry.log("info", "ResearchEngine stopped")


from typing import Optional, Dict  # noqa: E402
