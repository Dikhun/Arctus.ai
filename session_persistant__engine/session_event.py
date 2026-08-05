"""
session_events.py
Event-driven architecture for the Session Persistence Engine.
Implements domain events for CQRS and event sourcing patterns.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, Awaitable

from pydantic import BaseModel, ConfigDict, Field

from session_models import (
    SessionState, SessionStatus, SessionLock, RecoveryLog,
    Subtask, AgentMemory, ExecutionPlan, ConversationState,
    DeviceConnection, SessionSnapshot
)


class EventPriority(int, enum.Enum):
    """Priority levels for event processing."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class DomainEvent(BaseModel):
    """Base class for all domain events."""
    model_config = ConfigDict(extra="allow")
    
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    session_id: str
    tenant_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1  # Event version for schema evolution
    priority: EventPriority = EventPriority.NORMAL
    metadata: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None  # For distributed tracing
    causation_id: Optional[str] = None  # Previous event that caused this


# --- Session Lifecycle Events ---

class SessionCreated(DomainEvent):
    """Emitted when a new session is created."""
    event_type: str = "session.created"
    owner_id: str
    initial_status: SessionStatus
    configuration: Dict[str, Any] = Field(default_factory=dict)


class SessionActivated(DomainEvent):
    """Session transitioned to active state."""
    event_type: str = "session.activated"
    previous_status: SessionStatus
    activated_by: str


class SessionPaused(DomainEvent):
    """Session paused (e.g., user-initiated)."""
    event_type: str = "session.paused"
    reason: str
    paused_by: Optional[str] = None


class SessionSuspended(DomainEvent):
    """Session suspended (e.g., infrastructure issue)."""
    event_type: str = "session.suspended"
    reason: str
    expected_resume: Optional[datetime] = None


class SessionResumed(DomainEvent):
    """Session resumed from paused/suspended state."""
    event_type: str = "session.resumed"
    from_status: SessionStatus
    resumed_by: str


class SessionCompleted(DomainEvent):
    """Session completed successfully."""
    event_type: str = "session.completed"
    completion_result: Dict[str, Any] = Field(default_factory=dict)


class SessionFailed(DomainEvent):
    """Session failed."""
    event_type: str = "session.failed"
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    fatal: bool = False


class SessionExpired(DomainEvent):
    """Session expired due to timeout."""
    event_type: str = "session.expired"
    expiry_reason: str  # idle_timeout, absolute_timeout, forced


class SessionCleaned(DomainEvent):
    """Session resources cleaned up."""
    event_type: str = "session.cleaned"
    cleanup_reason: str


# --- State Mutation Events ---

class StateMutated(DomainEvent):
    """Generic state mutation event."""
    event_type: str = "state.mutated"
    mutation_type: str
    path: str  # JSON path to mutated field
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None


class AgentMemoryUpdated(DomainEvent):
    """Agent memory state changed."""
    event_type: str = "agent.memory_updated"
    agent_id: str
    memory_delta: Dict[str, Any]
    memory_version: int


class ExecutionPlanUpdated(DomainEvent):
    """Execution plan modified."""
    event_type: str = "execution.plan_updated"
    plan_id: str
    plan_version: int
    changes: List[str]  # List of changed field paths


class SubtaskStarted(DomainEvent):
    """Subtask execution started."""
    event_type: str = "subtask.started"
    subtask_id: str
    stage_id: str
    assigned_agent: Optional[str] = None
    assigned_vm: Optional[str] = None


class SubtaskCompleted(DomainEvent):
    """Subtask finished execution."""
    event_type: str = "subtask.completed"
    subtask_id: str
    stage_id: str
    result_summary: Dict[str, Any] = Field(default_factory=dict)


class SubtaskFailed(DomainEvent):
    """Subtask execution failed."""
    event_type: str = "subtask.failed"
    subtask_id: str
    stage_id: str
    error: Dict[str, Any]
    will_retry: bool = False


