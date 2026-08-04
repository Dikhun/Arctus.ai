"""Arctus AI Orchestration Framework - Abstract Protocols.

Defines the contracts (interfaces) that all Queen Module components
implement against. Enables loose coupling, testability, and plugin
architecture via structural subtyping.
"""

from __future__ import annotations

import uuid
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    runtime_checkable,
)

from domain_models import (
    AgentSpec,
    CapabilityScore,
    CostEstimate,
    ExecutionPlan,
    LatencyEstimate,
    OrchestrationEvent,
    OrchestrationResult,
    ProviderModel,
    QualityMetrics,
    SubTask,
    TaskIntent,
    TokenCount,
    WorkerResult,
)


# ─── Planning Protocols ───────────────────────────────────────────────────────

@runtime_checkable
class IntentAnalyzer(Protocol):
    """Extracts structured intent from natural language input."""

    async def analyze(self, raw_input: str, context: Optional[Dict[str, Any]] = None) -> TaskIntent:
        """Analyze raw user input and extract structured intent.

        Args:
            raw_input: The user's natural language request.
            context: Optional conversation or session context.

        Returns:
            Structured task intent with goals, constraints, and hints.
        """


@runtime_checkable
class PlanValidator(Protocol):
    """Validates generated execution plans for correctness and feasibility."""

    async def validate(self, plan: ExecutionPlan) -> tuple[bool, List[str]]:
        """Validate an execution plan.

        Args:
            plan: The execution plan to validate.

        Returns:
            Tuple of (is_valid, list_of_violation_messages).
        """


