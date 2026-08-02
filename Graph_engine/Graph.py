import threading
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from .models import Edge, Node


class ConfidenceGraph:
    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    # --- Node Operations ---

    def add_node(self, node: Node) -> Node:
        with self._lock:
            self._nodes[node.id] = node
        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            node = self._nodes.pop(node_id, None)
            if node is None:
                return None
            # Cascade delete edges
            for eid in list(self._outgoing[node_id]):
                self._remove_edge_core(eid)
            for eid in list(self._incoming[node_id]):
                self._remove_edge_core(eid)
            self._outgoing.pop(node_id, None)
            self._incoming.pop(node_id, None)
            return node

    def nodes(self) -> Iterable[Node]:
        with self._lock:
            return list(self._nodes.values())

    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    # --- Edge Operations ---

    def add_edge(self, edge: Edge) -> Edge:
        with self._lock:
            if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
                raise ValueError(
                    f"Missing endpoint for edge {edge.id}: "
                    f"{edge.source_id} -> {edge.target_id}"
                )
            self._edges[edge.id] = edge
            self._outgoing[edge.source_id].add(edge.id)
            self._incoming[edge.target_id].add(edge.id)
        return edge

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        with self._lock:
            return self._edges.get(edge_id)

    def get_edges_from(self, node_id: str) -> List[Edge]:
        with self._lock:
            return [self._edges[eid] for eid in self._outgoing.get(node_id, [])]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        with self._lock:
            return [self._edges[eid] for eid in self._incoming.get(node_id, [])]

    def remove_edge(self, edge_id: str) -> Optional[Edge]:
        with self._lock:
            return self._remove_edge_core(edge_id)

    def _remove_edge_core(self, edge_id: str) -> Optional[Edge]:
        edge = self._edges.pop(edge_id, None)
        if edge:
            self._outgoing[edge.source_id].discard(edge_id)
            self._incoming[edge.target_id].discard(edge_id)
        return edge

    def edges(self) -> Iterable[Edge]:
        with self._lock:
            return list(self._edges.values())

    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)

    # --- Traversal ---

    def neighbors(self, node_id: str) -> List[Node]:
        with self._lock:
            return [
                self._nodes[e.target_id]
                for e in self.get_edges_from(node_id)
                if e.target_id in self._nodes
            ]

    def predecessors(self, node_id: str) -> List[Node]:
        with self._lock:
            return [
                self._nodes[e.source_id]
                for e in self.get_edges_to(node_id)
                if e.source_id in self._nodes
            ]
