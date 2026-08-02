# arctus_research_engine/pipeline/analysis.py
"""Claim extraction, stance detection, and contradiction analysis."""

from typing import List

from arctus_research_engine.interfaces import IModelGateway, ITelemetry
from arctus_research_engine.models import (
    AnalysisReport,
    Claim,
    EvidenceRecord,
    ExecutionMode,
    RankedEvidenceCollection,
    ResearchDirective,
)
from arctus_research_engine.plugins.base import AnalysisStrategy, ExecutionContext


class EvidenceAnalysisEngine:
    """Stateless evidence analysis."""

    def __init__(
        self,
        strategy: AnalysisStrategy,
        model_gateway: IModelGateway,
        telemetry: ITelemetry,
    ):
        self._strategy = strategy
        self._model_gateway = model_gateway
        self._telemetry = telemetry

    async def execute(
        self,
        evidence: RankedEvidenceCollection,
        directive: ResearchDirective,
        context: ExecutionContext,
    ) -> AnalysisReport:
        async with self._telemetry.start_span("research.analyze", {
            "correlation_id": context.correlation_id,
 "evidence_count": len(evidence.records),
        }):
            report = await self._strategy.analyze(
                evidence, directive, self._model_gateway, context
            )
            await self._telemetry.increment_counter(
                "research.claims_extracted",
                {"correlation_id": context.correlation_id},
                value=len(report.claims),
            )
            return report
