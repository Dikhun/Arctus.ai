# arctus_research_engine/pipeline/synthesis.py
"""Integration of evidence into coherent knowledge structures."""

from typing import List

from arctus_research_engine.interfaces import IModelGateway, ITelemetry
from arctus_research_engine.models import (
    AnalysisReport,
    RankedEvidenceCollection,
    ReportSection,
    ResearchDirective,
)
from arctus_research_engine.plugins.base import ExecutionContext, SynthesisStrategy


class SynthesisEngine:
    def __init__(
        self,
        strategy: SynthesisStrategy,
        model_gateway: IModelGateway,
        telemetry: ITelemetry,
    ):
        self._strategy = strategy
        self._model_gateway = model_gateway
        self._telemetry = telemetry

    async def execute(
        self,
        evidence: RankedEvidenceCollection,
        analysis: AnalysisReport,
        directive: ResearchDirective,
        context: ExecutionContext,
    ) -> List[ReportSection]:
        async with self._telemetry.start_span("research.synthesize", {
            "correlation_id": context.correlation_id,
        }):
            return await self._strategy.synthesize(
                evidence, analysis, directive, self._model_gateway, context
            )
