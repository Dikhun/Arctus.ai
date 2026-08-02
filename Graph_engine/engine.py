from dataclasses import dataclass, field
from typing import List

from cge.core.graph import ConfidenceGraph
from cge.core.models import Edge, Node


@dataclass
class QueryResult:
    node: Node
    score: float
    evidence: List[Edge] = field(default_factory=list)


class ConfidenceQueryEngine:
    def __init__(self, graph: ConfidenceGraph, min_confidence: float = 0.7):
        self.graph = graph
        self.min_confidence = min_confidence

    def query_by_label(self, label: str, exact: bool = False) -> List[QueryResult]:
        label_cmp = label if exact else label.lower()
        results: List[QueryResult] = []

        for node in self.graph.nodes():
            node_label = node.label if exact else node.label.lower()
            matches = (
                node_label == label_cmp if exact
                else label_cmp in node_label
            )
            if matches and node.confidence >= self.min_confidence:
                evidence = self.graph.get_edges_to(node.id)
                results.append(
                    QueryResult(node=node, score=node.confidence, evidence=evidence)
                )

        return sorted(results, key=lambda r: r.score, reverse=True)

    def subgraph_with_confidence(
        self,
        start_id: str,
        depth: int = 2,
        min_confidence: float = 0.0,
    ) -> List[QueryResult]:
        if self.graph.get_node(start_id) is None:
            return []

        visited: set[str] = set()
        queue = [(start_id, 1.0, 0)]  # (node_id, path_conf, current_depth)
        results: List[QueryResult] = []

        while queue:
            current_id, path_conf, d = queue.pop(0)
            if current_id in visited or d > depth:
                continue
            visited.add(current_id)

            node = self.graph.get_node(current_id)
            if node and path_conf >= min_confidence:
                results.append(
                    QueryResult(node=node, score=path_conf, evidence=[])
                )

            if d < depth:
                for edge in self.graph.get_edges_from(current_id):
                    new_conf = path_conf * edge.confidence
                    if new_conf >= min_confidence:
                        queue.append((edge.target_id, new_conf, d + 1))

        return sorted(results, key=lambda r: r.score, reverse=True)
