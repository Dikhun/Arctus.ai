"""
session_models.py
Core domain models for the Session Persistence Engine.
Fully typed Pydantic models with enterprise-grade validation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union
from enum import auto

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionStatus(str, enum.Enum):
    """Lifecycle states of an orchestration session."""
    CREATED = "created"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CLEANED = "cleaned"


class AgentStatus(str, enum.Enum):
    """Status of an agent within a session."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    ERROR = "error"
    RECOVERING = "recovering"


class SubtaskStatus(str, enum.Enum):
    """Status of individual subtasks."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class RecoveryType(str, enum.Enum):
    """Types of recovery operations."""
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    FORCED = "forced"


class LockType(str, enum.Enum):
    """Types of session locks."""
    EXCLUSIVE = "exclusive"
    SHARED = "shared"
    MAINTENANCE = "maintenance"


class SessionLock(BaseModel):
    """Distributed lock for session coordination."""
    model_config = ConfigDict(frozen=True)
    
    lock_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    lock_type: LockType
    owner: str
    acquired_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentMemory(BaseModel):
    """Persistent agent memory snapshot."""
    model_config = ConfigDict(extra="allow")
    
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    short_term: List[Dict[str, Any]] = Field(default_factory=list)
    long_term_refs: List[str] = Field(default_factory=list)  # References to vector DB
    working_memory: Dict[str, Any] = Field(default_factory=dict)
    context_window: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class ExecutionPlan(BaseModel):
    """Serializable execution plan state."""
    model_config = ConfigDict(extra="allow")
    
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    goal: str
    strategy: str
    stages: List[PlanStage] = Field(default_factory=list)
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStage(BaseModel):
    """Individual stage within an execution plan."""
    stage_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    status: SubtaskStatus = SubtaskStatus.QUEUED
    subtasks: List[Subtask] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3


class Subtask(BaseModel):
    """Individual subtask within a stage."""
    subtask_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    status: SubtaskStatus = SubtaskStatus.QUEUED
    agent_id: Optional[str] = None
    vm_id: Optional[str] = None
    browser_id: Optional[str] = None
    terminal_id: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    checkpoint_data: Optional[Dict[str, Any]] = None


class VMStateRef(BaseModel):
    """Reference to VM state stored externally."""
    vm_id: str
    snapshot_id: Optional[str] = None
    state_bucket: str
    state_key: str
    last_synced: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BrowserStateRef(BaseModel):
    """Reference to browser automation state."""
    browser_id: str
    session_storage_key: Optional[str] = None
    local_storage_snapshot: Optional[str] = None
    cookie_jar_ref: Optional[str] = None
    page_states: List[Dict[str, Any]] = Field(default_factory=list)
    last_synced: datetime = Field(default_factory=datetime.utcnow)


class TerminalStateRef(BaseModel):
    """Reference to terminal/shell state."""
    terminal_id: str
    session_log_key: Optional[str] = None
    cwd: Optional[str] = None
    env_snapshot: Optional[str] = None
    command_history_ref: Optional[str] = None
    last_synced: datetime = Field(default_factory=datetime.utcnow)


class FilesystemMetadata(BaseModel):
    """Metadata for persisted filesystem state."""
    fs_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_path: str
    file_tree_hash: str
    uploaded_files: List[FileRef] = Field(default_factory=list)
    generated_artifacts: List[FileRef] = Field(default_factory=list)
    last_synced: datetime = Field(default_factory=datetime.utcnow)


class FileRef(BaseModel):
    """Reference to a persisted file."""
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_name: str
    storage_key: str
    size_bytes: int
    mime_type: Optional[str] = None
    checksum: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class EnvironmentConfig(BaseModel):
    """Environment variables and resource allocation."""
    env_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    variables: Dict[str, str] = Field(default_factory=dict)
    secrets_refs: Dict[str, str] = Field(default_factory=dict)  # References to secret store
    resource_alloc: ResourceAllocation = Field(default_factory=lambda: ResourceAllocation())
    network_config: Dict[str, Any] = Field(default_factory=dict)


class ResourceAllocation(BaseModel):
    """Resource allocation for session."""
    cpu_cores: Optional[float] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[int] = None
    gpu_units: Optional[int] = None
    timeout_seconds: Optional[int] = None


class ConversationState(BaseModel):
    """Persisted conversation/message state."""
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[Message] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_message_at: Optional[datetime] = None


class Message(BaseModel):
    """Individual message in conversation."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # user, assistant, system, agent
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceState(BaseModel):
    """Shared workspace state for multi-device access."""
    workspace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    active_devices: List[DeviceConnection] = Field(default_factory=list)
    layout_state: Dict[str, Any] = Field(default_factory=dict)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    collaboration_state: Dict[str, Any] = Field(default_factory=dict)


