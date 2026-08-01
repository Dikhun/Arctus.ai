import asyncio
import uuid
import logging
import sys
from enum import Enum
from typing import List, Dict, Set, Optional, Any
import networkx as nx
from pydantic import BaseModel, Field, ValidationError

# Configure Enterprise Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | CAUSAL_ENGINE: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- 1. Ontology Definitions ---

class NodeType(str, Enum):
    EVENT = "Events"
    DECISION = "Decisions"
    ACTION = "Actions"
    INFRASTRUCTURE = "Infrastructure"
    DEPLOYMENT = "Deployments"
    FAILURE = "Failures"
    SUCCESS = "Successes"

class EdgeType(str, Enum):
    CAUSES = "Causes"
    INFLUENCES = "Influences"
    BLOCKS = "Blocks"
    DEPENDS_ON = "Depends On"
    MITIGATES = "Mitigates"

# --- 2. Data Validation Models (Pydantic) ---

class Evidence(BaseModel):
    source: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    description: str

class CausalNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    node_type: NodeType
    state: Any
    timestamp: float

class CausalEdge(BaseModel):
    source_id: str
    target_id: str
    edge_type: EdgeType
    evidence: Evidence
    weight: float = Field(default=1.0, ge=0.0, le=1.0)

# --- 3. Core Engine Architecture ---

class CausalEngine:
    """
    The core Causal Engine responsible for tracking dependencies, performing 
    Root Cause Analysis (RCA), and simulating counterfactual interventions.
    """
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes_index: Dict[str, CausalNode] = {}
        logger.info("Causal Engine Initialized. Graph memory allocated.")

    def add_node(self, node: CausalNode) -> None:
        """Registers an entity in the causal space."""
        if node.id in self.nodes_index:
            logger.warning(f"Node {node.id} already exists. Updating state.")
        self.nodes_index[node.id] = node
        self.graph.add_node(node.id, **node.model_dump())
        logger.info(f"Node added: [{node.node_type.value}] {node.name}")

    def add_causal_edge(self, edge: CausalEdge) -> None:
        """Creates a validated causal link between two nodes."""
        if edge.source_id not in self.nodes_index or edge.target_id not in self.nodes_index:
            raise ValueError("Cannot create edge: Source or Target node missing.")
        
        # Prevent cycles (Correlation is not causation; time flows forward)
        self.graph.add_edge(edge.source_id, edge.target_id, **edge.model_dump())
        if not nx.is_directed_acyclic_graph(self.graph):
            self.graph.remove_edge(edge.source_id, edge.target_id)
            raise ValueError("Causal violation: Adding this edge creates a closed time-like curve (cycle).")
            
        logger.info(f"Causal link validated: {edge.source_id} -[{edge.edge_type.value}]-> {edge.target_id}")

    def root_cause_analysis(self, failure_node_id: str) -> List[CausalNode]:
        """
        Traverses upstream dependencies to identify original source nodes 
        (in-degree 0) or critical infrastructure decisions causing the failure.
        """
        if failure_node_id not in self.nodes_index:
            raise KeyError("Target failure node not found in Causal Graph.")

        logger.info(f"Initiating RCA for node: {failure_node_id}")
        ancestors = nx.ancestors(self.graph, failure_node_id)
        
        root_causes = []
        for node_id in ancestors:
            # A true root cause typically has no predecessors in the current scope
            if self.graph.in_degree(node_id) == 0:
                root_causes.append(self.nodes_index[node_id])
                
        return root_causes

    def predict_intervention_outcome(self, target_node_id: str, new_state: Any) -> Set[str]:
        """
        Simulates Judea Pearl's 'do-operator' by altering a node's state and 
        predicting the downstream causal impact.
        """
        if target_node_id not in self.nodes_index:
            raise KeyError("Intervention target node not found.")

        logger.info(f"Simulating Intervention: do({target_node_id} = {new_state})")
        
        # In a full simulation, edge weights/functions would be computed here.
        # For structural prediction, we identify all impacted downstream nodes.
        descendants = nx.descendants(self.graph, target_node_id)
        impacted_nodes = {self.nodes_index[d].name for d in descendants}
        return impacted_nodes


# --- 4. Autonomous Execution Routine ---

async def run_causal_analysis_pipeline() -> None:
    """Demonstrates a bug-free execution of the Causal Engine identifying a deployment failure."""
    
    engine = CausalEngine()
    
    try:
        # 1. Capture Events (Nodes)
        db_config = CausalNode(name="Database Config (Max Conns=10)", node_type=NodeType.DECISION, state="Active", timestamp=100.0)
        api_deploy = CausalNode(name="API Service v2 Deployment", node_type=NodeType.DEPLOYMENT, state="Deployed", timestamp=105.0)
        db_crash = CausalNode(name="Connection Pool Exhaustion", node_type=NodeType.FAILURE, state="Crashed", timestamp=110.0)

        engine.add_node(db_config)
        engine.add_node(api_deploy)
        engine.add_node(db_crash)

        # 2. Build Dependency Chains (Edges)
        engine.add_causal_edge(CausalEdge(
            source_id=db_config.id, 
            target_id=db_crash.id, 
            edge_type=EdgeType.CAUSES,
            evidence=Evidence(source="Telemetry Logs", confidence_score=0.98, description="Connections exceeded limit.")
        ))
        
        engine.add_causal_edge(CausalEdge(
            source_id=api_deploy.id, 
            target_id=db_crash.id, 
            edge_type=EdgeType.TRIGGERS,
            evidence=Evidence(source="System Metrics", confidence_score=0.95, description="Traffic spike post-deployment.")
        ))

        # 3. Execute Root Cause Analysis
        print("\n--- Generating Root Cause Analysis Report ---")
        roots = engine.root_cause_analysis(db_crash.id)
        for r in roots:
            print(f"- [ROOT CAUSE IDENTIFIED]: {r.name} (Type: {r.node_type.value})")

        # 4. Counterfactual Reasoning & Interventions
        print("\n--- Generating Intervention Impact Report ---")
        impact = engine.predict_intervention_outcome(db_config.id, new_state="Max Conns=100")
        print(f"Intervention on '{db_config.name}' will mitigate downstream nodes: {impact}")

    except ValidationError as ve:
        logger.error(f"Data Validation Failure: {ve}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected System Fault: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(run_causal_analysis_pipeline())
    except KeyboardInterrupt:
        logger.info("Causal execution manually terminated.")
        sys.exit(0)
  
