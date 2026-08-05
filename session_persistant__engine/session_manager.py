"""
session_manager.py
Dependency injection container and lifecycle manager.
Manages all session components and their dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

import asyncpg
import redis.asyncio as redis
from redis.asyncio import Redis

from session_models import SessionState
from session_events import EventBus
from session_serializer import SessionSerializer
from session_repository import (
    PostgreSQLRepository, RedisRepository, S3Repository, TieredRepository
)
from session_recovery import RecoveryEngine, StateValidator
from session_engine import SessionEngine, SessionPersistenceConfig


logger = logging.getLogger("session.manager")


class SessionManagerConfig:
    """Configuration for session manager."""
    
    def __init__(
        self,
        # PostgreSQL
        pg_dsn: str = "postgresql://user:pass@localhost/arctus",
        pg_pool_size: int = 20,
        # Redis
        redis_url: str = "redis://localhost:6379",
        redis_db: int = 0,
        # S3
        s3_endpoint: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        s3_access_key: Optional[str] = None,
        s3_secret_key: Optional[str] = None,
        # Encryption
        encryption_key: Optional[bytes] = None,
        # Engine
        auto_save_interval: float = 30.0,
        snapshot_interval: float = 300.0,
        idle_timeout: int = 3600,
        absolute_timeout: int = 86400,
        cleanup_interval: float = 300.0,
        # Recovery
        recovery_enabled: bool = True,
        version_compatibility: Optional[Dict[int, str]] = None
    ) -> None:
        self.pg_dsn = pg_dsn
        self.pg_pool_size = pg_pool_size
        self.redis_url = redis_url
        self.redis_db = redis_db
        self.s3_endpoint = s3_endpoint
        self.s3_bucket = s3_bucket
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key
        self.encryption_key = encryption_key
        self.auto_save_interval = auto_save_interval
        self.snapshot_interval = snapshot_interval
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self.cleanup_interval = cleanup_interval
        self.recovery_enabled = recovery_enabled
        self.version_compatibility = version_compatibility


class SessionManager:
    """
    Central manager for the Session Persistence Engine.
    Handles initialization, dependency injection, and lifecycle.
    """
    
    def __init__(self, config: SessionManagerConfig) -> None:
        self.config = config
        self._initialized = False
        
        # Components (initialized in start())
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.redis: Optional[Redis] = None
        self.event_bus: Optional[EventBus] = None
        self.serializer: Optional[SessionSerializer] = None
        self.pg_repo: Optional[PostgreSQLRepository] = None
        self.redis_repo: Optional[RedisRepository] = None
        self.s3_repo: Optional[S3Repository] = None
        self.tiered_repo: Optional[TieredRepository] = None
        self.validator: Optional[StateValidator] = None
        self.recovery: Optional[RecoveryEngine] = None
        self.engine: Optional[SessionEngine] = None
    
    async def start(self) -> SessionManager:
        """Initialize all components."""
        if self._initialized:
            return self
        
        logger.info("Starting Session Manager...")
        
        # 1. Initialize PostgreSQL pool
        self.pg_pool = await asyncpg.create_pool(
            self.config.pg_dsn,
            min_size=5,
            max_size=self.config.pg_pool_size
        )
        logger.info("PostgreSQL pool initialized")
        
        # 2. Initialize Redis
        self.redis = redis.from_url(
            self.config.redis_url,
            db=self.config.redis_db,
            decode_responses=False
        )
        await self.redis.ping()
        logger.info("Redis connected")
        
        # 3. Initialize Event Bus
        self.event_bus = EventBus()
        logger.info("Event bus initialized")
        
        # 4. Initialize Serializer
        self.serializer = SessionSerializer(
            encryption_key=self.config.encryption_key,
            encryption_backend="fernet" if self.config.encryption_key else "none",
            compression="gzip"
        )
        logger.info("Serializer initialized")
        
        # 5. Initialize Repositories
        self.pg_repo = PostgreSQLRepository(
            pool=self.pg_pool,
            serializer=self.serializer
        )
        await self.pg_repo.initialize()
        logger.info("PostgreSQL repository initialized")
        
        self.redis_repo = RedisRepository(
            redis_client=self.redis,
            serializer=self.serializer,
            ttl_seconds=self.config.idle_timeout
        )
        logger.info("Redis repository initialized")
        
        # S3 is optional
        if self.config.s3_endpoint and self.config.s3_bucket:
            self.s3_repo = S3Repository(
                endpoint_url=self.config.s3_endpoint,
                bucket=self.config.s3_bucket,
                access_key=self.config.s3_access_key or "",
                secret_key=self.config.s3_secret_key or "",
                serializer=self.serializer
            )
            logger.info("S3 repository initialized")
        
        # 6. Tiered Repository
        self.tiered_repo = TieredRepository(
            redis_repo=self.redis_repo,
            pg_repo=self.pg_repo,
            s3_repo=self.s3_repo,
            serializer=self.serializer
        )
        logger.info("Tiered repository initialized")
        
        # 7. Recovery Engine
        self.validator = StateValidator()
        self.recovery = RecoveryEngine(
            event_bus=self.event_bus,
            validator=self.validator,
            version_compatibility=self.config.version_compatibility
        )
        logger.info("Recovery engine initialized")
        
        # 8. Session Engine
        engine_config = SessionPersistenceConfig(
            auto_save_interval_seconds=self.config.auto_save_interval,
            snapshot_interval_seconds=self.config.snapshot_interval,
            idle_timeout_seconds=self.config.idle_timeout,
            absolute_timeout_seconds=self.config.absolute_timeout,
            cleanup_interval_seconds=self.config.cleanup_interval,
            encryption_key=self.config.encryption_key,
            recovery_enabled=self.config.recovery_enabled
        )
        
        self.engine = SessionEngine(
            repository=self.tiered_repo,
            event_bus=self.event_bus,
            recovery_engine=self.recovery,
            config=engine_config
        )
        
        await self.engine.start()
        logger.info("Session engine started")
        
        self._initialized = True
        logger.info("Session Manager fully initialized")
        
        return self
    
    async def stop(self) -> None:
        """Graceful shutdown."""
        if not self._initialized:
            return
        
        logger.info("Stopping Session Manager...")
        
        if self.engine:
            await self.engine.stop()
        
        if self.redis:
            await self.redis.close()
        
        if self.pg_pool:
            await self.pg_pool.close()
        
        self._initialized = False
        logger.info("Session Manager stopped")
    
    def get_engine(self) -> SessionEngine:
        """Get the session engine."""
        if not self.engine:
            raise RuntimeError("SessionManager not initialized")
        return self.engine
    
    def get_event_bus(self) -> EventBus:
        """Get the event bus."""
        if not self.event_bus:
            raise RuntimeError("SessionManager not initialized")
        return self.event_bus
    
    def get_repository(self) -> TieredRepository:
        """Get the tiered repository."""
        if not self.tiered_repo:
            raise RuntimeError("SessionManager not initialized")
        return self.tiered_repo
    
    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[SessionManager, None]:
        """Context manager for full lifecycle."""
        try:
            await self.start()
            yield self
        finally:
            await self.stop()


class GlobalSessionManager:
    """
    Singleton-like global access to session manager.
    For use in applications that need module-level access.
    """
    
    _instance: Optional[SessionManager] = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def initialize(cls, config: SessionManagerConfig) -> SessionManager:
        """Initialize global instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = SessionManager(config)
                await cls._instance.start()
            return cls._instance
    
    @classmethod
    async def shutdown(cls) -> None:
        """Shutdown global instance."""
        async with cls._lock:
            if cls._instance:
                await cls._instance.stop()
                cls._instance = None
    
    @classmethod
    def get(cls) -> SessionManager:
        """Get global instance."""
        if cls._instance is None:
            raise RuntimeError("GlobalSessionManager not initialized")
        return cls._instance
