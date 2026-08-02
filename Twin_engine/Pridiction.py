from __future__ import annotations

from typing import Sequence

from .graph_store import GraphStore
from .models import ImpactLevel, PredictionResult


class PredictionEngine:
    def __init__(self, store: GraphStore):
        self._store = store

    async def predict_dependency_breakage(self, changed_entity_id: str) -> PredictionResult:
        impacted = await self._store.traverse_impact(changed_entity_id, max_depth=3)
        count = len(impacted)
        confidence = min(0.99, count / 50.0) if count > 0 else 0.05
        impact = (
            ImpactLevel.HIGH
            if count > 20
            else ImpactLevel.MEDIUM
            if count > 5
            else ImpactLevel.LOW
        )
        return PredictionResult(
            prediction_type="dependency_breakage",
            confidence=confidence,
            impact_level=impact,
            affected_entity_ids=list(impacted.keys()),
            description=f"Change propagates to {count} downstream dependents.",
            recommended_action="Run full test suite and verify API contracts.",
        )

    async def predict_deployment_risk(self, changed_ids: Sequence[str]) -> PredictionResult:
        total = 0
        for eid in changed_ids:
            total += len(await self._store.traverse_impact(eid, max_depth=5))
        impact = (
            ImpactLevel.CRITICAL
            if total > 100
            else ImpactLevel.HIGH
            if total > 30
            else ImpactLevel.LOW
        )
        return PredictionResult(
            prediction_type="deployment_risk",
            confidence=0.85,
            impact_level=impact,
            affected_entity_ids=list(changed_ids),
            description=f"Deployment touches {total} inferred components.",
            recommended_action="Staged rollout with canary verification.",
        )
