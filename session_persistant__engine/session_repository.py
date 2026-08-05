"""
session_repository.py
Repository pattern implementation for session persistence.
Supports PostgreSQL (primary), Redis (hot cache), and S3 (cold storage).
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

import aioboto3
import asyncpg
import redis.asyncio as redis
from redis.asyncio import Redis

from session_models import (
    SessionState, SessionStatus, SessionSnapshot, SessionLock,
    AuditRecord, RecoveryLog
)
from session_serializer import SerializedSession, SessionSerializer


logger = logging.getLogger("session.repository")


class RepositoryError(Exception):
    """Base repository exception."""
    pass


class SessionNotFoundError(RepositoryError):
    """Session not found in storage."""
    pass


class LockConflictError(RepositoryError):
    """Unable to acquire lock due to conflict."""
    pass


class StorageTier(str, enum.Enum):
    """Storage tier classification."""
    HOT = "hot"      # Redis - active sessions
    WARM = "warm"    # PostgreSQL - recent sessions
    COLD = "cold"    # S3 - archived sessions


class SessionRepository(ABC):
    """Abstract base for session repositories."""
    
    @abstractmethod
    async def save(
        self,
        session: SessionState,
        serialized: Optional[SerializedSession] = None
    ) -> None:
        """Persist session state."""
        pass
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[SessionState]:
        """Retrieve session by ID."""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete session."""
        pass
    
    @abstractmethod
    async def list_active(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionState]:
        """List active sessions."""
        pass
    
    @abstractmethod
    async def find_expired(self, before: datetime) -> List[str]:
        """Find expired session IDs."""
        pass
    
    @abstractmethod
    async def save_snapshot(
        self,
        snapshot: SessionSnapshot,
        serialized: Optional[SerializedSession] = None
    ) -> None:
        """Save snapshot."""
        pass
    
    @abstractmethod
    async def get_snapshots(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[SessionSnapshot]:
        """Get snapshots for session."""
        pass
    
    @abstractmethod
    async def acquire_lock(
        self,
        lock: SessionLock,
        timeout_ms: int = 5000
    ) -> bool:
        """Acquire distributed lock."""
        pass
    
    @abstractmethod
    async def release_lock(self, lock_id: str) -> bool:
        """Release distributed lock."""
        pass
    
    @abstractmethod
    async def audit_log(self, record: AuditRecord) -> None:
        """Write audit record."""
        pass


class PostgreSQLRepository(SessionRepository):
    """
    PostgreSQL repository for durable session storage.
    Uses JSONB for flexible schema, supports full CRUD and querying.
    """
    
    def __init__(
        self,
        pool: asyncpg.Pool,
        serializer: SessionSerializer,
        table_prefix: str = "arctus"
    ) -> None:
        self.pool = pool
        self.serializer = serializer
        self.table_prefix = table_prefix
        self._table = f"{table_prefix}_sessions"
        self._snapshots_table = f"{table_prefix}_snapshots"
        self._locks_table = f"{table_prefix}_locks"
        self._audit_table = f"{table_prefix}_audit"
    
    async def initialize(self) -> None:
        """Create tables if not exists."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    session_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ,
                    data JSONB NOT NULL,
                    state_hash TEXT,
                    tags TEXT[] DEFAULT '{{}}',
                    metadata JSONB DEFAULT '{{}}'
                );
                
                CREATE INDEX IF NOT EXISTS idx_{self._table}_tenant 
                    ON {self._table}(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_{self._table}_status 
                    ON {self._table}(status);
                CREATE INDEX IF NOT EXISTS idx_{self._table}_activity 
                    ON {self._table}(last_activity_at);
                CREATE INDEX IF NOT EXISTS idx_{self._table}_expires 
                    ON {self._table}(expires_at) 
                    WHERE expires_at IS NOT NULL;
                
                CREATE TABLE IF NOT EXISTS {self._snapshots_table} (
                    snapshot_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES {self._table}(session_id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    trigger TEXT NOT NULL,
                    state_hash TEXT,
                    compressed_size_bytes INTEGER,
                    storage_key TEXT,
                    metadata JSONB DEFAULT '{{}}'
                );
                
                CREATE INDEX IF NOT EXISTS idx_{self._snapshots_table}_session 
                    ON {self._snapshots_table}(session_id, created_at DESC);
                
                CREATE TABLE IF NOT EXISTS {self._locks_table} (
                    lock_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    lock_type TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    metadata JSONB DEFAULT '{{}}'
                );
                
                CREATE INDEX IF NOT EXISTS idx_{self._locks_table}_session 
                    ON {self._locks_table}(session_id);
                CREATE INDEX IF NOT EXISTS idx_{self._locks_table}_expires 
                    ON {self._locks_table}(expires_at);
                
                CREATE TABLE IF NOT EXISTS {self._audit_table} (
                    record_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    success BOOLEAN NOT NULL DEFAULT TRUE,
                    details JSONB DEFAULT '{{}}',
                    ip_address TEXT,
                    user_agent TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_{self._audit_table}_session 
                    ON {self._audit_table}(session_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_{self._audit_table}_tenant 
                    ON {self._audit_table}(tenant_id, timestamp DESC);
            """)
    
    async def save(
        self,
        session: SessionState,
        serialized: Optional[SerializedSession] = None
    ) -> None:
        """Upsert session to PostgreSQL."""
        # Serialize if not provided
        if serialized is None:
            serialized = self.serializer.serialize(session)
        
        # Convert to dict for JSONB
        session_dict = session.model_dump(exclude={'lock'})
        
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self._table} (
                    session_id, tenant_id, owner_id, status, version,
                    created_at, updated_at, last_activity_at, expires_at,
                    data, state_hash, tags, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (session_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    owner_id = EXCLUDED.owner_id,
                    status = EXCLUDED.status,
                    version = EXCLUDED.version,
                    updated_at = EXCLUDED.updated_at,
                    last_activity_at = EXCLUDED.last_activity_at,
                    expires_at = EXCLUDED.expires_at,
                    data = EXCLUDED.data,
                    state_hash = EXCLUDED.state_hash,
                    tags = EXCLUDED.tags,
                    metadata = EXCLUDED.metadata
            """,
                session.session_id,
                session.tenant_id,
                session.owner_id,
                session.status.value,
                session.version,
                session.created_at,
                session.updated_at,
                session.last_activity_at,
                session.expires_at,
                json.dumps(session_dict),
                serialized.state_hash,
                session.tags,
                json.dumps(session.metadata)
            )
        
        logger.debug(f"Saved session {session.session_id} to PostgreSQL")
    
    async def get(self, session_id: str) -> Optional[SessionState]:
        """Retrieve session from PostgreSQL."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT data FROM {self._table} WHERE session_id = $1",
                session_id
            )
        
        if not row:
            return None
        
        data = json.loads(row['data'])
        return SessionState.model_validate(data)
    
    async def delete(self, session_id: str) -> bool:
        """Delete session."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._table} WHERE session_id = $1",
                session_id
            )
        deleted = "DELETE 1" in result
        logger.debug(f"Deleted session {session_id}: {deleted}")
        return deleted
    
    async def list_active(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionState]:
        """List active sessions."""
        query = f"SELECT data FROM {self._table} WHERE status IN ('active', 'initializing', 'recovering')"
        params: List[Any] = []
        
        if tenant_id:
            query += " AND tenant_id = $1"
            params.append(tenant_id)
        
        query += f" ORDER BY last_activity_at DESC LIMIT ${len(params) + 1}"
        params.append(limit)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [SessionState.model_validate(json.loads(r['data'])) for r in rows]
    
    async def find_expired(self, before: datetime) -> List[str]:
        """Find expired sessions."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT session_id FROM {self._table}
                WHERE expires_at IS NOT NULL AND expires_at < $1
                   OR last_activity_at < $2
                """,
                before,
                before - timedelta(hours=1)  # configurable
            )
        return [r['session_id'] for r in rows]
    
    async def save_snapshot(
        self,
        snapshot: SessionSnapshot,
        serialized: Optional[SerializedSession] = None
    ) -> None:
        """Save snapshot metadata."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self._snapshots_table} (
                    snapshot_id, session_id, version, created_at,
                    trigger, state_hash, compressed_size_bytes, storage_key, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
                snapshot.snapshot_id,
                snapshot.session_id,
                snapshot.version,
                snapshot.created_at,
                snapshot.trigger,
                snapshot.state_hash,
                snapshot.compressed_size_bytes,
                snapshot.storage_key,
                json.dumps(snapshot.metadata or {})
            )
    
    async def get_snapshots(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[SessionSnapshot]:
        """Get snapshots for session."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT * FROM {self._snapshots_table}
                WHERE session_id = $1
                ORDER BY created_at DESC LIMIT $2
                """,
                session_id,
                limit
            )
        
        return [
            SessionSnapshot(
                snapshot_id=r['snapshot_id'],
                session_id=r['session_id'],
                version=r['version'],
                created_at=r['created_at'],
                trigger=r['trigger'],
                state_hash=r['state_hash'],
                compressed_size_bytes=r['compressed_size_bytes'],
                storage_key=r['storage_key']
            )
            for r in rows
        ]
    
    async def acquire_lock(
        self,
        lock: SessionLock,
        timeout_ms: int = 5000
    ) -> bool:
        """Acquire lock using PostgreSQL advisory locks."""
        async with self.pool.acquire() as conn:
            # Use advisory lock based on session_id hash
            lock_key = hash(lock.session_id) % (2**63 - 1)
            
            # Try to acquire with timeout
            acquired = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)",
                lock_key
            )
            
            if acquired:
                # Store lock metadata
                await conn.execute(f"""
                    INSERT INTO {self._locks_table} (
                        lock_id, session_id, lock_type, owner, acquired_at, expires_at, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (session_id) DO UPDATE SET
                        lock_id = EXCLUDED.lock_id,
                        lock_type = EXCLUDED.lock_type,
                        owner = EXCLUDED.owner,
                        acquired_at = EXCLUDED.acquired_at,
                        expires_at = EXCLUDED.expires_at,
                        metadata = EXCLUDED.metadata
                """,
                    lock.lock_id,
                    lock.session_id,
                    lock.lock_type.value,
                    lock.owner,
                    lock.acquired_at,
                    lock.expires_at,
                    json.dumps(lock.metadata)
                )
                return True
            
            return False
    
    async def release_lock(self, lock_id: str) -> bool:
        """Release lock."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT session_id FROM {self._locks_table} WHERE lock_id = $1",
                lock_id
            )
            
            if row:
                lock_key = hash(row['session_id']) % (2**63 - 1)
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
                await conn.execute(
                    f"DELETE FROM {self._locks_table} WHERE lock_id = $1",
                    lock_id
                )
                return True
            return False
    
    async def audit_log(self, record: AuditRecord) -> None:
        """Write audit record."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self._audit_table} (
                    record_id, session_id, tenant_id, user_id, action,
                    resource, timestamp, success, details, ip_address, user_agent
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
                record.record_id,
                record.session_id,
                record.tenant_id,
                record.user_id,
                record.action,
                record.resource,
                record.timestamp,
                record.success,
                json.dumps(record.details),
                record.ip_address,
                record.user_agent
            )


