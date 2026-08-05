"""
session_api.py
FastAPI-based REST API for session management.
Provides endpoints for all session operations.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from session_models import SessionState, SessionStatus, DeviceConnection
from session_engine import SessionEngine, SessionNotFoundError, SessionExpiredError
from session_service import SessionService, SessionCreationRequest, ExecutionResult
from session_manager import SessionManager, SessionManagerConfig, GlobalSessionManager
from session_events import EventBus


logger = logging.getLogger("session.api")


# --- Pydantic Schemas ---

class CreateSessionRequest(BaseModel):
    tenant_id: str
    owner_id: str
    goal: Optional[str] = None
    strategy: Optional[str] = "default"
    environment: Optional[Dict[str, str]] = None
    resources: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    parent_session_id: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SubmitTaskRequest(BaseModel):
    task_description: str
    task_input: Optional[Dict[str, Any]] = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class DeviceConnectRequest(BaseModel):
    device_id: str
    device_type: str = "browser"
    capabilities: List[str] = Field(default_factory=list)


class RecoveryRequest(BaseModel):
    recovery_type: str = "automatic"  # automatic, manual, forced


class SessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    owner_id: str
    status: str
    version: int
    created_at: datetime
    last_activity_at: datetime
    expires_at: Optional[datetime] = None


class DashboardStateResponse(BaseModel):
    session_id: str
    status: str
    version: int
    agent: Dict[str, Any]
    execution: Dict[str, Any]
    devices: List[Dict[str, Any]]
    conversation: Dict[str, Any]
    vm: Optional[Dict[str, Any]] = None
    browser: Optional[Dict[str, Any]] = None
    terminal: Optional[Dict[str, Any]] = None


# --- Dependencies ---

async def get_manager() -> SessionManager:
    """Dependency to get session manager."""
    return GlobalSessionManager.get()


async def get_engine(manager: SessionManager = Depends(get_manager)) -> SessionEngine:
    """Dependency to get session engine."""
    return manager.get_engine()


async def get_service(engine: SessionEngine = Depends(get_engine)) -> SessionService:
    """Dependency to get session service."""
    return SessionService(
        engine=engine,
        event_bus=engine.events
    )


# --- FastAPI Application ---

def create_app(manager: Optional[SessionManager] = None) -> FastAPI:
    """Create FastAPI application."""
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager."""
        if manager:
            yield
        else:
            # Initialize with defaults for standalone mode
            config = SessionManagerConfig()
            await GlobalSessionManager.initialize(config)
            yield
            await GlobalSessionManager.shutdown()
    
    app = FastAPI(
        title="Arctus Session Persistence API",
        description="Production-grade session management for AI orchestration",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # --- Session Endpoints ---
    
    @app.post("/sessions", response_model=SessionResponse)
    async def create_session(
        request: CreateSessionRequest,
        service: SessionService = Depends(get_service)
    ) -> SessionResponse:
        """Create a new session."""
        session = await service.create(
            SessionCreationRequest(
                tenant_id=request.tenant_id,
                owner_id=request.owner_id,
                goal=request.goal,
                strategy=request.strategy,
                environment=request.environment,
                resources=request.resources,
                metadata=request.metadata,
                parent_session_id=request.parent_session_id
            )
        )
        
        return SessionResponse(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            owner_id=session.owner_id,
            status=session.status.value,
            version=session.version,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
            expires_at=session.expires_at
        )
    
    @app.get("/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> SessionResponse:
        """Get session by ID."""
        session = await engine.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionResponse(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            owner_id=session.owner_id,
            status=session.status.value,
            version=session.version,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
            expires_at=session.expires_at
        )
    
    @app.post("/sessions/{session_id}/pause")
    async def pause_session(
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, str]:
        """Pause a session."""
        try:
            await engine.pause_session(session_id, "user_requested")
            return {"status": "paused"}
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    @app.post("/sessions/{session_id}/resume")
    async def resume_session(
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, str]:
        """Resume a session."""
        try:
            await engine.resume_session(session_id, "user")
            return {"status": "resumed"}
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    @app.post("/sessions/{session_id}/complete")
    async def complete_session(
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, str]:
        """Complete a session."""
        try:
            await engine.complete_session(session_id)
            return {"status": "completed"}
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    @app.post("/sessions/{session_id}/recover")
    async def recover_session(
        session_id: str,
        request: RecoveryRequest,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, Any]:
        """Recover a session."""
        try:
            session = await engine.recover_session(session_id, request.recovery_type)
            return {
                "status": "recovered",
                "session_id": session.session_id,
                "version": session.version
            }
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, str]:
        """Delete a session."""
        deleted = await engine.repo.delete(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "deleted"}
    
    # --- Task Endpoints ---
    
    @app.post("/sessions/{session_id}/tasks", response_model=ExecutionResult)
    async def submit_task(
        session_id: str,
        request: SubmitTaskRequest,
        service: SessionService = Depends(get_service)
    ) -> ExecutionResult:
        """Submit a task to session."""
        return await service.submit_task(
            session_id,
            request.task_description,
            request.task_input
        )
    
    # --- Message Endpoints ---
    
    @app.post("/sessions/{session_id}/messages")
    async def add_message(
        session_id: str,
        request: AddMessageRequest,
        service: SessionService = Depends(get_service)
    ) -> Dict[str, Any]:
        """Add message to session conversation."""
        session = await service.add_message(
            session_id,
            request.role,
            request.content,
            request.metadata
        )
        return {
            "message_count": len(session.conversation.messages),
            "last_message_at": session.conversation.last_message_at
        }
    
    # --- Device Endpoints ---
    
    @app.post("/sessions/{session_id}/devices")
    async def connect_device(
        session_id: str,
        request: DeviceConnectRequest,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, Any]:
        """Connect a device to session."""
        device = DeviceConnection(
            device_id=request.device_id,
            connection_id=f"{request.device_id}-{datetime.utcnow().timestamp()}",
            device_type=request.device_type,
            capabilities=request.capabilities
        )
        
        try:
            session = await engine.connect_device(session_id, device)
            return {
                "connected": True,
                "active_devices": len(session.workspace.active_devices)
            }
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    @app.delete("/sessions/{session_id}/devices/{device_id}")
    async def disconnect_device(
        session_id: str,
        device_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, Any]:
        """Disconnect a device from session."""
        try:
            session = await engine.disconnect_device(session_id, device_id)
            return {
                "disconnected": True,
                "active_devices": len(session.workspace.active_devices)
            }
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    # --- Dashboard Endpoints ---
    
    @app.get("/sessions/{session_id}/dashboard", response_model=DashboardStateResponse)
    async def get_dashboard(
        session_id: str,
        service: SessionService = Depends(get_service)
    ) -> DashboardStateResponse:
        """Get dashboard state for session."""
        try:
            state = await service.get_dashboard_state(session_id)
            return DashboardStateResponse(**state)
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")
    
    @app.get("/tenants/{tenant_id}/sessions")
    async def list_sessions(
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        service: SessionService = Depends(get_service)
    ) -> List[Dict[str, Any]]:
        """List sessions for tenant."""
        session_status = SessionStatus(status) if status else None
        return await service.list_sessions(tenant_id, session_status, limit)
    
    # --- WebSocket for Real-time Updates ---
    
    @app.websocket("/ws/sessions/{session_id}")
    async def session_websocket(
        websocket: WebSocket,
        session_id: str,
        engine: SessionEngine = Depends(get_engine)
    ) -> None:
        """WebSocket for real-time session updates."""
        await websocket.accept()
        
        # Subscribe to events for this session
        async def event_handler(event: Any) -> None:
            await websocket.send_json({
                "type": event.event_type,
                "data": event.model_dump() if hasattr(event, 'model_dump') else str(event)
            })
        
        engine.events.subscribe_all(event_handler)
        
        try:
            while True:
                # Keep connection alive, handle ping
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        
        except WebSocketDisconnect:
            pass
        finally:
            # Unsubscribe
            engine.events.unsubscribe_all(event_handler)
    
    # --- Health Check ---
    
    @app.get("/health")
    async def health_check(
        engine: SessionEngine = Depends(get_engine)
    ) -> Dict[str, Any]:
        """Health check endpoint."""
        stats = await engine.get_session_stats()
        return {
            "status": "healthy",
            "engine": stats
        }
    
    return app


# Factory function for ASGI servers
app = create_app()
