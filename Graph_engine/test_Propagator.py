import pytest
from cge.core.graph import ConfidenceGraph
from cge.core.models import Edge, Node
from cge.core.propagator import (
 ConfidencePropagator,
    ConservativePropagation,
    ProductPropagation,
)


def test_product_propagation_chain(graph: ConfidenceGraph):
    a = Node(label="A", confidence=1.0)
    b = Node(label="B")
    c = Node(label="C")
    graph.add_node(a)
    graph.add_node(b)
    graph.add_node(c)

    graph.add_edge(Edge(source_id=a.id, target_id=b.id, confidence=0.8))
    graph.add_edge(Edge(source_id=b.id, target_id=c.id, confidence=0.5))

    prop = ConfidencePropagator(graph, strategy=ProductPropagation(), decay_factor=1.0)
    confs = prop.compute_fixed_point()

    assert confs[c.id] == pytest.approx(0.4, abs=0.001)


def test_conservative_propagation(graph: ConfidenceGraph):
    a = Node(label="A", confidence=1.0)
    b = Node(label="B")
    graph.add_node(a)
    graph.add_node(b)

    graph.add_edge(Edge(source_id=a.id, target_id=b.id, confidence=0.6))

    prop = ConfidencePropagator(
        graph, strategy=ConservativePropagation(), decay_factor=1.0
    )
    confs = prop.compute_fixed_point()
    assert confs[b.id] == pytest.approx(0.6, abs=0.001)
