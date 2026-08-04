"""Arctus AI Orchestration Framework - Custom Exception Hierarchy.

This module defines the complete exception hierarchy for the Queen Module
subsystem, enabling precise error handling, structured logging, and
graceful degradation across all orchestration components.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class ErrorSeverity(Enum):
    """Classification of error impact on system operation."""

    CRITICAL = auto()  # System-wide failure, immediate halt required
    HIGH = auto()  # Component failure, escalation required
    MEDIUM = auto()  # Degraded operation, retry may succeed
    LOW = auto()  # Minor issue, operation can continue
    WARNING = auto()  # Informational, no operational impact


class ErrorCategory(Enum):
    """Domain classification for error routing and handling."""

    ORCHESTRATION = auto()
    PLANNING = auto()
    ROUTING = auto()
    EXECUTION = auto()
    MEMORY = auto()
    VERIFICATION = auto()
    NETWORK = auto()
    PROVIDER = auto()
    AUTHENTICATION = auto()
    VALIDATION = auto()
    RESOURCE = auto()
    TIMEOUT = auto()
    CIRCUIT_BREAKER = auto()
    LEARNING = auto()
    SYNTHESIS = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class ErrorContext:
    """Structured context attached to every exception for observability.

    Attributes:
        module: Source module identifier.
        operation: Operation being performed when error occurred.
        task_id: Associated task identifier, if any.
        agent_id: Associated agent identifier, if any.
        provider: Associated provider identifier, if any.
        retry_count: Number of retries attempted so far.
        metadata: Additional structured context.
    """

    module: str = "unknown"
    operation: str = "unknown"
    task_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    provider: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ArctusException(Exception):
    """Base exception for all Arctus framework errors.

    All exceptions in the Queen Module hierarchy inherit from this class,
    ensuring consistent structured logging and error propagation.

    Attributes:
        message: Human-readable error description.
        severity: Impact level of this error.
        category: Domain classification for routing.
        context: Structured operational context.
        cause: Original exception if wrapped.
    """

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.category = category
        self.context = context or ErrorContext()
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        """Serialize exception to structured dictionary for logging."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.name,
            "category": self.category.name,
            "context": {
                "module": self.context.module,
                "operation": self.context.operation,
                "task_id": str(self.context.task_id) if self.context.task_id else None,
                "agent_id": str(self.context.agent_id) if self.context.agent_id else None,
                "provider": self.context.provider,
                "retry_count": self.context.retry_count,
                "metadata": self.context.metadata,
            },
            "cause": str(self.cause) if self.cause else None,
        }


# ─── Orchestration Errors ─────────────────────────────────────────────────────

class OrchestrationException(ArctusException):
    """Base for orchestration lifecycle errors."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.ORCHESTRATION,
            context=context,
            cause=cause,
        )


class QueenBrainException(OrchestrationException):
    """Central controller failure or invalid state transition."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            cause=cause,
        )


class LifecycleException(OrchestrationException):
    """Invalid orchestration lifecycle operation."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )


# ─── Planning Errors ──────────────────────────────────────────────────────────

class PlanningException(ArctusException):
    """Task planning and decomposition failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.PLANNING,
            context=context,
            cause=cause,
        )


class DecompositionException(PlanningException):
    """Task decomposition into subtasks failed."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )


class ConstraintViolationException(PlanningException):
    """Task constraints cannot be satisfied."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            cause=cause,
        )


class PlanValidationException(PlanningException):
    """Generated execution plan failed validation."""

    def __init__(
        self,
        message: str,
        *,
        violations: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )
        self.violations = violations or []


# ─── Routing Errors ───────────────────────────────────────────────────────────

class RoutingException(ArctusException):
    """Model or capability routing failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.ROUTING,
            context=context,
            cause=cause,
        )


class ModelRouterException(RoutingException):
    """LLM provider or model selection failure."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )


