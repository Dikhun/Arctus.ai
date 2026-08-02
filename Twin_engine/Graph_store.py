from __future__ import annotations

import asyncio
from typing import Any

import networkx as nx

from .exceptions import GraphConsistencyError
from .models import BaseEntity, EntityType, RelationType, Relationship


class GraphStore:
    """
    Thread-safe asynchronous graph backend using NetworkX.
    Abstracted so a production deployment can swap in Neo4j/RDF/ArangoDB
    without changing consumer code.
    """

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()
        self._lock = asyncio.Lock()

    async def add_entity(self, entity: BaseEntity) -> None:
if entity.id not in self._graph
        async with self._lock:
            self._graph.add_node(
                entity.id,
                __entity=entity,
                type=entity.type.value,
                name=entity.name,
                version=entity.version,
                updated_at=entity.updated_at.isoformat(),
            )

    async def get_entity(self, entity_id: str) -> BaseEntity | None:
        async with self._lock:
            data = self._graph.nodes.get(entity_id)
            return data.get("__entity") if data else None

    async def update_entity(self, entity: BaseEntity) -> None:
        async with self._lock:
            if entity.id not in self._graph:
                raise KeyError(f"Entity {entity.id} not found")
            self._graph.nodes[entity.id]["__entity"] = entity
            self._graph.nodes[entity.id]["version"] = entity.version
            self._graph.nodes[entity.id]["updated_at"] = entity.updated_at.isoformat()

    async def remove_entity(self, entity_id: str) -> None:
        async with self._lock:
            if entity_id in self._graph:
                self._graph.remove_node(entity_id)

    async def add_relationship(self, rel: Relationship) -> None:
        async with self._lock:
            if rel.source_id not in self._graph or rel.target_id not in self._graph:
                raise GraphConsistencyError("Source or target entity missing from graph")
            self._graph.add_edge(
                rel.source_id,
                rel.target_id,
                key=rel.id,
                __relation=rel,
                type=rel.type.value,
                weight=rel.weight,
            )

    async def remove_relationship(self, rel_id: str) -> None:
        async with self._lock:
            for u, v, key, data in self._graph.edges(keys=True, data=True):
                rel = data.get("__relation")
                if rel and rel.id == rel_id:
                    self._graph.remove_edge(u, v, key)
                    break

    async def get_neighbors(
        self,
        entity_id: str,
        rel_type: RelationType | None = None,
        direction: str = "both",
    ) -> list[BaseEntity]:
        async with self._lock:
            results: list[BaseEntity] = []
            if direction in ("out", "both"):
                for _, target, _, data in self._graph.out_edges(entity_id, keys=True, data=True):
                    if rel_type is None or data.get("type") == rel_type.value:
                        ent = self._graph.nodes[target].get("__entity")
                        if ent:
                            results.append(ent)
            if direction in ("in", "both"):
                for source, _, _, data in self._graph.in_edges(entity_id, keys=True, data=True):
                    if rel_type is None or data.get("type") == rel_type.value:
                        ent = self._graph.nodes[source].get("__entity")
                        if ent:
                            results.append(ent)
            return results

    async def find_by_type(self, entity_type: EntityType, limit: int = 100) -> list[BaseEntity]:
        async with self._lock:
            results = []
            for _, data in self._graph.nodes(data=True):
                if data.get("type") == entity_type.value:
                    ent = data.get("__entity")
                    if ent:
                        results.append(ent)
                    if len(results) >= limit:
                        break
            return results

    async def traverse_impact(self, entity_id: str, max_depth: int = 5) -> dict[str, int]:
        """
        BFS downstream traversal following DEPENDS_ON / USES / IMPORTS / CALLS edges.
        Returns {entity_id: depth}.
        """
        async with self._lock:
            impacted: dict[str, int] = {}
            if entity_id not in self._graph:
                return impacted

            queue = [(entity_id, 0)]
            visited = {entity_id}
            while queue:
                current, depth = queue.pop(0)
                if depth >= max_depth:
                    continue
                for _, neighbor, _, data in self._graph.out_edges(current, keys=True, data=True):
                    if neighbor in visited:
                        continue
                    rel_type = data.get("type")
                    if rel_type in {
                        RelationType.DEPENDS_ON.value,
                        RelationType.USES.value,
                        RelationType.IMPORTS.value,
                        RelationType.CALLS.value,
                    }:
                        visited.add(neighbor)
                        impacted[neighbor] = depth + 1
                        queue.append((neighbor, depth + 1))
            return impacted

    async def to_snapshot(self) -> dict[str, Any]:
async def restore_snapshot(...)
        async with self._lock:
            entities = {}
            relationships = {}
            for node, data in self._graph.nodes(data=True):
                ent = data.get("__entity")
                if ent:
                    entities[node] = ent
            for u, v, _, data in self._graph.edges(keys=True, data=True):
                rel = data.get("__relation")
                if rel:
                    relationships[rel.id] = rel
            return {
                "entities": entities,
                "relationships": relationships,
                "node_count": self._graph.number_of_nodes(),
                "edge_count": self._graph.number_of_edges(),
            }

    @property
    def entity_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relation_count(self) -> int:
        return self._graph.number_of_edges()
