"""
session_engine.py
Core Session Persistence Engine implementing the full lifecycle
of session persistence, recovery, and synchronization.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple

from session_models import (
    SessionState, SessionStatus, SessionLock, LockType,
    SessionSnapshot, AuditRecord, DeviceConnection,
    AgentMemory, ExecutionPlan, EnvironmentConfig, ConversationState, WorkspaceState
)
from session_events import (
    EventBus, DomainEvent,
    SessionCreated, SessionActivated, SessionPaused, SessionResumed,
    SessionCompleted, SessionFailed, SessionExpired, SessionSaved,
    SessionLoaded, SnapshotCreated, DeviceConnected, DeviceDisconnected,
    StateMutated
)
from session_serializer import SessionSerializer, SerializedSession
from session_repository import (
    SessionRepository, TieredRepository, LockConflictError
)
from session_recovery import RecoveryEngine, RecoveryError, ValidationError


logger = logging.getLogger("session.engine")


class SessionEngineError(Exception):
    """Base engine exception."""
    pass


class SessionOperationError(SessionEngineError):
    """Operation failed."""
    pass


class SessionNotFoundError(SessionEngineError):
    """Session not found."""
    pass


class SessionExpiredError(SessionEngineError):
    """Session has expired."""
    pass


class SessionPersistenceConfig:
    """Configuration for session persistence behavior."""
    
    def __init__(
        self,
        auto_save_interval_seconds: float = 30.0,
        snapshot_interval_seconds: float = 300.0,
        idle_timeout_seconds: int = 3600,
        absolute_timeout_seconds: int = 86400,
        cleanup_interval_seconds: float = 300.0,
        max_snapshots_per_session: int = 10,
        enable_background_save: bool = True,
        enable_compression: bool = True,
        encryption_key: Optional[bytes] = None,
        tenant_isolation: bool = True,
        lock_timeout_ms: int = 5000,
        recovery_enabled: bool = True,
        multi_device_sync: bool = True
    ) -> None:
        self.auto_save_interval = auto_save_interval_seconds
        self.snapshot_interval = snapshot_interval_seconds
        self.idle_timeout = idle_timeout_seconds
        self.absolute_timeout = absolute_timeout_seconds
        self.cleanup_interval = cleanup_interval_seconds
        self.max_snapshots = max_snapshots_per_session
        self.enable_background_save = enable_background_save
        self.enable_compression = enable_compression
        self.encryption_key = encryption_key
        self.tenant_isolation = tenant_isolation
        self.lock_timeout_ms = lock_timeout_ms
        self.recovery_enabled = recovery_enabled
        self.multi_device_sync = multi_device_sync


class SessionEngine:
    """
    Core Session Persistence Engine.
    
    Manages the complete lifecycle of sessions including:
    - Creation and initialization
    - Periodic auto-save with snapshots
    - Idle timeout and expiration handling
    - Crash recovery and state restoration
    - Multi-device synchronization
    - Background cleanup
    """
    
    def __init__(
        self,
        repository: TieredRepository,
        event_bus: EventBus,
        recovery_engine: RecoveryEngine,
        config: SessionPersistenceConfig
    ) -> None:
        self.repo = repository
        self.events = event_bus
        self.recovery = recovery_engine
        self.config = config
        
        # In-memory session cache for active sessions
        self._active_sessions: Dict[str, SessionState] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._save_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Serializer
        self.serializer = SessionSerializer(
            encryption_key=config.encryption_key,
            compression=CompressionAlgorithm.GZIP if config.enable_compression else CompressionAlgorithm.NONE
        )
    
    async def start(self) -> None:
        """Start the session engine background tasks."""
        self._running = True
        
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(
            self._background_cleanup(),
            name="session-cleanup"
        )
        
        # Load active sessions from repository
        active = await self.repo.list_active(limit=1000)
        for session in active:
            self._active_sessions[session.session_id] = session
            if self.config.enable_background_save:
                self._start_auto_save(session.session_id)
        
        logger.info(f"Session engine started with {len(active)} active sessions")
    
    async def stop(self) -> None:
        """Gracefully stop the session engine."""
        self._running = False
        
        # Cancel all auto-save tasks
        for task in self._save_tasks.values():
            task.cancel()
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Final save of all active sessions
        save_tasks = [
            self._force_save(session_id)
            for session_id in list(self._active_sessions.keys())
        ]
        if save_tasks:
            await asyncio.gather(*save_tasks, return_exceptions=True)
        
        logger.info("Session engine stopped")
    
    async def create_session(
        self,
        tenant_id: str,
        owner_id: str,
        configuration: Optional[Dict[str, Any]] = None,
        parent_session_id: Optional[str] = None
    ) -> SessionState:
        """
        Create a new persistent session.
        """
        config = configuration or {}
        
        # Initialize session state
        session = SessionState(
            tenant_id=tenant_id,
            owner_id=owner_id,
            parent_session_id=parent_session_id,
            status=SessionStatus.CREATED,
            agent_memory=AgentMemory(agent_id=str(uuid.uuid4())),
            execution_plan=ExecutionPlan(
                goal=config.get("goal", ""),
                strategy=config.get("strategy", "default")
            ),
            environment=EnvironmentConfig(
                variables=config.get("env", {}),
                resource_alloc=config.get("resources", {})
            ),
            expires_at=datetime.utcnow() + timedelta(
                seconds=self.config.absolute_timeout
            ) if self.config.absolute_timeout else None,
            idle_timeout_seconds=self.config.idle_timeout,
            metadata=config.get("metadata", {})
        )
        
        # Acquire lock
        lock = SessionLock(
            session_id=session.session_id,
            lock_type=LockType.EXCLUSIVE,
            owner=owner_id,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        acquired = await self.repo.acquire_lock(lock, self.config.lock_timeout_ms)
        if not acquired:
            raise SessionOperationError("Failed to acquire initial session lock")
        
        session.lock = lock
        
        # Save to repository
        await self.repo.save(session)
        
        # Cache in memory
        self._active_sessions[session.session_id] = session
        self._session_locks[session.session_id] = asyncio.Lock()
        
        # Emit event
        await self.events.publish(SessionCreated(
            event_type="session.created",
            session_id=session.session_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            initial_status=session.status,
            configuration=config
        ))
        
        # Audit log
        await self.repo.audit_log(AuditRecord(
            session_id=session.session_id,
            tenant_id=tenant_id,
            user_id=owner_id,
            action="session.create",
            resource=f"session/{session.session_id}",
            success=True,
            details={"parent_session": parent_session_id}
        ))
        
        # Start auto-save
        if self.config.enable_background_save:
            self._start_auto_save(session.session_id)
        
        logger.info(f"Created session {session.session_id} for tenant {tenant_id}")
        return session
    
    async def get_session(
        self,
        session_id: str,
        for_mutation: bool = False
    ) -> Optional[SessionState]:
        """
        Get session by ID. Optionally acquire lock for mutation.
        """
        # Check memory cache first
        session = self._active_sessions.get(session_id)
        
        if not session:
            # Load from repository
            session = await self.repo.get(session_id)
            if session:
                self._active_sessions[session_id] = session
                if session_id not in self._session_locks:
                    self._session_locks[session_id] = asyncio.Lock()
        
        if not session:
            return None
        
        # Check expiration
        if session.is_expired():
            await self._handle_expiration(session)
            raise SessionExpiredError(f"Session {session_id} has expired")
        
        if for_mutation:
            # Acquire exclusive lock
            lock = SessionLock(
                session_id=session_id,
                lock_type=LockType.EXCLUSIVE,
                owner="engine",
                expires_at=datetime.utcnow() + timedelta(minutes=5)
            )
            acquired = await self.repo.acquire_lock(lock, self.config.lock_timeout_ms)
            if not acquired:
                raise SessionOperationError(f"Could not acquire lock for session {session_id}")
            session.lock = lock
        
        session.touch()
        return session
    
    async def update_session(
        self,
        session_id: str,
        mutation: Callable[[SessionState], None],
        save: bool = True
    ) -> SessionState:
        """
        Apply a mutation to session state with automatic versioning and save.
        """
        async with self._session_locks.get(session_id, asyncio.Lock()):
            session = await self.get_session(session_id, for_mutation=True)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            
            # Apply mutation
            previous_version = session.version
            mutation(session)
            session.bump_version()
            
            # Emit state mutation event
            await self.events.publish(StateMutated(
                event_type="state.mutated",
                session_id=session_id,
                tenant_id=session.tenant_id,
                mutation_type="update",
                path="session",
                previous_value={"version": previous_version},
                new_value={"version": session.version}
            ))
            
            # Save if requested
            if save:
                await self._save_session(session)
            
            return session
    
    async def activate_session(self, session_id: str) -> SessionState:
        """Transition session to active state."""
        session = await self.update_session(
            session_id,
            lambda s: setattr(s, 'status', SessionStatus.ACTIVE)
        )
        
        await self.events.publish(SessionActivated(
            event_type="session.activated",
            session_id=session_id,
            tenant_id=session.tenant_id,
            previous_status=SessionStatus.INITIALIZING,
            activated_by=session.owner_id
        ))
        
        return session
    
    async def pause_session(
        self,
        session_id: str,
        reason: str,
        paused_by: Optional[str] = None
    ) -> SessionState:
        """Pause session execution."""
        session = await self.update_session(
            session_id,
            lambda s: setattr(s, 'status', SessionStatus.PAUSED)
        )
        
        await self.events.publish(SessionPaused(
            event_type="session.paused",
            session_id=session_id,
            tenant_id=session.tenant_id,
            reason=reason,
            paused_by=paused_by
        ))
        
        # Save immediately on pause
        await self._save_session(session)
        
        return session
    
    async def resume_session(
        self,
        session_id: str,
        resumed_by: str
    ) -> SessionState:
        """Resume a paused or suspended session."""
        session = await self.get_session(session_id, for_mutation=True)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        from_status = session.status
        
        if from_status == SessionStatus.SUSPENDED:
            # May need recovery
            if self.config.recovery_enabled:
                session, _ = await self.recovery.execute_recovery(
                    session,
                    recovery_type=RecoveryType.AUTOMATIC
                )
        
        session.status = SessionStatus.ACTIVE
        session.touch()
        await self._save_session(session)
        
        await self.events.publish(SessionResumed(
            event_type="session.resumed",
            session_id=session_id,
            tenant_id=session.tenant_id,
            from_status=from_status,
            resumed_by=resumed_by
        ))
        
        return session
    
    async def complete_session(
        self,
        session_id: str,
        result: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        """Mark session as completed."""
        session = await self.update_session(
            session_id,
            lambda s: setattr(s, 'status', SessionStatus.COMPLETED)
        )
        
        # Final save
        await self._save_session(session)
        
        # Create final snapshot
        await self._create_snapshot(session, "completion")
        
        # Clean up in-memory
        self._active_sessions.pop(session_id, None)
        self._cancel_auto_save(session_id)
        
        await self.events.publish(SessionCompleted(
            event_type="session.completed",
            session_id=session_id,
            tenant_id=session.tenant_id,
            completion_result=result or {}
        ))
        
        # Release lock
        if session.lock:
            await self.repo.release_lock(session.lock.lock_id)
        
        return session
    
    async def fail_session(
        self,
        session_id: str,
        error: Exception,
        fatal: bool = False
    ) -> SessionState:
        """Mark session as failed."""
        session = await self.update_session(
            session_id,
            lambda s: setattr(s, 'status', SessionStatus.FAILED)
        )
        
        session.metadata["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "fatal": fatal
        }
        
        await self._save_session(session)
        
        # Attempt recovery if not fatal
        if not fatal and self.config.recovery_enabled:
            try:
                recovered, log = await self.recovery.execute_recovery(
                    session,
                    recovery_type=RecoveryType.AUTOMATIC
                )
                if log.success:
                    return recovered
            except RecoveryError as e:
                logger.error(f"Auto-recovery failed for {session_id}: {e}")
        
        await self.events.publish(SessionFailed(
            event_type="session.failed",
            session_id=session_id,
            tenant_id=session.tenant_id,
            error_type=type(error).__name__,
            error_message=str(error),
            fatal=fatal
        ))
        
        return session
    
    async def recover_session(
        self,
        session_id: str,
        recovery_type_str: str = "automatic"
    ) -> SessionState:
        """
        Manually trigger recovery for a session.
        """
        from session_recovery import RecoveryType
        
        session = await self.get_session(session_id, for_mutation=True)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        recovery_type = RecoveryType(recovery_type_str)
        
        recovered, log = await self.recovery.execute_recovery(
            session,
            recovery_type=recovery_type
        )
        
        if log.success:
            self._active_sessions[session_id] = recovered
            await self._save_session(recovered)
        
        return recovered
    
    async def connect_device(
        self,
        session_id: str,
        device: DeviceConnection
    ) -> SessionState:
        """Connect a new device to session."""
        async with self._session_locks.get(session_id, asyncio.Lock()):
            session = await self.get_session(session_id)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            
            # Check for existing device
            existing = next(
                (d for d in session.workspace.active_devices if d.device_id == device.device_id),
                None
            )
            
            if existing:
                # Reconnect
                session.workspace.active_devices.remove(existing)
                await self.events.publish(DeviceReconnected(
                    event_type="device.reconnected",
                    session_id=session_id,
                    tenant_id=session.tenant_id,
                    device_id=device.device_id,
                    previous_connection_id=existing.connection_id
                ))
            
            session.workspace.active_devices.append(device)
            session.touch()
            
            await self.events.publish(DeviceConnected(
                event_type="device.connected",
                session_id=session_id,
                tenant_id=session.tenant_id,
                device=device
            ))
            
            await self._save_session(session)
            return session
    
    async def disconnect_device(
        self,
        session_id: str,
        device_id: str,
        reason: str = "client_disconnect"
    ) -> SessionState:
        """Disconnect a device from session."""
        async with self._session_locks.get(session_id, asyncio.Lock()):
            session = await self.get_session(session_id)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            
            session.workspace.active_devices = [
                d for d in session.workspace.active_devices
                if d.device_id != device_id
            ]
            
            await self.events.publish(DeviceDisconnected(
                event_type="device.disconnected",
                session_id=session_id,
                tenant_id=session.tenant_id,
                device_id=device_id,
                disconnect_reason=reason
            ))
            
            # If no devices remain, consider pausing
            if not session.workspace.active_devices:
                logger.info(f"Session {session_id} has no connected devices")
            
            session.touch()
            await self._save_session(session)
            return session
    
    async def _save_session(
        self,
        session: SessionState,
        trigger: str = "auto"
    ) -> None:
        """Persist session to all storage tiers."""
        start_time = time.time()
        
        # Serialize
        serialized = self.serializer.serialize(session)
        
        # Save to repository
        await self.re
