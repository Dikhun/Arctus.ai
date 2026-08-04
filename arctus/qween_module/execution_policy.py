"""Arctus AI Orchestration Framework - Execution Policy.

Responsible for sequential execution, parallel execution,
retry policy, escalation policy, and timeout policy.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from domain_models import ExecutionMode, ExecutionPlan, SubTask, TaskStatus, WorkerResult
from exceptions import (
    ErrorContext,
    ExecutionException,
    TimeoutException,
    WorkerException,
)
from infrastructure import LogContext, async_timed, gather_with_concurrency, get_logger
from protocols import ExecutionPolicy, TaskDispatcher


logger = get_logger("execution_policy")


@dataclass
class RetryPolicy:
    """Configurable retry behavior."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (Exception,)
    on_retry_callback: Optional[Callable[[int, Exception], Any]] = None


@dataclass
class TimeoutPolicy:
    """Configurable timeout behavior."""

    default_timeout_seconds: float = 60.0
    max_timeout_seconds: float = 300.0
    graceful_shutdown_seconds: float = 5.0


@dataclass
class EscalationPolicy:
    """Configurable escalation behavior."""

    enabled: bool = True
    escalation_threshold: int = 2  # Failures before escalation
    escalate_to: Optional[str] = None  # Target agent/role
    notify_channels: List[str] = field(default_factory=list)


