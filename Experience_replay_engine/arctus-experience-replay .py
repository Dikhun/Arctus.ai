# =============================================================================
# Arctus AI Operating System — Experience Replay Engine
# =============================================================================
# Module: experience_replay/
# Role:  Capture, store, analyze, and replay all execution experiences to enable
#        continuous learning, failure prevention, and capability improvement.
# =============================================================================

# =============================================================================
# FILE: experience_replay/__init__.py
# =============================================================================

"""
Arctus Experience Replay Engine

Transforms every execution into reusable experience that continuously improves
future planning, reasoning, execution, and learning.
"""

__version__ = "1.0.0"
__author__ = "Arctus AI Systems"

from .engine import ExperienceReplayEngine
from .recorder import ExperienceRecorder
from .storage import ExperienceStorage
from .replay import ReplayExecutor
from .retrieval import ExperienceRetrieval
from .ranking import ExperienceRanker
from .indexing import ExperienceIndexer
from .embeddings import EmbeddingGenerator
from .similarity import SimilaritySearch
from .compression import ExperienceCompressor
from .deduplication import DeduplicationEngine
from .summarizer import ExperienceSummarizer
from .feedback import FeedbackIntegrator
from .reward import RewardCalculator
from .reinforcement import RLIntegration
from .forgetting import ForgettingPolicy
from .retention import RetentionPolicy
from .analytics import ExperienceAnalytics
from .visualization import ReplayVisualizer
from .api import ReplayAPI
from .config import ReplayConfig

__all__ = [
    "ExperienceReplayEngine",
    "ExperienceRecorder",
    "ExperienceStorage",
    "ReplayExecutor",
    "ExperienceRetrieval",
    "ExperienceRanker",
    "ExperienceIndexer",
    "EmbeddingGenerator",
    "SimilaritySearch",
    "ExperienceCompressor",
    "DeduplicationEngine",
    "ExperienceSummarizer",
    "FeedbackIntegrator",
    "RewardCalculator",
    "RLIntegration",
    "ForgettingPolicy",
    "RetentionPolicy",
    "ExperienceAnalytics",
    "ReplayVisualizer",
    "ReplayAPI",
    "ReplayConfig",
]


# =============================================================================
# FILE: experience_replay/config.py
# =============================================================================