# --- Persistence Events ---

class SessionSaved(DomainEvent):
    """Session successfully persisted."""
    event_type: str = "session.saved"
    snapshot_id: Optional[str] = None
    storage_tier: str  # hot, warm, cold
    save_duration_ms: float
    size_bytes: int


class SessionLoaded(DomainEvent):
    """Session loaded from persistence."""
    event_type: str = "session.loaded"
    from_snapshot_id: Optional[str] = None
    load_duration_ms: float
    version_loaded: int


class SnapshotCreated(DomainEvent):
    """Point-in-time snapshot created."""
    event_type: str = "snapshot.created"
    snapshot: SessionSnapshot


class SnapshotRestored(DomainEvent):
    """Snapshot restored as active state."""
    event_type: str = "snapshot.restored"
    snapshot_id: str
    restored_by: str


# --- Recovery Events ---

class RecoveryInitiated(DomainEvent):
    """Recovery process started."""
    event_type: str = "recovery.initiated"
    recovery_type: str
    from_version: int
    target_version: Optional[int] = None
    recovery_plan: Dict[str, Any] = Field(default_factory=dict)


class RecoveryCompleted(DomainEvent):
    """Recovery process finished."""
    event_type: str = "recovery.completed"
    recovery_id: str
    success: bool
    final_version: int
    duration_ms: float


class RecoveryValidated(DomainEvent):
    """Recovery validation completed."""
    event_type: str = "recovery.validated"
    recovery_id: str
    validation_passed: bool
    checks: Dict[str, bool]


# --- Security Events ---

class SessionLocked(DomainEvent):
    """Session lock acquired."""
    event_type: str = "session.locked"
    lock: SessionLock


class SessionUnlocked(DomainEvent):
    """Session lock released."""
    event_type: str = "session.unlocked"
    lock_id: str
    held_duration_seconds: float


class OwnershipValidated(DomainEvent):
    """Session ownership validated."""
    event_type: str = "session.ownership_validated"
    user_id: str
    validation_method: str


class AuditEventLogged(DomainEvent):
    """Audit record created."""
    event_type: str = "audit.event_logged"
    action: str
    resource: str
    success: bool


# --- Device/Connection Events ---

class DeviceConnected(DomainEvent):
    """New device connected to session."""
    event_type: str = "device.connected"
    device: DeviceConnection


class DeviceDisconnected(DomainEvent):
    """Device disconnected from session."""
    event_type: str = "device.disconnected"
    device_id: str
    disconnect_reason: str


class DeviceReconnected(DomainEvent):
    """Device reconnected after disconnect."""
    event_type: str = "device.reconnected"
    device_id: str
    previous_connection_id: str


# --- Event Bus ---

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """
    In-memory event bus for session domain events.
    Production use would integrate with Redis Streams, Kafka, or NATS.
    """
    
    def __init__(self) -> None:
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
    
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events."""
        self._global_handlers.append(handler)
    
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a subscription."""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
    
    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers."""
        handlers = self._handlers.get(event.event_type, []).copy()
        handlers.extend(self._global_handlers)
        
        # Execute handlers concurrently for performance
        import asyncio
        if handlers:
            await asyncio.gather(
                *[self._safe_invoke(h, event) for h in handlers],
                return_exceptions=True
            )
    
    async def _safe_invoke(self, handler: EventHandler, event: DomainEvent) -> None:
        """Invoke handler with error isolation."""
        try:
            await handler(event)
        except Exception as e:
            # Log but don't fail - event bus should be resilient
            print(f"Event handler failed for {event.event_type}: {e}")
    
    def create_event(
        self,
        event_class: type,
        session_id: str,
        tenant_id: str,
        **kwargs: Any
    ) -> DomainEvent:
        """Factory method to create events with common fields populated."""
        return event_class(
            session_id=session_id,
            tenant_id=tenant_id,
            **kwargs
  )
