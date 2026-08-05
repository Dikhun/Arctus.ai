#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Human Approval Engine
===========================================================
Human-in-the-loop workflow engine with risk scoring, policy enforcement,
multi-approver support, and comprehensive audit trails.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# Optional email/webhook support
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger("arctus.approval")
logger.setLevel(logging.DEBUG)

# ============================================================================
# ENUMERATIONS
# ============================================================================

class ApprovalStatus(Enum):
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    MODIFIED = auto()
    EXPIRED = auto()
    ESCALATED = auto()
    OVERRIDDEN = auto()

class RiskLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class ApprovalAction(Enum):
    EXECUTE_COMMAND = auto()
    DELETE_FILES = auto()
    RUN_SHELL_SCRIPT = auto()
    DEPLOY_APPLICATION = auto()
    SPEND_MONEY = auto()
    ACCESS_SECRETS = auto()
    EXTERNAL_API = auto()
    BROWSER_PURCHASE = auto()
    DATABASE_MODIFICATION = auto()

class NotificationChannel(Enum):
    DASHBOARD = auto()
    EMAIL = auto()
    WEBHOOK = auto()
    SMS = auto()
    SLACK = auto()

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass(frozen=True, slots=True)
class RiskProfile:
    """Risk assessment for an approval request."""
    score: float  # 0.0 to 100.0
    level: RiskLevel
    factors: List[str] = field(default_factory=list)
    automated_decision: Optional[bool] = None  # True=auto-approve, False=auto-reject, None=needs human
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.name,
            "factors": self.factors,
            "automated_decision": self.automated_decision,
        }

@dataclass(slots=True)
class ApprovalRequest:
    """Single approval request."""
    request_id: str
    action_type: ApprovalAction
    status: ApprovalStatus
    created_at: datetime
    created_by: str
    tenant_id: str
    workspace_id: str
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    
    # Request details
    title: str = ""
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Risk
    risk_profile: Optional[RiskProfile] = None
    
    # Approval flow
    required_approvers: int = 1
    approvers: List[str] = field(default_factory=list)
    approved_by: List[str] = field(default_factory=list)
    rejected_by: List[str] = field(default_factory=list)
    approval_timeout: Optional[datetime] = None
    
    # Modifications
    original_payload: Optional[Dict[str, Any]] = None
    modified_payload: Optional[Dict[str, Any]] = None
    modification_reason: str = ""
    
    # Resolution
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_comment: str = ""
    
    # Emergency override
    overridden: bool = False
    overridden_by: Optional[str] = None
    override_reason: str = ""
    
    # Notifications
    notifications_sent: List[Dict[str, Any]] = field(default_factory=list)
    
    # Audit
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_type": self.action_type.name,
            "status": self.status.name,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "description": self.description,
            "payload": self.payload,
            "risk_profile": self.risk_profile.to_dict() if self.risk_profile else None,
            "required_approvers": self.required_approvers,
            "approved_by": self.approved_by,
            "rejected_by": self.rejected_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "overridden": self.overridden,
        }

@dataclass
class ApprovalPolicy:
    """Policy defining approval rules."""
    policy_id: str
    name: str
    tenant_id: str = "default"
    
    # Action rules
    action_rules: Dict[ApprovalAction, Dict[str, Any]] = field(default_factory=dict)
    # Example: {ApprovalAction.SPEND_MONEY: {"min_amount": 100, "require_approvers": 2}}
    
    # Risk thresholds
    auto_approve_below: float = 10.0  # Risk score
    auto_reject_above: float = 90.0
    require_approval_above: float = 20.0
    
    # Role mappings
    role_approvers: Dict[str, List[str]] = field(default_factory=dict)
    # Example: {"admin": ["user1", "user2"], "finance": ["user3"]}
    
    # Emergency contacts
    emergency_contacts: List[str] = field(default_factory=list)
    
    # Timeout
    default_timeout_minutes: int = 60

@dataclass
class ApprovalHistory:
    """Historical record of approvals."""
    request_id: str
    action_type: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    created_by: str
    resolved_by: Optional[str]
    risk_score: float
    duration_seconds: float

# ============================================================================
# RISK SCORING ENGINE
# ============================================================================

