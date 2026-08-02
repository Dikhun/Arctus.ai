# arctus_research_engine/planning.py
"""Autonomous research decomposition and strategy optimization."""

from typing import List, Optional

from arctus_research_engine.interfaces import IModelGateway, ITelemetry
from arctus_research_engine.models import (
    ExecutionMode,
    ResearchDirective,
    ResearchPlanStep,
    WorkflowManifest,
)
from arctus_research_engine.plugins.base import ExecutionContext, PlanningStrategy


class PlanningEngine:
    def __init__(
        self,
        strategy: PlanningStrategy,
        model_gateway: IModelGateway,
        telemetry: ITelemetry,
    ):
        self._strategy = strategy
        self._model_gateway = model_gateway
        self._telemetry = telemetry

    async def create_plan(
        self,
        directive: ResearchDirective,
        context: ExecutionContext,
    ) -> List[ResearchPlanStep]:
        async with self._telemetry.start_span("research.plan.create", {
            "correlation_id": context.correlation_id,
        }):
            return await self._strategy.create_plan(directive, self._model_gateway, context)

    async def determine_next_action(
        self,
        manifest: WorkflowManifest,
        context: ExecutionContext,
    ) -> Optional[ResearchPlanStep]:
        async with self._telemetry.start_span("research.plan.step", {
            "correlation_id": manifest.correlation_id,
            "stage": manifest.current_stage_index,
        }):
            return await self._strategy.determine_next_action(
                manifest, self._model_gateway, context
            )