class RedisRepository(SessionRepository):
    """
    Redis repository for hot session cache.
    Provides sub-millisecond access to active sessions.
    """
    
    def __init__(
        self,
        redis_client: Redis,
        serializer: SessionSerializer,
        ttl_seconds: int = 3600,
        key_prefix: str = "arctus:session"
    ) -> None:
        self.redis = redis_client
        self.serializer = serializer
        self.ttl = ttl_seconds
        self.prefix = key_prefix
        self._lock_prefix = f"{key_prefix}:lock"
        self._audit_prefix = f"{key_prefix}:audit"
    
    def _session_key(self, session_id: str) -> str:
        return f"{self.prefix}:{session_id}"
    
    def _snapshot_key(self, session_id: str) -> str:
        return f"{self.prefix}:{session_id}:snapshots"
    
    def _lock_key(self, session_id: str) -> str:
        return f"{self._lock_prefix}:{session_id}"
    
    def _audit_key(self, session_id: str) -> str:
        return f"{self._audit_prefix}:{session_id}"
    
    async def save(
        self,
        session: SessionState,
        serialized: Optional[SerializedSession] = None
    ) -> None:
        """Save session to Redis with TTL."""
        if serialized is None:
            serialized = self.serializer.serialize(session)
        
        key = self._session_key(session.session_id)
        data = serialized.to_storage_dict()
        
        pipe = self.redis.pipeline()
        pipe.set(key, json.dumps(data), ex=self.ttl)
        # Index by tenant
        pipe.sadd(f"{self.prefix}:tenant:{session.tenant_id}", session.session_id)
        # Index by status
        pipe.sadd(f"{self.prefix}:status:{session.status.value}", session.session_id)
        await pipe.execute()
        
        logger.debug(f"Cached session {session.session_id} in Redis")
    
    async def get(self, session_id: str) -> Optional[SessionState]:
        """Get session from Redis."""
        key = self._session_key(session_id)
        data = await self.redis.get(key)
        
        if not data:
            return None
        
        storage_dict = json.loads(data)
        serialized = SerializedSession.from_storage_dict(storage_dict)
        return self.serializer.deserialize(serialized)
    
    async def delete(self, session_id: str) -> bool:
        """Delete session from Redis."""
        key = self._session_key(session_id)
        session = await self.get(session_id)
        
        pipe = self.redis.pipeline()
        pipe.delete(key)
        pipe.delete(self._snapshot_key(session_id))
        pipe.delete(self._lock_key(session_id))
        
        if session:
            pipe.srem(f"{self.prefix}:tenant:{session.tenant_id}", session_id)
            pipe.srem(f"{self.prefix}:status:{session.status.value}", session_id)
        
        results = await pipe.execute()
        return results[0] > 0
    
    async def list_active(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionState]:
        """List active sessions from Redis."""
        if tenant_id:
            session_ids = a
