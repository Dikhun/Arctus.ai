from contextlib import asynccontextmanager
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from cge.core.graph import ConfidenceGraph
from cge.core.models import Edge, Node, Provenance, SourceType
from cge.observability.metrics import (
    api_requests_total,
    graph_edges_total,
    graph_nodes_total,
    query_duration,
    query_results_total,
)
from cge.query.engine import ConfidenceQueryEngine, QueryResult

# --- Singletons (use dependency injection in larger systems) ---
_graph = ConfidenceGraph()
_engine = ConfidenceQueryEngine(_graph)


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph_nodes_total.set_function(lambda: _graph.node_count())
    graph_edges_total.set_function(lambda: _graph.edge_count())
    yield
 # Flush metrics or close connections here if needed


app = FastAPI(
    title="Confidence Graph Engine",
    version="1.0.0",
    lifespan=lifespan,
)


class NodeCreate(BaseModel):
    label: str = Field(..., min_length=1)
    node_type: str = "generic"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_type: str = "fallback"
    source_uri: str = ""
    payload: dict = Field(default_factory=dict)


class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    relation: str = Field(..., min_length=1)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_type: str = "fallback"
    source_uri: str = ""
    metadata: dict = Field(default_factory=dict)


class ResultDTO(BaseModel):
    node_id: str
    label: str
    score: float
    node_type: str    tier: str


@app.post("/nodes", status_code=201)
def create_node(payload: NodeCreate):
    try:
        s = SourceType(payload.source_type)
    except ValueError:
        s = SourceType.FALLBACK
    node = Node(
        label=payload.label,
        node_type=payload.node_type,
        confidence=payload.confidence,
        provenance=Provenance(source_type=s, source_uri=payload.source_uri),
        payload=payload.payload,
    )
    _graph.add_node(node)
    api_requests_total.labels(method="POST", endpoint="/nodes", status="201").inc()
    return {"id": node.id, "tier": node.tier.name}


@app.post("/edges", status_code=201)
def create_edge(payload: EdgeCreate):
    if _graph.get_node(payload.source_id) is None or _graph.get_node(payload.target_id) is None:
        api_requests_total.labels(method="POST", endpoint="/edges", status="404").inc()
        raise HTTPException(status_code=404, detail="Source or target node not found")
    try:
        s = SourceType(payload.source_type)
    except ValueError:
        s = SourceType.FALLBACK
    edge = Edge(
        source_id=payload.source_id,
        target_id=payload.target_id,
        relation=payload.relation,
        confidence=payload.confidence,
        provenance=Provenance(source_type=s, source_uri=payload.source_uri),
        metadata=payload.metadata,
    )
    _graph.add_edge(edge)
    api_requests_total.labels(method="POST", endpoint="/edges", status="201").inc()
    return {"id": edge.id, "tier": edge.tier.name}


@app.get("/query", response_model=List[ResultDTO])
def query_nodes(
    q: str,
    exact: bool = False,
    min_confidence: float = Query(0.7, ge=0.0, le=1.0),
):
    import time    start = time.perf_counter()
    _engine.min_confidence = min_confidence
    results: List[QueryResult] = _engine.query_by_label(q, exact=exact)
    duration = time.perf_counter() - start

    query_duration.labels(method="query_by_label").observe(duration)
    query_results_total.labels(method="query_by_label").inc(len(results))
    api_requests_total.labels(method="GET", endpoint="/query", status="200").inc()

    return [
        ResultDTO(
            node_id=r.node.id,
            label=r.node.label,
            score=r.score,
            node_type=r.node.node_type,
            tier=r.node.tier.name,
        )
        for r in results
    ]


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "nodes": _graph.node_count(),
        "edges": _graph.edge_count(),
    }


if __name__ == "__main__":
    uvicorn.run("cge.api.server:app", host="0.0.0.0", port=8000, workers=1)