class RiskScoringEngine:
    """Calculate risk scores for approval requests."""
    
    # Base risk by action type
    ACTION_RISK: Dict[ApprovalAction, float] = {
        ApprovalAction.EXECUTE_COMMAND: 30.0,
        ApprovalAction.DELETE_FILES: 25.0,
        ApprovalAction.RUN_SHELL_SCRIPT: 40.0,
        ApprovalAction.DEPLOY_APPLICATION: 35.0,
        ApprovalAction.SPEND_MONEY: 50.0,
        ApprovalAction.ACCESS_SECRETS: 60.0,
        ApprovalAction.EXTERNAL_API: 20.0,
        ApprovalAction.BROWSER_PURCHASE: 55.0,
        ApprovalAction.DATABASE_MODIFICATION: 45.0,
    }
    
    # Risk modifiers
    MODIFIERS = {
        "production_environment": 20.0,
        "external_network": 15.0,
        "privileged_access": 25.0,
        "irreversible": 20.0,
        "large_scale": 15.0,
        "sensitive_data": 20.0,
        "untested_code": 10.0,
        "after_hours": 5.0,
    }
    
    def calculate_risk(
        self,
        action: ApprovalAction,
        payload: Dict[str, Any],
        context: Dict[str, Any],
    ) -> RiskProfile:
        """Calculate risk profile for request."""
        base_score = self.ACTION_RISK.get(action, 20.0)
        factors = []
        
        # Check modifiers
        if context.get("environment") == "production":
            base_score += self.MODIFIERS["production_environment"]
            factors.append("production_environment")
        
        if context.get("external_network", False):
            base_score += self.MODIFIERS["external_network"]
            factors.append("external_network")
        
        if context.get("privileged", False):
            base_score += self.MODIFIERS["privileged_access"]
            factors.append("privileged_access")
        
        if context.get("irreversible", False):
            base_score += self.MODIFIERS["irreversible"]
            factors.append("irreversible")
        
        if payload.get("amount", 0) > 1000:
            base_score += self.MODIFIERS["large_scale"]
            factors.append("large_scale")
        
        if context.get("sensitive_data", False):
            base_score += self.MODIFIERS["sensitive_data"]
            factors.append("sensitive_data")
        
        # Cap at 100
        score = min(base_score, 100.0)
        
        # Determine level
        if score < 20:
            level = RiskLevel.LOW
        elif score < 40:
            level = RiskLevel.MEDIUM
        elif score < 70:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL
        
        # Automated decision
        auto = None
        if score < 10:
            auto = True
        elif score > 90:
            auto = False
        
        return RiskProfile(
            score=score,
            level=level,
            factors=factors,
            automated_decision=auto,
        )

# ============================================================================
# POLICY ENGINE
# ============================================================================

