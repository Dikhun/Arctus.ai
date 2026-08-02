# arctus_research_engine/orchestrator.py
"""Stateless workflow controller. All mutable state externalized to persistent memory."""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from arctus_research_engine.interfaces import (
    IEventBus,
    IPersistentMemory,
    ITelemetry,
)
from arctus_research_engine.models import (
    EventType,
    ResearchDirective,
    ResearchEvent,
    ResearchFragment,
    ResearchPlanStep,
    ResearchReport,
    WorkflowManifest,
)
from arctus_research_engine.pipeline.analysis import EvidenceAnalysisEngine
from arctus_research_engine.pipeline.citation import CitationEngine
from arctus_research_engine.pipeline.retrieval import RetrievalSubsystem
from arctus_research_engine.pipeline.synthesis import SynthesisEngine
from arctus_research_engine.planning import PlanningEnginefrom arctus_research_engine.plugins.base import ExecutionContext


class ResearchOrchestrator:
    """The brain of the engine. Stateless; correlation state lives in IPersistentMemory."""

    CHECKPOINT_PREFIX = "research"

    def __init__(
        self,
        persistent_memory: IPersistentMemory,
        event_bus: IEventBus,
        planner: PlanningEngine,
        retrieval: RetrievalSubsystem,
        analysis: EvidenceAnalysisEngine,
        synthesis: SynthesisEngine,
        citation: CitationEngine,
        telemetry: ITelemetry,
        deterministic_salt: str = "arctus-research-v1",
    ):
        self._memory = persistent_memory
        self._event_bus = event_bus
        self._planner = planner
        self._retrieval = retrieval
        self._analysis = analysis
        self._synthesis = synthesis
        self._citation = citation
        self._telemetry = telemetry
        self._salt = deterministic_salt

    async def run(self, event: ResearchEvent) -> None:
        """Main entry point per event. Stateless execution with external checkpointing."""
        async with self._telemetry.start_span("research.orchestrator.run", {
            "correlation_id": event.correlation_id,
        }):
            manifest = await self._load_manifest(event.correlation_id)
            if manifest is None:
                manifest = WorkflowManifest(
                    correlation_id=event.correlation_id,
                    directive=ResearchDirective(**event.payload),
                    execution_mode=event.payload.get("execution_mode", "standard"),
                )
 await self._checkpoint(manifest, stage=0)

            # Idempotency guard            if event.processing_counter > 0:
                last_counter = await self._get_last_counter(event.correlation_id)
                if event.processing_counter <= (last_counter or 0):
                    await self._telemetry.log("info", "Deduplicating stale event", {
                        "correlation_id": event.correlation_id,
                    })
                    return

            context = ExecutionContext(
                correlation_id=event.correlation_id,
                execution_mode=manifest.execution_mode,
                telemetry=self._telemetry,
                secret_resolver=None,  # injected into plugins directly by framework
            )

            try:
                await self._execute_workflow(manifest, context)
                await self._set_counter(event.correlation_id, event.processing_counter)
                await self._publish_completion(manifest)
            except Exception as exc:
                await self._publish_failure(event, exc)
                raise

    async def handle_fragment(self, fragment: ResearchFragment) -> None:
        """Integrate results from peer agents in multi-agent mode."""
        async with self._telemetry.start_span("research.orchestrator.fragment", {
            "correlation_id": fragment.correlation_id,
            "sender": fragment.sender_agent_id,
        }):
            # Load artifact from persistent memory URI            raw = await self._memory.get(fragment.artifact_uri)
            if raw is None:
                raise ValueError(f"Fragment artifact not found: {fragment.artifact_uri}")
            # Deserialize and merge into manifest            manifest = await self._load_manifest(fragment.correlation_id)
            # ... merge logic omitted for brevity, would update checkpoint            await self._checkpoint(manifest, stage=manifest.current_stage_index)

    async def _execute_workflow(self, manifest: WorkflowManifest, context: ExecutionContext) -> None:
        # Phase 1: Planning
        if not manifest.plan:
            plan = await self._planner.create_plan(manifest.directive, context)
            manifest = manifest.with_plan(plan)
            await self._checkpoint(manifest, stage=0)

        # Phase 2-5: Iterative execution
        while not manifest.is_complete:
            step = manifest.plan[manifest.current_stage_index]
            seed = self._derive_seed(manifest.correlation_id, manifest.current_stage_index)

            if step.step_type == "retrieve":
                query = manifest.directive.query
                if step.query_override:
                    query = manifest.directive.__class__(**{**manifest.directive.__dict__, "query": step.query_override})
                evidence = await self._retrieval.execute(
                    query=query, # type: ignore[arg-type]
                    context=context,
                    http_client=None,  # injected by framework through retrieval adapters
                )
                manifest = manifest.with_evidence(evidence)

            elif step.step_type == "analyze":
                if not manifest.evidence.records:
                    raise RuntimeError("Analysis stage reached with no evidence")
                analysis = await self._analysis.execute(
                    manifest.evidence, manifest.directive, context
                )
                manifest = manifest.with_analysis(analysis)

            elif step.step_type == "synthesize":
                if manifest.analysis is None:
                    raise RuntimeError("Synthesis stage reached with no analysis")
                sections = await self._synthesis.execute(
                    manifest.evidence, manifest.analysis, manifest.directive, context
                )
                # store intermediate sections in checkpoint payload manifest = replace(manifest, report= ResearchReport( # type: ignore[call-arg]
 correlation_id=manifest.correlation_id,
                    title="",
                    sections=sections,
                    bibliography=[],
                    integrity_hash="",
                    generated_at=datetime.utcnow(),
                ))

            elif step.step_type == "cite":
                report = await self._citation.execute(
                    manifest.evidence,
                    manifest.report.sections if manifest.report else [],
                    manifest.directive.required_citation_format,
                    manifest.correlation_id,
                    context,
                )
                manifest = replace(manifest, report=report, is_complete=True)  # type: ignore[call-arg]

            elif step.step_type == "delegate":
                # Multi-agent partition; hand off and return
                await self._event_bus.publish(
                    "research.requests",
                    {
                        "correlation_id": manifest.correlation_id,
                        "sub_task_id": step.sub_task_id if hasattr(step, "sub_task_id") else "",
                        "query": step.query_override or manifest.directive.query,
                        "depth": manifest.directive.depth,
                    },
                    ordering_key=manifest.correlation_id,
                )
                # Pause current workflow until fragment returns
                break if not manifest.is_complete:
                manifest = manifest.advance_stage()

            await self._checkpoint(manifest, stage=manifest.current_stage_index)

    def _derive_seed(self, correlation_id: str, stage_index: int) -> int:
        digest = hashlib.sha256(
            f"{correlation_id}:{stage_index}:{self._salt}".encode()
        ).hexdigest()
        return int(digest, 16) % (2**32)

    async def _load_manifest(self, correlation_id: str) -> Optional[WorkflowManifest]:
        raw = await self._memory.get(f"{self.CHECKPOINT_PREFIX}/{correlation_id}/manifest")
        if raw is None:
            return None
        # In production, use a typed deserializer (e.g., framework-provided or pydantic).
        # Here we demonstrate the contract boundary.
        return WorkflowManifest(**json.loads(raw))

    async def _checkpoint(self, manifest: WorkflowManifest, stage: int) -> None:
        raw = json.dumps(manifest.__dict__, default=str).encode("utf-8")
        await self._memory.set(
            f"{self.CHECKPOINT_PREFIX}/{manifest.correlation_id}/manifest",
            raw,
            ttl_seconds=2592000,  # 30 days
        )
        await self._memory.set(
            f"{self.CHECKPOINT_PREFIX}/{manifest.correlation_id}/stage",
            str(stage).encode(),
            ttl_seconds=2592000,
        )

    async def _get_last_counter(self, correlation_id: str) -> Optional[int]:
        raw = await self._memory.get(f"{self.CHECKPOINT_PREFIX}/{correlation_id}/counter")
        return int(raw) if raw else None

    async def _set_counter(self, correlation_id: str, value: int) -> None:
        await self._memory.set(
            f"{self.CHECKPOINT_PREFIX}/{correlation_id}/counter",
            str(value).encode(),
            ttl_seconds=2592000,
        )

    async def _publish_completion(self, manifest: WorkflowManifest) -> None:
        if manifest.report is None:
            raise RuntimeError("Completion published without report")
        await self._event_bus.publish(
            EventType.RESEARCH_COMPLETION.value,
            {
                "correlation_id": manifest.correlation_id,
                "report_uri": f"{self.CHECKPOINT_PREFIX}/{manifest.correlation_id}/report",
                "integrity_hash": manifest.report.integrity_hash,
                "generated_at": manifest.report.generated_at.isoformat(),
            },
            ordering_key=manifest.correlation_id,
        )

    async def _publish_failure(self, event: ResearchEvent, exc: Exception) -> None:
        await self._event_bus.publish(
            EventType.RESEARCH_FAILURE.value,
            {
                "correlation_id": event.correlation_id,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "processing_counter": event.processing_counter,
            },
            ordering_key=event.correlation_id,
        )


from dataclasses import replace  # noqa: E402
