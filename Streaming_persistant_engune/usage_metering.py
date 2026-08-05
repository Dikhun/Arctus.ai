#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Usage Metering Engine
=======================================================
Comprehensive usage tracking, real-time billing, cost prediction,
budget alerts, and quota management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
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

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger("arctus.metering")
logger.setLevel(logging.DEBUG)

# ============================================================================
# DATA MODELS
# ============================================================================

class ResourceType(Enum):
    LLM_TOKENS = auto()
    PROMPT_TOKENS = auto()
    COMPLETION_TOKENS = auto()
    CACHED_TOKENS = auto()
    API_COST = auto()
    VM_RUNTIME = auto()
    CPU = auto()
    RAM = auto()
    GPU = auto()
    DISK = auto()
    BANDWIDTH = auto()
    STORAGE = auto()
    BROWSER_RUNTIME = auto()
    TERMINAL_RUNTIME = auto()
    TOOL_EXECUTION = auto()
    AGENT_RUNTIME = auto()

@dataclass(frozen=True, slots=True)
class UsageEvent:
    """Single usage event."""
    event_id: str
    timestamp: datetime
    resource_type: ResourceType
    quantity: float
    unit: str
    cost_per_unit: float
    total_cost: float
    user_id: str
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "resource_type": self.resource_type.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "cost_per_unit": self.cost_per_unit,
            "total_cost": self.total_cost,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "metadata": self.metadata,
        }

@dataclass
class UsageAggregate:
    """Aggregated usage over a time period."""
    period_start: datetime
    period_end: datetime
    resource_type: ResourceType
    total_quantity: float
    total_cost: float
    event_count: int
    dimensions: Dict[str, str] = field(default_factory=dict)

@dataclass
class BudgetAlert:
    """Budget alert configuration."""
    alert_id: str
    name: str
    scope_type: str  # user, project, organization, workspace
    scope_id: str
    budget_amount: float
    threshold_percent: float  # 0-100
    current_spend: float = 0.0
    triggered: bool = False
    last_triggered: Optional[datetime] = None
    notification_channels: List[str] = field(default_factory=list)

@dataclass
class Quota:
    """Resource quota definition."""
    quota_id: str
    resource_type: ResourceType
    scope_type: str
    scope_id: str
    limit: float
    period: str  # hourly, daily, weekly, monthly
    current_usage: float = 0.0
    period_start: datetime = field(default_factory=datetime.utcnow)
    enforced: bool = True

@dataclass
class CostPrediction:
    """Predicted future costs."""
    resource_type: ResourceType
    current_run_rate: float  # cost per hour
    predicted_daily: float
    predicted_monthly: float
    confidence: float  # 0-1
    trend: str  # increasing, decreasing, stable

# ============================================================================
# PRICING ENGINE
# ============================================================================

class PricingEngine:
    """Calculate costs for resource usage."""
    
    # Default pricing (would load from config/database)
    DEFAULT_PRICES: Dict[ResourceType, Dict[str, Any]] = {
        ResourceType.LLM_TOKENS: {"per_unit": 0.000002, "unit": "token"},  # $2 per million
        ResourceType.PROMPT_TOKENS: {"per_unit": 0.0000015, "unit": "token"},
        ResourceType.COMPLETION_TOKENS: {"per_unit": 0.000002, "unit": "token"},
        ResourceType.CACHED_TOKENS: {"per_unit": 0.0000005, "unit": "token"},
        ResourceType.API_COST: {"per_unit": 1.0, "unit": "usd"},
        ResourceType.VM_RUNTIME: {"per_unit": 0.05, "unit": "minute"},  # $3/hour
        ResourceType.CPU: {"per_unit": 0.02, "unit": "core-minute"},
        ResourceType.RAM: {"per_unit": 0.01, "unit": "gb-minute"},
        ResourceType.GPU: {"per_unit": 0.50, "unit": "minute"},
        ResourceType.DISK: {"per_unit": 0.0001, "unit": "gb"},
        ResourceType.BANDWIDTH: {"per_unit": 0.01, "unit": "gb"},
        ResourceType.STORAGE: {"per_unit": 0.02, "unit": "gb-month"},
        ResourceType.BROWSER_RUNTIME: {"per_unit": 0.01, "unit": "minute"},
        ResourceType.TERMINAL_RUNTIME: {"per_unit": 0.005, "unit": "minute"},
        ResourceType.TOOL_EXECUTION: {"per_unit": 0.10, "unit": "call"},
        ResourceType.AGENT_RUNTIME: {"per_unit": 0.02, "unit": "minute"},
    }
    
    def __init__(self, custom_prices: Optional[Dict[ResourceType, Dict[str, Any]]] = None):
        self.prices = custom_prices or self.DEFAULT_PRICES
    
    def calculate_cost(self, resource_type: ResourceType, quantity: float) -> Tuple[float, float, str]:
        """
        Calculate cost for usage.
        Returns (cost_per_unit, total_cost, unit).
        """
        pricing = self.prices.get(resource_type, {"per_unit": 0.0, "unit": "unit"})
        per_unit = pricing["per_unit"]
        unit = pricing["unit"]
        total = per_unit * quantity
        return per_unit, total, unit
    
    def set_price(self, resource_type: ResourceType, per_unit: float, unit: str):
        """Update price for resource type."""
        self.prices[resource_type] = {"per_unit": per_unit, "unit": unit}