class ExecutionPolicyImpl(ExecutionPolicy):
    """Production execution policy with multiple execution modes.

    Implements sequential, parallel, pipeline, and DAG execution
    with integrated retry, timeout, and escalation handling.
    """

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        escalation_policy: Optional[EscalationPolicy] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_policy = timeout_policy or TimeoutPolicy()
        self.escalation_policy = escalation_policy or EscalationPolicy()
        self.event_bus = event_bus
        self.logger = get_logger("execution_policy")
        self._failure_counts: Dict[uuid.UUID, int] = {}

    @async_timed
    async def execute(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[WorkerResult]:
        """Execute plan according to its execution mode.

        Args:
            plan: The execution plan.
            dispatcher: Task dispatcher for actual execution.
            context: Execution context.

        Returns:
            Collected worker results.
        """
        with LogContext(module="execution_policy", operation="execute", plan_id=plan.id):
            self.logger.info(
                "Executing plan",
                extra={
                    "plan_id": str(plan.id),
                    "mode": plan.execution_mode.name,
                    "subtasks": len(plan.subtasks),
                },
            )

            if plan.execution_mode == ExecutionMode.SEQUENTIAL:
                results = await self._execute_sequential(plan, dispatcher, context)
            elif plan.execution_mode == ExecutionMode.PARALLEL:
                results = await self._execute_parallel(plan, dispatcher, context)
            elif plan.execution_mode == ExecutionMode.PIPELINE:
                results = await self._execute_pipeline(plan, dispatcher, context)
            elif plan.execution_mode == ExecutionMode.DAG:
                results = await self._execute_dag(plan, dispatcher, context)
            else:
                results = await self._execute_sequential(plan, dispatcher, context)

            self.logger.info(
                "Execution complete",
                extra={
                    "plan_id": str(plan.id),
                    "results": len(results),
                    "failures": sum(1 for r in results if not getattr(r, 'success', True)),
                },
            )

            return results

    async def _execute_sequential(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> List[WorkerResult]:
        """Execute all tasks sequentially in plan order.

        Args:
            plan: Execution plan.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker results in task order.
        """
        results: List[WorkerResult] = []

        for task in plan.subtasks:
            result = await self._execute_with_retry(task, dispatcher, context)
            results.append(result)

            # Check for escalation
            if self._should_escalate(task, result):
                await self._escalate(task, result, dispatcher, context)

        return results

    async def _execute_parallel(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> List[WorkerResult]:
        """Execute all tasks in parallel.

        Args:
            plan: Execution plan.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker results in task order.
        """
        # Prepare prompts (would integrate with prompt_framer)
        prompts = [f"Execute: {task.description}" for task in plan.subtasks]

        # Use gather with concurrency limit
        max_parallel = plan.parallelism_factor

        coros = [
            self._execute_with_retry(task, dispatcher, context)
            for task in plan.subtasks
        ]

        return await gather_with_concurrency(max_parallel, *coros)

    async def _execute_pipeline(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> List[WorkerResult]:
        """Execute tasks in pipeline stages.

        Args:
            plan: Execution plan.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker results.
        """
        # Group tasks by pipeline stage
        # For simplicity, execute in waves based on dependencies
        from dependency_graph import DependencyGraphImpl
        from workflow_planner import WorkflowPlannerImpl

        workflow = WorkflowPlannerImpl()
        graph = await workflow.build_execution_graph(plan)

        results: List[WorkerResult] = []
        completed: Dict[uuid.UUID, WorkerResult] = {}

        for level in graph.levels:
            level_tasks = [t for t in plan.subtasks if t.id in level]
            level_prompts = [f"Execute: {task.description}" for task in level_tasks]

            # Build context from previous results
            level_context = dict(context or {})
            for tid, result in completed.items():
                level_context[f"result_{tid}"] = result.output

            # Execute level
            level_results = await gather_with_concurrency(
                len(level_tasks),
                *[
                    self._execute_with_retry(task, dispatcher, level_context)
                    for task in level_tasks
                ]
            )

            for task, result in zip(level_tasks, level_results):
                completed[task.id] = result
                results.append(result)

        return results

    async def _execute_dag(
        self,
        plan: ExecutionPlan,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> List[WorkerResult]:
        """Execute tasks respecting DAG dependencies.

        Args:
            plan: Execution plan.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker results.
        """
        from dependency_graph import DependencyGraphImpl

        dep_graph = DependencyGraphImpl()

        # Build adjacency
        adj: Dict[uuid.UUID, Set[uuid.UUID]] = {t.id: t.dependencies for t in plan.subtasks}
        task_map = {t.id: t for t in plan.subtasks}

        try:
            levels = await dep_graph.topological_sort(adj, task_map)
        except Exception as e:
            self.logger.error("DAG execution failed", extra={"error": str(e)})
            raise ExecutionException(
                f"DAG execution failed: {e}",
                context=ErrorContext(
                    module="execution_policy",
                    operation="execute_dag",
                    task_id=plan.root_task_id,
                ),
            )

        results: List[WorkerResult] = []
        completed: Dict[uuid.UUID, WorkerResult] = {}

        for level in levels:
            level_tasks = [task_map[tid] for tid in level if tid in task_map]

            # Build context from dependencies
            level_context = dict(context or {})
            for tid, result in completed.items():
                level_context[f"result_{tid}"] = result.output

            level_results = await gather_with_concurrency(
                len(level_tasks),
                *[
                    self._execute_with_retry(task, dispatcher, level_context)
                    for task in level_tasks
                ]
            )

            for task, result in zip(level_tasks, level_results):
                completed[task.id] = result
                results.append(result)

        return results

    async def _execute_with_retry(
        self,
        task: SubTask,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> WorkerResult:
        """Execute single task with retry logic.

        Args:
            task: Task to execute.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker result, potentially from successful retry.
        """
        last_exception: Optional[Exception] = None
        prompt = f"Execute: {task.description}"  # Simplified; would use prompt_framer

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                # Apply timeout
                timeout = min(task.timeout_seconds, self.timeout_policy.max_timeout_seconds)

                result = await asyncio.wait_for(
                    dispatcher.dispatch(task, prompt, context),
                    timeout=timeout,
                )

                # Success - reset failure count
                self._failure_counts.pop(task.id, None)

                if attempt > 0:
                    self.logger.info(
                        "Task succeeded after retry",
                        extra={"task_id": str(task.id), "attempt": attempt + 1},
                    )

                return result

            except asyncio.TimeoutError:
                last_exception = TimeoutException(
                    f"Task {task.id} timed out after {timeout}s",
                    allocated_seconds=timeout,
                    context=ErrorContext(
                        module="execution_policy",
                        operation="execute_with_retry",
                        task_id=task.id,
                    ),
                )
            except self.retry_policy.retryable_exceptions as e:
                last_exception = e

            # Retry logic
            if attempt < self.retry_policy.max_retries:
                delay = min(
                    self.retry_policy.base_delay_seconds * (
                        self.retry_policy.exponential_base ** attempt
                    ),
                    self.retry_policy.max_delay_seconds,
                )

                self.logger.warning(
                    "Task failed, retrying",
                    extra={
                        "task_id": str(task.id),
                        "attempt": attempt + 1,
                        "delay": delay,
                        "error": str(last_exception),
                    },
                )

                if self.retry_policy.on_retry_callback:
                    self.retry_policy.on_retry_callback(attempt + 1, last_exception)

                await asyncio.sleep(delay)

        # All retries exhausted
        self._failure_counts[task.id] = self._failure_counts.get(task.id, 0) + 1

        self.logger.error(
            "Task failed after all retries",
            extra={
                "task_id": str(task.id),
                "attempts": self.retry_policy.max_retries + 1,
                "last_error": str(last_exception),
            },
        )

        # Return failure result
        return WorkerResult(
            task_id=task.id,
            output=f"FAILED: {last_exception}",
            latency_ms=0.0,
            metadata={"error": str(last_exception), "retries_exhausted": True},
        )

    def _should_escalate(self, task: SubTask, result: WorkerResult) -> bool:
        """Check if task failure warrants escalation.

        Args:
            task: Executed task.
            result: Execution result.

        Returns:
            True if escalation needed.
        """
        if not self.escalation_policy.enabled:
            return False

        failures = self._failure_counts.get(task.id, 0)
        return failures >= self.escalation_policy.escalation_threshold

    async def _escalate(
        self,
        task: SubTask,
        result: WorkerResult,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]],
    ) -> None:
        """Escalate failed task.

        Args:
            task: Failed task.
            result: Failure result.
            dispatcher: Dispatcher.
            context: Execution context.
        """
        self.logger.critical(
            "Escalating task",
            extra={
                "task_id": str(task.id),
                "escalate_to": self.escalation_policy.escalate_to,
                "channels": self.escalation_policy.notify_channels,
            },
        )

        if self.event_bus:
            await self.event_bus.publish(
                OrchestrationEvent(
                    event_type="task_escalated",
                    task_id=task.id,
                    payload={
                        "escalate_to": self.escalation_policy.escalate_to,
                        "failure_count": self._failure_counts.get(task.id, 0),
                    },
                )
            )

    async def execute_single(
        self,
        task: SubTask,
        dispatcher: TaskDispatcher,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkerResult:
        """Execute single task with full policy application.

        Args:
            task: Task to execute.
            dispatcher: Task dispatcher.
            context: Execution context.

        Returns:
            Worker result.
        """
        return await self._execute_with_retry(task, dispatcher, context)


# Factory
async def create_execution_policy(
    retry_policy: Optional[RetryPolicy] = None,
    timeout_policy: Optional[TimeoutPolicy] = None,
    escalation_policy: Optional[EscalationPolicy] = None,
    event_bus: Optional[Any] = None,
) -> ExecutionPolicyImpl:
    """Factory for creating configured execution policy.

    Args:
        retry_policy: Retry configuration.
        timeout_policy: Timeout configuration.
        escalation_policy: Escalation configuration.
        event_bus: Optional event bus.

    Returns:
        Configured ExecutionPolicyImpl.
    """
    return ExecutionPolicyImpl(
        retry_policy=retry_policy,
        timeout_policy=timeout_policy,
        escalation_policy=escalation_policy,
        event_bus=event_bus,
    )


from dataclasses import field
from domain_models import OrchestrationEvent
