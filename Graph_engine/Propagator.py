from abc import ABC, abstractmethod
from typing import Dict, Optional

from .graph import ConfidenceGraph


class PropagationStrategy(ABC):
    @abstractmethod
    def aggregate_path(self, edge_confidences: list[float]) -> float:
        ...

    @abstractmethod
    def combine_parallel(self, path_confidences: list[float]) -> float:
        ...
class ProductPropagation(PropagationStrategy):
    """Multiplicative decay along a single path; Noisy-OR for parallel paths."""

    def aggregate_path(self, edge_confidences: list[float]) -> float:
        prod = 1.0
        for c in edge_confidences:
            prod *= max(0.0, min(1.0, c))
        return prod

    def combine_parallel(self, path_confidences: list[float]) -> float:
        if not path_confidences:
            return 0.0
        result = 1.0
        for p in path_confidences:
            p = max(0.0, min(1.0, p))
            result *= 1.0 - p
        return 1.0 - result


class ConservativePropagation(PropagationStrategy):
    """Uses minimum edge confidence for paths; maximum for parallel alternatives."""

    def aggregate_path(self, edge_confidences: list[float]) -> float:
        if not edge_confidences:
            return 0.0
        return min(edge_confidences)

    def combine_parallel(self, path_confidences: list[float]) -> float:
        if not path_confidences:
            return 0.0
        return max(path_confidences)


class ConfidencePropagator:
    def __init__(
        self,
        graph: ConfidenceGraph,
        strategy: Optional[PropagationStrategy] = None,
        decay_factor: float = 0.95,
        max_iterations: int = 100,
        epsilon: float = 1e-6,
    ):
        self.graph = graph
        self.strategy = strategy or ProductPropagation()
        self.decay_factor = decay_factor
        self.max_iterations = max_iterations
        self.epsilon = epsilon

    def compute_fixed_point(self) -> Dict[str, float]:
        """
        Iterative fixed-point update. Handles cycles naturally via convergence.
        Each node's derived confidence is never lower than its intrinsic confidence.
        """
        with self.graph._lock:
            confidences = {
                n.id: max(0.0, min(1.0, n.confidence)) for n in self.graph.nodes()
            }

            for iteration in range(self.max_iterations):
                new_confidences = confidences.copy()
                updated = False

                for node in self.graph.nodes():
                    incoming = self.graph.get_edges_to(node.id)
                    if not incoming:
                        continue

                    parallel = []
                    for edge in incoming:
                        source_conf = confidences.get(edge.source_id, 0.0)
                        path_conf = source_conf * edge.confidence * self.decay_factor
                        parallel.append(path_conf)

                    aggregated = self.strategy.combine_parallel(parallel)
                    final = max(confidences[node.id], aggregated)
                    final = max(0.0, min(1.0, final))

                    if abs(final - confidences[node.id]) > self.epsilon:
                        updated = True
                    new_confidences[node.id] = final

                confidences = new_confidences
                if not updated:
                    break return confidences
