"""Arctus AI Orchestration Framework - Core Domain Models.

Pydantic-based domain models shared across all Queen Module components.
Defines the universal type system for tasks, agents, providers, plans,
and execution artifacts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enumerations ─────────────────────────────────────────────────────────────

class TaskStatus(Enum):
    """Lifecycle states of an orchestrated task."""

    PENDING = auto()
    ANALYZING = auto()
    PLANNED = auto()
    ROUTED = auto()
    DISPATCHED = auto()
    EXECUTING = auto()
    VERIFYING = auto()
    SYNTHESIZING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    RETRYING = auto()
    ESCALATED = auto()


class ExecutionMode(Enum):
    """Execution strategy for task sets."""

    SEQUENTIAL = auto()
    PARALLEL = auto()
    PIPELINE = auto()
    DAG = auto()


class Priority(Enum):
    """Business priority for scheduling and resource allocation."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class ProviderStatus(Enum):
    """Operational status of an LLM provider."""

    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    OFFLINE = auto()
    CIRCUIT_OPEN = auto()


class AgentRole(Enum):
    """Specialist role classification for capability routing."""

    GENERALIST = auto()
    CODER = auto()
    ANALYST = auto()
    CREATIVE = auto()
    RESEARCHER = auto()
    REVIEWER = auto()
    PLANNER = auto()
    EXECUTOR = auto()


class RiskLevel(Enum):
    """Risk assessment for task planning."""

    NONE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class ComplexityLevel(Enum):
    """Complexity classification for decomposition decisions."""

    TRIVIAL = auto()
    SIMPLE = auto()
    MODERATE = auto()
    COMPLEX = auto()
    VERY_COMPLEX = auto()


# ─── Value Objects ────────────────────────────────────────────────────────────

class TokenCount(BaseModel):
    """Token usage breakdown for cost optimization."""

    model_config = ConfigDict(frozen=True)

    prompt: int = Field(default=0, ge=0)
    completion: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)

    @field_validator("total", mode="before")
    @classmethod
    def compute_total(cls, v: int, info: Any) -> int:
        """Ensure total equals prompt + completion if not explicitly set."""
        if v == 0 and info.data.get("prompt") and info.data.get("completion"):
            return info.data["prompt"] + info.data["completion"]
        return v


class CostEstimate(BaseModel):
    """Monetary cost estimation for execution planning."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    estimated_tokens: TokenCount
    estimated_cost_usd: Decimal = Field(default=Decimal("0.0"), decimal_places=6)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class LatencyEstimate(BaseModel):
    """Performance prediction for routing decisions."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    estimated_ms: float = Field(default=0.0, ge=0.0)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    percentile_95_ms: Optional[float] = None


class CapabilityScore(BaseModel):
    """Quantified agent or model capability match."""

    model_config = ConfigDict(frozen=True)

    capability: str
    score: float = Field(ge=0.0, le=1.0)
    evidence: Optional[str] = None  # Reasoning for score


class QualityMetrics(BaseModel):
    """Standardized quality dimensions for verification."""

    model_config = ConfigDict(frozen=True)

    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    consistency: float = Field(default=0.0, ge=0.0, le=1.0)
    completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    overall: float = Field(default=0.0, ge=0.0, le=1.0)


# ─── Entity Models ──────────────────────────────────────────────────────────────

class ProviderModel(BaseModel):
    """Registered LLM provider with operational metadata."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str  # e.g., "openai", "anthropic", "groq"
    display_name: str
    base_url: Optional[str] = None
    api_key_env_var: str
    models: List[str] = Field(default_factory=list)
    status: ProviderStatus = ProviderStatus.HEALTHY
    priority: int = Field(default=5, ge=1, le=10)  # Lower = higher priority
    cost_profile: Dict[str, Decimal] = Field(default_factory=dict)  # per-model
    latency_profile_ms: Dict[str, float] = Field(default_factory=dict)
    capabilities: Set[str] = Field(default_factory=set)
    max_tokens: Dict[str, int] = Field(default_factory=dict)
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_health_check: Optional[datetime] = None


class AgentSpec(BaseModel):
    """Specialist agent registration for capability routing."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    role: AgentRole
    capabilities: Set[str] = Field(default_factory=set)
    model_preferences: List[str] = Field(default_factory=list)
    max_concurrency: int = Field(default=5, ge=1)
    current_load: int = Field(default=0, ge=0)
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    avg_latency_ms: float = Field(default=0.0, ge=0.0)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskIntent(BaseModel):
    """Extracted user intent from natural language input."""

    model_config = ConfigDict(frozen=True)

    raw_input: str
    goals: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    explicit_tools: List[str] = Field(default_factory=list)
    desired_output_format: Optional[str] = None
    urgency_indicators: List[str] = Field(default_factory=list)
    domain_hints: List[str] = Field(default_factory=list)
    estimated_complexity: ComplexityLevel = ComplexityLevel.MODERATE


class SubTask(BaseModel):
    """Atomic unit of work within an execution plan."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_id: Optional[uuid.UUID] = None
    name: str
    description: str
    required_capabilities: Set[str] = Field(default_factory=set)
    estimated_tokens: Optional[TokenCount] = None
    estimated_cost: Optional[CostEstimate] = None
    estimated_latency_ms: Optional[float] = None
    dependencies: Set[uuid.UUID] = Field(default_factory=set)
    priority: Priority = Priority.NORMAL
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    assigned_agent_id: Optional[uuid.UUID] = None
    assigned_provider: Optional[str] = None
    assigned_model: Optional[str] = None
    max_retries: int = Field(default=3, ge=0)
    timeout_seconds: float = Field(default=60.0, ge=0.0)
    context_window_size: int = Field(default=4096, ge=0)
    status: TaskStatus = TaskStatus.PENDING


class ExecutionPlan(BaseModel):
    """Complete orchestration plan for a user request."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    original_intent: TaskIntent
    root_task_id: uuid.UUID
    subtasks: List[SubTask] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.DAG
    total_estimated_cost: Optional[CostEstimate] = None
    total_estimated_latency_ms: Optional[float] = None
    risk_level: RiskLevel = RiskLevel.LOW
    parallelism_factor: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validated: bool = False


class WorkerResult(BaseModel):
    """Output from an individual worker/agent execution."""

    model_config = ConfigDict(frozen=True)

    task_id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    output: str
    token_usage: TokenCount = Field(default_factory=TokenCount)
    cost_usd: Decimal = Decimal("0.0")
    latency_ms: float = Field(default=0.0)
    quality: Optional[QualityMetrics] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationResult(BaseModel):
    """Final synthesized result delivered to the user."""

    model_config = ConfigDict(frozen=True)

    plan_id: uuid.UUID
    status: TaskStatus
    final_answer: str
    worker_results: List[WorkerResult] = Field(default_factory=list)
    total_tokens: TokenCount = Field(default_factory=TokenCount)
    total_cost_usd: Decimal = Decimal("0.0")
    total_latency_ms: float = Field(default=0.0)
    quality_score: Optional[QualityMetrics] = None
    providers_used: List[str] = Field(default_factory=list)
    agents_used: List[uuid.UUID] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Event Models ─────────────────────────────────────────────────────────────

class OrchestrationEvent(BaseModel):
    """Domain event for event-driven module communication."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    plan_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    provider: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    severity: str = "INFO"


# ─── Generic Types ────────────────────────────────────────────────────────────

T = TypeVar("T")
AsyncCallable = Callable[..., Coroutine[Any, Any, T]]
