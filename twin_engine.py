"""
Arctus AI Operating System: Digital Twin Engine (Prototype)
Single-File Implementation of the Unified State Graph and Synchronization Pipeline.
"""

import uuid
import copy
from datetime import datetime
from enum import Enum
from typing import Dict, List, Set, Optional, Any

# ==========================================
# 1. Core Vocabulary & Enums
# ==========================================

class EntityType(Enum):
    PROJECT = "Project"
    REPOSITORY = "Repository"
    FILE = "File"
    SOURCE_CODE = "Source Code"
    API = "API"
    DATABASE_SCHEMA = "Database Schema"
    INFRASTRUCTURE = "Infrastructure"
    CONTAINER = "Container"
    AGENT = "Agent"
    # (Other types omitted for brevity)

class RelType(Enum):
    DEPENDS_ON = "Depends On"
    CALLS = "Calls"
    READS_FROM = "Reads From"
    WRITES_TO = "Writes To"
    DEPLOYS = "Deploys"
    SECURES = "Secures"

class EventType(Enum):
    ENTITY_CREATED = "Entity Created"
    ENTITY_MODIFIED = "Entity Modified"
    RELATIONSHIP_ADDED = "Relationship Added"
    RELATIONSHIP_REMOVED = "Relationship Removed"

# ==========================================
# 2. Data Models (The Graph)
# ==========================================