class PolicyEngine:
    """Evaluate approval requests against policies."""
    
    def __init__(self):
        self.policies: Dict[str, ApprovalPolicy] = {}
        self.risk_engine = RiskScoringEngine()
    
    def register_policy(self, policy: ApprovalPolicy):
        """Register approval policy."""
        self.policies[policy.policy_id] = policy
    
    def evaluate(
        self,
        request: ApprovalRequest,
        policy: Optional[ApprovalPolicy] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate request against policy.
        Returns (allowed, reason).
        """
        if policy is None:
            policy = self._find_policy(request)
        
        if not policy:
            return True, None  # Default allow if no policy
        
        # Check action rules
        action_rule = policy.action_rules.get(request.action_type, {})
        
        # Check amount limits
        if "max_amount" in action_rule:
            amount = request.payload.get("amount", 0)
            if amount > action_rule["max_amount"]:
                return False, f"Amount {amount} exceeds maximum {action_rule['max_amount']}"
        
        # Check required approvers
        request.required_approvers = action_rule.get("require_approvers", 1)
        
        # Check risk-based auto decisions
        if request.risk_profile:
            if request.risk_profile.automated_decision is True:
                return True, "auto-approved: low risk"
            elif request.risk_profile.automated_decision is False:
                return False, "auto-rejected: critical risk"
        
        return True, None
    
    def get_approvers_for_request(
        self,
        request: ApprovalRequest,
        policy: Optional[ApprovalPolicy] = None,
    ) -> List[str]:
        """Get list of eligible approvers for request."""
        if policy is None:
            policy = self._find_policy(request)
        
        if not policy:
            return []
        
        # Collect approvers from roles
        approvers = set()
        for role, users in policy.role_approvers.items():
            approvers.update(users)
        
        # Action-specific approvers
        action_rule = policy.action_rules.get(request.action_type, {})
        if "approvers" in action_rule:
            approvers.update(action_rule["approvers"])
        
        return list(approvers)
    
    def _find_policy(self, request: ApprovalRequest) -> Optional[ApprovalPolicy]:
        """Find applicable policy for request."""
        # Match by tenant
        for policy in self.policies.values():
            if policy.tenant_id == request.tenant_id:
                return policy
        return None

# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================

class NotificationDispatcher:
    """Dispatch approval notifications across channels."""
    
    def __init__(self):
        self._channels: Dict[NotificationChannel, Callable] = {}
        self._webhook_urls: Dict[str, str] = {}
    
    def register_channel(
        self,
        channel: NotificationChannel,
        handler: Callable[[ApprovalRequest, Dict[str, Any]], Coroutine],
    ):
        """Register notification channel handler."""
        self._channels[channel] = handler
    
    def register_webhook(self, name: str, url: str):
        """Register webhook endpoint."""
        self._webhook_urls[name] = url
    
    async def dispatch(
        self,
        request: ApprovalRequest,
        channels: List[NotificationChannel],
        context: Optional[Dict[str, Any]] = None,
    ):
        """Send notification to specified channels."""
        ctx = context or {}
        
        for channel in channels:
            handler = self._channels.get(channel)
            if handler:
                try:
                    await handler(request, ctx)
                    request.notifications_sent.append({
                        "channel": channel.name,
                        "timestamp": datetime.utcnow().isoformat(),
                        "success": True,
                    })
                except Exception as e:
                    logger.error(f"Notification failed for {channel}: {e}")
                    request.notifications_sent.append({
                        "channel": channel.name,
                        "timestamp": datetime.utcnow().isoformat(),
                        "success": False,
                        "error": str(e),
                    })
    
    # Built-in handlers
    async def _dashboard_handler(self, request: ApprovalRequest, ctx: Dict[str, Any]):
        """Dashboard notification (in-app)."""
        logger.info(f"[DASHBOARD] Approval request: {request.request_id}")
    
    async def _email_handler(self, request: ApprovalRequest, ctx: Dict[str, Any]):
        """Email notification."""
        recipients = ctx.get("email_recipients", [])
        logger.info(f"[EMAIL] To {recipients}: Approval {request.request_id}")
    
    async def _webhook_handler(self, request: ApprovalRequest, ctx: Dict[str, Any]):
        """Webhook notification."""
        if not AIOHTTP_AVAILABLE:
            return
        
        webhook_name = ctx.get("webhook_name", "default")
        url = self._webhook_urls.get(webhook_name)
        if not url:
            return
        
        payload = {
            "event": "approval_request",
            "request": request.to_dict(),
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"Webhook returned {resp.status}")

# ============================================================================
# APPROVAL ENGINE CORE
# ============================================================================

class ApprovalEngine:
    """
    Human approval workflow engine.
    
    Features:
    - Approval requests with risk scoring
    - Multi-approver support with role-based routing
    - Policy engine with auto-approve/reject
    - Approval timeout and escalation
    - Request modification
    - Emergency override
    - Comprehensive audit trail
    """
    
    def __init__(self):
        self.requests: Dict[str, ApprovalRequest] = {}
        self.history: List[ApprovalHistory] = []
        self.policy_engine = PolicyEngine()
        self.notification_dispatcher = NotificationDispatcher()
        self._lock = asyncio.Lock()
        self._timeout_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self._on_status_change: List[Callable[[ApprovalRequest], Coroutine]] = []
        self._on_resolve: List[Callable[[ApprovalRequest], Coroutine]] = []
        
        # Setup default notifications
        self.notification_dispatcher.register_channel(
            NotificationChannel.DASHBOARD,
            self.notification_dispatcher._dashboard_handler,
        )
        self.notification_dispatcher.register_channel(
            NotificationChannel.EMAIL,
            self.notification_dispatcher._email_handler,
        )
        self.notification_dispatcher.register_channel(
            NotificationChannel.WEBHOOK,
            self.notification_dispatcher._webhook_handler,
        )
    
    async def start(self):
        """Start background tasks."""
        self._timeout_task = asyncio.create_task(self._timeout_monitor_loop())
        logger.info("Approval engine started")
    
    async def stop(self):
        """Stop background tasks."""
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
    
    # -------------------------------------------------------------------------
    # REQUEST CREATION
    # -------------------------------------------------------------------------
    
    async def create_request(
        self,
        action_type: ApprovalAction,
        created_by: str,
        tenant_id: str,
        workspace_id: str,
        title: str,
        description: str = "",
        payload: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout_minutes: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create new approval request."""
        request_id = f"apr-{uuid.uuid4().hex[:12]}"
        
        # Calculate risk
        risk = self.policy_engine.risk_engine.calculate_risk(
            action_type,
            payload or {},
            context or {},
        )
        
        request = ApprovalRequest(
            request_id=request_id,
            action_type=action_type,
            status=ApprovalStatus.PENDING,
            created_at=datetime.utcnow(),
            created_by=created_by,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            project_id=project_id,
            agent_id=agent_id,
            title=title,
            description=description,
            payload=payload or {},
            context=context or {},
            risk_profile=risk,
        )
        
        # Evaluate policy
        policy = self.policy_engine._find_policy(request)
        allowed, reason = self.policy_engine.evaluate(request, policy)
        
        if not allowed:
            request.status = ApprovalStatus.REJECTED
            request.resolved_at = datetime.utcnow()
            request.resolution_comment = reason or "Policy rejection"
            request.audit_log.append({
                "action": "auto_reject",
                "timestamp": datetime.utcnow().isoformat(),
                "reason": reason,
            })
        
        # Set timeout
        if timeout_minutes or (policy and policy.default_timeout_minutes):
            mins = timeout_minutes or policy.default_timeout_minutes
            request.approval_timeout = datetime.utcnow() + timedelta(minutes=mins)
        
        # Set approvers
        if policy:
            request.approvers = self.policy_engine.get_approvers_for_request(request, policy)
            request.required_approvers = max(
                request.required_approvers,
                policy.action_rules.get(action_type, {}).get("require_approvers", 1),
            )
        
        async with self._lock:
            self.requests[request_id] = request
        
        # Auto-approve low risk
        if risk.automated_decision is True:
            request.status = ApprovalStatus.APPROVED
            request.resolved
