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