class Entity:
    def __init__(self, name: str, entity_type: EntityType, properties: dict = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = entity_type
        self.properties = properties or {}
        self.version = 1
        self.last_updated = datetime.utcnow()

    def update(self, new_properties: dict):
        self.properties.update(new_properties)
        self.version += 1
        self.last_updated = datetime.utcnow()

    def __repr__(self):
        return f"[{self.type.value}] {self.name} (v{self.version})"

class Relationship:
    def __init__(self, source_id: str, target_id: str, rel_type: RelType):
        self.id = str(uuid.uuid4())
        self.source_id = source_id
        self.target_id = target_id
        self.rel_type = rel_type

    def __repr__(self):
        return f"({self.source_id}) --{self.rel_type.value}--> ({self.target_id})"

class StateGraph:
    """The in-memory topology of the ecosystem."""
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relationships: List[Relationship] = []

    def add_entity(self, entity: Entity):
        self.entities[entity.id] = entity

    def add_relationship(self, source_id: str, target_id: str, rel_type: RelType):
        rel = Relationship(source_id, target_id, rel_type)
        self.relationships.append(rel)

    def get_downstream_dependents(self, entity_id: str) -> Set[str]:
        """Finds all entities that depend on the given entity (blast radius)."""
        dependents = set()
        queue = [entity_id]
        
        while queue:
            current_id = queue.pop(0)
            # Find relationships where the target is the current_id (meaning source depends on it)
            for rel in self.relationships:
                if rel.target_id == current_id and rel.source_id not in dependents:
                    dependents.add(rel.source_id)
                    queue.append(rel.source_id)
                    
        return dependents

# ==========================================
# 3. Engine Components
# ==========================================

class HistoricalEngine:
    """Maintains immutable snapshots of the ecosystem."""
    def __init__(self):
        self.snapshots = []

    def commit_snapshot(self, graph: StateGraph, event_description: str):
        # Deepcopy to preserve immutable state at this exact point in time
        snapshot = copy.deepcopy(graph)
        timestamp = datetime.utcnow()
        self.snapshots.append({"time": timestamp, "event": event_description, "state": snapshot})
        print(f"[History] Snapshot saved: {event_description}")

class PredictionEngine:
    """Analyzes the graph to forecast impacts of changes."""
    @staticmethod
    def analyze_impact(target_entity_id: str, graph: StateGraph) -> dict:
        target = graph.entities.get(target_entity_id)
        if not target:
            return {"error": "Entity not found"}

        impacted_ids = graph.get_downstream_dependents(target_entity_id)
        impacted_entities = [graph.entities[e_id].name for e_id in impacted_ids]
        
        return {
            "target": target.name,
            "blast_radius_count": len(impacted_ids),
            "impacted_systems": impacted_entities,
            "risk_level": "HIGH" if len(impacted_ids) > 2 else "LOW"
        }

class DigitalTwinEngine:
    """The central orchestrator for the Digital Twin."""
    def __init__(self):
        self.graph = StateGraph()
        self.history = HistoricalEngine()
        self.is_synchronized = True

    def process_event(self, event_type: EventType, data: dict):
        """The core synchronization pipeline."""
        self.is_synchronized = False
        print(f"\n[Event Pipeline] Processing {event_type.value}...")
        
        if event_type == EventType.ENTITY_CREATED:
            entity = data['entity']
            self.graph.add_entity(entity)
            desc = f"Created {entity.name}"
            
        elif event_type == EventType.RELATIONSHIP_ADDED:
            self.graph.add_relationship(data['source'], data['target'], data['type'])
            desc = f"Added relationship between {data['source']} and {data['target']}"
            
        elif event_type == EventType.ENTITY_MODIFIED:
            entity = self.graph.entities[data['entity_id']]
            entity.update(data['properties'])
            desc = f"Updated {entity.name}"

        # 1. Notify Interested Components (Mock)
        print(f"  -> Broadcasted state change to Kernel and Scheduler.")
        
        # 2. Store Historical Snapshot
        self.history.commit_snapshot(self.graph, desc)
        
        self.is_synchronized = True

    def create_simulation_sandbox(self) -> StateGraph:
        """Returns a safe, isolated clone of the current state for testing."""
        print("\n[Sandbox] Forking Digital Twin state for simulation...")
        return copy.deepcopy(self.graph)

# ==========================================
# 4. Execution & Demonstration
# ==========================================

if __name__ == "__main__":
    print("=== Arctus AI OS: Digital Twin Engine Initializing ===")
    twin = DigitalTwinEngine()

    # 1. Populate initial state (Observe Creation)
    auth_db = Entity("Auth_Postgres_DB", EntityType.DATABASE_SCHEMA, {"version": "14.2"})
    auth_api = Entity("Auth_Service_API", EntityType.API, {"protocol": "gRPC"})
    gateway = Entity("API_Gateway", EntityType.INFRASTRUCTURE, {"type": "Envoy"})
    frontend = Entity("Web_Dashboard", EntityType.PROJECT, {"framework": "React"})

    twin.process_event(EventType.ENTITY_CREATED, {"entity": auth_db})
    twin.process_event(EventType.ENTITY_CREATED, {"entity": auth_api})
    twin.process_event(EventType.ENTITY_CREATED, {"entity": gateway})
    twin.process_event(EventType.ENTITY_CREATED, {"entity": frontend})

    # 2. Build the relationship graph (Observe Connections)
    twin.process_event(EventType.RELATIONSHIP_ADDED, {
        "source": auth_api.id, "target": auth_db.id, "type": RelType.READS_FROM
    })
    twin.process_event(EventType.RELATIONSHIP_ADDED, {
        "source": gateway.id, "target": auth_api.id, "type": RelType.CALLS
    })
    twin.process_event(EventType.RELATIONSHIP_ADDED, {
        "source": frontend.id, "target": gateway.id, "type": RelType.DEPENDS_ON
    })

    # 3. Simulation & Prediction (Autonomous Reasoning)
    print("\n=== Agent requests architecture change simulation ===")
    
    # Fork reality into a sandbox
    sandbox = twin.create_simulation_sandbox()
    
    # Predict impact of taking down the Auth Database in the sandbox
    print(f"[Prediction Engine] Analyzing impact of modifying/dropping {auth_db.name}...")
    impact_report = PredictionEngine.analyze_impact(auth_db.id, sandbox)
    
    print("\n[Impact Analysis Report]")
    for k, v in impact_report.items():
        print(f"  - {k}: {v}")

    # 4. Commit actual change to reality
    print("\n=== Executing Safe Change ===")
    twin.process_event(EventType.ENTITY_MODIFIED, {
        "entity_id": auth_db.id, 
        "properties": {"version": "15.0", "status": "migrated"}
    })

    print(f"\nFinal State: {twin.graph.entities[auth_db.id]}")
    print(f"Total Snapshots Retained: {len(twin.history.snapshots)}")
      
