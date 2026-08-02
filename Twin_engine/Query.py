from __future__ import annotations

import time

from .graph_store import GraphStore
from .models import QueryResult, RelationType

class QueryEngine:
    def __init__(self, store: GraphStore):
        self._store = store

    async def query_entity_by_name(self, name: str) -> QueryResult:
        start = time.perf_counter()
        snap = await self._store.to_snapshot()
        results = [
            ent.model_dump()
            for ent in snap["entities"].values()
            if name.lower() in ent.name.lower()
        ]
        return QueryResult(
            query=f"name contains '{name}'",
            results=results,
            execution_ms=(time.perf_counter() - start) * 1000,
        )

    async def query_impact(self, entity_id: str, max_depth: int = 5) -> QueryResult:
        start = time.perf_counter()
        impacted = await self._store.traverse_impact(entity_id, max_depth)
        return QueryResult(
            query=f"impact from {entity_id} depth {max_depth}",
            results=[{"entity_id": eid, "depth": d} for eid, d in impacted.items()],
            execution_ms=(time.perf_counter() - start) * 1000,
        )

    async def query_relationships(
        self,
        entity_id: str,
        rel_type: RelationType | None = None,
    ) -> QueryResult:
        start = time.perf_counter()
        neighbors = await self._store.get_neighbors(entity_id, rel_type=rel_type, direction="both")
        return QueryResult(
            query=f"relationships of {entity_id}",
            results=[n.model_dump() for n in neighbors],
            execution_ms=(time.perf_counter() - start) * 1000,
        )
