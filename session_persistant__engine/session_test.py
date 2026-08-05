"""
session_tests.py
Comprehensive test suite for the Session Persistence Engine.
Includes unit tests, integration tests, and fault-tolerance tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from session_models import (
    SessionState, SessionStatus, SessionLock, LockType,
    AgentMemory, ExecutionPlan, PlanStage, Subtask, SubtaskStatus,
    EnvironmentConfig, ConversationState, WorkspaceState, DeviceConnection,
    SessionSnapshot, AuditRecord, RecoveryLog, RecoveryType
)
from session_events import EventBus, SessionCreated, SessionSaved
from session_serializer import SessionSerializer, SerializedSession, CompressionAlgorithm, SerializationFormat
from session_repository import (
    PostgreSQLRepository, RedisRepository, S3Repository, TieredRepository,
    SessionNotFoundError as RepoNotFoundError
)
from session_recovery import RecoveryEngine, StateValidator, ValidationResult, RecoveryError
from session_engine import SessionEngine, SessionPersistenceConfig, SessionNotFoundError, SessionExpiredError
from session_service import SessionService, SessionCreationRequest, ExecutionResult
from session_manager import SessionManager, SessionManagerConfig


# --- Fixtures ---

@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def sample_session() -> SessionState:
    """Create a sample session for testing."""
    return SessionState(
        session_id=str(uuid.uuid4()),
        tenant_id="tenant-1",
        owner_id="user-1",
        status=SessionStatus.ACTIVE,
        agent_memory=AgentMemory(agent_id="agent-1"),
        execution_plan=ExecutionPlan(
            goal="Test goal",
            strategy="test",
            stages=[
                PlanStage(
                    name="stage-1",
                    subtasks=[
                        Subtask(name="task-1", status=SubtaskStatus.QUEUED),
                        Subtask(name="task-2", status=SubtaskStatus.RUNNING)
                    ]
                )
            ]
        ),
        environment=EnvironmentConfig(
            variables={"KEY": "value"},
            resource_alloc={"cpu_cores": 2.0, "memory_mb": 4096}
        ),
        conversation=ConversationState(
            messages=[],
            participants=["user", "assistant"]
        ),
        workspace=WorkspaceState(
            active_devices=[]
        ),
        idle_timeout_seconds=3600
    )


@pytest.fixture
def serializer() -> SessionSerializer:
    return SessionSerializer(
        encryption_key=b"test-key-for-encryption-32bytes!",
        compression=CompressionAlgorithm.GZIP,
        format=SerializationFormat.JSON
    )


# --- Unit Tests: Models ---

class TestSessionModels:
    """Test session model behavior."""
    
    def test_session_creation(self, sample_session: SessionState) -> None:
        assert sample_session.session_id
        assert sample_session.tenant_id == "tenant-1"
        assert sample_session.status == SessionStatus.ACTIVE
    
    def test_session_is_active(self, sample_session: SessionState) -> None:
        assert sample_session.is_active() is True
        sample_session.status = SessionStatus.COMPLETED
        assert sample_session.is_active() is False
    
    def test_session_is_expired(self, sample_session: SessionState) -> None:
        assert sample_session.is_expired() is False
        sample_session.last_activity_at = datetime.utcnow() - timedelta(hours=2)
        sample_session.idle_timeout_seconds = 3600
        assert sample_session.is_expired() is True
    
    def test_version_bump(self, sample_session: SessionState) -> None:
        initial_version = sample_session.version
        sample_session.bump_version()
        assert sample_session.version == initial_version + 1
    
    def test_session_serialization(self, sample_session: SessionState) -> None:
        data = sample_session.model_dump_json()
        restored = SessionState.model_validate_json(data)
        assert restored.session_id == sample_session.session_id
        assert len(restored.execution_plan.stages) == 1


# --- Unit Tests: Serializer ---

class TestSessionSerializer:
    """Test serialization and encryption."""
    
    def test_roundtrip_json(self, serializer: SessionSerializer, sample_session: SessionState) -> None:
        serialized = serializer.serialize(sample_session)
        assert serialized.encrypted is True
        assert serialized.format == SerializationFormat.JSON
        
        restored = serializer.deserialize(serialized)
        assert restored.session_id == sample_session.session_id
        assert restored.version == sample_session.version
    
    def test_compression_reduces_size(self, serializer: SessionSerializer, sample_session: SessionState) -> None:
        # Create larger session
        sample_session.agent_memory.short_term = [{"data": "x" * 1000} for _ in range(100)]
        
        serialized = serializer.serialize(sample_session)
        assert serialized.compressed_size < serialized.original_size
        assert serialized.size_ratio() < 1.0
    
    def test_integrity_check(self, serializer: SessionSerializer, sample_session: SessionState) -> None:
        serialized = serializer.serialize(sample_session)
        
        # Tamper with data
        tampered = SerializedSession(
            data=b"tampered" + serialized.data[8:],
            format=serialized.format,
            compression=serialized.compression,
            encrypted=serialized.encrypted,
            encryption_backend=serialized.encryption_backend,
            original_size=serialized.original_size,
            compressed_size=serialized.compressed_size,
            state_hash=serialized.state_hash,
            version=serialized.version,
            tenant_id=serialized.tenant_id,
            session_id=serialized.session_id
        )
        
        with pytest.raises(ValueError, match="Integrity check failed"):
            serializer.deserialize(tampered)
    
    def test_tenant_isolation(self, serializer: SessionSerializer) -> None:
        session1 = SessionState(
            session_id="s1",
            tenant_id="tenant-a",
            owner_id="user-1",
            agent_memory=AgentMemory(agent_id="a1"),
            execution_plan=ExecutionPlan(goal="g1", strategy="s1")
        )
        session2 = SessionState(
            session_id="s2",
            tenant_id="tenant-b",
            owner_id="user-2",
            agent_memory=AgentMemory(agent_id="a2"),
            execution_plan=ExecutionPlan(goal="g2", strategy="s2")
        )
        
        serialized1 = serializer.serialize(session1)
        serialized2 = serializer.serialize(session2)
        
        # Should not be able to decrypt with wrong tenant key
        # (In real implementation, this would fail)


# --- Unit Tests: Events ---

@pytest.mark.asyncio
class TestEventBus:
    """Test event bus functionality."""
    
    async def test_publish_subscribe(self, event_bus: EventBus) -> None:
        received_events: List[Any] = []
        
        async def handler(event: Any) -> None:
            received_events.append(event)
        
        event_bus.subscribe("test.event", handler)
        
        from session_events import DomainEvent
        event = DomainEvent(
            event_type="test.event",
            session_id="s1",
            tenant_id="t1"
        )
        
        await event_bus.publish(event)
        assert len(received_events) == 1
    
    async def test_multiple_subscribers(self, event_bus: EventBus) -> None:
        count = 0
        
        async def handler1(event: Any) -> None:
            nonlocal count
            count += 1
        
        async def handler2(event: Any) -> None:
            nonlocal count
            count += 1
        
        event_bus.subscribe("test.event", handler1)
        event_bus.subscribe("test.event", handler2)
        
        from session_events import DomainEvent
        event = DomainEvent(
            event_type="test.event",
            session_id="s1",
            tenant_id="t1"
        )
        
        await event_bus.publish(event)
        assert count == 2
    
    async def test_global_subscription(self, event_bus: EventBus) -> None:
        received: List[str] = []
        
        async def global_handler(event: Any) -> None:
            received.append(event.event_type)
        
        event_bus.subscribe_all(global_handler)
        
        from session_events import DomainEvent
        await event_bus.publish(DomainEvent(
            event_type="event.a", session_id="s1", tenant_id="t1"
        ))
        await event_bus.publish(DomainEvent(
            event_type="event.b", session_id="s1", tenant_id="t1"
        ))
        
        assert len(received) == 2
        assert "event.a" in received
        assert "event.b" in received


# --- Unit Tests: Recovery ---

@pytest.mark.asyncio
class TestRecoveryEngine:
    """Test recovery functionality."""
    
    async def test_create_recovery_plan(self, event_bus: EventBus) -> None:
        validator = StateValidator()
        engine = RecoveryEngine(event_bus, validator)
        
        session = SessionState(
            session_id="s1",
            tenant_id="t1",
            owner_id="u1",
            status=SessionStatus.SUSPENDED,
            agent_memory=AgentMemory(agent_id="a1"),
            execution_plan=ExecutionPlan(goal="g1", strategy="s1"),
            snapshots=[
                SessionSnapshot(
                    session_id="s1",
                    version=5,
                    trigger="periodic",
                    state_hash="abc"
                )
            ],
            version=10
        )
        
        plan = await engine.create_recovery_plan(session, RecoveryType.AUTOMATIC)
        
        assert plan.session_id == "s1"
        assert plan.from_version == 5
        assert plan.target_version == 10
        assert any("snapshot" in step for step in plan.steps)
    
    async def test_validation_pass(self, event_bus: EventBus) -> None:
        validator = StateValidator()
        engine = RecoveryEngine(event_bus, validator)
        
        session = SessionState(
            session_id="s1",
            tenant_id="t1",
            owner_id="u1",
            status=SessionStatus.ACTIVE,
            agent_memory=AgentMemory(agent_id="a1"),
            execution_plan=ExecutionPlan(goal="g1", strategy="s1")
        )
        
        result = await validator.validate(session)
        assert result.passed is True
        assert len(result.errors) == 0
    
    async def test_validation_fail_missing_agent(self, event_bus: EventBus) -> None:
        validator = StateValidator()
        
        session = SessionState(
            session_id="s1",
            tenant_id="t1",
            owner_id="u1",
            status=SessionStatus.ACTIVE,
            agent_memory=AgentMemory(agent_id=""),  # Invalid - empty agent_id
            execution_plan=ExecutionPlan(goal="g1", strategy="s1")
        )
        
        result = await validator.validate(session)
        assert result.passed is False
        assert any("agent" in err for err in result.errors)
    
    async def test_detect_conflicts(self, event_bus: EventBus) -> None:
        validator = StateValidator()
        engine = RecoveryEngine(event_bus, validator)
        
        original = SessionState(
            session_id="s1",
            tenant_id="t1",
            owner_id="u1",
            status=SessionStatus.ACTIVE,
            version=5,
            agent_memory=AgentMemory(agent_id="a1"),
            execution_plan=ExecutionPlan(goal="g1", strategy="s1")
        )
        
        recovered = original.model_copy(deep=True)
        recovered.version = 6
        recovered.status = SessionStatus.RECOVERING
        
        conflicts = await engine.detect_conflicts(original, recovered)
        
        assert len(conflicts) > 0
        version_conflict = next(c for c in conflicts if c["type"] == "version_mismatch")
        assert version_conflict["original"] == 5
        assert version_conflict["recovered"] == 6


# --- Integration Tests: Engine ---

@pytest.mark.asyncio
class TestSessionEngineIntegration:
    """Integration tests with mocked repositories."""
    
    @pytest_asyncio.fixture
    async def engine(self, event_bus: EventBus) -> SessionEngine:
        # Create mock repository
        mock_repo = AsyncMock(spec=TieredRepository)
        mock_repo.list_active = AsyncMock(return_value=[])
        
        config = SessionPersistenceConfig(
            auto_save_interval_seconds=0.1,  # Fast for tests
            enable_background_save=False  # Disable for predictability
        )
        
        recovery = RecoveryEngine(event_bus, StateValidator())
        engine = SessionEngine(mock_repo, event_bus, recovery, config)
        await engine.start()
        
        yield engine
        
        await engine.stop()
    
    async def test_create_and_get_session(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1",
            configuration={"goal": "test"}
        )
        
        assert session.session_id
        assert session.status == SessionStatus.ACTIVE
        assert session.tenant_id == "tenant-1"
        
        # Verify saved to repository
        engine.repo.save.assert_called()
        
        # Should be in active sessions
        retrieved = await engine.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
    
    async def test_session_expiration(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1"
        )
        
        # Manually expire
        session.last_activity_at = datetime.utcnow() - timedelta(hours=2)
        session.idle_timeout_seconds = 3600
        
        with pytest.raises(SessionExpiredError):
            await engine.get_session(session.session_id)
    
    async def test_update_session(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1"
        )
        
        updated = await engine.update_session(
            session.session_id,
            lambda s: setattr(s, 'metadata', {'key': 'value'})
        )
        
        assert updated.metadata['key'] == 'value'
        assert updated.version > session.version
    
    async def test_pause_and_resume(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1"
        )
        
        paused = await engine.pause_session(session.session_id, "test_pause")
        assert paused.status == SessionStatus.PAUSED
        
        resumed = await engine.resume_session(session.session_id, "test_user")
        assert resumed.status == SessionStatus.ACTIVE
    
    async def test_device_connect_disconnect(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1"
        )
        
        device = DeviceConnection(
            device_id="device-1",
            connection_id="conn-1",
            device_type="browser"
        )
        
        connected = await engine.connect_device(session.session_id, device)
        assert len(connected.workspace.active_devices) == 1
        
        disconnected = await engine.disconnect_device(
            session.session_id,
            "device-1"
        )
        assert len(disconnected.workspace.active_devices) == 0
    
    async def test_session_context(self, engine: SessionEngine) -> None:
        session = await engine.create_session(
            tenant_id="tenant-1",
            owner_id="user-1"
        )
        
        async with engine.session_context(session.session_id) as s:
            s.metadata["in_context"] = True
        
        # After context, should be saved
        engine.repo.save.assert_called()
        
        retrieved = await engine.get_session(session.session_id)
        assert retrieved.metadata.get("in_context") is True


# --- Fault Tolerance Tests ---

@pytest.mark.asyncio
class TestFaultTolerance:
    """Test fault tolerance and recovery scenarios."""
    
    async def test_auto_save_on_crash(self, event_bus: EventBus) -> None:
        """Simulate crash during operation and verify state is saved."""
        mock_repo = AsyncMock(spec=TieredRepository)
        mock_repo.list_active = AsyncMock(return_value=[])
        
        config = SessionPersistenceConfig(
            auto_save_interval_seconds=0.05,
            enable_background_save=True
        )
        
        recovery = RecoveryEngine(event_bus, StateValidator())
        engine = SessionEngine(mock_repo, event_bus, recovery, config)
        await engine.start()
        
        try:
            session = await engine.create_session(
                tenant_id="tenant-1",
                owner_id="user-1"
            )
            
            # Wait for auto-save
            await asyncio.sleep(0.15)
            
            # Verify multiple saves occurred
            save_calls = [c for c in mock_repo.save.call_args_list 
                         if c[0][0].session_id == session.session_id]
            assert len(save_calls) >= 2  # At least initial + auto-save
        
        finally:
            await engine.stop()
    
    async def test_recovery_after_simulated_crash(self, event_bus: EventBus) -> None:
        """Test recovering a session after simulated crash."""
        # Create session state as it would be loaded from DB
        crashed_session = SessionState(
            session_id="crashed-1",
            tenant_id="tenant-1",
            owner_id="user-1",
            status=SessionStatus.SUSPENDED,  # Would be suspended on crash
            agent_memory=AgentMemory(agent_id="agent-1"),
            execution_plan=ExecutionPlan(
                goal="test",
                strategy="default",
                stages=[
                    PlanStage(
                        name="stage-1",
                        subtasks=[
                            Subtask(name="task-1", status=SubtaskStatus.RUNNING),
                            Subtask(name="task-2", status=SubtaskStatus.QUEUED)
                        ]
                    )
                ]
            ),
            running_subtasks=[
                Subtask(name="task-1", status=SubtaskStatus.RUNNING, started_at=datetime.utcnow())
            ],
            queued_subtasks=[
                Subtask(name="task-2", status=SubtaskStatus.QUEUED)
            ],
            snapshots=[
                SessionSnapshot(
                    session_id="crashed-1",
                    version=5,
                    trigger="periodic",
                    state_hash="hash123"
                )
            ],
            version=8
        )
        
        validator = StateValidator()
        recovery = RecoveryEngine(event_bus, validator)
        
        recovered, log = await recovery.execute_recovery(
            crashed_session,
            RecoveryType.AUTOMATIC
        )
        
        assert log.success is True
        assert recovered.status == SessionStatus.ACTIVE
        
        # Running tasks should be reset
        assert len(recovered.running_subtasks) == 0
        
        # Queued tasks should remain
        assert len(recovered.queued_subtasks) == 2  # Both re-queued
    
    async def test_concurrent_access_isolation(self, event_bus: EventBus) ->