class CapabilityRouterException(RoutingException):
    """Specialist agent matching failure."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )


class NoProviderAvailableException(ModelRouterException):
    """All providers exhausted or unavailable."""

    def __init__(
        self,
        message: str = "No LLM providers available for routing",
        *,
        attempted_providers: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            cause=cause,
        )
        self.attempted_providers = attempted_providers or []


class NoAgentAvailableException(CapabilityRouterException):
    """No specialist agent matches required capabilities."""

    def __init__(
        self,
        message: str = "No agents available with required capabilities",
        *,
        required_capabilities: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )
        self.required_capabilities = required_capabilities or []


# ─── Execution Errors ─────────────────────────────────────────────────────────

class ExecutionException(ArctusException):
    """Task execution and dispatch failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.EXECUTION,
            context=context,
            cause=cause,
        )


class DispatcherException(ExecutionException):
    """Async task dispatch failure."""

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )


class WorkerException(ExecutionException):
    """Individual worker task failure."""

    def __init__(
        self,
        message: str,
        *,
        worker_id: Optional[uuid.UUID] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            cause=cause,
        )
        self.worker_id = worker_id


class TimeoutException(ExecutionException):
    """Operation exceeded allocated time budget."""

    def __init__(
        self,
        message: str,
        *,
        allocated_seconds: Optional[float] = None,
        elapsed_seconds: Optional[float] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.TIMEOUT,
            context=context,
            cause=cause,
        )
        self.allocated_seconds = allocated_seconds
        self.elapsed_seconds = elapsed_seconds


# ─── Graph and Dependency Errors ────────────────────────────────────────────

class DependencyException(ArctusException):
    """Dependency graph and topological operation failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.VALIDATION,
            context=context,
            cause=cause,
        )


class CycleDetectedException(DependencyException):
    """Circular dependency detected in task graph."""

    def __init__(
        self,
        message: str,
        *,
        cycle_path: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            cause=cause,
        )
        self.cycle_path = cycle_path or []


# ─── Memory Errors ──────────────────────────────────────────────────────────────

class MemoryException(ArctusException):
    """Memory routing and retrieval failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.MEMORY,
            context=context,
            cause=cause,
        )


# ─── Verification Errors ──────────────────────────────────────────────────────

class VerificationException(ArctusException):
    """Output verification and quality assurance failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.VERIFICATION,
            context=context,
            cause=cause,
        )


class QualityThresholdException(VerificationException):
    """Output quality below acceptable threshold."""

    def __init__(
        self,
        message: str,
        *,
        score: Optional[float] = None,
        threshold: Optional[float] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            cause=cause,
        )
        self.score = score
        self.threshold = threshold


# ─── Provider and Network Errors ───────────────────────────────────────────────

class ProviderException(ArctusException):
    """External provider (LLM API) failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.PROVIDER,
            context=context,
            cause=cause,
        )
        self.provider = provider
        self.status_code = status_code


class ProviderHealthException(ArctusException):
    """Provider health monitoring and failover events."""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.PROVIDER,
            context=context,
            cause=cause,
        )
        self.provider = provider


class AuthenticationException(ArctusException):
    """API key or credential failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.AUTHENTICATION,
            context=context,
            cause=cause,
        )
        self.provider = provider


# ─── Resource and Budget Errors ───────────────────────────────────────────────

class ResourceException(ArctusException):
    """Resource exhaustion or allocation failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=severity,
            category=ErrorCategory.RESOURCE,
            context=context,
            cause=cause,
        )


class BudgetExceededException(ResourceException):
    """Cost or token budget exceeded."""

    def __init__(
        self,
        message: str,
        *,
        budget_type: str = "unknown",
        limit: Optional[float] = None,
        current: Optional[float] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            cause=cause,
        )
        self.budget_type = budget_type
        self.limit = limit
        self.current = current


# ─── Circuit Breaker and Retry Errors ─────────────────────────────────────────

class CircuitBreakerException(ArctusException):
    """Circuit breaker open or half-open state rejection."""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        open_duration: Optional[float] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.CIRCUIT_BREAKER,
            context=context,
            cause=cause,
        )
        self.provider = provider
        self.open_duration = open_duration


class RetryExhaustedException(ArctusException):
    """All retry attempts consumed without success."""

    def __init__(
        self,
        message: str,
        *,
        max_retries: int = 0,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause,
        )
        self.max_retries = max_retries


# ─── Synthesis Errors ───────────────────────────────────────────────────────────

class SynthesisException(ArctusException):
    """Output merging and final answer generation failures."""

    def __init__(
        self,
        message: str,
        *,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Optional[ErrorContext] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
      
