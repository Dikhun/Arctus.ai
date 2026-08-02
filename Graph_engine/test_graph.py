import pytest
from cge.core.graph import ConfidenceGraph
from cge.core.models import Edge, Node, SourceType


def test_add_and_retrieve_node(graph: ConfidenceGraph):
    n = Node(label="auth_service")
    graph.add_node(n)
    assert graph.get_node(n.id) is not None
    assert graph.get_node(n.id).label == "auth_service"


def test_add_edge_missing_node(graph: ConfidenceGraph):
    e = Edge(source_id="a", target_id="b")
    with pytest.raises(ValueError):
        graph.add_edge(e)


def test_cascade_delete(graph: ConfidenceGraph):
    a = Node(label="A")
    b = Node(label="B")
    graph.add_node(a)
    graph.add_node(b)
    e = Edge(source_id=a.id, target_id=b.id, confidence=0.9)
    graph.add_edge(e)
    graph.remove_node(a.id)
    assert graph.get_edge(e.id) is None
    assert graph.get_node(b.id) is not None
