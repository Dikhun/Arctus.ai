"""
session_service.py
Business service layer providing high-level session operations.
Implements use cases and orchestrates between engine and external systems.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from session_models import (
    SessionState, SessionStatus, DeviceConnection,
    Subtask, SubtaskStatus, Message, AgentMemory
)
from session_engine import SessionEngine, SessionNotFoundError, SessionExpiredError
from session_events import EventBus, DomainEvent


logger = logging.getLogger("session.service")


@dataclass
class SessionCreationRequest:
    """Request to create a new session."""
    tenant_id: str
    owner_id: str
    goal: Optional[str] = None
    strategy: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    resources: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    parent_session_id: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of an execution operation."""
    success: bool
    session_id: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    state_version: int = 0


class SessionService:
    """
    High-level service for session management.
    Provides business operations and integration with other engines.
    """
    
    def __init__(
        self,
        engine: SessionEngine,
        event_bus: EventBus,
        execution_callback: Optional[Callable[[str, Dict], Any]] = None,
        memory_callback: Optional[Callable[[str, Dict], Any]] = None,
        vm_callback: Optional[Callable[[str, Dict], Any]] = None,
        browser_callback: Optional[Callable[[str, Dict], Any]] = None,
        terminal_callback: Optional[Callable[[str, Dict], Any]] = None
    ) -> None:
        self.engine = engine
        self.events = event_bus
        self._execution_callback = execution_callback
        self._memory_callback = memory_callback
        self._vm_callback = vm_callback
        self._browser_callback = browser_callback
        self._terminal_callback = terminal_callback
    
    async def create(self, request: SessionCreationRequest) -> SessionState:
        """Create a new session from request."""
        config = {
            "goal": request.goal or "",
            "strategy": request.strategy or "default",
            "env": request.environment or {},
            "resources": request.resources or {},
            "metadata": request.metadata or {}
        }
        
        session = await self.engine.create_session(
            tenant_id=request.tenant_id,
            owner_id=request.owner_id,
            configuration=config,
            parent_session_id=request.parent_session_id
        )
        
        # Initialize with execution engine if callback provided
        if self._execution_callback:
            await self._execution_callback(
                session.session_id,
                {"action": "initialize", "plan": session.execution_plan.model_dump()}
            )
        
        # Activate
        session = await self.engine.activate_session(session.session_id)
        
        return session
    
    async def submit_task(
        self,
        session_id: str,
        task_description: str,
        task_input: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Submit a task for execution within a session.
        """
        try:
            async with self.engine.session_context(session_id) as session:
                # Add to execution plan
                from session_models import PlanStage
                
                stage = PlanStage(
                    name=f"task_{len(session.execution_plan.stages)}",
                    subtasks=[
                        Subtask(
                            name="execute",
                            description=task_description,
                            input_data=task_input or {}
                        )
                    ]
                )
                session.execution_plan.stages.append(stage)
                session.execution_plan.version += 1
                
                # Queue subtasks
                for subtask in stage.subtasks:
                    session.queued_subtasks.append(subtask)
                
                # Notify execution engine
                if self._execution_callback:
                    result = await self._execution_callback(
                        session_id,
                        {
                            "action": "execute",
                            "stage_id": stage.stage_id,
                            "subtasks": [s.model_dump() for s in stage.subtasks]
                        }
                    )
                    
                    return ExecutionResult(
                        success=True,
                        session_id=session_id,
                        output=result,
                        state_version=session.version
                    )
                
                return ExecutionResult(
                    success=True,
                    session_id=session_id,
                    state_version=session.version
                )
        
        except SessionNotFoundError as e:
            return ExecutionResult(success=False, session_id=session_id, error=str(e))
        except SessionExpiredError as e:
            return ExecutionResult(success=False, session_id=session_id, error=str(e))
    
    async def update_execution_state(
        self,
        session_id: str,
        subtask_id: str,
        status: SubtaskStatus,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        """Update execution state from execution engine."""
        async with self.engine.session_context(session_id) as session:
            # Find and update subtask
            updated = False
            
            # Check running subtasks
            for subtask in session.running_subtasks:
                if subtask.subtask_id == subtask_id:
                    subtask.status = status
                    if output:
                        subtask.output_data = output
                    if error:
                        subtask.error_info = error
                    if status == SubtaskStatus.COMPLETED:
                        subtask.completed_at = datetime.utcnow()
                        session.running_subtasks.remove(subtask)
                    updated = True
                    break
            
            # Check queued subtasks
            if not updated:
                for subtask in session.queued_subtasks:
                    if subtask.subtask_id == subtask_id:
                        subtask.status = status
                        if status == SubtaskStatus.RUNNING:
                            subtask.started_at = datetime.utcnow()
                            session.running_subtasks.append(subtask)
                            session.queued_subtasks.remove(subtask)
                        updated = True
                        break
            
            if not updated:
                logger.warning(f"Subtask {subtask_id} not found in session {session_id}")
            
            return session
    
    async def update_agent_memory(
        self,
        session_id: str,
        memory_delta: Dict[str, Any],
        agent_id: Optional[str] = None
    ) -> SessionState:
        """Update agent memory from memory engine."""
        async with self.engine.session_context(session_id) as session:
            if "short_term" in memory_delta:
                session.agent_memory.short_term.extend(
                    memory_delta["short_term"]
                )
            if "working_memory" in memory_delta:
                session.agent_memory.working_memory.update(
                    memory_delta["working_memory"]
                )
            if "context_window" in memory_delta:
                session.agent_memory.context_window = memory_delta["context_window"]
            
            session.agent_memory.last_updated = datetime.utcnow()
            
            # Notify memory engine
            if self._memory_callback:
                await self._memory_callback(
                    session_id,
                    {"action": "sync", "memory": session.agent_memory.model_dump()}
                )
            
            return session
    
    async def update_vm_state(
        self,
        session_id: str,
        vm_id: str,
        state_reference: Dict[str, Any]
    ) -> SessionState:
        """Update VM state reference."""
        from session_models import VMStateRef
        
        async with self.engine.session_context(session_id) as session:
            session.vm_state = VMStateRef(
                vm_id=vm_id,
                state_bucket=state_reference.get("bucket", ""),
                state_key=state_reference.get("key", ""),
                metadata=state_reference.get("metadata", {})
            )
            
            if self._vm_callback:
                await self._vm_callback(
                    session_id,
                    {"action": "sync", "vm_id": vm_id}
                )
            
            return session
    
    async def update_browser_state(
        self,
        session_id: str,
        browser_id: str,
        page_states: List[Dict[str, Any]]
    ) -> SessionState:
        """Update browser state reference."""
        from session_models import BrowserStateRef
        
        async with self.engine.session_context(session_id) as session:
            session.browser_state = BrowserStateRef(
                browser_id=browser_id,
                page_states=page_states,
                last_synced=datetime.utcnow()
            )
            
            if self._browser_callback:
                await self._browser_callback(
                    session_id,
                    {"action": "sync", "browser_id": browser_id}
                )
            
            return session
    
    async def update_terminal_state(
        self,
        session_id: str,
        terminal_id: str,
        cwd: str,
        env_snapshot: Optional[str] = None
    ) -> SessionState:
        """Update terminal state reference."""
        from session_models import TerminalStateRef
        
        async with self.engine.session_context(session_id) as session:
            session.terminal_state = TerminalStateRef(
                terminal_id=terminal_id,
                cwd=cwd,
                env_snapshot=env_snapshot,
                last_synced=datetime.utcnow()
            )
            
            if self._terminal_callback:
                await self._terminal_callback(
                    session_id,
                    {"action": "sync", "terminal_id": terminal_id}
                )
            
            return session
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        """Add message to conversation."""
        from session_models import Message
        
        async with self.engine.session_context(session_id) as session:
            message = Message(
                role=role,
                content=content,
                metadata=metadata or {}
            )
            session.conversation.messages.append(message)
            session.conversation.last_message_at = datetime.utcnow()
            
            # Update participants
            if role not in session.conversation.participants:
                session.conversation.participants.append(role)
            
            return session
    
    async def reconnect(
        self,
        session_id: str,
        device: DeviceConnection
    ) -> Optional[SessionState]:
        """
        Handle device reconnection to existing session.
        """
        try:
            session = await self.engine.get_session(session_id)
            if not session:
                return None
            
            # Check if session needs recovery
            if session.status == SessionStatus.SUSPENDED:
                session = await self.engine.resume_session(
                    session_id,
                    resumed_by=device.device_id
                )
            
            # Connect device
            session = await self.engine.connect_device(session_id, device)
            
            return session
        
        except SessionExpiredError:
            logger.warning(f"Reconnect failed - session {session_id} expired")
            return None
    
    async def get_dashboard_state(self, session_id: str) -> Dict[str, Any]:
        """Get state for dashboard display."""
        session = await self.engine.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        return {
            "session_id": session.session_id,
            "status": session.status.value,
            "version": session.version,
            "agent": {
                "id": session.agent_memory.agent_id,
                "status": "active"  # derived
            },
            "execution": {
                "plan_version": session.execution_plan.version,
                "stages_total": len(session.execution_plan.stages),
                "running": len(session.running_subtasks),
                "queued": len(session.queued_subtasks)
            },
            "devices": [
                {
                    "id": d.device_id,
                    "type": d.device_type,
                    "connected_at": d.connected_at.isoformat()
                }
                for d in session.workspace.active_devices
            ],
            "conversation": {
                "message_count": len(session.conversation.messages),
                "last_message": session.conversation.last_message_at.isoformat() if session.conversation.last_message_at else None
            },
            "vm": session.vm_state.model_dump() if session.vm_state else None,
            "browser": session.browser_state.model_dump() if session.browser_state else None,
            "terminal": session.terminal_state.model_dump() if session.terminal_state else None
        }
    
    async def list_sessions(
        self,
        tenant_id: str,
        status: Optional[SessionStatus] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List sessions for tenant."""
        sessions = await self.engine.repo.list_active(tenant_id, limit)
        
        if status:
            sessions = [s for s in sessions if s.status == status]
        
        return [
            {
                "session_id": s.session_id,
                "status": s.status.value,
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity_at.isoformat(),
                "version": s.version
            }
            for s in sessions
      ]