class DeviceConnection(BaseModel):
    """Connected device information."""
    device_id: str
    connection_id: str
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    device_type: str  # browser, api, cli, mobile
    ip_address: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)


class SessionSnapshot(BaseModel):
    """Point-in-time snapshot of session state."""
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    trigger: str  # periodic, manual, pre-checkpoint, pre-migration
    state_hash: str
    compressed_size_bytes: Optional[int] = None
    storage_key: Optional[str] = None  # S3 key if offloaded


class RecoveryLog(BaseModel):
    """Log of recovery operations."""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    recovery_type: RecoveryType
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None
    from_snapshot_id: Optional[str] = None
    to_version: Optional[int] = None
    errors: List[str] = Field(default_factory=list)
    validation_results: Dict[str, bool] = Field(default_factory=dict)


class AuditRecord(BaseModel):
    """Security audit record."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    tenant_id: str
    user_id: Optional[str] = None
    action: str
    resource: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    success: bool = True
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SessionState(BaseModel):
    """
    Complete session state - the primary aggregate root.
    This is the object that gets serialized, encrypted, and persisted.
    """
    model_config = ConfigDict(extra="allow")
    
    # Identity
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    owner_id: str
    parent_session_id: Optional[str] = None
    
    # Lifecycle
    status: SessionStatus = SessionStatus.CREATED
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    idle_timeout_seconds: int = 3600  # 1 hour default
    
    # State components
    agent_memory: AgentMemory
    execution_plan: ExecutionPlan
    running_subtasks: List[Subtask] = Field(default_factory=list)
    queued_subtasks: List[Subtask] = Field(default_factory=list)
    vm_state: Optional[VMStateRef] = None
    browser_state: Optional[BrowserStateRef] = None
    terminal_state: Optional[TerminalStateRef] = None
    filesystem: Optional[FilesystemMetadata] = None
    environment: EnvironmentConfig = Field(default_factory=lambda: EnvironmentConfig())
    conversation: ConversationState = Field(default_factory=lambda: ConversationState())
    workspace: WorkspaceState = Field(default_factory=lambda: WorkspaceState())
    
    # Recovery
    snapshots: List[SessionSnapshot] = Field(default_factory=list)
    recovery_logs: List[RecoveryLog] = Field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    
    # Lock (not persisted, loaded at runtime)
    lock: Optional[SessionLock] = None
    
    @field_validator('expires_at')
    @classmethod
    def validate_expiration(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v < datetime.utcnow():
            raise ValueError("Expiration must be in the future")
        return v
    
    def is_active(self) -> bool:
        """Check if session is in an active state."""
        return self.status in {
            SessionStatus.ACTIVE,
            SessionStatus.INITIALIZING,
            SessionStatus.RECOVERING
        }
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at and self.expires_at < datetime.utcnow():
            return True
        idle_time = (datetime.utcnow() - self.last_activity_at).total_seconds()
        return idle_time > self.idle_timeout_seconds
    
    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_at = datetime.utcnow()
    
    def bump_version(self) -> None:
        """Increment version on mutation."""
        self.version += 1
        self.updated_at = datetime.utcnow()