@runtime_checkable
class ExecutionPlanner(Protocol):
    """Generates optimized execution plans from task intents."""

    async def create_plan(self, intent: TaskIntent, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """Create an execution plan from analyzed intent.

        Args:
            intent: Structured task intent.
            context: Optional historical or session context.

        Returns:
            Complete execution plan with subtasks and dependencies.
        """


# ─── Routing Protocols ────────────────────────────────────────────────────────

@runtime_checkable
class ModelRouter(Protocol):
    """Selects optimal LLM provider and model for a task."""

    async def route(
        self,
        task: SubTask,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:  # (provider_name, model_name)
        """Select provider and model for task execution.

        Args:
            task: The subtask requiring model assignment.
            preferences: Optional routing preferences (cost, latency, quality).

        Returns:
            Selected provider name and model name.
        """


@runtime_checkable
class CapabilityRouter(Protocol):
    """Matches tasks with specialist agents based on capability requirements."""

    async def match_agent(
        self,
        task: SubTask,
        available_agents: List[AgentSpec],
    ) -> Optional[AgentSpec]:
        """Find best matching agent for a task.

        Args:
            task: The subtask requiring agent assignment.
            available_agents: Pool of currently available agents.

        Returns:
            Best matching agent spec, or None if no match.
        """

    async def score_capabilities(
        self,
        task: SubTask,
        agent: AgentSpec,
    ) -> List[CapabilityScore]:
        """Score how well an agent matches task capabilities.

        Args:
            task: The subtask to evaluate.
            agent: The agent to score.

        Returns:
            List of capability scores with evidence.
        """


# ─── Workflow and Graph Protocols ─────────────────────────────────────────────

@runtime_checkable
class WorkflowPlanner(Protocol):
    """Generates execution workflows and directed acyclic graphs."""

    async def build_dag(self, plan: ExecutionPlan) -> Dict[uuid.UUID, Set[uuid.UUID]]:
        """Build dependency DAG from execution plan.

        Args:
            plan: Execution plan containing subtasks.

        Returns:
            Adjacency list mapping task_id -> set of dependent task_ids.
        """


@runtime_checkable
class DependencyResolver(Protocol):
    """Analyzes and orders task dependencies."""

    async def detect_cycles(self, graph: Dict[uuid.UUID, Set[uuid.UUID]]) -> Optional[List[uuid.UUID]]:
        """Detect cycles in dependency graph.

        Args:
            graph: Adjacency list representation.

        Returns:
            Cycle path if found, None if acyclic.
        """

    async def topological_sort(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
        tasks: Dict[uuid.UUID, SubTask],
    ) -> List[List[uuid.UUID]]:
        """Generate execution levels via topological sort.

        Args:
            graph: Adjacency list of dependencies.
            tasks: Mapping of task_id to SubTask.

        Returns:
            List of execution levels, each containing parallelizable task IDs.
        """


# ─── Execution Protocols ──────────────────────────────────────────────────────

@runtime_checkable
class AgentAllocator(Protocol):
    """Allocates and schedules agents for task execution."""

    async def allocate(self, tasks: List[SubTask], agents: List[AgentSpec]) -> Dict[uuid.UUID, uuid.UUID]:
        """Allocate agents to tasks.

        Args:
            tasks: Tasks requiring agent assignment.
            agents: Available agent pool.

        Returns:
            Mapping of task_id -> agent_id.
        """


@runtime_checkable
class TaskDispatcher(Protocol):
    """Dispatches tasks to workers and monitors execution."""

    async def dispatch(
        self,
        task: SubTask,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkerResult:
        """Dispatch a single task to its assigned worker.

        Args:
            task: The subtask to execute.
            prompt: Framed prompt for the worker.
            context: Execution context.

        Returns:
            Worker execution result.
        """

    async def dispatch_parallel(
        self,
        tasks: List[SubTask],
        prompts: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[WorkerResult]:
        """Dispatch multiple tasks in parallel.

        Args:
            tasks: Subtasks to execute concurrently.
            prompts: Corresponding framed prompts.
            context: Shared execution context.

        Returns:
            List of worker results in task order.
        """


@runtime_checkable
class ExecutionPolicy(Protocol):
    """Defines execution strategies and policies."""

    async def execute(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[WorkerResult]:
        """Execute plan according to policy.

        Args:
            plan: The execution plan.
            dispatcher: Task dispatcher for actual execution.
            context: Execution context.

        Returns:
            Collected worker results.
        """


# ─── Context and Prompt Protocols ─────────────────────────────────────────────

@runtime_checkable
class ContextExtractor(Protocol):
    """Extracts and optimizes relevant context for tasks."""

    async def extract(
        self,
        task: SubTask,
        conversation_history: List[Dict[str, Any]],
        max_tokens: int,
    ) -> str:
        """Extract relevant context for a task.

        Args:
            task: The subtask requiring context.
            conversation_history: Full conversation history.
            max_tokens: Maximum tokens for context window.

        Returns:
            Optimized context string.
        """


@runtime_checkable
class PromptFramer(Protocol):
    """Generates optimized prompts for workers."""

    async def frame_worker_prompt(
        self,
        task: SubTask,
        context: str,
        style: Optional[str] = None,
    ) -> str:
        """Generate worker prompt for task execution.

        Args:
            task: The subtask to frame.
            context: Extracted relevant context.
            style: Optional prompt style override.

        Returns:
            Framed prompt string.
        """

    async def frame_system_prompt(
        self,
        agent_role: str,
        capabilities: Set[str],
        constraints: List[str],
    ) -> str:
        """Generate system prompt for agent initialization.

        Args:
            agent_role: Role identifier.
            capabilities: Agent capabilities.
            constraints: Operational constraints.

        Returns:
            System prompt string.
        """


# ─── Memory Protocols ─────────────────────────────────────────────────────────

@runtime_checkable
class MemoryRouter(Protocol):
    """Routes memory operations to appropriate memory backends."""

    async def select_memory(
        self,
        task: SubTask,
        memory_types: List[str],
    ) -> List[str]:
        """Select relevant memory sources for a task.

        Args:
            task: The subtask to find memory for.
            memory_types: Available memory type identifiers.

        Returns:
            Selected memory source identifiers.
        """


# ─── Verification Protocols ─────────────────────────────────────────────────────

@runtime_checkable
class VerificationManager(Protocol):
    """Verifies and scores worker outputs."""

    async def verify(
        self,
        result: WorkerResult,
        task: SubTask,
        expected_format: Optional[str] = None,
    ) -> QualityMetrics:
        """Verify a worker result.

        Args:
            result: The worker output to verify.
            task: Original task specification.
            expected_format: Expected output format.

        Returns:
            Quality metrics for the result.
        """


# ─── Cost and Health Protocols ────────────────────────────────────────────────

@runtime_checkable
class CostOptimizer(Protocol):
    """Optimizes and tracks execution costs."""

    async def estimate_cost(self, plan: ExecutionPlan) -> CostEstimate:
        """Estimate total cost for executing a plan.

        Args:
            plan: The execution plan.

        Returns:
            Aggregated cost estimate.
        """

    async def optimize_tokens(self, text: str, target_tokens: int) -> str:
        """Compress text to fit token budget.

        Args:
            text: Source text.
            target_tokens: Target token count.

        Returns:
            Optimized text.
        """


@runtime_checkable
class ProviderHealthMonitor(Protocol):
    """Monitors provider health and manages failover."""

    async def check_health(self, provider: ProviderModel) -> bool:
        """Check if provider is healthy.

        Args:
            provider: Provider to check.

        Returns:
            True if healthy.
        """

    async def get_stats(self, provider_name: str) -> Dict[str, Any]:
        """Get provider statistics.

        Args:
            provider_name: Provider identifier.

        Returns:
            Provider statistics dictionary.
        """


# ─── Retry and Circuit Breaker Protocols ──────────────────────────────────────

@runtime_checkable
class RetryManager(Protocol):
    """Manages retry logic with backoff strategies."""

    async def execute_with_retry(
        self,
        operation: Callable[..., Any],
        max_retries: int = 3,
        exceptions: Optional[tuple] = None,
    ) -> Any:
        """Execute operation with retry logic.

        Args:
            operation: Async callable to execute.
            max_retries: Maximum retry attempts.
            exceptions: Tuple of exceptions to catch.

        Returns:
            Operation result.
        """


@runtime_checkable
class CircuitBreaker(Protocol):
    """Circuit breaker pattern for provider resilience."""

    async def call(self, operation: Callable[..., Any], provider: str) -> Any:
        """Execute operation through circuit breaker.

        Args:
            operation: Async callable.
            provider: Provider identifier for circuit tracking.

        Returns:
            Operation result or raises CircuitBreakerException.
        """


# ─── Learning and Synthesis Protocols ─────────────────────────────────────────

@runtime_checkable
class LearningManager(Protocol):
    """Tracks execution analytics and adapts strategies."""

    async def record_execution(self, result: OrchestrationResult) -> None:
        """Record execution result for learning.

        Args:
            result: Completed orchestration result.
        """

    async def get_strategy(self, task_type: str) -> Dict[str, Any]:
        """Get learned strategy for task type.

        Args:
            task_type: Classification of task.

        Returns:
            Strategy parameters.
        """


@runtime_checkable
class Synthesizer(Protocol):
    """Merges worker outputs into coherent final answers."""

    async def synthesize(
        self,
        results: List[WorkerResult],
        original_intent: TaskIntent,
    ) -> str:
        """Synthesize final answer from worker results.

        Args:
            results: Collected worker outputs.
            original_intent: Original user intent.

        Returns:
            Synthesized final answer.
        """


# ─── Event Bus Protocol ───────────────────────────────────────────────────────

@runtime_checkable
class EventPublisher(Protocol):
    """Publishes events to the event bus."""

    async def publish(self, event: OrchestrationEvent) -> None:
        """Publish event.

        Args:
            event: Event to publish.
        """


@runtime_checkable
class EventSubscriber(Protocol):
    """Subscribes to events from the event bus."""

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[OrchestrationEvent], Any],
    ) -> None:
        """Subscribe to event type.

        Args:
            event_type: Event type to subscribe to.
            handler: Async handler function.
        """
