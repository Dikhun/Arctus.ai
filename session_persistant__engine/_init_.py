"""
Arctus AI Orchestration Framework - Session Persistence Engine

A production-grade session persistence system providing:

- Event-driven architecture with CQRS support
- Fully asynchronous I/O
- Repository pattern with PostgreSQL, Redis, and S3 tiers
- Dependency injection container
- State serialization with encryption and compression
- Automatic recovery from crashes, restarts, and failures
- Multi-device reconnection and synchronization
- Session locking and distributed coordination
- Idle timeout and expiration management
- Background cleanup and maintenance
- Comprehensive audit logging

Usage:
    from session_manager import SessionManager, SessionManagerConfig
    
    config = SessionManagerConfig(
        pg_dsn="postgresql://user:pass@localhost/arctus",
        redis_url="redis://localhost:6379",
        encryption_key=b"your-32-byte-encryption-key-here!!"
    )
    
    manager = SessionManager(config)
    await manager.start()
    
    engine = manager.get_engine()
    session = await engine.create_session(
        tenant_id="tenant-1",
        owner_id="user-1"
    )
"""

__version__ = "1.0.0"
__author__ = "Arctus AI Engineering"

# Core exports
from session_models import (
    SessionState,
    SessionStatus,
    SessionLock,
    SessionSnapshot,
    AgentMemory,
    ExecutionPlan,
    Subtask,
    SubtaskStatus,
    DeviceConnection,
    RecoveryLog,
    AuditRecord,
)

from session_events import (
    EventBus,
    DomainEvent,
    SessionCreated,
    SessionSaved,
    SessionLoaded,
    RecoveryCompleted,
)

from session_serializer import (
    SessionSerializer,
    SerializedSession,
    CompressionAlgorithm,
    SerializationFormat,
    EncryptionBackend,
)

from session_repository import (
    SessionRepository,
    PostgreSQLRepository,
    RedisRepository,
    S3Repository,
    TieredRepository,
)

from session_recovery import (
    RecoveryEngine,
    StateValidator,
    ValidationResult,
    RecoveryPlan,
)

from session_engine import (
    SessionEngine,
    SessionPersistenceConfig,
    SessionEngineError,
    SessionNotFoundError,
    SessionExpiredError,
)

from session_service import (
    SessionService,
    SessionCreationRequest,
    ExecutionResult,
)

from session_manager import (
    SessionManager,
    SessionManagerConfig,
    GlobalSessionManager,
)

# API (optional, requires FastAPI)
try:
    from session_api import create_app
    __all__ = ["create_app"]
except ImportError:
    pass

__all__ = [
    # Models
    "SessionState",
    "SessionStatus",
    "SessionLock",
    "SessionSnapshot",
    "AgentMemory",
    "ExecutionPlan",
    "Subtask",
    "SubtaskStatus",
    "DeviceConnection",
    "RecoveryLog",
    "AuditRecord",
    
    # Events
    "EventBus",
    "DomainEvent",
    "SessionCreated",
    "SessionSaved",
    "SessionLoaded",
    "RecoveryCompleted",
    
    # Serialization
    "SessionSerializer",
    "SerializedSession",
    "CompressionAlgorithm",
    "SerializationFormat",
    "EncryptionBackend",
    
    # Repository
    "SessionRepository",
    "PostgreSQLRepository",
    "RedisRepository",
    "S3Repository",
    "TieredRepository",
    
    # Recovery
    "RecoveryEngine",
    "StateValidator",
    "ValidationResult",
    "RecoveryPlan",
    
    # Engine
    "SessionEngine",
    "SessionPersistenceConfig",
    "SessionEngineError",
    "SessionNotFoundError",
    "SessionExpiredError",
    
    # Service
    "SessionService",
    "SessionCreationRequest",
    "ExecutionResult",
    
    # Manager
    "SessionManager",
    "SessionManagerConfig",
    "GlobalSessionManager",
]
