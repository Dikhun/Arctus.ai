from __future__ import annotations

from .graph_store import GraphStore
from .models import AnalysisReport


class AnalysisEngine:
    def __init__(self, store: GraphStore):
        self._store = store

    async def architecture_analysis(self) -> AnalysisReport:
        snap = await self._store.to_snapshot()
        node_count = snap["node_count"]
        edge_count = snap["edge_count"]
        return AnalysisReport(
            analysis_type="architecture_analysis",
            metrics={
                "entity_count": float(node_count),
                "relation_count": float(edge_count),
                "avg_out_degree": float(edge_count) / max(1, node_count),
            },
            summary=f"System: {node_count} entities, {edge_count} relationships.",
        )

    async def dependency_analysis(self) -> AnalysisReport:
        return AnalysisReport(
            analysis_type="dependency_analysis",
            summary="Circular dependency and coupling analysis placeholder.",
        )