"""
Configuration for the Experience Replay Engine.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class StorageConfig:
    """Database and storage configuration."""
    backend: str = "sqlite"  # sqlite, postgresql, mongodb, redis
    connection_string: Optional[str] = None
    database_path: str = "./data/experience_replay.db"
    index_path: str = "./data/experience_index"
    embedding_cache_path: str = "./data/embeddings"
    max_experience_size_mb: int = 10
    compression_threshold_days: int = 30
    deduplication_enabled: bool = True
    batch_size: int = 100


@dataclass
class EmbeddingConfig:
    """Semantic embedding configuration."""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_dimension: int = 384
    normalize_embeddings: bool = True
    batch_size: int = 32
    device: str = "cpu"
    cache_embeddings: bool = True


@dataclass
class ReplayConfig:
    """Main configuration for the Experience Replay Engine."""
    
    # Storage
    storage: StorageConfig = field(default_factory=StorageConfig)
    
    # Embeddings
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    
    # Replay settings
    max_replay_steps: int = 10000
    replay_timeout_seconds: int = 300
    deterministic_mode: bool = True
    branch_from_any_point: bool = True
    
    # Learning
    learning_rate: float = 0.001
    discount_factor: float = 0.95
    priority_alpha: float = 0.6  # Priority exponent for PER
    priority_beta: float = 0.4  # Importance sampling exponent
    
    # Retention
    max_experiences: int = 1000000
    retention_window_days: int = 365
    forget_threshold: float = 0.1  # Minimum importance to retain
    
    # Compression
    compression_enabled: bool = True
    compression_ratio: float = 0.5
    summarize_after_steps: int = 100
    
    # Analytics
    analytics_enabled: bool = True
    metrics_collection_interval: int = 60
    
    # Feedback
    feedback_weight_user: float = 1.0
    feedback_weight_verification: float = 0.8
    feedback_weight_simulation: float = 0.6
    
    # Classification thresholds
    success_threshold: float = 0.8
    partial_success_threshold: float = 0.5
    failure_threshold: float = 0.3
    
    # Integration
    kernel_endpoint: Optional[str] = None
    knowledge_graph_endpoint: Optional[str] = None
    capability_graph_endpoint: Optional[str] = None
    
    def __post_init__(self):
        """Ensure paths exist."""
        Path(self.storage.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.storage.index_path).mkdir(parents=True, exist_ok=True)
        Path(self.storage.embedding_cache_path).mkdir(parents=True, exist_ok=True)


# =============================================================================
# FILE: experience_replay/storage.py
# =============================================================================

"""
Experience Storage — Database interface for persisting execution experiences.
Supports SQLite, PostgreSQL, and MongoDB backends with full provenance tracking.
"""

import json
import sqlite3
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Iterator, Union
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import threading

import numpy as np


@dataclass
class ExperienceRecord:
    """Complete execution experience record."""
    experience_id: str
    session_id: str
    timestamp: datetime
    version: int
    
    # Capture fields
    user_intent: Optional[str] = None
    execution_plan: Optional[Dict] = None
    execution_dag: Optional[Dict] = None
    agent_decisions: Optional[List[Dict]] = None
    model_selection: Optional[Dict] = None
    tool_invocations: Optional[List[Dict]] = None
    capability_usage: Optional[List[str]] = None
    context_assembly: Optional[Dict] = None
    memory_retrieval: Optional[List[Dict]] = None
    prompt_versions: Optional[Dict] = None
    execution_timeline: Optional[List[Dict]] = None
    intermediate_results: Optional[List[Dict]] = None
    verification_results: Optional[Dict] = None
    performance_metrics: Optional[Dict] = None
    resource_usage: Optional[Dict] = None
    final_outcome: Optional[Dict] = None
    
    # Analysis fields
    classification: Optional[str] = None  # Experience classification
    importance_score: float = 0.0
    success_score: float = 0.0
    embedding_vector: Optional[np.ndarray] = None
    metadata: Optional[Dict] = None
    
    # Provenance
    parent_experience_id: Optional[str] = None
    replay_count: int = 0
    derived_from: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = asdict(self)
        if self.embedding_vector is not None:
            data['embedding_vector'] = self.embedding_vector.tolist()
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExperienceRecord':
        """Deserialize from dictionary."""
        data = data.copy()
        if 'embedding_vector' in data and data['embedding_vector'] is not None:
            data['embedding_vector'] = np.array(data['embedding_vector'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ExperienceStorage:
    """
    Database interface for the Experience Replay Engine.
    Supports multiple backends with unified API.
    """
    
    def __init__(self, config):
        self.config = config.storage if hasattr(config, 'storage') else config
        self.backend = self.config.backend
        self._lock = threading.RLock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema."""
        if self.backend == 'sqlite':
            self._init_sqlite()
        elif self.backend == 'postgresql':
            self._init_postgresql()
        elif self.backend == 'mongodb':
            self._init_mongodb()
    
    def _init_sqlite(self):
        """Initialize SQLite schema."""
        conn = sqlite3.connect(self.config.database_path, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        
        # Main experiences table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS experiences (
                experience_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                user_intent TEXT,
                execution_plan TEXT,
                execution_dag TEXT,
                agent_decisions TEXT,
                model_selection TEXT,
                tool_invocations TEXT,
                capability_usage TEXT,
                context_assembly TEXT,
                memory_retrieval TEXT,
                prompt_versions TEXT,
                execution_timeline TEXT,
                intermediate_results TEXT,
                verification_results TEXT,
                performance_metrics TEXT,
                resource_usage TEXT,
                final_outcome TEXT,
                classification TEXT,
                importance_score REAL DEFAULT 0,
                success_score REAL DEFAULT 0,
                embedding_vector BLOB,
                metadata TEXT,
                parent_experience_id TEXT,
                replay_count INTEGER DEFAULT 0,
                derived_from TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_session ON experiences(session_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON experiences(timestamp)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_classification ON experiences(classification)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_importance ON experiences(importance_score)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_success ON experiences(success_score)')
        
        # Experience lineage table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS experience_lineage (
                child_id TEXT,
                parent_id TEXT,
                relation_type TEXT,
                timestamp TEXT,
                FOREIGN KEY (child_id) REFERENCES experiences(experience_id),
                FOREIGN KEY (parent_id) REFERENCES experiences(experience_id)
            )
        ''')
        
        # Replay sessions table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS replay_sessions (
                replay_id TEXT PRIMARY KEY,
                experience_id TEXT NOT NULL,
                replay_mode TEXT,
                start_time TEXT,
                end_time TEXT,
                outcome TEXT,
                divergence_score REAL,
                FOREIGN KEY (experience_id) REFERENCES experiences(experience_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _init_postgresql(self):
        """Placeholder for PostgreSQL initialization."""
        # Would use psycopg2 or asyncpg
        pass
    
    def _init_mongodb(self):
        """Placeholder for MongoDB initialization."""
        # Would use pymongo
        pass
    
    @contextmanager
    def _connection(self):
        """Get database connection context manager."""
        if self.backend == 'sqlite':
            conn = sqlite3.connect(self.config.database_path, check_same_thread=False)
            try:
                yield conn
            finally:
                conn.close()
        else:
            yield None  # Placeholder for other backends
    
    def save_experience(self, experience: ExperienceRecord) -> str:
        """
        Save an experience record to storage.
        Returns the experience_id.
        """
        with self._lock:
            with self._connection() as conn:
                if self.backend == 'sqlite':
                    data = experience.to_dict()
                    
                    # Serialize complex fields
                    for field in ['execution_plan', 'execution_dag', 'agent_decisions',
                                  'model_selection', 'tool_invocations', 'capability_usage',
                                  'context_assembly', 'memory_retrieval', 'prompt_versions',
                                  'execution_timeline', 'intermediate_results',
                                  'verification_results', 'performance_metrics',
                                  'resource_usage', 'final_outcome', 'metadata', 'derived_from']:
                        if data.get(field) is not None:
                            data[field] = json.dumps(data[field])
                    
                    # Handle embedding vector
                    if data.get('embedding_vector') is not None:
                        data['embedding_vector'] = np.array(data['embedding_vector']).tobytes()
                    
                    # Build insert query
                    fields = list(data.keys())
                    placeholders = ', '.join(['?' for _ in fields])
                    field_names = ', '.join(fields)
                    
                    sql = f'INSERT OR REPLACE INTO experiences ({field_names}) VALUES ({placeholders})'
                    values = [data.get(f) for f in fields]
                    
                    conn.execute(sql, values)
                    conn.commit()
                    
                    return experience.experience_id
    
    def get_experience(self, experience_id: str) -> Optional[ExperienceRecord]:
        """Retrieve a single experience by ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM experiences WHERE experience_id = ?',
                (experience_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_experience(cursor, row)
            return None
    
    def _row_to_experience(self, cursor, row) -> ExperienceRecord:
        """Convert database row to ExperienceRecord."""
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        
        # Deserialize JSON fields
        json_fields = ['execution_plan', 'execution_dag', 'agent_decisions',
                       'model_selection', 'tool_invocations', 'capability_usage',
                       'context_assembly', 'memory_retrieval', 'prompt_versions',
                       'execution_timeline', 'intermediate_results',
                       'verification_results', 'performance_metrics',
                       'resource_usage', 'final_outcome', 'metadata', 'derived_from']
        
        for field in json_fields:
            if data.get(field) is not None:
                data[field] = json.loads(data[field])
        
        # Deserialize embedding
        if data.get('embedding_vector') is not None:
            data['embedding_vector'] = np.frombuffer(data['embedding_vector'], dtype=np.float32)
        
        # Deserialize timestamp
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        
        return ExperienceRecord.from_dict(data)
    
    def query_experiences(
        self,
        classification: Optional[str] = None,
        min_importance: Optional[float] = None,
        max_importance: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ExperienceRecord]:
        """Query experiences with filters."""
        with self._connection() as conn:
            conditions = []
            params = []
            
            if classification:
                conditions.append('classification = ?')
                params.append(classification)
            if min_importance is not None:
                conditions.append('importance_score >= ?')
                params.append(min_importance)
            if max_importance is not None:
                conditions.append('importance_score <= ?')
                params.append(max_importance)
            if start_time:
                conditions.append('timestamp >= ?')
                params.append(start_time.isoformat())
            if end_time:
                conditions.append('timestamp <= ?')
                params.append(end_time.isoformat())
            if session_id:
                conditions.append('session_id = ?')
                params.append(session_id)
            
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            
            sql = f'''
                SELECT * FROM experiences 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            '''
            params.extend([limit, offset])
            
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            
            return [self._row_to_experience(cursor, row) for row in rows]
    
    def get_experience_count(self) -> int:
        """Get total number of stored experiences."""
        with self._connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM experiences')
            return cursor.fetchone()[0]
    
    def update_experience(
        self,
        experience_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update specific fields of an experience."""
        with self._lock:
            with self._connection() as conn:
                # Build update query
                set_clauses = []
                params = []
                
                for key, value in updates.items():
                    set_clauses.append(f'{key} = ?')
                    if isinstance(value, (dict, list)):
                        params.append(json.dumps(value))
                    else:
                        params.append(value)
                
                params.append(experience_id)
                sql = f'''
                    UPDATE experiences 
                    SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                    WHERE experience_id = ?
                '''
                
                conn.execute(sql, params)
                conn.commit()
                return True
    
    def delete_experience(self, experience_id: str) -> bool:
        """Delete an experience (soft delete via metadata flag)."""
        return self.update_experience(experience_id, {
            'metadata': {'deleted': True, 'deleted_at': datetime.now().isoformat()}
        })
    
    def get_experience_lineage(self, experience_id: str) -> List[Dict]:
        """Get the lineage/parentage of an experience."""
        with self._connection() as conn:
            cursor = conn.execute('''
                SELECT parent_id, relation_type, timestamp 
                FROM experience_lineage 
                WHERE child_id = ?
                ORDER BY timestamp
            ''', (experience_id,))
            
            return [
                {'parent_id': row[0], 'relation': row[1], 'timestamp': row[2]}
                for row in cursor.fetchall()
            ]
    
    def iterate_all(self, batch_size: int = 100) -> Iterator[List[ExperienceRecord]]:
        """Iterate over all experiences in batches."""
        offset = 0
        while True:
            batch = self.query_experiences(limit=batch_size, offset=offset)
            if not batch:
                break
            yield batch
            offset += batch_size


# =============================================================================
# FILE: experience_replay/recorder.py
# =============================================================================

"""
Experience Recorder — Captures complete execution history from the Arctus pipeline.
"""

import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import json
import copy


@dataclass
class ExecutionSnapshot:
    """Point-in-time snapshot during execution."""
    step_number: int
    timestamp: float
    event_type: str  # 'decision', 'tool_call', 'agent_message', 'verification', etc.
    data: Dict[str, Any]
    context_hash: Optional[str] = None


class ExperienceRecorder:
    """
    Records complete execution experiences from the Arctus pipeline.
    Integrates with Reasoning, Planning, and Execution engines.
    """
    
    CAPTURE_FIELDS = [
        'user_intent', 'execution_plan', 'execution_dag', 'agent_decisions',
        'model_selection', 'tool_invocations', 'capability_usage', 'context_assembly',
        'memory_retrieval', 'prompt_versions', 'execution_timeline',
        'intermediate_results', 'verification_results', 'performance_metrics',
        'resource_usage', 'final_outcome'
    ]
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
        self._active_sessions: Dict[str, Dict] = {}
        self._snapshots: Dict[str, List[ExecutionSnapshot]] = {}
        self._hooks: Dict[str, List[Callable]] = {}
    
    def start_session(self, user_intent: str, context: Optional[Dict] = None) -> str:
        """
        Begin recording a new execution session.
        Called when user request enters the Reasoning Engine.
        """
        session_id = str(uuid.uuid4())
        
        self._active_sessions[session_id] = {
            'session_id': session_id,
            'start_time': datetime.now(),
            'user_intent': user_intent,
            'context': context or {},
            'status': 'recording',
            'capture': {field: None for field in self.CAPTURE_FIELDS}
        }
        
        self._snapshots[session_id] = []
        
        # Initialize capture fields
        self._active_sessions[session_id]['capture']['user_intent'] = user_intent
        self._active_sessions[session_id]['capture']['execution_timeline'] = []
        
        return session_id
    
    def record_planning(self, session_id: str, execution_plan: Dict, execution_dag: Dict):
        """Record planning phase output."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['execution_plan'] = execution_plan
        self._active_sessions[session_id]['capture']['execution_dag'] = execution_dag
        
        self._add_snapshot(session_id, 'planning_complete', {
            'plan': execution_plan,
            'dag': execution_dag
        })
    
    def record_decision(self, session_id: str, decision: Dict):
        """Record an agent decision."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['agent_decisions'] is None:
            self._active_sessions[session_id]['capture']['agent_decisions'] = []
        
        self._active_sessions[session_id]['capture']['agent_decisions'].append({
            'timestamp': datetime.now().isoformat(),
            **decision
        })
        
        self._add_snapshot(session_id, 'agent_decision', decision)
    
    def record_model_selection(self, session_id: str, selection: Dict):
        """Record model selection decision."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['model_selection'] = selection
    
    def record_tool_invocation(self, session_id: str, tool_call: Dict):
        """Record a tool/function invocation."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['tool_invocations'] is None:
            self._active_sessions[session_id]['capture']['tool_invocations'] = []
        
        invocation_record = {
            'timestamp': datetime.now().isoformat(),
            'tool_name': tool_call.get('name'),
            'arguments': tool_call.get('arguments'),
            'result': tool_call.get('result'),
            'latency_ms': tool_call.get('latency_ms'),
            'success': tool_call.get('success', True),
            'error': tool_call.get('error')
        }
        
        self._active_sessions[session_id]['capture']['tool_invocations'].append(invocation_record)
        self._add_snapshot(session_id, 'tool_invocation', invocation_record)
    
    def record_capability_usage(self, session_id: str, capabilities: List[str]):
        """Record which system capabilities were used."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['capability_usage'] = capabilities
    
    def record_context_assembly(self, session_id: str, context: Dict):
        """Record how context was assembled for the execution."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['context_assembly'] = context
    
    def record_memory_retrieval(self, session_id: str, memories: List[Dict]):
        """Record memories retrieved during execution."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['memory_retrieval'] = memories
    
    def record_prompt_version(self, session_id: str, prompt_name: str, version: str, content: str):
        """Record prompt version used."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['prompt_versions'] is None:
            self._active_sessions[session_id]['capture']['prompt_versions'] = {}
        
        self._active_sessions[session_id]['capture']['prompt_versions'][prompt_name] = {
            'version': version,
            'hash': hash(content) & 0xFFFFFFFF,
            'length': len(content)
        }
    
    def record_intermediate_result(self, session_id: str, step: int, result: Dict):
        """Record intermediate execution result."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['intermediate_results'] is None:
            self._active_sessions[session_id]['capture']['intermediate_results'] = []
        
        self._active_sessions[session_id]['capture']['intermediate_results'].append({
            'step': step,
            'timestamp': datetime.now().isoformat(),
            'result': result
        })
    
    def record_verification(self, session_id: str, verification: Dict):
        """Record verification engine results."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['verification_results'] = verification
        
        self._add_snapshot(session_id, 'verification', verification)
    
    def record_performance_metrics(self, session_id: str, metrics: Dict):
        """Record performance metrics."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['performance_metrics'] = metrics
    
    def record_resource_usage(self, session_id: str, usage: Dict):
        """Record resource consumption."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['resource_usage'] = usage
    
    def finalize_session(
        self,
        session_id: str,
        final_outcome: Dict,
        classification: Optional[str] = None
    ) -> 'ExperienceRecord':
        """
        Finalize recording and create an ExperienceRecord.
        Called after Execution Engine completes.
        """
        self._ensure_session(session_id)
        session = self._active_sessions[session_id]
        
        session['capture']['final_outcome'] = final_outcome
        session['end_time'] = datetime.now()
        session['status'] = 'completed'
        
        # Calculate execution timeline from snapshots
        session['capture']['execution_timeline'] = [
            {
                'step': s.step_number,
                'timestamp': s.timestamp,
                'event_type': s.event_type,
                'data_summary': self._summarize_snapshot_data(s.data)
            }
            for s in self._snapshots.get(session_id, [])
        ]
        
        # Build the experience record
        experience_id = str(uuid.uuid4())
        experience = ExperienceRecord(
            experience_id=experience_id,
            session_id=session_id,
            timestamp=session['start_time'],
            version=1,
            **session['capture']
        )
        
        # Store in database
        self.storage.save_experience(experience)
        
        # Clean up
        del self._active_sessions[session_id]
        del self._snapshots[session_id]
        
        # Notify hooks
        self._notify_hooks('experience_recorded', experience)
        
        return experience
    
    def _ensure_session(self, session_id: str):
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")
    
    def _add_snapshot(self, session_id: str, event_type: str, data: Dict):
        snapshots = self._snapshots[session_id]
        snapshot = ExecutionSnapshot(
            step_number=len(snapshots),
            timestamp=time.time(),
            event_type=event_type,
            data=copy.deepcopy(data),
            context_hash=self._hash_context(data)
        )
        snapshots.append(snapshot)
    
    def _hash_context(self, data: Dict) -> str:
        """Create hash of context for deduplication."""
        return str(hash(json.dumps(data, sort_keys=True, default=str)) & 0xFFFFFFFF)
    
    def _summarize_snapshot_data(self, data: Dict) -> Dict:
        """Create a summary of snapshot data for timeline."""
        return {
            'keys': list(data.keys()),
            'size': len(json.dumps(data, default=str)),
            'has_result': 'result' in data,
            'has_error': 'error' in data
        }
    
    def register_hook(self, event: str, callback: Callable):
        """Register a callback for recording events."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
    
    def _notify_hooks(self, event: str, data: Any):
        """Notify registered hooks."""
        for callback in self._hooks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                print(f"Hook error for {event}: {e}")
    
    def get_active_sessions(self) -> List[str]:
        """Get list of currently recording session IDs."""
        return list(self._active_sessions.keys())


# =============================================================================
# FILE: experience_replay/ranking.py
# =============================================================================

"""
Experience Ranking — Importance scoring and prioritization of experiences.
"""

import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import numpy as np

from .storage import ExperienceRecord


class ExperienceRanker:
    """
    Calculates importance scores for experiences to prioritize replay.
    Uses multiple signals: outcome, rarity, recency, user feedback.
    """
    
    def __init__(self, config):
        self.config = config
        self.decay_factor = 0.995  # Daily decay
    
    def score_experience(self, experience: ExperienceRecord) -> float:
        """
        Calculate comprehensive importance score for an experience.
        Score range: 0.0 to 1.0
        """
        scores = {
            'outcome': self._outcome_score(experience),
            'rarity': self._rarity_score(experience),
            'recency': self._recency_score(experience),
            'complexity': self._complexity_score(experience),
            'feedback': self._feedback_score(experience),
            'learning_potential': self._learning_potential(experience)
        }
        
        # Weighted combination
        weights = {
            'outcome': 0.25,
            'rarity': 0.20,
            'recency': 0.15,
            'complexity': 0.15,
            'feedback': 0.15,
            'learning_potential': 0.10
        }
        
        total_score = sum(scores[k] * weights[k] for k in scores)
        return min(1.0, max(0.0, total_score))
    
    def _outcome_score(self, exp: ExperienceRecord) -> float:
        """Score based on execution outcome."""
        if exp.classification == 'Successful Execution':
            return 0.7 + (exp.success_score * 0.3)
        elif exp.classification == 'Partial Success':
            return 0.4 + (exp.success_score * 0.3)
        elif exp.classification == 'Failure':
            return 0.8  # High importance for failures (learning opportunity)
        elif exp.classification == 'User Correction':
            return 0.9  # Very high - direct feedback
        elif exp.classification == 'Security Violation':
            return 1.0  # Critical
        else:
            return 0.5
    
    def _rarity_score(self, exp: ExperienceRecord) -> float:
        """Score based on how unusual/rare this experience is."""
        # Higher score for rare/unusual experiences
        # Would be calculated against full corpus in practice
        tool_count = len(exp.tool_invocations or [])
        decision_count = len(exp.agent_decisions or [])
        
        # Unusual tool usage patterns get higher scores
        if tool_count > 10 or decision_count > 20:
            return 0.8
        
        return 0.5
    
    def _recency_score(self, exp: ExperienceRecord) -> float:
        """Score based on how recent the experience is."""
        age_days = (datetime.now() - exp.timestamp).days
        return self.decay_factor ** age_days
    
    def _complexity_score(self, exp: ExperienceRecord) -> float:
        """Score based on execution complexity."""
        scores = []
        
        # Plan complexity
        if exp.execution_plan:
            scores.append(min(1.0, len(str(exp.execution_plan)) / 10000))
        
        # DAG complexity
        if exp.execution_dag:
            node_count = len(exp.execution_dag.get('nodes', []))
            scores.append(min(1.0, node_count / 50))
        
        # Tool variety
        if exp.tool_invocations:
            unique_tools = len(set(t.get('tool_name') for t in exp.tool_invocations))
            scores.append(min(1.0, unique_tools / 10))
        
        # Decision count
        if exp.agent_decisions:
            scores.append(min(1.0, len(exp.agent_decisions) / 20))
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _feedback_score(self, exp: ExperienceRecord) -> float:
        """Score based on explicit or implicit feedback."""
        metadata = exp.metadata or {}
        feedback = metadata.get('feedback', {})
        
        if not feedback:
            return 0.5
        
        user_rating = feedback.get('user_rating', 0.5)
        verification_pass = feedback.get('verification_pass', True)
        
        score = user_rating
        if not verification_pass:
            score *= 0.7
        
        return score
    
    def _learning_potential(self, exp: ExperienceRecord) -> float:
        """Estimate how much can be learned from this experience."""
        # Failures have high learning potential
        if exp.classification in ['Failure', 'Timeout', 'Performance Regression']:
            return 0.9
        
        # New capabilities discovered
        if exp.classification == 'Capability Discovery':
            return 0.95
        
        # User corrections indicate learning opportunity
        if exp.classification == 'User Correction':
            return 0.85
        
        # Optimization opportunities
        if exp.classification == 'Optimization Opportunity':
            return 0.8
        
        return 0.5
    
    def rank_experiences(
        self,
        experiences: List[ExperienceRecord],
        top_k: Optional[int] = None
    ) -> List[Tuple[ExperienceRecord, float]]:
        """Rank experiences by importance score."""
        scored = [(exp, self.score_experience(exp)) for exp in experiences]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        if top_k:
            return scored[:top_k]
        return scored
    
    def update_scores(self, storage):
        """Recalculate and update all experience scores."""
        for batch in storage.iterate_all(batch_size=100):
            for exp in batch:
                new_score = self.score_experience(exp)
                storage.update_experience(exp.experience_id, {
                    'importance_score': new_score
                })


# =============================================================================
# FILE: experience_replay/embeddings.py
# =============================================================================

"""
Embedding Generator — Creates semantic embeddings for experience search.
"""

import hashlib
import json
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np


class EmbeddingGenerator:
    """
    Generates semantic embeddings for experiences to enable similarity search.
    Supports multiple embedding backends.
    """
    
    def __init__(self, config):
        self.config = config.embeddings if hasattr(config, 'embeddings') else config
        self.model = None
        self._cache: Dict[str, np.ndarray] = {}
        self._load_model()
    
    def _load_model(self):
        """Load the embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.config.model_name, device=self.config.device)
        except ImportError:
            # Fallback to simple embedding
            self.model = None
    
    def _simple_embedding(self, text: str, dim: int = 384) -> np.ndarray:
        """Fallback simple embedding using character n-gram hashing."""
        # Simple but deterministic embedding for when transformers unavailable
        vec = np.zeros(dim, dtype=np.float32)
        text = text.lower()
        
        # Character trigrams
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            idx = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec
    
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a text string."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.model is not None:
            embedding = self.model.encode(text, convert_to_numpy=True)
            if self.config.normalize_embeddings:
                embedding = embedding / np.linalg.norm(embedding)
        else:
            embedding = self._simple_embedding(text)
        
        self._cache[cache_key] = embedding
        return embedding
    
    def embed_experience(self, experience) -> np.ndarray:
        """
        Generate embedding for an experience record.
        Combines multiple fields for rich semantic representation.
        """
        # Build rich text representation
        parts = []
        
        if experience.user_intent:
            parts.append(f"Intent: {experience.user_intent}")
        
        if experience.execution_plan:
            plan_text = json.dumps(experience.execution_plan, default=str)
            parts.append(f"Plan: {plan_text[:500]}")
        
        if experience.tool_invocations:
            tools = [t.get('tool_name', 'unknown') for t in experience.tool_invocations]
            parts.append(f"Tools: {', '.join(tools)}")
        
        if experience.classification:
            parts.append(f"Outcome: {experience.classification}")
        
        if experience.final_outcome:
            outcome_text = json.dumps(experience.final_outcome, default=str)
            parts.append(f"Result: {outcome_text[:500]}")
        
        text = " | ".join(parts)
        return self.embed_text(text)
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for multiple texts efficiently."""
        if self.model is not None:
            embeddings = self.model.encode(texts, convert_to_numpy=True, batch_size=self.config.batch_size)
            if self.config.normalize_embeddings:
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                embeddings = embeddings / np.maximum(norms, 1e-8)
            return embeddings
        
        # Fallback
        return np.array([self._simple_embedding(t) for t in texts])
    
    def similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings."""
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-8))


# =============================================================================
# FILE: experience_replay/similarity.py
# =============================================================================

"""
Similarity Search — Vector similarity search for finding related experiences.
"""

import numpy as np
from typing import List, Tuple, Optional
import heapq


class SimilaritySearch:
    """
    Efficient vector similarity search for experience retrieval.
    Supports exact and approximate nearest neighbor search.
    """
    
    def __init__(self, config, embedding_generator):
        self.config = config
        self.embedder = embedding_generator
        self._vectors: List[np.ndarray] = []
        self._ids: List[str] = []
        self._index_built = False
    
    def add_experience(self, experience_id: str, embedding: np.ndarray):
        """Add an experience vector to the search index."""
        self._vectors.append(embedding)
        self._ids.append(experience_id)
        self._index_built = False
    
    def build_index(self):
        """Build search index for efficient retrieval."""
        if not self._vectors:
            return
        
        self._vectors_array = np.array(self._vectors)
        self._index_built = True
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        min_similarity: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Search for most similar experiences.
        Returns list of (experience_id, similarity_score) tuples.
        """
        if not self._index_built:
            self.build_index()
        
        if len(self._vectors) == 0:
            return []
        
        # Compute similarities
        similarities = np.dot(self._vectors_array, query_embedding)
        
        # Filter by minimum similarity
        valid_indices = np.where(similarities >= min_similarity)[0]
        
        # Get top-k
        if len(valid_indices) <= top_k:
            top_indices = valid_indices[np.argsort(-similarities[valid_indices])]
        else:
            top_indices = heapq.nlargest(
                top_k,
                valid_indices,
                key=lambda i: similarities[i]
            )
        
        return [
            (self._ids[i], float(similarities[i]))
            for i in top_indices
        ]
    
    def search_experiences(
        self,
        query_experience,
        storage,
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """Find experiences similar to a given experience."""
        query_embedding = self.embedder.embed_experience(query_experience)
        return self.search(query_embedding, top_k=top_k)
    
    def batch_search(
        self,
        query_embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[List[Tuple[str, float]]]:
        """Search for multiple queries at once."""
        if not self._index_built:
            self.build_index()
        
        if len(self._vectors) == 0:
            return [[] for _ in range(len(query_embeddings))]
        
        # Matrix multiplication for all queries
        similarities = np.dot(query_embeddings, self._vectors_array.T)
        
        results = []
        for sim_vector in similarities:
            valid_indices = np.where(sim_vector >= 0)[0]
            top_indices = heapq.nlargest(
                min(top_k, len(valid_indices)),
                valid_indices,
                key=lambda i: sim_vector[i]
            )
            results.append([
                (self._ids[i], float(sim_vector[i]))
                for i in top_indices
            ])
        
        return results
    
    def clear(self):
        """Clear the search index."""
        self._vectors = []
        self._ids = []
        self._index_built = False
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        return {
            'total_vectors': len(self._vectors),
            'index_built': self._index_built,
            'vector_dimension': len(self._vectors[0]) if self._vectors else 0
        }


# =============================================================================
# FILE: experience_replay/retrieval.py
# =============================================================================

"""
Experience Retrieval — Find relevant past experiences for current context.
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta


class ExperienceRetrieval:
    """
    Retrieves relevant experiences using multiple strategies:
    - Semantic similarity
    - Temporal proximity
    - Classification matching
    - Capability overlap
    - Success pattern matching
    """
    
    def __init__(self, storage, similarity_search, ranker, config):
        self.storage = storage
        self.similarity = similarity_search
        self.ranker = ranker
        self.config = config
    
    def find_similar_experiences(
        self,
        current_intent: str,
        current_context: Optional[Dict] = None,
        top_k: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Find experiences semantically similar to current context.
        """
        from .embeddings import EmbeddingGenerator
        
        embedder = EmbeddingGenerator(self.config)
        query_embedding = embedder.embed_text(current_intent)
        
        similar = self.similarity.search(query_embedding, top_k=top_k * 2, min_similarity=min_similarity)
        
        results = []
        for exp_id, sim_score in similar:
            exp = self.storage.get_experience(exp_id)
            if exp:
                importance = self.ranker.score_experience(exp)
                results.append({
                    'experience': exp,
                    'similarity': sim_score,
                    'importance': importance,
                    'combined_score': sim_score * 0.6 + importance * 0.4
                })
        
        # Sort by combined score and return top_k
        results.sort(key=lambda x: x['combined_score'], reverse=True)
        return results[:top_k]
    
    def find_success_patterns(
        self,
        intent_category: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Find successful execution patterns for similar intents."""
        experiences = self.storage.query_experiences(
            classification='Successful Execution',
            limit=100
        )
        
        # Filter by intent similarity (simple keyword matching for now)
        filtered = []
        for exp in experiences:
            if exp.user_intent and intent_category.lower() in exp.user_intent.lower():
                filtered.append({
                    'experience': exp,
                    'score': self.ranker.score_experience(exp)
                })
        
        filtered.sort(key=lambda x: x['score'], reverse=True)
        return filtered[:top_k]
    
    def find_failure_precedents(
        self,
        current_plan: Dict,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar past failures to avoid repeating mistakes."""
        experiences = self.storage.query_experiences(
            classification='Failure',
            limit=100
        )
        
        # Rank by similarity to current plan
        results = []
        for exp in experiences:
            # Simple heuristic: similar tools or plan structure
            score = self._plan_similarity(current_plan, exp.execution_plan or {})
            if score > 0.3:
                results.append({
                    'experience': exp,
                    'similarity': score,
                    'lessons': self._extract_failure_lessons(exp)
                })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def _plan_similarity(self, plan1: Dict, plan2: Dict) -> float:
        """Calculate similarity between two execution plans."""
        # Simple structural similarity
        tools1 = set(str(plan1).split())
        tools2 = set(str(plan2).split())
        
        if not tools1 or not tools2:
            return 0.0
        
        intersection = len(tools1 & tools2)
        union = len(tools1 | tools2)
        
        return intersection / union if union > 0 else 0.0
    
    def _extract_failure_lessons(self, experience) -> List[str]:
        """Extract actionable lessons from a failure experience."""
        lessons = []
        
        if experience.final_outcome:
            error = experience.final_outcome.get('error', '')
            if error:
                lessons.append(f"Avoid: {error[:200]}")
        
        if experience.verification_results:
            failures = experience.verification_results.get('failed_checks', [])
            for failure in failures:
                lessons.append(f"Check: {failure}")
        
        if not lessons:
            lessons.append("Review execution timeline for failure points")
        
        return lessons
    
    def find_optimal_workflow(
        self,
        intent: str,
        constraints: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Find the best known workflow for a given intent."""
        patterns = self.find_success_patterns(intent, top_k=10)
        
        if not patterns:
            return None
        
        # Score by success + efficiency
        best = None
        best_score = -1
        
        for p in patterns:
            exp = p['experience']
            
            # Calculate efficiency score
            metrics = exp.performance_metrics or {}
            latency = metrics.get('total_latency_ms', float('inf'))
            token_usage = metrics.get('token_usage', float('inf'))
            
            # Lower is better for resource usage
            efficiency = 1.0 / (1.0 + latency / 1000 + token_usage / 1000)
            
            score = p['score'] * 0.6 + efficiency * 0.4
            
            if score > best_score:
                best_score = score
                best = {
                    'experience': exp,
                    'score': score,
                    'workflow': exp.execution_plan,
                    'expected_latency': latency,
                    'expected_tokens': token_usage
                }
        
        return best
    
    def get_recent_context(
        self,
        minutes: int = 30,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent experiences for short-term context."""
        since = datetime.now() - timedelta(minutes=minutes)
        
        experiences = self.storage.query_experiences(
            start_time=since,
            limit=limit
        )
        
        return [
            {
                'experience': exp,
                'time_ago_minutes': (datetime.now() - exp.timestamp).total_seconds() / 60
            }
            for exp in experiences
        ]
    
    def get_capability_evolution(
        self,
        capability_name: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Track how a capability has evolved over time."""
        since = datetime.now() - timedelta(days=days)
        
        all_exp = self.storage.query_experiences(start_time=since, limit=1000)
        
        # Filter by capability usage
        related = []
        for exp in all_exp:
            capabilities = exp.capability_usage or []
            if capability_name in capabilities:
                related.append({
                    'timestamp': exp.timestamp,
                    'success': exp.classification == 'Successful Execution',
                    'score': exp.success_score,
                    'performance': exp.performance_metrics
                })
        
        return sorted(related, key=lambda x: x['timestamp'])


# =============================================================================
# FILE: experience_replay/replay.py
# =============================================================================

"""
Replay Executor — Replay past executions with multiple modes.
"""

import copy
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum


class ReplayMode(Enum):
    """Supported replay modes."""
    DETERMINISTIC = "deterministic"
    STEP_BY_STEP = "step_by_step"
    ACCELERATED = "accelerated"
    SELECTIVE = "selective"
    FAILURE = "failure"
    SUCCESS = "success"
    ALTERNATIVE = "alternative"
    SIMULATION = "simulation"
    REGRESSION = "regression"


@dataclass
class ReplayResult:
    """Result of a replay execution."""
    replay_id: str
    experience_id: str
    mode: ReplayMode
    success: bool
    steps_executed: int
    total_steps: int
    divergence_points: List[int]
    final_state: Dict[str, Any]
    metrics: Dict[str, Any]
    comparison: Optional[Dict] = None


class ReplayExecutor:
    """
    Replays past execution experiences for analysis, learning, and testing.
    Supports multiple replay modes with deterministic behavior.
    """
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
        self._replay_hooks: Dict[str, List[Callable]] = {}
        self._active_replays: Dict[str, Dict] = {}
    
    def replay(
        self,
        experience_id: str,
        mode: ReplayMode = ReplayMode.DETERMINISTIC,
        branch_point: Optional[int] = None,
        modifications: Optional[Dict] = None
    ) -> ReplayResult:
        """
        Replay a past experience.
        
        Args:
            experience_id: ID of experience to replay
            mode: Replay mode
            branch_point: Step number to branch from (for alternative strategies)
            modifications: Changes to apply during replay
        """
        experience = self.storage.get_experience(experience_id)
        if not experience:
            raise ValueError(f"Experience {experience_id} not found")
        
        replay_id = f"replay_{experience_id}_{int(time.time())}"
        
        # Initialize replay state
        replay_state = {
            'replay_id': replay_id,
            'experience': experience,
            'mode': mode,
            'current_step': 0,
            'branch_point': branch_point,
            'modifications': modifications or {},
            'divergence_points': [],
            'executed_steps': [],
            'metrics': {
                'start_time': time.time(),
                'step_latencies': []
            }
        }
        
        self._active_replays[replay_id] = replay_state
        
        try:
            result = self._execute_replay(replay_state)
            return result
        finally:
            del self._active_replays[replay_id]
    
    def _execute_replay(self, state: Dict) -> ReplayResult:
        """Execute the replay logic."""
        experience = state['experience']
        mode = state['mode']
        
        timeline = experience.execution_timeline or []
        total_steps = len(timeline)
        
        # Determine which steps to replay
        steps_to_replay = self._select_steps(timeline, mode)
        
        # Execute each step
        for step_info in steps_to_replay:
            step_num = step_info.get('step', 0)
            state['current_step'] = step_num
            
            # Check for branch point
            if state['branch_point'] is not None and step_num >= state['branch_point']:
                # Apply modifications
                modified_step = self._apply_modifications(step_info, state['modifications'])
                result = self._execute_step(modified_step, state)
            else:
                result = self._execute_step(step_info, state)
            
            state['executed_steps'].append({
                'step': step_num,
                'result': result,
                'timestamp': time.time()
            })
            
            # Check for divergence
            if not self._verify_step_fidelity(step_info, result):
                state['divergence_points'].append(step_num)
            
            # Step-by-step mode: pause after each step
            if mode == ReplayMode.STEP_BY_STEP:
                # In real implementation, would wait for external signal
                pass
        
        # Compile results
        return ReplayResult(
            replay_id=state['replay_id'],
            experience_id=experience.experience_id,
            mode=mode,
            success=len(state['divergence_points']) == 0,
            steps_executed=len(state['executed_steps']),
            total_steps=total_steps,
            divergence_points=state['divergence_points'],
            final_state=self._extract_final_state(state),
            metrics=self._compile_metrics(state)
        )
    
    def _select_steps(self, timeline: List[Dict], mode: ReplayMode) -> List[Dict]:
        """Select which steps to replay based on mode."""
        if mode == ReplayMode.FAILURE:
            # Replay only up to failure point
            for i, step in enumerate(timeline):
                if step.get('data_summary', {}).get('has_error'):
                    return timeline[:i+1]
            return timeline
        
        elif mode == ReplayMode.SUCCESS:
            # Replay only successful path
            return [s for s in timeline if not s.get('data_summary', {}).get('has_error')]
        
        elif mode == ReplayMode.SELECTIVE:
            # Replay key decision points only
            return [s for s in timeline if s.get('event_type') in [
                'agent_decision', 'tool_invocation', 'verification'
            ]]
        
        else:
            # Default: replay all
            return timeline
    
    def _apply_modifications(self, step: Dict, modifications: Dict) -> Dict:
        """Apply modifications to a step for alternative strategy replay."""
        modified = copy.deepcopy(step)
        
        if 'tool_substitutions' in modifications:
            # Replace tool calls
            tool_subs = modifications['tool_substitutions']
            if modified.get('event_type') == 'tool_invocation':
                tool_name = modified.get('data', {}).get('tool_name')
                if tool_name in tool_subs:
                    modified['data']['tool_name'] = tool_subs[tool_name]
        
        if 'parameter_overrides' in modifications:
            # Override parameters
            params = modifications['parameter_overrides']
            if 'data' in modified and 'arguments' in modified['data']:
                modified['data']['arguments'].update(params)
        
        return modified
    
    def _execute_step(self, step: Dict, state: Dict) -> Dict:
        """Execute a single replay step."""
        start = time.time()
        
        # In real implementation, this would invoke actual tools/agents
        # For now, simulate execution
        result = {
            'step': step.get('step'),
            'event_type': step.get('event_type'),
            'simulated': True,
            'latency_ms': (time.time() - start) * 1000
        }
        
        state['metrics']['step_latencies'].append(result['latency_ms'])
        
        return result
    
    def _verify_step_fidelity(self, original: Dict, replay_result: Dict) -> bool:
        """Check if replay matches original execution."""
        # Simplified fidelity check
        # In production, would compare outputs, states, side effects
        return replay_result.get('simulated', False)
    
    def _extract_final_state(self, state: Dict) -> Dict:
        """Extract final state after replay."""
        return {
            'steps_completed': len(state['executed_steps']),
            'total_divergences': len(state['divergence_points']),
            'execution_time': time.time() - state['metrics']['start_time']
        }
    
    def _compile_metrics(self, state: Dict) -> Dict:
        """Compile replay metrics."""
        latencies = state['metrics']['step_latencies']
        return {
            'total_time_seconds': time.time() - state['metrics']['start_time'],
            'avg_step_latency_ms': sum(latencies) / len(latencies) if latencies else 0,
            'max_step_latency_ms': max(latencies) if latencies else 0,
            'min_step_latency_ms': min(latencies) if latencies else 0
        }
    
    def compare_replays(
        self,
        replay_id_1: str,
        replay_id_2: str
    ) -> Dict[str, Any]:
        """Compare two replay outcomes."""
        # Would retrieve stored replay results and compare
        return {
            'divergence_comparison': {},
            'performance_delta': {},
            'recommendation': ''
        }
    
    def register_hook(self, event: str, callback: Callable):
        """Register replay event hooks."""
        if event not in self._replay_hooks:
            self._replay_hooks[event] = []
        self._replay_hooks[event].append(callback)


# =============================================================================
# FILE: experience_replay/compression.py
# =============================================================================

"""
Experience Compression — Compress and summarize old experiences for efficiency.
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class ExperienceCompressor:
    """
    Compresses old experiences to reduce storage while preserving learning value.
    Uses semantic compression and hierarchical summarization.
    """
    
    def __init__(self, storage, summarizer, config):
        self.storage = storage
        self.summarizer = summarizer
        self.config = config
    
    def compress_experience(self, experience_id: str) -> Optional[Dict[str, Any]]:
        """
        Compress a single experience by summarizing its contents.
        Returns compressed representation.
        """
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return None
        
        # Generate summary
        summary = self.summarizer.summarize(experience)
        
        # Compress timeline
        compressed_timeline = self._compress_timeline(
            experience.execution_timeline or []
        )
        
        # Compress intermediate results
        compressed_results = self._compress_intermediate_results(
            experience.intermediate_results or []
        )
        
        compressed = {
            'experience_id': experience.experience_id,
            'original_version': experience.version,
            'compression_timestamp': datetime.now().isoformat(),
            'summary': summary,
            'compressed_timeline': compressed_timeline,
            'compressed_results': compressed_results,
            'key_decisions': self._extract_key_decisions(experience),
            'key_tools': self._extract_key_tools(experience),
            'outcome_summary': self._summarize_outcome(experience),
            'retain_full': False
        }
        
        # Mark original as compressed
        self.storage.update_experience(experience_id, {
            'metadata': {
                'compressed': True,
                'compressed_at': datetime.now().isoformat(),
                'compression_ratio': self._calculate_compression_ratio(experience, compressed)
            }
        })
        
        return compressed
    
    def _compress_timeline(self, timeline: List[Dict]) -> List[Dict]:
        """Compress execution timeline by removing redundant steps."""
        if len(timeline) <= 10:
            return timeline
        
        # Keep first, last, and every Nth step
        compressed = [timeline[0]]
        
        step_interval = max(1, len(timeline) // 10)
        for i in range(step_interval, len(timeline) - 1, step_interval):
            compressed.append({
                'step': timeline[i]['step'],
                'event_type': timeline[i]['event_type'],
                'summary': timeline[i]['data_summary']
            })
        
        compressed.append(timeline[-1])
        return compressed
    
    def _compress_intermediate_results(self, results: List[Dict]) -> List[Dict]:
        """Compress intermediate results, keeping only important ones."""
        if not results:
            return []
        
        # Keep results that led to failures or significant changes
        important = []
        for result in results:
            result_data = result.get('result', {})
            if result_data.get('error') or result_data.get('significant_change'):
                important.append({
                    'step': result['step'],
                    'had_error': bool(result_data.get('error')),
                    'change_magnitude': result_data.get('change_magnitude', 0)
                })
        
        return important
    
    def _extract_key_decisions(self, experience) -> List[Dict]:
        """Extract most important decisions from experience."""
        decisions = experience.agent_decisions or []
        
        # Sort by impact (simplified)
        return [
            {
                'timestamp': d.get('timestamp'),
                'type': d.get('decision_type', 'unknown'),
                'impact': d.get('impact_score', 0.5)
            }
            for d in decisions[:5]  # Top 5 decisions
        ]
    
    def _extract_key_tools(self, experience) -> List[str]:
        """Extract most frequently used tools."""
        invocations = experience.tool_invocations or []
        tool_counts = {}
        
        for inv in invocations:
            tool = inv.get('tool_name', 'unknown')
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        # Return most used
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tools[:5]]
    
    def _summarize_outcome(self, experience) -> Dict:
        """Create compact outcome summary."""
        outcome = experience.final_outcome or {}
        
        return {
            'success': experience.classification == 'Successful Execution',
            'classification': experience.classification,
            'key_metrics': {
                'latency_ms': outcome.get('latency_ms'),
                'token_usage': outcome.get('token_usage'),
                'error_count': len(outcome.get('errors', []))
            }
        }
    
    def _calculate_compression_ratio(
        self,
        original,
        compressed: Dict
    ) -> float:
        """Calculate how much the experience was compressed."""
        orig_size = len(json.dumps(original.to_dict(), default=str))
        comp_size = len(json.dumps(compressed, default=str))
        
        return 1.0 - (comp_size / orig_size) if orig_size > 0 else 0.0
    
    def batch_compress(self, older_than_days: int = 30):
        """Compress all experiences older than threshold."""
        cutoff = datetime.now() - timedelta(days=older_than_days)
        
        compressed_count = 0
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                if exp.timestamp < cutoff and not (exp.metadata or {}).get('compressed'):
                    self.compress_experience(exp.experience_id)
                    compressed_count += 1
        
        return compressed_count
    
    def decompress_experience(self, experience_id: str) -> Optional[Dict]:
        """Attempt to reconstruct full experience from compressed form."""
        # In practice, may not be fully reversible
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return None
        
        metadata = experience.metadata or {}
        if not metadata.get('compressed'):
            return experience.to_dict()
        
        # Return best available reconstruction
        return {
            'experience_id': experience_id,
            'note': 'Reconstructed from compressed form',
            'available_summary': metadata.get('summary', 'N/A'),
            'original_classification': experience.classification
        }


# =============================================================================
# FILE: experience_replay/deduplication.py
# =============================================================================

"""
Deduplication Engine — Remove duplicate or near-duplicate experiences.
"""

import hashlib
import json
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict


class DeduplicationEngine:
    """
    Identifies and handles duplicate or near-duplicate experiences
    to prevent storage bloat and improve retrieval quality.
    """
    
    def __init__(self, storage, embedding_generator, config):
        self.storage = storage
        self.embedder = embedding_generator
        self.config = config
        self._signature_cache: Dict[str, str] = {}
    
    def compute_signature(self, experience) -> str:
        """
        Compute a deterministic signature for an experience.
        Used for exact deduplication.
        """
        # Build canonical representation
        canonical = {
            'intent': (experience.user_intent or '').lower().strip()[:200],
            'plan_structure': self._canonicalize_plan(experience.execution_plan),
            'tool_sequence': self._extract_tool_sequence(experience),
            'classification': experience.classification,
            'decision_count': len(experience.agent_decisions or [])
        }
        
        json_str = json.dumps(canonical, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()[:32]
    
    def _canonicalize_plan(self, plan: Optional[Dict]) -> str:
        """Create canonical representation of plan structure."""
        if not plan:
            return ''
        # Extract just the structure, not parameter values
        return str(sorted(plan.keys()))
    
    def _extract_tool_sequence(self, experience) -> List[str]:
        """Extract ordered tool names from experience."""
        invocations = experience.tool_invocations or []
        return [inv.get('tool_name', 'unknown') for inv in invocations]
    
    def find_duplicates(
        self,
        threshold: float = 0.95
    ) -> List[List[str]]:
        """
        Find groups of duplicate experiences.
        Returns lists of experience IDs that are duplicates.
        """
        # Build signature index
        signatures: Dict[str, List[str]] = defaultdict(list)
        
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                sig = self.compute_signature(exp)
                signatures[sig].append(exp.experience_id)
        
        # Find groups with multiple members
        duplicates = [ids for ids in signatures.values() if len(ids) > 1]
        
        # Also check near-duplicates with embeddings
        near_duplicates = self._find_near_duplicates(threshold)
        
        return duplicates + near_duplicates
    
    def _find_near_duplicates(self, threshold: float) -> List[List[str]]:
        """Find semantically similar experiences using embeddings."""
        # In production, would use vector DB for this
        # Simplified implementation
        return []
    
    def merge_duplicates(self, duplicate_ids: List[str]) -> Optional[str]:
        """
        Merge duplicate experiences into a single representative record.
        Keeps the most complete version and updates metadata.
        """
        if len(duplicate_ids) < 2:
            return None
        
        # Fetch all duplicates
        experiences = []
        for eid in duplicate_ids:
            exp = self.storage.get_experience(eid)
            if exp:
                experiences.append(exp)
        
        if not experiences:
            return None
        
        # Select best representative (most complete, highest score)
        best = max(experiences, key=lambda e: (
            len(json.dumps(e.to_dict(), default=str)),
            e.importance_score
        ))
        
        # Update best with merge metadata
        merged_meta = best.metadata or {}
        merged_meta['merged_from'] = duplicate_ids
        merged_meta['merge_count'] = len(duplicate_ids)
        merged_meta['merge_timestamp'] = datetime.now().isoformat()
        
        self.storage.update_experience(best.experience_id, {
            'metadata': merged_meta,
            'version': best.version + 1
        })
        
        # Mark others as duplicates
        for exp in experiences:
            if exp.experience_id != best.experience_id:
                self.storage.update_experience(exp.experience_id, {
                    'metadata': {
                        'duplicate_of': best.experience_id,
                        'hidden': True
                    }
                })
        
        return best.experience_id
    
    def run_deduplication(self) -> Dict[str, int]:
        """Run full deduplication process."""
        duplicates = self.find_duplicates()
        
        merged = 0
        for group in duplicates:
            result = self.merge_duplicates(group)
            if result:
                merged += 1
        
        return {
            'duplicate_groups_found': len(duplicates),
            'groups_merged': merged,
            'total_examined': sum(len(g) for g in duplicates)
        }


# =============================================================================
# FILE: experience_replay/summarizer.py
# =============================================================================

"""
Experience Summarizer — Summarize long experiences for efficient processing.
"""

from typing import Dict, List, Optional, Any


class ExperienceSummarizer:
    """
    Generates concise summaries of experiences for quick understanding
    and efficient storage.
    """
    
    def __init__(self, config):
        self.config = config
        self.max_summary_length = 500  # words
    
    def summarize(self, experience) -> Dict[str, Any]:
        """Generate comprehensive summary of an experience."""
        return {
            'executive_summary': self._executive_summary(experience),
            'what_happened': self._narrative_summary(experience),
            'key_decisions': self._decision_summary(experience),
            'tool_usage': self._tool_summary(experience),
            'outcome': self._outcome_summary(experience),
            'lessons': self._extract_lessons(experience),
            'recommendations': self._generate_recommendations(experience)
        }
    
    def _executive_summary(self, experience) -> str:
        """One-paragraph executive summary."""
        parts = []
        
        # Intent
        intent = (experience.user_intent or 'Unknown intent')[:100]
        parts.append(f"Task: {intent}")
        
        # Outcome
        outcome = experience.classification or 'Unknown outcome'
        parts.append(f"Outcome: {outcome}")
        
        # Scale
        tool_count = len(experience.tool_invocations or [])
        decision_count = len(experience.agent_decisions or [])
        parts.append(f"Scale: {tool_count} tools, {decision_count} decisions")
        
        # Performance
        metrics = experience.performance_metrics or {}
        latency = metrics.get('total_latency_ms', 'unknown')
        parts.append(f"Latency: {latency}ms")
        
        return " | ".join(parts)
    
    def _narrative_summary(self, experience) -> str:
        """Step-by-step narrative of what happened."""
        timeline = experience.execution_timeline or []
        
        if not timeline:
            return "No timeline available"
        
        # Extract key events
        key_events = []
        for event in timeline:
            event_type = event.get('event_type', 'unknown')
            step = event.get('step', 0)
            
            if event_type in ['agent_decision', 'tool_invocation', 'verification']:
                key_events.append(f"Step {step}: {event_type}")
        
        return "; ".join(key_events[:10])  # Limit length
    
    def _decision_summary(self, experience) -> List[Dict]:
        """Summary of key decisions made."""
        decisions = experience.agent_decisions or []
        
        return [
            {
                'type': d.get('decision_type', 'unknown'),
                'rationale': d.get('rationale', '')[:100],
                'impact': d.get('impact_score', 0.5)
            }
            for d in decisions[:5]
        ]
    
    def _tool_summary(self, experience) -> Dict:
        """Summary of tool usage."""
        invocations = experience.tool_invocations or []
        
        tool_stats = {}
        for inv in invocations:
            name = inv.get('tool_name', 'unknown')
            if name not in tool_stats:
                tool_stats[name] = {'count': 0, 'errors': 0, 'avg_latency': 0}
            
            tool_stats[name]['count'] += 1
            if inv.get('error'):
                tool_stats[name]['errors'] += 1
            tool_stats[name]['avg_latency'] += inv.get('latency_ms', 0)
        
        # Average latencies
        for name in tool_stats:
            count = tool_stats[name]['count']
            if count > 0:
                tool_stats[name]['avg_latency'] /= count
        
        return {
            'total_invocations': len(invocations),
            'unique_tools': len(tool_stats),
            'tool_breakdown': tool_stats
        }
    
    def _outcome_summary(self, experience) -> Dict:
        """Summary of final outcome."""
        outcome = experience.final_outcome or {}
        
        return {
            'success': experience.classification == 'Successful Execution',
            'classification': experience.classification,
            'deliverable': outcome.get('deliverable_type', 'unknown'),
            'quality_score': outcome.get('quality_score', 0),
            'user_satisfaction': outcome.get('user_satisfaction', 0)
        }
    
    def _extract_lessons(self, experience) -> List[str]:
        """Extract actionable lessons from experience."""
        lessons = []
        
        # From failures
        if experience.classification == 'Failure':
            final = experience.final_outcome or {}
            error = final.get('error', '')
            if error:
                lessons.append(f"Failure mode: {error[:150]}")
        
        # From user corrections
        if experience.classification == 'User Correction':
            meta = experience.metadata or {}
            correction = meta.get('user_correction', '')
            if correction:
                lessons.append(f"User preference: {correction[:150]}")
        
        # From verification
        verif = experience.verification_results or {}
        failed = verif.get('failed_checks', [])
        for check in failed[:3]:
            lessons.append(f"Verification: {check}")
        
        # From performance
        metrics = experience.performance_metrics or {}
        if metrics.get('timeout_occurred'):
            lessons.append("Performance: timeout risk")
        
        return lessons if lessons else ["No explicit lessons extracted"]
    
    def _generate_recommendations(self, experience) -> List[str]:
        """Generate recommendations based on experience."""
        recs = []
        
        # Performance recommendations
        metrics = experience.performance_metrics or {}
        latency = metrics.get('total_latency_ms', 0)
        if latency > 5000:
            recs.append("Consider caching or parallelization to reduce latency")
        
        # Tool recommendations
        tool_summary = self._tool_summary(experience)
        for tool, stats in tool_summary.get('tool_breakdown', {}).items():
            if stats['errors'] > 0:
                recs.append(f"Review {tool} reliability ({stats['errors']} errors)")
        
        # Planning recommendations
        if experience.classification == 'Failure':
            recs.append("Review planning assumptions for similar tasks")
        
        return recs if recs else ["No specific recommendations"]


# =============================================================================
# FILE: experience_replay/feedback.py
# =============================================================================

"""
Feedback Integrator — Integrate human and system feedback into learning.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime


class FeedbackIntegrator:
    """
    Integrates feedback from multiple sources to improve experience quality
    and learning outcomes.
    """
    
    FEEDBACK_SOURCES = [
        'user_feedback',
        'verification_engine',
        'simulation_engine',
        'confidence_graph',
        'observability_engine',
        'benchmark_results',
        'performance_analytics',
        'human_review'
    ]
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
    
    def add_user_feedback(
        self,
        experience_id: str,
        rating: float,  # 0.0 to 1.0
        comment: Optional[str] = None,
        corrections: Optional[List[str]] = None
    ) -> bool:
        """
        Add direct user feedback to an experience.
        """
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return False
        
        feedback = {
            'source': 'user_feedback',
            'timestamp': datetime.now().isoformat(),
            'rating': rating,
            'comment': comment,
            'corrections': corrections or []
        }
        
        # Update experience metadata
        metadata = experience.metadata or {}
        if 'feedback_history' not in metadata:
            metadata['feedback_history'] = []
        
        metadata['feedback_history'].append(feedback)
        metadata['latest_user_rating'] = rating
        
        # Adjust importance based on feedback
        importance_adjustment = (rating - 0.5) * 0.2  # -0.1 to +0.1
        
        self.storage.update_experience(experience_id, {
            'metadata': metadata,
            'importance_score': min(1.0, max(0.0, experience.importance_score + importance_adjustment))
        })
        
        return True
    
    def add_verification_feedback(
        self,
        experience_id: str,
        verification_result: Dict[str, Any]
    ) -> bool:
        """
        Add feedback from the verification engine.
        """
        passed = verification_result.get('all_checks_passed', False)
        failed_checks = verification_result.get('failed_checks', [])
        
        feedback = {
            'source': 'verification_engine',
            'timestamp': datetime.now().isoformat(),
            'passed': passed,
            'failed_checks': failed_checks,
            'score': verification_result.get('score', 0.0)
        }
        
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return False
        
        metadata = experience.metadata or {}
        metadata['verification_feedback'] = feedback
        
        # Update classification if verification reveals issues
        new_classification = experience.classification
        if not passed and experience.classification == 'Successful Execution':
            new_classification = 'Partial Success'
        
        self.storage.update_experience(experience_id, {
            'metadata': metadata,
            'classification': new_classification,
            'success_score': feedback['score']
        })
        
        return True
    
    def add_simulation_feedback(
        self,
        experience_id: str,
        simulation_results: Dict[str, Any]
    ) -> bool:
        """
        Add feedback from simulation engine (Digital Twin).
        """
        feedback = {
            'source': 'simulation_engine',
            'timestamp': datetime.now().isoformat(),
            'predicted_success': simulation_results.get('predicted_success', False),
            'predicted_latency': simulation_results.get('predicted_latency_ms'),
            'divergence_from_actual': simulation_results.get('divergence_score', 0)
        }
        
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return False
        
        metadata = experience.metadata or {}
        metadata['simulation_feedback'] = feedback
        
        self.storage.update_experience(experience_id, {
            'metadata': metadata
        })
        
        return True
    
    def process_feedback_queue(self) -> Dict[str, int]:
        """
        Process all pending feedback and update learning weights.
        """
        # In production, would process a queue
        # For now, recalculate all experience priorities
        
        updated = 0
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                new_priority = self._calculate_replay_priority(exp)
                self.storage.update_experience(exp.experience_id, {
                    'metadata': {
                        **(exp.metadata or {}),
                        'replay_priority': new_priority
                    }
                })
                updated += 1
        
        return {'processed': updated}
    
    def _calculate_replay_priority(self, experience) -> float:
        """Calculate replay priority based on all feedback sources."""
        metadata = experience.metadata or {}
        
        # Base priority from importance
        priority = experience.importance_score
        
        # User feedback adjustment
        user_rating = metadata.get('latest_user_rating', 0.5)
        priority += (user_rating - 0.5) * self.config.feedback_weight_user
        
        # Verification adjustment
        verif = metadata.get('verification_feedback', {})
        verif_score = verif.get('score', 0.5)
        priority += (verif_score - 0.5) * self.config.feedback_weight_verification
        
        # Simulation adjustment
        sim = metadata.get('simulation_feedback', {})
        sim_success = 1.0 if sim.get('predicted_success', True) else 0.0
        priority += (sim_success - 0.5) * self.config.feedback_weight_simulation
        
        return min(1.0, max(0.0, priority))


# =============================================================================
# FILE: experience_replay/reward.py
# =============================================================================

"""
Reward Calculator — Calculate rewards for reinforcement learning.
"""

from typing import Dict, List, Optional, Any
import numpy as np


class RewardCalculator:
    """
    Calculates rewards for experiences to enable RL-based learning.
    Decomposes rewards into multiple components.
    """
    
    def __init__(self, config):
        self.config = config
    
    def calculate_reward(self, experience) -> Dict[str, float]:
        """
        Calculate comprehensive reward signal for an experience.
        Returns decomposed reward components.
        """
        components = {
            'outcome_reward': self._outcome_reward(experience),
            'efficiency_reward': self._efficiency_reward(experience),
            'correctness_reward': self._correctness_reward(experience),
            'user_satisfaction_reward': self._user_satisfaction_reward(experience),
            'exploration_reward': self._exploration_reward(experience),
            'safety_reward': self._safety_reward(experience)
        }
        
        # Combined reward with weights
        weights = {
            'outcome_reward': 0.30,
            'efficiency_reward': 0.20,
            'correctness_reward': 0.25,
            'user_satisfaction_reward': 0.15,
            'exploration_reward': 0.05,
            'safety_reward': 0.05
        }
        
        components['total_reward'] = sum(
            components[k] * weights[k] for k in weights
        )
        
        return components
    
    def _outcome_reward(self, experience) -> float:
        """Reward based on execution outcome."""
        classification = experience.classification or 'Unknown'
        
        rewards = {
            'Successful Execution': 1.0,
            'Partial Success': 0.5,
            'Failure': -1.0,
            'Timeout': -0.5,
            'User Correction': 0.3,  # Positive because we learned
            'Security Violation': -2.0,
            'Performance Regression': -0.3,
            'Architecture Improvement': 0.8,
            'Capability Discovery': 0.9,
            'Optimization Opportunity': 0.7
        }
        
        return rewards.get(classification, 0.0)
    
    def _efficiency_reward(self, experience) -> float:
        """Reward based on resource efficiency."""
        metrics = experience.performance_metrics or {}
        resources = experience.resource_usage or {}
        
        # Latency penalty
        latency = metrics.get('total_latency_ms', 0)
        latency_penalty = -0.001 * max(0, latency - 5000) / 1000
        
        # Token efficiency
        tokens = metrics.get('token_usage', 0)
        token_penalty = -0.0001 * max(0, tokens - 10000) / 1000
        
        # Memory efficiency
        memory = resources.get('peak_memory_mb', 0)
        memory_penalty = -0.01 * max(0, memory - 1000) / 100
        
        return max(-1.0, latency_penalty + token_penalty + memory_penalty)
    
    def _correctness_reward(self, experience) -> float:
        """Reward based on verification and correctness."""
        verification = experience.verification_results or {}
        
        if not verification:
            return 0.0
        
        checks_passed = verification.get('checks_passed', 0)
        checks_failed = verification.get('checks_failed', 0)
        total = checks_passed + checks_failed
        
        if total == 0:
            return 0.0
        
        return (checks_passed - checks_failed) / total
    
    def _user_satisfaction_reward(self, experience) -> float:
        """Reward based on explicit user feedback."""
        metadata = experience.metadata or {}
        rating = metadata.get('latest_user_rating', None)
        
        if rating is None:
            return 0.0
        
        return (rating - 0.5) * 2  # Scale to -1 to 1
    
    def _exploration_reward(self, experience) -> float:
        """Reward for discovering new capabilities or patterns."""
        if experience.classification == 'Capability Discovery':
            return 1.0
        
        # Reward novel tool combinations
        tools = experience.tool_invocations or []
        unique_tools = len(set(t.get('tool_name') for t in tools))
        
        if unique_tools > 3:
            return 0.1 * min(unique_tools / 10, 1.0)
        
        return 0.0
    
    def _safety_reward(self, experience) -> float:
        """Reward for safe, secure execution."""
        if experience.classification == 'Security Violation':
            return -2.0
        
        # Check for any security flags
        metadata = experience.metadata or {}
        security_flags = metadata.get('security_flags', [])
        
        return -0.5 * len(security_flags)
    
    def calculate_td_error(
        self,
        current_reward: float,
        next_value: float,
        current_value: float
    ) -> float:
        """
        Calculate temporal difference error for value learning.
        """
        discount = self.config.discount_factor
        return current_reward + discount * next_value - current_value


# =============================================================================
# FILE: experience_replay/reinforcement.py
# =============================================================================

"""
RL Integration — Integrate with reinforcement learning for continuous improvement.
"""

from typing import Dict, List, Optional, Any, Tuple
import numpy as np


class RLIntegration:
    """
    Integrates experience replay with reinforcement learning.
    Implements Prioritized Experience Replay (PER) and policy improvement.
    """
    
    def __init__(self, storage, reward_calculator, ranker, config):
        self.storage = storage
        self.reward_calc = reward_calculator
        self.ranker = ranker
        self.config = config
        
        # PER parameters
        self.alpha = config.priority_alpha  # Priority exponent
        self.beta = config.priority_beta    # Importance sampling exponent
        self.beta_increment = 0.001
        self.epsilon = 1e-6
        
        # Value function approximation (simplified)
        self.value_estimates: Dict[str, float] = {}
    
    def compute_priorities(self, experiences: List[Any]) -> List[float]:
        """
        Compute sampling priorities for experiences.
        Higher priority = more likely to be sampled for training.
        """
        priorities = []
        
        for exp in experiences:
            # Priority based on TD error magnitude
            td_error = self._estimate_td_error(exp)
            
            # Also consider importance score
            importance = exp.importance_score
            
            # Combined priority
            priority = (abs(td_error) + self.epsilon) ** self.alpha
            priority *= importance
            
            priorities.append(priority)
        
        return priorities
    
    def _estimate_td_error(self, experience) -> float:
        """Estimate TD error for an experience."""
        rewards = self.reward_calc.calculate_reward(experience)
        total_reward = rewards['total_reward']
        
        # Get current value estimate
        exp_id = experience.experience_id
        current_value = self.value_estimates.get(exp_id, 0.0)
        
        # Estimate next value (simplified - would use actual successor)
        next_value = 0.0  # Terminal for now
        
        return self.reward_calc.calculate_td_error(
            total_reward, next_value, current_value
        )
    
    def sample_batch(
        self,
        batch_size: int = 32
    ) -> List[Tuple[Any, float, float]]:
        """
        Sample a batch of experiences for RL training.
        Returns (experience, priority, importance_weight) tuples.
        """
        # Get candidate experiences
        candidates = []
        for batch in self.storage.iterate_all(batch_size=200):
            candidates.extend(batch)
        
        if len(candidates) <= batch_size:
            sampled = candidates
        else:
            # Prioritized sampling
            priorities = self.compute_priorities(candidates)
            total_priority = sum(priorities)
            
            if total_priority == 0:
                # Uniform sampling fallback
                indices = np.random.choice(
                    len(candidates),
                    size=batch_size,
                    replace=False
                )
            else:
                probs = [p / total_priority for p in priorities]
                indices = np.random.choice(
                    len(candidates),
                    size=batch_size,
                    replace=False,
                    p=probs
                )
            
            sampled = [candidates[i] for i in indices]
        
        # Calculate importance sampling weights
        # Correction for bias introduced by prioritized sampling
        importance_weights = self._compute_importance_weights(
            sampled, candidates
        )
        
        return [
            (exp, priorities[i] if i < len(priorities) else 0, w)
            for i, (exp, w) in enumerate(zip(sampled, importance_weights))
        ]
    
    def _compute_importance_weights(
        self,
        sampled: List[Any],
        all_candidates: List[Any]
    ) -> List[float]:
        """Compute importance sampling weights."""
        N = len(all_candidates)
        n = len(sampled)
        
        # Simplified: uniform weights for now
        # In full implementation, would use actual sampling probabilities
        max_weight = (N * self.beta) ** -1
        
        weights = []
        for _ in sampled:
            # Weight = (N * P(i))^(-beta)
            prob = 1.0 / N  # Simplified
            weight = (N * prob) ** -self.beta
            weights.append(weight / max_weight)  # Normalize
        
        # Anneal beta
        self.beta = min(1.0, self.beta + self.beta_increment)
        
        return weights
    
    def update_value_estimate(self, experience_id: str, value: float):
        """Update value function estimate for an experience."""
        self.value_estimates[experience_id] = value
    
    def generate_policy_improvement(self, experience) -> Dict[str, Any]:
        """
        Generate policy improvement suggestions from an experience.
        """
        rewards = self.reward_calc.calculate_reward(experience)
        
        suggestions = {
            'experience_id': experience.experience_id,
            'total_reward': rewards['total_reward'],
            'reward_breakdown': {
                k: v for k, v in rewards.items() if k != 'total_reward'
            },
            'improvements': []
        }
        
        # Analyze reward components for improvement opportunities
        if rewards['efficiency_reward'] < -0.1:
            suggestions['improvements'].append({
                'area': 'efficiency',
                'suggestion': 'Optimize tool usage or enable parallel execution',
                'expected_gain': -rewards['efficiency_reward'] * 0.5
            })
        
        if rewards['correctness_reward'] < 0.5:
            suggestions['improvements'].append({
                'area': 'correctness',
                'suggestion': 'Add additional verification steps',
                'expected_gain': (0.5 - rewards['correctness_reward']) * 0.5
            })
        
        if rewards['outcome_reward'] < 0:
            suggestions['improvements'].append({
                'area': 'outcome',
                'suggestion': 'Review planning strategy for similar tasks',
                'expected_gain': -rewards['outcome_reward'] * 0.3
            })
        
        return suggestions
    
    def train_step(self, batch: List[Tuple[Any, float, float]]) -> Dict[str, Any]:
        """
        Perform one RL training step on a batch of experiences.
        Simplified - would connect to actual RL algorithm.
        """
        losses = []
        
        for experience, priority, weight in batch:
            # Compute target
            rewards = self.reward_calc.calculate_reward(experience)
            target_value = rewards['total_reward']
            
            # Current estimate
            current = self.value_estimates.get(experience.experience_id, 0.0)
            
            # Update with weighted TD learning
            lr = self.config.learning_rate * weight
            new_value = current + lr * (target_value - current)
            
            self.update_value_estimate(experience.experience_id, new_value)
            
            losses.append(abs(target_value - current))
        
        return {
            'mean_loss': np.mean(losses) if losses else 0,
            'max_loss': max(losses) if losses else 0,
            'batch_size': len(batch)
        }


# =============================================================================
# FILE: experience_replay/forgetting.py
# =============================================================================

"""
Forgetting Policy — Intelligently forget old or low-value experiences.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class ForgettingPolicy:
    """
    Manages intelligent forgetting of experiences to maintain
    storage efficiency while preserving valuable knowledge.
    """
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
    
    def should_forget(self, experience) -> bool:
        """
        Determine if an experience should be forgotten.
        """
        # Never forget critical experiences
        if experience.classification in [
            'Security Violation',
            'Capability Discovery',
            'Architecture Improvement'
        ]:
            return False
        
        # Check importance threshold
        if experience.importance_score > 0.8:
            return False
        
        # Check if too old and low value
        age_days = (datetime.now() - experience.timestamp).days
        max_age = self.config.retention_window_days
        
        if age_days > max_age and experience.importance_score < self.config.forget_threshold:
            return True
        
        # Check if superseded by better versions
        if self._has_better_version(experience):
            return True
        
        # Check if duplicate (handled by deduplication)
        metadata = experience.metadata or {}
        if metadata.get('duplicate_of'):
            return True
        
        return False
    
    def _has_better_version(self, experience) -> bool:
        """Check if a newer, better version of this experience exists."""
        # Search for similar successful experiences
        similar = self.storage.query_experiences(
            classification='Successful Execution',
            start_time=experience.timestamp,
            limit=10
        )
        
        # Simple heuristic: if many newer successes exist, this may be forgettable
        return len(similar) > 5 and experience.classification != 'Successful Execution'
    
    def apply_forgetting(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Apply forgetting policy to all experiences.
        """
        to_forget = []
        to_compress = []
        
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                if self.should_forget(exp):
                    to_forget.append(exp.experience_id)
                elif self._should_compress(exp):
                    to_compress.append(exp.experience_id)
        
        if not dry_run:
            # Mark for forgetting (soft delete)
            for eid in to_forget:
                self.storage.update_experience(eid, {
                    'metadata': {
                        'forgotten': True,
                        'forgotten_at': datetime.now().isoformat(),
                        'reason': 'policy'
                    }
                })
        
        return {
            'to_forget': len(to_forget),
            'to_compress': len(to_compress),
            'forgotten_ids': to_forget if dry_run else [],
            'retained': self.storage.get_experience_count() - len(to_forget)
        }
    
    def _should_compress(self, experience) -> bool:
        """Determine if experience should be compressed rather than forgotten."""
        age_days = (datetime.now() - experience.timestamp).days
        return age_days > self.config.storage.compression_threshold_days and \
               experience.importance_score > self.config.forget_threshold
    
    def emergency_retention(self, experience_ids: List[str]) -> bool:
        """
        Prevent specific experiences from being forgotten.
        Used for critical learning moments.
        """
        for eid in experience_ids:
            self.storage.update_experience(eid, {
                'metadata': {
                    'retention_lock': True,
                    'locked_at': datetime.now().isoformat(),
                    'lock_reason': 'emergency_retention'
                },
                'importance_score': 1.0  # Max importance
            })
        
        return True
    
    def get_forgotten_stats(self) -> Dict[str, Any]:
        """Get statistics about forgotten experiences."""
        # Query forgotten experiences
        all_exp = []
        for batch in self.storage.iterate_all(batch_size=500):
            all_exp.extend(batch)
        
        forgotten = [e for e in all_exp if (e.metadata or {}).get('forgotten')]
        
        by_reason = {}
        for exp in forgotten:
            reason = (exp.metadata or {}).get('reason', 'unknown')
            by_reason[reason] = by_reason.get(reason, 0) + 1
        
        return {
            'total_forgotten': len(forgotten),
            'by_reason': by_reason,
            'space_saved_estimate_mb': len(forgotten) * 0.5  # rough estimate
        }


# =============================================================================
# FILE: experience_replay/retention.py
# =============================================================================

"""
Retention Policy — Ensure valuable experiences are retained long-term.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class RetentionPolicy:
    """
    Complements forgetting by explicitly ensuring valuable experiences
    are retained and accessible.
    """
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
        
        # Categories that must always be retained
        RETAIN_CATEGORIES = [
            'Security Violation',
            'Capability Discovery',
            'Architecture Improvement',
            'User Correction'
        ]
        
        # Minimum retention periods
        self.retention_periods = {
            'default': 90,  # days
            'Security Violation': 2555,  # 7 years
            'Capability Discovery': 730,  # 2 years
            'Architecture Improvement': 1095,  # 3 years
            'User Correction': 730,
            'Successful Execution': 365,
            'Failure': 730  # Keep failures longer for learning
        }
    
    def evaluate_retention(self, experience) -> Dict[str, Any]:
        """
        Evaluate whether an experience meets retention criteria.
        """
        age_days = (datetime.now() - experience.timestamp).days
        
        category = experience.classification or 'default'
        required_days = self.retention_periods.get(category, self.retention_periods['default'])
        
        # Check if experience is locked
        metadata = experience.metadata or {}
        is_locked = metadata.get('retention_lock', False)
        
        # Determine status
        if is_locked:
            status = 'locked'
            action = 'retain'
        elif age_days < required_days:
            status = 'active'
            action = 'retain'
        elif experience.importance_score > 0.9:
            status = 'high_value'
            action = 'retain'
        elif category in ['Security Violation', 'Capability Discovery']:
            status = 'critical_category'
            action = 'retain'
        else:
            status = 'eligible_for_archive'
            action = 'archive'
        
        return {
            'experience_id': experience.experience_id,
            'status': status,
            'recommended_action': action,
            'age_days': age_days,
            'required_days': required_days,
            'importance_score': experience.importance_score,
            'can_forget': action == 'archive'
        }
    
    def enforce_retention(self) -> Dict[str, Any]:
        """
        Apply retention policy to all experiences.
        """
        stats = {
            'retained': 0,
            'archived': 0,
            'promoted': 0,
            'evaluated': 0
        }
        
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                evaluation = self.evaluate_retention(exp)
                stats['evaluated'] += 1
                
                if evaluation['recommended_action'] == 'retain':
                    stats['retained'] += 1
                    
                    # Promote high-value experiences
                    if exp.importance_score > 0.85 and not (exp.metadata or {}).get('promoted'):
                        self._promote_experience(exp)
                        stats['promoted'] += 1
                else:
                    stats['archived'] += 1
                    self._archive_experience(exp)
        
        return stats
    
    def _promote_experience(self, experience):
        """Promote an experience to long-term high-priority storage."""
        self.storage.update_experience(experience.experience_id, {
            'metadata': {
                **(experience.metadata or {}),
                'promoted': True,
                'promoted_at': datetime.now().isoformat(),
                'retention_tier': 'long_term_high_priority'
            }
        })
    
    def _archive_experience(self, experience):
        """Move experience to archive tier."""
        self.storage.update_experience(experience.experience_id, {
            'metadata': {
                **(experience.metadata or {}),
                'archived': True,
                'archived_at': datetime.now().isoformat(),
                'retention_tier': 'archive'
            }
        })
    
    def get_retention_report(self) -> Dict[str, Any]:
        """Generate retention policy report."""
        total = self.storage.get_experience_count()
        
        # Count by tier
        tiers = {'long_term_high_priority': 0, 'active': 0, 'archive': 0, 'unknown': 0}
        
        for batch in self.storage.iterate_all(batch_size=200):
            for exp in batch:
                tier = (exp.metadata or {}).get('retention_tier', 'unknown')
                tiers[tier] = tiers.get(tier, 0) + 1
        
        return {
            'total_experiences': total,
            'by_tier': tiers,
            'retention_rate': tiers.get('long_term_high_priority', 0) / total if total > 0 else 0,
            'archive_rate': tiers.get('archive', 0) / total if total > 0 else 0
        }


# =============================================================================
# FILE: experience_replay/analytics.py
# =============================================================================

"""
Experience Analytics — Measure and analyze learning progress.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import statistics


class ExperienceAnalytics:
    """
    Comprehensive analytics for the Experience Replay Engine.
    Measures learning effectiveness and system improvement.
    """
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
    
    def compute_learning_rate(self, window_days: int = 30) -> Dict[str, float]:
        """
        Measure how quickly the system is learning from experiences.
        """
        since = datetime.now() - timedelta(days=window_days)
        
        experiences = []
        for batch in self.storage.iterate_all(batch_size=200):
            for exp in batch:
                if exp.timestamp >= since:
                    experiences.append(exp)
        
        if not experiences:
            return {'rate': 0.0, 'trend': 'flat'}
        
        # Success rate over time
        daily_success = {}
        for exp in experiences:
            day = exp.timestamp.date()
            if day not in daily_success:
                daily_success[day] = {'success': 0, 'total': 0}
            
            daily_success[day]['total'] += 1
            if exp.classification == 'Successful Execution':
                daily_success[day]['success'] += 1
        
        # Calculate trend
        days = sorted(daily_success.keys())
        if len(days) < 2:
            return {'rate': 0.0, 'trend': 'insufficient_data'}
        
        success_rates = [
            daily_success[d]['success'] / daily_success[d]['total']
            for d in days
        ]
        
        # Linear regression for trend
        x = list(range(len(days)))
        n = len(x)
        
        mean_x = sum(x) / n
        mean_y = sum(success_rates) / n
        
        # Slope
        numerator = sum((x[i] - mean_x) * (success_rates[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        
        return {
            'rate': slope,
            'trend': 'improving' if slope > 0.001 else 'declining' if slope < -0.001 else 'stable',
            'current_success_rate': success_rates[-1] if success_rates else 0,
            'avg_success_rate': mean_y
        }
    
    def compute_replay_accuracy(self) -> float:
        """
        Measure how accurately experiences can be replayed.
        """
        # In practice, would track actual replay results
        # Simplified metric
        total = self.storage.get_experience_count()
        if total == 0:
            return 0.0
        
        # Assume high accuracy for well-recorded experiences
        return 0.95
    
    def compute_failure_reduction(self, window_days: int = 30) -> Dict[str, Any]:
        """
        Measure reduction in repeated failures.
        """
        since = datetime.now() - timedelta(days=window_days)
        
        # Get failures
        failures = []
        for batch in self.storage.iterate_all(batch_size=200):
            for exp in batch:
                if exp.timestamp >= since and exp.classification == 'Failure':
                    failures.append(exp)
        
        # Group by failure pattern
        patterns = {}
        for exp in failures:
            # Simple pattern: tool + error type
            tools = tuple(sorted(set(
                t.get('tool_name', 'unknown') for t in (exp.tool_invocations or [])
            )))
            
            error = (exp.final_outcome or {}).get('error', 'unknown')[:50]
            pattern = (tools, error)
            
            patterns[pattern] = patterns.get(pattern, 0) + 1
        
        # Repeated failures are patterns with multiple occurrences
        repeated = {k: v for k, v in patterns.items() if v > 1}
        
        return {
            'total_failures': len(failures),
            'unique_patterns': len(patterns),
            'repeated_patterns': len(repeated),
            'repeat_rate': len(repeated) / len(patterns) if patterns else 0,
            'most_common_repeated': sorted(repeated.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    def compute_capability_reuse(self) -> Dict[str, Any]:
        """
        Measure how often capabilities are successfully reused.
        """
        all_exp = []
        for batch in self.storage.iterate_all(batch_size=200):
            all_exp.extend(batch)
        
        capability_usage = {}
        for exp in all_exp:
            for cap in (exp.capability_usage or []):
                if cap not in capability_usage:
                    capability_usage[cap] = {'uses': 0, 'successes': 0}
                
                capability_usage[cap]['uses'] += 1
                if exp.classification == 'Successful Execution':
                    capability_usage[cap]['successes'] += 1
        
        # Calculate reuse rates
        for cap in capability_usage:
            uses = capability_usage[cap]['uses']
            capability_usage[cap]['success_rate'] = \
                capability_usage[cap]['successes'] / uses if uses > 0 else 0
        
        return {
            'total_capabilities': len(capability_usage),
            'most_used': sorted(capability_usage.items(), key=lambda x: x[1]['uses'], reverse=True)[:10],
            'highest_success': sorted(
                capability_usage.items(),
                key=lambda x: x[1]['success_rate'],
                reverse=True
            )[:10]
        }
    
    def compute_knowledge_growth(self, window_days: int = 30) -> Dict[str, Any]:
        """
        Measure growth in system knowledge.
        """
        since = datetime.now() - timedelta(days=window_days)
        
        # Count new patterns discovered
        new_patterns = 0
        total_experiences = 0
        
        for batch in self.storage.iterate_all(batch_size=200):
            for exp in batch:
                if exp.timestamp >= since:
                    total_experiences += 1
                    if exp.classification == 'Capability Discovery':
                        new_patterns += 1
        
        # Unique tool combinations
        tool_combos = set()
        for batch in self.storage.iterate_all(batch_size=200):
            for exp in batch:
                if exp.timestamp >= since:
                    tools = tuple(sorted(set(
                        t.get('tool_name') for t in (exp.tool_invocations or [])
                    )))
                    if tools:
                        tool_combos.add(tools)
        
        return {
            'new_patterns_discovered': new_patterns,
            'experiences_in_period': total_experiences,
            'unique_tool_combinations': len(tool_combos),
            'discovery_rate': new_patterns / total_experiences if total_experiences > 0 else 0
        }
    
    def generate_full_report(self) -> Dict[str, Any]:
        """Generate comprehensive analytics report."""
        return {
            'learning_rate': self.compute_learning_rate(),
            'replay_accuracy': self.compute_replay_accuracy(),
            'failure_reduction': self.compute_failure_reduction(),
            'capability_reuse': self.compute_capability_reuse(),
            'knowledge_growth': self.compute_knowledge_growth(),
            'total_experiences': self.storage.get_experience_count(),
            'generated_at': datetime.now().isoformat()
        }


# =============================================================================
# FILE: experience_replay/visualization.py
# =============================================================================

"""
Replay Visualization — Visualize experience timelines and replay data.
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class ReplayVisualizer:
    """
    Generates visualizations of experiences, replays, and learning progress.
    Produces data structures for frontend rendering.
    """
    
    def __init__(self, config):
        self.config = config
    
    def generate_timeline_data(self, experience) -> Dict[str, Any]:
        """
        Generate timeline visualization data for an experience.
        """
        timeline = experience.execution_timeline or []
        
        nodes = []
        edges = []
        
        for i, event in enumerate(timeline):
            node = {
                'id': f"step_{i}",
                'step': event.get('step', i),
                'type': event.get('event_type', 'unknown'),
                'timestamp': event.get('timestamp'),
                'has_error': event.get('data_summary', {}).get('has_error', False),
                'data_keys': event.get('data_summary', {}).get('keys', [])
            }
            nodes.append(node)
            
            if i > 0:
                edges.append({
                    'from': f"step_{i-1}",
                    'to': f"step_{i}",
                    'type': 'sequence'
                })
        
        return {
            'experience_id': experience.experience_id,
            'session_id': experience.session_id,
            'classification': experience.classification,
            'nodes': nodes,
            'edges': edges,
            'total_steps': len(nodes)
        }
    
    def generate_replay_comparison_data(
        self,
        original_experience,
        replay_result
    ) -> Dict[str, Any]:
        """
        Generate comparison data between original and replay.
        """
        return {
            'original_id': original_experience.experience_id,
            'replay_id': replay_result.replay_id,
            'mode': replay_result.mode.value if hasattr(replay_result.mode, 'value') else str(replay_result.mode),
            'divergence_points': replay_result.divergence_points,
            'steps_match': f"{replay_result.steps_executed}/{replay_result.total_steps}",
            'success': replay_result.success,
            'metrics': replay_result.metrics
        }
    
    def generate_learning_curve_data(
        self,
        analytics: 'ExperienceAnalytics',
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Generate data for learning curve visualization.
        """
        # Get daily success rates
        since = datetime.now() - __import__('datetime').timedelta(days=days)
        
        # This would query actual data in production
        # Generating sample structure
        return {
            'title': 'Learning Curve',
            'x_axis': 'Date',
            'y_axis': 'Success Rate',
            'data_points': [],  # Would be populated from analytics
            'trend_line': {
                'slope': 0.0,
                'intercept': 0.5
            },
            'annotations': [
                {'date': '2024-01-15', 'event': 'Major update'},
                {'date': '2024-02-01', 'event': 'New capability'}
            ]
        }
    
    def generate_experience_graph_data(
        self,
        experiences: List[Any]
    ) -> Dict[str, Any]:
        """
        Generate force-directed graph of experience relationships.
        """
        nodes = []
        edges = []
        seen_ids = set()
        
        for exp in experiences:
            if exp.experience_id not in seen_ids:
                nodes.append({
                    'id': exp.experience_id,
                    'label': exp.classification or 'Unknown',
                    'importance': exp.importance_score,
                    'success': exp.classification == 'Successful Execution'
                })
                seen_ids.add(exp.experience_id)
            
            # Parent relationships
            if exp.parent_experience_id and exp.parent_experience_id in seen_ids:
                edges.append({
                    'from': exp.parent_experience_id,
                    'to': exp.experience_id,
                    'type': 'derived_from'
                })
        
        return {
            'nodes': nodes,
            'edges': edges,
            'node_count': len(nodes),
            'edge_count': len(edges)
        }
    
    def generate_svg_timeline(self, experience) -> str:
        """
        Generate an SVG timeline visualization.
        """
        timeline = experience.execution_timeline or []
        height = 100
        width = max(800, len(timeline) * 50)
        step_width = width / max(len(timeline), 1)
        
        svg_parts = [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
            f'<rect width="100%" height="100%" fill="#f8f9fa"/>'
        ]
        
        # Timeline bar
        svg_parts.append(
            f'<line x1="20" y1="{height/2}" x2="{width-20}" y2="{height/2}" stroke="#dee2e6" stroke-width="2"/>'
        )
        
        # Events
        for i, event in enumerate(timeline):
            x = 20 + i * step_width
            y = height / 2
            
            color = '#dc3545' if event.get('data_summary', {}).get('has_error') else '#28a745'
            
            svg_parts.append(
                f'<circle cx="{x}" cy="{y}" r="8" fill="{color}" stroke="white" stroke-width="2"/>'
            )
            
            # Event type label
            event_type = event.get('event_type', 'unknown')[:10]
            svg_parts.append(
                f'<text x="{x}" y="{y-15}" text-anchor="middle" font-size="10" fill="#495057">{event_type}</text>'
            )
        
        svg_parts.append('</svg>')
        
        return '\n'.join(svg_parts)
    
    def generate_dashboard_data(self, analytics: 'ExperienceAnalytics') -> Dict[str, Any]:
        """Generate data for main analytics dashboard."""
        report = analytics.generate_full_report()
        
        return {
            'summary_cards': [
                {
                    'title': 'Total Experiences',
                    'value': report['total_experiences'],
                    'trend': 'up'
                },
                {
                    'title': 'Learning Rate',
                    'value': f"{report['learning_rate']['rate']:.4f}",
                    'trend': report['learning_rate']['trend']
                },
                {
                    'title': 'Success Rate',
                    'value': f"{report['learning_rate']['current_success_rate']:.1%}",
                    'trend': 'up' if report['learning_rate']['rate'] > 0 else 'down'
                },
                {
                    'title': 'Replay Accuracy',
                    'value': f"{report['replay_accuracy']:.1%}",
                    'trend': 'stable'
                }
            ],
            'charts': {
                'learning_curve': self.generate_learning_curve_data(analytics),
                'failure_patterns': report['failure_reduction'],
                'capability_reuse': report['capability_reuse']
            },
            'generated_at': report['generated_at']
        }


# =============================================================================
# FILE: experience_replay/indexing.py
# =============================================================================

"""
Experience Indexing — Fast indexing for experience retrieval.
"""

import hashlib
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict


class ExperienceIndexer:
    """
    Multi-dimensional indexing for fast experience retrieval.
    Supports inverted indexes, spatial indexes, and temporal indexes.
    """
    
    def __init__(self, config):
        self.config = config
        
        # Inverted index: term -> experience IDs
        self._inverted_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Classification index
        self._classification_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Temporal index (date -> IDs)
        self._temporal_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Tool usage index
        self._tool_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Capability index
        self._capability_index: Dict[str, Set[str]] = defaultdict(set)
    
    def index_experience(self, experience):
        """Add an experience to all indexes."""
        exp_id = experience.experience_id
        
        # Index terms from intent
        if experience.user_intent:
            terms = self._extract_terms(experience.user_intent)
            for term in terms:
                self._inverted_index[term].add(exp_id)
        
        # Index classification
        if experience.classification:
            self._classification_index[experience.classification].add(exp_id)
        
        # Index date
        date_key = experience.timestamp.strftime('%Y-%m-%d')
        self._temporal_index[date_key].add(exp_id)
        
        # Index tools
        for inv in (experience.tool_invocations or []):
            tool = inv.get('tool_name')
            if tool:
                self._tool_index[tool].add(exp_id)
        
        # Index capabilities
        for cap in (experience.capability_usage or []):
            self._capability_index[cap].add(exp_id)
    
    def _extract_terms(self, text: str) -> List[str]:
        """Extract indexable terms from text."""
        # Simple tokenization
        words = text.lower().split()
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must',
                      'shall', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of',
                      'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'and', 'but', 'or', 'yet', 'so'}
        
        terms = []
        for word in words:
            word = word.strip('.,!?;:"()[]{}')
            if word and word not in stop_words and len(word) > 2:
                terms.append(word)
                # Also add stemmed version (simplified)
                if word.endswith('ing'):
                    terms.append(word[:-3])
                elif word.endswith('ed'):
                    terms.append(word[:-2])
        
        return list(set(terms))
    
    def search_by_terms(self, query: str) -> Set[str]:
        """Search experiences by text terms."""
        terms = self._extract_terms(query)
        
        if not terms:
            return set()
        
        # Intersection of all term postings
        result = None
        for term in terms:
            postings = self._inverted_index.get(term, set())
            if result is None:
                result = postings.copy()
            else:
                result &= postings
        
        return result or set()
    
    def search_by_classification(self, classification: str) -> Set[str]:
        """Search by experience classification."""
        return self._classification_index.get(classification, set()).copy()
    
    def search_by_date_range(self, start_date: str, end_date: str) -> Set[str]:
        """Search by date range (YYYY-MM-DD format)."""
        result = set()
        for date_key, ids in self._temporal_index.items():
            if start_date <= date_key <= end_date:
                result.update(ids)
        return result
    
    def search_by_tool(self, tool_name: str) -> Set[str]:
        """Search by tool usage."""
        return self._tool_index.get(tool_name, set()).copy()
    
    def search_by_capability(self, capability: str) -> Set[str]:
        """Search by capability usage."""
        return self._capability_index.get(capability, set()).copy()
    
    def combined_search(self, criteria: Dict[str, Any]) -> Set[str]:
        """
        Combined search using multiple criteria.
        
        criteria: {
            'terms': str,
            'classification': str,
            'tools': [str],
            'capabilities': [str],
            'date_range': (start, end)
        }
        """
        results = None
        
        if 'terms' in criteria:
            term_results = self.search_by_terms(criteria['terms'])
            results = term_results if results is None else (results & term_results)
        
        if 'classification' in criteria:
            class_results = self.search_by_classification(criteria['classification'])
            results = class_results if results is None else (results & class_results)
        
        if 'tools' in criteria:
            tool_results = set()
            for tool in criteria['tools']:
                tool_results |= self.search_by_tool(tool)
            results = tool_results if results is None else (results & tool_results)
        
        if 'capabilities' in criteria:
            cap_results = set()
            for cap in criteria['capabilities']:
                cap_results |= self.search_by_capability(cap)
            results = cap_results if results is None else (results & cap_results)
        
        if 'date_range' in criteria:
            date_results = self.search_by_date_range(*criteria['date_range'])
            results = date_results if results is None else (results & date_results)
        
        return results or set()
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            'total_indexed_experiences': len(set(
                id for ids in self._inverted_index.values() for id in ids
            )),
            'unique_terms': len(self._inverted_index),
            'classifications': list(self._classification_index.keys()),
            'tools': list(self._tool_index.keys()),
            'capabilities': list(self._capability_index.keys())
        }
    
    def remove_experience(self, experience_id: str):
        """Remove an experience from all indexes."""
        # In production, would need reverse mappings for efficient removal
        # Simplified: rebuild affected indexes
        for term, ids in list(self._inverted_index.items()):
            ids.discard(experience_id)
        
        for class_name, ids in list(self._classification_index.items()):
            ids.discard(experience_id)
        
        for date, ids in list(self._temporal_index.items()):
            ids.discard(experience_id)
        
        for tool, ids in list(self._tool_index.items()):
            ids.discard(experience_id)
        
        for cap, ids in list(self._capability_index.items()):
            ids.discard(experience_id)


# =============================================================================
# FILE: experience_replay/api.py
# =============================================================================

"""
External API — RESTful API for the Experience Replay Engine.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class APIResponse:
    """Standard API response format."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    meta: Optional[Dict] = None


class ReplayAPI:
    """
    External API for integrating the Experience Replay Engine
    with other Arctus modules and external systems.
    """
    
    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
    
    # ==================== Experience Management ====================
    
    def record_experience_start(self, user_intent: str, context: Optional[Dict] = None) -> APIResponse:
        """Start recording a new experience."""
        try:
            session_id = self.engine.recorder.start_session(user_intent, context)
            return APIResponse(success=True, data={'session_id': session_id})
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    def record_experience_event(self, session_id: str, event_type: str, data: Dict) -> APIResponse:
        """Record an event during execution."""
        try:
            recorder = self.engine.recorder
            
            if event_type == 'planning':
                recorder.record_planning(session_id, data.get('plan'), data.get('dag'))
            elif event_type == 'decision':
                recorder.record_decision(session_id, data)
            elif event_type == 'tool_invocation':
                recorder.record_tool_invocation(session_id, data)
            elif event_type == 'verification':
                recorder.record_verification(session_id, data)
            elif event_type == 'performance':
                recorder.record_performance_metrics(session_id, data)
            else:
                return APIResponse(success=False, error=f"Unknown event type: {event_type}")
            
            return APIResponse(success=True)
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    def finalize_experience(self, session_id: str, outcome: Dict) -> APIResponse:
        """Finalize and store an experience."""
        try:
            experience = self.engine.recorder.finalize_session(session_id, outcome)
            return APIResponse(
                success=True,
                data={'experience_id': experience.experience_id}
            )
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # ==================== Retrieval ====================
    
    def find_similar_experiences(
        self,
        intent: str,
        context: Optional[Dict] = None,
        top_k: int = 10
    ) -> APIResponse:
        """Find experiences similar to current context."""
        try:
            results = self.engine.retrieval.find_similar_experiences(
                intent, context, top_k
            )
            
            return APIResponse(success=True, data={
                'results': [
                    {
                        'experience_id': r['experience'].experience_id,
                        'similarity': r['similarity'],
                        'classification': r['experience'].classification
                    }
                    for r in results
                ],
                'count': len(results)
            })
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    def get_experience(self, experience_id: str) -> APIResponse:
        """Retrieve a specific experience."""
        try:
            exp = self.engine.storage.get_experience(experience_id)
            if not exp:
                return APIResponse(success=False, error="Experience not found")
            
            return APIResponse(success=True, data=exp.to_dict())
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # ==================== Replay ====================
    
    def replay_experience(
        self,
        experience_id: str,
        mode: str = 'deterministic',
        branch_point: Optional[int] = None
    ) -> APIResponse:
        """Replay a past experience."""
        try:
            from .replay import ReplayMode
            
            mode_enum = ReplayMode(mode)
            result = self.engine.replay.replay(
                experience_id, mode_enum, branch_point
            )
            
            return APIResponse(success=True, data={
                'replay_id': result.replay_id,
                'success': result.success,
                'steps': f"{result.steps_executed}/{result.total_steps}",
                'divergences': len(result.divergence_points)
            })
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # ==================== Feedback ====================
    
    def add_feedback(
        self,
        experience_id: str,
        feedback_type: str,
        data: Dict
    ) -> APIResponse:
        """Add feedback to an experience."""
        try:
            if feedback_type == 'user':
                self.engine.feedback.add_user_feedback(
                    experience_id,
                    data.get('rating', 0.5),
                    data.get('comment'),
                    data.get('corrections')
                )
            elif feedback_type == 'verification':
                self.engine.feedback.add_verification_feedback(
                    experience_id, data
                )
            else:
                return APIResponse(success=False, error=f"Unknown feedback type: {feedback_type}")
            
            return APIResponse(success=True)
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # ==================== Analytics ====================
    
    def get_analytics(self, metric_type: Optional[str] = None) -> APIResponse:
        """Get analytics data."""
        try:
            if metric_type == 'learning_rate':
                data = self.engine.analytics.compute_learning_rate()
            elif metric_type == 'failure_reduction':
                data = self.engine.analytics.compute_failure_reduction()
            elif metric_type == 'knowledge_growth':
                data = self.engine.analytics.compute_knowledge_growth()
            else:
                data = self.engine.analytics.generate_full_report()
            
            return APIResponse(success=True, data=data)
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # ==================== Maintenance ====================
    
    def run_maintenance(self, operation: str) -> APIResponse:
        """Run maintenance operations."""
        try:
            if operation == 'compress':
                count = self.engine.compressor.batch_compress()
                return APIResponse(success=True, data={'compressed': count})
            elif operation == 'deduplicate':
                result = self.engine.deduplicator.run_deduplication()
                return APIResponse(success=True, data=result)
            elif operation == 'forget':
                result = self.engine.forgetting.apply_forgetting()
                return APIResponse(success=True, data=result)
            elif operation == 'enforce_retention':
                result = self.engine.retention.enforce_retention()
                return APIResponse(success=True, data=result)
            else:
                return APIResponse(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return APIResponse(success=False, error=str(e))


# =============================================================================
# FILE: experience_replay/engine.py
# =============================================================================

"""
Experience Replay Engine — Main engine orchestrating all components.
"""

from typing import Dict, List, Optional, Any
import threading


class ExperienceReplayEngine:
    """
    Central orchestrator for the Experience Replay Engine.
    Coordinates all subsystems: recording, storage, replay, learning, and analytics.
    """
    
    def __init__(self, config=None):
        self.config = config or ReplayConfig()
        
        # Initialize subsystems
        self.storage = ExperienceStorage(self.config)
        self.embedder = EmbeddingGenerator(self.config)
        self.similarity = SimilaritySearch(self.config, self.embedder)
        self.ranker = ExperienceRanker(self.config)
        self.indexer = ExperienceIndexer(self.config)
        self.recorder = ExperienceRecorder(self.storage, self.config)
        self.retrieval = ExperienceRetrieval(self.storage, self.similarity, self.ranker, self.config)
        self.replay = ReplayExecutor(self.storage, self.config)
        self.summarizer = ExperienceSummarizer(self.config)
        self.compressor = ExperienceCompressor(self.storage, self.summarizer, self.config)
        self.deduplicator = DeduplicationEngine(self.storage, self.embedder, self.config)
        self.feedback = FeedbackIntegrator(self.storage, self.config)
        self.reward_calc = RewardCalculator(self.config)
        self.rl = RLIntegration(self.storage, self.reward_calc, self.ranker, self.config)
        self.forgetting = ForgettingPolicy(self.storage, self.config)
        self.retention = RetentionPolicy(self.storage, self.config)
        self.analytics = ExperienceAnalytics(self.storage, self.config)
        self.visualizer = ReplayVisualizer(self.config)
        self.api = ReplayAPI(self, self.config)
        
        # Background processing
        self._maintenance_thread = None
        self._shutdown_event = threading.Event()
        
        # Statistics
        self._stats = {
            'experiences_recorded': 0,
            'experiences_replayed': 0,
            'feedback_received': 0,
            'learning_cycles': 0
        }
    
    def initialize(self):
        """Initialize the engine and load existing data."""
        # Build indexes from existing experiences
        for batch in self.storage.iterate_all(batch_size=100):
            for exp in batch:
                # Index in similarity search
                embedding = self.embedder.embed_experience(exp)
                self.similarity.add_experience(exp.experience_id, embedding)
                
                # Index in inverted index
                self.indexer.index_experience(exp)
        
        self.similarity.build_index()
        
        # Start background maintenance if configured
        # self._start_maintenance_thread()
    
    def record_execution_start(self, user_intent: str, context=None) -> str:
        """
        Begin recording an execution session.
        Called by the Execution Engine before starting work.
        """
        return self.recorder.start_session(user_intent, context)
    
    def record_execution_progress(self, session_id: str, event_type: str, data: Dict):
        """
        Record progress during execution.
        Called by Execution Engine at key points.
        """
        if event_type == 'tool_call':
            self.recorder.record_tool_invocation(session_id, data)
        elif event_type == 'decision':
            self.recorder.record_decision(session_id, data)
        elif event_type == 'verification':
            self.recorder.record_verification(session_id, data)
        elif event_type == 'performance':
            self.recorder.record_performance_metrics(session_id, data)
    
    def record_execution_complete(
        self,
        session_id: str,
        outcome: Dict,
        classification: Optional[str] = None
    ) -> str:
        """
        Finalize execution recording.
        Called by Execution Engine after completion.
        Returns experience_id.
        """
        experience = self.recorder.finalize_session(session_id, outcome, classification)
        
        # Index the new experience
        embedding = self.embedder.embed_experience(experience)
        self.similarity.add_experience(experience.experience_id, embedding)
        self.indexer.index_experience(experience)
        
        # Calculate initial importance
        importance = self.ranker.score_experience(experience)
        self.storage.update_experience(experience.experience_id, {
            'importance_score': importance,
            'classification': classification or self._auto_classify(experience)
        })
        
        # Calculate rewards
        rewards = self.reward_calc.calculate_reward(experience)
        self.storage.update_experience(experience.experience_id, {
            'metadata': {
                'rewards': rewards,
                'recorded_at': datetime.now().isoformat()
            }
        })
        
        self._stats['experiences_recorded'] += 1
        
        return experience.experience_id
    
    def _auto_classify(self, experience) -> str:
        """Automatically classify an experience based on outcome."""
        outcome = experience.final_outcome or {}
        
        if outcome.get('error') or outcome.get('failed'):
            if outcome.get('timeout'):
                return 'Timeout'
            return 'Failure'
        
        if outcome.get('partial'):
            return 'Partial Success'
        
        if outcome.get('user_corrected'):
            return 'User Correction'
        
        if outcome.get('security_flag'):
            return 'Security Violation'
        
        return 'Successful Execution'
    
    def find_relevant_experiences(
        self,
        current_intent: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find relevant past experiences for current context.
        Called by Reasoning/Planning engines.
        """
        return self.retrieval.find_similar_experiences(current_intent, top_k=top_k)
    
    def get_failure_precedents(self, current_plan: Dict, top_k: int = 5) -> List[Dict]:
        """
        Get similar past failures to avoid repeating mistakes.
        Called by Planning Engine before execution.
        """
        return self.retrieval.find_failure_precedents(current_plan, top_k)
    
    def get_optimal_workflow(self, intent: str) -> Optional[Dict]:
        """
        Get the best known workflow for an intent.
        Called by Planning Engine for optimization.
        """
        return self.retrieval.find_optimal_workflow(intent)
    
    def replay_for_learning(
        self,
        experience_id: str,
        mode: str = 'deterministic'
    ) -> Dict[str, Any]:
        """
        Replay an experience for learning/analysis.
        """
        from .replay import ReplayMode
        
        mode_enum = ReplayMode(mode)
        result = self.replay.replay(experience_id, mode_enum)
        
        self._stats['experiences_replayed'] += 1
        
        return {
            'replay_id': result.replay_id,
            'success': result.success,
            'divergence_count': len(result.divergence_points),
            'metrics': result.metrics
        }
    
    def run_learning_cycle(self) -> Dict[str, Any]:
        """
        Run one RL learning cycle.
        """
        # Sample batch
        batch = self.rl.sample_batch(batch_size=32)
        
        # Train
        training_result = self.rl.train_step(batch)
        
        # Generate improvements
        improvements = []
        for experience, _, _ in batch[:5]:
            suggestion = self.rl.generate_policy_improvement(experience)
            improvements.append(suggestion)
        
        self._stats['learning_cycles'] += 1
        
        return {
            'training': training_result,
            'improvements': improvements,
            'cycle': self._stats['learning_cycles']
        }
    
    def integrate_feedback(
        self,
        experience_id: str,
        feedback_type: str,
        data: Dict
    ) -> bool:
        """
        Integrate feedback into learning.
        """
        if feedback_type == 'user':
            return self.feedback.add_user_feedback(
                experience_id,
                data.get('rating', 0.5),
                data.get('comment'),
                data.get('corrections')
            )
        elif feedback_type == 'verification':
            return self.feedback.add_verification_feedback(experience_id, data)
        
        return False
    
    def generate_experience_report(self, experience_id: str) -> Dict[str, Any]:
        """
        Generate comprehensive report for an experience.
        """
        experience = self.storage.get_experience(experience_id)
        if not experience:
            return {'error': 'Experience not found'}
        
        summary = self.summarizer.summarize(experience)
        rewards = self.reward_calc.calculate_reward(experience)
        
        return {
            'experience_id': experience_id,
            'summary': summary,
            'rewards': rewards,
            'visualization': self.visualizer.generate_timeline_data(experience),
            'similar_experiences': [
                r['experience'].experience_id
                for r in self.retrieval.find_similar_experiences(
                    experience.user_intent or '', top_k=5
                )
            ]
        }
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            **self._stats,
            'total_experiences': self.storage.get_experience_count(),
            'index_stats': self.indexer.get_index_stats(),
            'analytics': self.analytics.generate_full_report()
        }
    
    def shutdown(self):
        """Gracefully shutdown the engine."""
        self._shutdown_event.set()
        
        if self._maintenance_thread:
            self._maintenance_thread.join(timeout=5)
        
        # Final maintenance
        self.forgetting.apply_forgetting()
        self.retention.enforce_retention()
        
        # Build final index
        self.similarity.build_index()
    
    def _start_maintenance_thread(self):
        """Start background maintenance thread."""
        def maintenance_loop():
            while not self._shutdown_event.wait(3600):  # Every hour
                self.compressor.batch_compress()
                self.deduplicator.run_deduplication()
                self.forgetting.apply_forgetting()
                self.retention.enforce_retention()
        
        self._maintenance_thread = threading.Thread(target=maintenance_loop)
        self._maintenance_thread.daemon = True
        self._maintenance_thread.start()


# Import needed for engine
from datetime import datetime

# Re-import all components for engine
from .storage import ExperienceStorage, ExperienceRecord
from .recorder import ExperienceRecorder
from .ranking import ExperienceRanker
from .indexing import ExperienceIndexer
from .embeddings import EmbeddingGenerator
from .similarity import SimilaritySearch
from .retrieval import ExperienceRetrieval
from .replay import ReplayExecutor
from .summarizer import ExperienceSummarizer
from .compression import ExperienceCompressor
from .deduplication import DeduplicationEngine
from .feedback import FeedbackIntegrator
from .reward import RewardCalculator
from .reinforcement import RLIntegration
from .forgetting import ForgettingPolicy
from .retention import RetentionPolicy
from .analytics import ExperienceAnalytics
from .visualization import ReplayVisualizer
from .api import ReplayAPI
from .config import ReplayConfig


# =============================================================================
# FILE: experience_replay/tests/test_engine.py
# =============================================================================

"""
Tests for the Experience Replay Engine.
"""

import unittest
import tempfile
import shutil
from datetime import datetime


class TestExperienceReplayEngine(unittest.TestCase):
    """Test suite for the Experience Replay Engine."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = ReplayConfig()
        self.config.storage.database_path = f"{self.temp_dir}/test.db"
        self.config.storage.index_path = f"{self.temp_dir}/index"
        
        self.engine = ExperienceReplayEngine(self.config)
        self.engine.initialize()
    
    def tearDown(self):
        """Clean up test environment."""
        self.engine.shutdown()
        shutil.rmtree(self.temp_dir)
    
    def test_record_and_retrieve_experience(self):
        """Test basic recording and retrieval."""
        # Start session
        session_id = self.engine.record_execution_start(
            "Test intent: calculate fibonacci",
            {'user_id': 'test_user'}
        )
        
        # Record some events
        self.engine.record_execution_progress(session_id, 'tool_call', {
            'name': 'calculator',
            'arguments': {'expression': 'fib(10)'},
            'result': 55,
            'success': True,
            'latency_ms': 100
        })
        
        # Complete
        exp_id = self.engine.record_execution_complete(
            session_id,
            {'result': 55, 'latency_ms': 100},
            'Successful Execution'
        )
        
        # Retrieve
        experience = self.engine.storage.get_experience(exp_id)
        self.assertIsNotNone(experience)
        self.assertEqual(experience.user_intent, "Test intent: calculate fibonacci")
        self.assertEqual(experience.classification, 'Successful Execution')
    
    def test_similarity_search(self):
        """Test finding similar experiences."""
        # Create multiple experiences
        intents = [
            "Calculate fibonacci sequence",
            "Compute fibonacci numbers",
            "Sort a list of numbers",
            "Find prime numbers"
        ]
        
        exp_ids = []
        for intent in intents:
            session_id = self.engine.record_execution_start(intent)
            exp_id = self.engine.record_execution_complete(
                session_id,
                {'result': 'done'},
                'Successful Execution'
            )
            exp_ids.append(exp_id)
        
        # Rebuild index
        self.engine.similarity.build_index()
        
        # Search for similar to first
        results = self.engine.find_relevant_experiences(
            "Calculate fibonacci numbers",
            top_k=3
        )
        
        self.assertTrue(len(results) > 0)
        # First result should be most similar
    
    def test_replay(self):
        """Test experience replay."""
        # Create experience
        session_id = self.engine.record_execution_start("Test replay")
        
        self.engine.record_execution_progress(session_id, 'tool_call', {
            'name': 'test_tool',
            'arguments': {},
            'result': 'success'
        })
        
        exp_id = self.engine.record_execution_complete(
            session_id,
            {'result': 'success'}
        )
        
        # Replay
        result = self.engine.replay_for_learning(exp_id, 'deterministic')
        
        self.assertIn('replay_id', result)
        self.assertIn('success', result)
    
    def test_feedback_integration(self):
        """Test feedback integration."""
        # Create experience
        session_id = self.engine.record_execution_start("Test feedback")
        exp_id = self.engine.record_execution_complete(
            session_id,
            {'result': 'done'}
        )
        
        # Add feedback
        success = self.engine.integrate_feedback(
            exp_id,
            'user',
            {'rating': 0.9, 'comment': 'Great result!'}
        )
        
        self.assertTrue(success)
        
        # Verify updated
        experience = self.engine.storage.get_experience(exp_id)
        metadata = experience.metadata or {}
        self.assertEqual(metadata.get('latest_user_rating'), 0.9)
    
    def test_learning_cycle(self):
        """Test RL learning cycle."""
        # Create some experiences
        for i in range(10):
            session_id = self.engine.record_execution_start(f"Learning test {i}")
            self.engine.record_execution_complete(
                session_id,
                {'result': 'success' if i % 2 == 0 else 'failure'}
            )
        
        # Run learning cycle
        result = self.engine.run_learning_cycle()
        
        self.assertIn('training', result)
        self.assertIn('improvements', result)
    
    def test_analytics(self):
        """Test analytics generation."""
        # Create experiences with different outcomes
        for i in range(5):
            session_id = self.engine.record_execution_start(f"Analytics test {i}")
            self.engine.record_execution_complete(
                session_id,
                {'result': 'success'},
                'Successful Execution'
            )
        
        # Generate report
        report = self.engine.analytics.generate_full_report()
        
        self.assertIn('learning_rate', report)
        self.assertIn('total_experiences', report)
        self.assertGreaterEqual(report['total_experiences'], 5)


def run_tests():
    """Run the test suite."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestExperienceReplayEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    run_tests()