# ============================================================================
# METERING ENGINE
# ============================================================================

class MeteringEngine:
    """
    Comprehensive usage metering engine.
    
    Features:
    - Real-time usage tracking for all resource types
    - Cost calculation with configurable pricing
    - Budget alerts with notifications
    - Quota management and enforcement
    - Historical analytics and reporting
    - Cost prediction using trend analysis
    """
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        pricing_engine: Optional[PricingEngine] = None,
    ):
        self.storage_path = Path(storage_path or tempfile.gettempdir()) / "arctus" / "metering"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.pricing = pricing_engine or PricingEngine()
        
        # Event storage
        self._events: deque = deque(maxlen=100000)  # In-memory ring buffer
        self._aggregates: Dict[str, UsageAggregate] = {}
        
        # Indexes
        self._by_user: Dict[str, List[UsageEvent]] = defaultdict(list)
        self._by_project: Dict[str, List[UsageEvent]] = defaultdict(list)
        self._by_org: Dict[str, List[UsageEvent]] = defaultdict(list)
        self._by_agent: Dict[str, List[UsageEvent]] = defaultdict(list)
        self._by_resource: Dict[ResourceType, List[UsageEvent]] = defaultdict(list)
        
        # Budgets and quotas
        self._budget_alerts: Dict[str, BudgetAlert] = {}
        self._quotas: Dict[str, Quota] = {}
        
        # Callbacks
        self._on_event: List[Callable[[UsageEvent], Coroutine]] = []
        self._on_budget_alert: List[Callable[[BudgetAlert], Coroutine]] = []
        self._on_quota_exceeded: List[Callable[[Quota], Coroutine]] = []
        
        # Background tasks
        self._aggregate_task: Optional[asyncio.Task] = None
        self._alert_task: Optional[asyncio.Task] = None
        
        # Locks
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Start background processing."""
        self._aggregate_task = asyncio.create_task(self._aggregation_loop())
        self._alert_task = asyncio.create_task(self._alert_loop())
        logger.info("Metering engine started")
    
    async def stop(self):
        """Stop background processing."""
        for task in [self._aggregate_task, self._alert_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    # -------------------------------------------------------------------------
    # EVENT TRACKING
    # -------------------------------------------------------------------------
    
    async def track_usage(
        self,
        resource_type: ResourceType,
        quantity: float,
        user_id: str,
        project_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageEvent:
        """
        Record a usage event.
        
        Args:
            resource_type: Type of resource consumed
            quantity: Amount consumed
            user_id: User responsible for usage
            project_id: Associated project
            organization_id: Associated organization
            workspace_id: Associated workspace
            agent_id: Associated AI agent
            task_id: Associated task
            metadata: Additional context
        
        Returns:
            Created UsageEvent
        """
        # Calculate cost
        cost_per_unit, total_cost, unit = self.pricing.calculate_cost(resource_type, quantity)
        
        event = UsageEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow(),
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            cost_per_unit=cost_per_unit,
            total_cost=total_cost,
            user_id=user_id,
            project_id=project_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            task_id=task_id,
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._events.append(event)
            self._by_user[user_id].append(event)
            if project_id:
                self._by_project[project_id].append(event)
            if organization_id:
                self._by_org[organization_id].append(event)
            if agent_id:
                self._by_agent[agent_id].append(event)
            self._by_resource[resource_type].append(event)
        
        # Check quotas
        await self._check_quotas(event)
        
        # Persist
        await self._persist_event(event)
        
        # Notify
        for callback in self._on_event:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")
        
        return event
    
    async def track_llm_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        model: str = "gpt-4",
        user_id: str = "",
        **kwargs,
    ) -> List[UsageEvent]:
        """Convenience method for LLM token tracking."""
        events = []
        
        if prompt_tokens > 0:
            events.append(await self.track_usage(
                ResourceType.PROMPT_TOKENS,
                prompt_tokens,
                user_id=user_id,
                metadata={"model": model, "token_type": "prompt"},
                **kwargs,
            ))
        
        if completion_tokens > 0:
            events.append(await self.track_usage(
                ResourceType.COMPLETION_TOKENS,
                completion_tokens,
                user_id=user_id,
                metadata={"model": model, "token_type": "completion"},
                **kwargs,
            ))
        
        if cached_tokens > 0:
            events.append(await self.track_usage(
                ResourceType.CACHED_TOKENS,
                cached_tokens,
                user_id=user_id,
                metadata={"model": model, "token_type": "cached"},
                **kwargs,
            ))
        
        # Total LLM tokens
        total = prompt_tokens + completion_tokens + cached_tokens
        if total > 0:
            events.append(await self.track_usage(
                ResourceType.LLM_TOKENS,
                total,
                user_id=user_id,
                metadata={"model": model, "breakdown": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "cached": cached_tokens,
                }},
                **kwargs,
            ))
        
        return events
    
    async def track_runtime(
        self,
        resource_type: ResourceType,
        duration_seconds: float,
        user_id: str,
        **kwargs,
    ) -> UsageEvent:
        """Track runtime duration (converts seconds to minutes for billing)."""
        minutes = duration_seconds / 60.0
        return await self.track_usage(
            resource_type,
            minutes,
            user_id=user_id,
            metadata={"duration_seconds": duration_seconds},
            **kwargs,
        )
    
    # -------------------------------------------------------------------------
    # AGGREGATION
    # -------------------------------------------------------------------------
    
    async def _aggregation_loop(self):
        """Background loop to aggregate usage."""
        while True:
            try:
                await asyncio.sleep(60)  # Aggregate every minute
                
                now = datetime.utcnow()
                window_start = now - timedelta(minutes=5)
                
                # Aggregate by various dimensions
                await self._compute_aggregates(window_start, now)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Aggregation error: {e}")
    
    async def _compute_aggregates(self, start: datetime, end: datetime):
        """Compute usage aggregates for time window."""
        # Filter events in window
        events_in_window = [
            e for e in self._events
            if start <= e.timestamp <= end
        ]
        
        # Group by dimensions
        groups: Dict[str, List[UsageEvent]] = defaultdict(list)
        
        for event in events_in_window:
            # By resource type
            key = f"resource:{event.resource_type.name}:{start.isoformat()}"
            groups[key].append(event)
            
            # By user + resource
            key = f"user:{event.user_id}:{event.resource_type.name}:{start.isoformat()}"
            groups[key].append(event)
            
            # By project + resource
            if event.project_id:
                key = f"project:{event.project_id}:{event.resource_type.name}:{start.isoformat()}"
                groups[key].append(event)
        
        # Create aggregates
        for key, events in groups.items():
            total_qty = sum(e.quantity for e in events)
            total_cost = sum(e.total_cost for e in events)
            
            aggregate = UsageAggregate(
                period_start=start,
                period_end=end,
                resource_type=events[0].resource_type,
                total_quantity=total_qty,
                total_cost=total_cost,
                event_count=len(events),
                dimensions={"group_key": key},
            )
            
            self._aggregates[key] = aggregate
    
    # -------------------------------------------------------------------------
    # BUDGET ALERTS
    # -------------------------------------------------------------------------
    
    def create_budget_alert(
        self,
        name: str,
        scope_type: str,
        scope_id: str,
        budget_amount: float,
        threshold_percent: float = 80.0,
        notification_channels: Optional[List[str]] = None,
    ) -> BudgetAlert:
        """Create budget alert."""
        alert = BudgetAlert(
            alert_id=f"bal-{uuid.uuid4().hex[:8]}",
            name=name,
            scope_type=scope_type,
            scope_id=scope_id,
            budget_amount=budget_amount,
            threshold_percent=threshold_percent,
            notification_channels=notification_channels or ["dashboard"],
        )
        self._budget_alerts[alert.alert_id] = alert
        return alert
    
    async def _alert_loop(self):
        """Background loop to check budget thresholds."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                for alert in self._budget_alerts.values():
                    if alert.triggered:
                        continue
                    
                    # Calculate current spend
                    spend = await self._calculate_spend(
                        alert.scope_type,
                        alert.scope_id,
                    )
                    alert.current_spend = spend
                    
                    threshold_amount = alert.budget_amount * (alert.threshold_percent / 100)
                    
                    if spend >= threshold_amount:
                        alert.triggered = True
                        alert.last_triggered = datetime.utcnow()
                        
                        # Notify
                        for callback in self._on_budget_alert:
                            try:
                                await callback(alert)
                            except Exception as e:
                                logger.error(f"Budget alert callback error: {e}")
                        
                        logger.warning(
                            f"Budget alert triggered: {alert.name} "
                            f"(${spend:.2f} / ${alert.budget_amount:.2f})"
                        )
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert loop error: {e}")
    
    async def _calculate_spend(self, scope_type: str, scope_id: str) -> float:
        """Calculate current spend for scope."""
        total = 0.0
        
        if scope_type == "user":
            events = self._by_user.get(scope_id, [])
        elif scope_type == "project":
            events = self._by_project.get(scope_id, [])
        elif scope_type == "organization":
            events = self._by_org.get(scope_id, [])
        else:
            return 0.0
        
        # Sum last 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        for event in events:
            if event.timestamp >= cutoff:
                total += event.total_cost
        
        return total
    
    # -------------------------------------------------------------------------
    # QUOTA MANAGEMENT
    # -------------------------------------------------------------------------
    
    def create_quota(
        self,
        resource_type: ResourceType,
        scope_type: str,
        scope_id: str,
        limit: float,
        period: str = "daily",
    ) -> Quota:
        """Create resource quota.
