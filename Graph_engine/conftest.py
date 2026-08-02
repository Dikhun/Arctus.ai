import pytest
from cge.core.graph import ConfidenceGraph


@pytest.fixture
def graph():
    return ConfidenceGraph()
