
"""Arctus AI Orchestration Framework - Dispatcher.

Responsible for async task execution, parallel dispatch,
worker lifecycle, and task monitoring.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from domain_models import SubTask, TaskStatus, WorkerResult
from exceptions import DispatcherException, ErrorContext, WorkerException
from infrastructure import LogContext, async_timed, gather_with_concurrency, get_logger
from protocols import TaskDispatcher


logger = get_logger("dispatcher")


@dataclass
class WorkerHandle:
    """Handle to a dispatched worker task."""

    task_id: uuid.UUID
    future: asyncio.Future[WorkerResult]
    start_time: float
    timeout_seconds: float
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class DispatcherImpl(TaskDispatcher):
    """Production async task dispatcher with lifecycle management.

    Manages worker execution, parallel dispatch, monitoring,
    and graceful shutdown.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 50,
        worker_factory: Optional[Callable[[SubTask, str, Optional[Dict[str, Any]]], Coroutine[Any, Any, WorkerResult]]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.max_concurrent = max_concurrent_tasks
        self.worker_factory = worker_factory or self._default_worker
        self.event_bus = event_bus
        self.logger = get_logger("dispatcher")
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._active_workers: Dict[uuid.UUID, WorkerHandle] = {}
        self._completed_results: Dict[uuid.UUID, WorkerResult] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False

    @async_timed
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

        Raises:
            DispatcherException: If dispatch fails.
        """
        with LogContext(module="dispatcher", operation="dispatch", task_id=task.id):
            if self._shutdown:
                raise DispatcherException(
                    "Dispatcher is shutting down",
                    context=ErrorContext(
                        module="dispatcher",
                        operation="dispatch",
                        task_id=task.id,
                    ),
                )

            self.logger.info(
                "Dispatching task",
                extra={
                    "task_id": str(task.id),
                    "agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                    "provider": task.assigned_provider,
                },
            )

            async with self._semaphore:
                start_time = time.perf_counter()
                try:
                    result = await self._execute_worker(task, prompt, context)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Enhance result with timing
                    result = result.model_copy(update={"latency_ms": elapsed_ms})

                    async with self._lock:
                        self._completed_results[task.id] = result

                    self.logger.info(
                        "Task completed",
                        extra={
                            "task_id": str(task.id),
                            "latency_ms": elapsed_ms,
                            "success": not result.output.startswith("FAILED"),
                        },
                    )

                    if self.event_bus:
                        await self.event_bus.publish(
                            OrchestrationEvent(
                                event_type="task_completed",
                                task_id=task.id,
                                payload={
                                    "latency_ms": elapsed_ms,
                                    "provider": task.assigned_provider,
                                    "model": task.assigned_model,
                                },
                            )
                        )

                    return result

                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    self.logger.error(
                        "Task failed",
                        extra={
                            "task_id": str(task.id),
                            "error": str(e),
                            "latency_ms": elapsed_ms,
                        },
                    )
                    raise WorkerException(
                        f"Worker execution failed: {e}",
                        worker_id=task.assigned_agent_id,
                        context=ErrorContext(
                            module="dispatcher",
                            operation="dispatch",
                            task_id=task.id,
                        ),
                        cause=e,
                    )

    @async_timed
    async def dispatch_parallel(
        self,
        tasks: List[SubTask],
        prompts: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[WorkerResult]:
        """Dispatch multiple tasks in parallel with concurrency control.

        Args:
            tasks: Subtasks to execute concurrently.
            prompts: Corresponding framed prompts.
            context: Shared execution context.

        Returns:
            List of worker results in task order.
        """
        with LogContext(module="dispatcher", operation="dispatch_parallel"):
            if len(tasks) != len(prompts):
                raise DispatcherException(
                    f"Task/prompt count mismatch: {len(tasks)} vs {len(prompts)}",
                    context=ErrorContext(
                        module="dispatcher",
                        operation="dispatch_parallel",
                    ),
                )

            self.logger.info(
                "Dispatching parallel batch",
                extra={"batch_size": len(tasks), "max_concurrent": self.max_concurrent},
            )

            # Create coroutines
            coros = [
                self.dispatch(task, prompt, context)
                for task, prompt in zip(tasks, prompts)
            ]

            # Execute with gather and return_exceptions to handle partial failures
            results = await asyncio.gather(*coros, return_exceptions=True)

            # Convert exceptions to failure results
            processed: List[WorkerResult] = []
            for task, result in zip(tasks, results):
                if isinstance(result, Exception):
                    processed.append(WorkerResult(
                        task_id=task.id,
                        output=f"FAILED: {result}",
                        latency_ms=0.0,
                        metadata={"error": str(result), "exception_type": type(result).__name__},
                    ))
                else:
                    processed.append(result)

            success_count = sum(1 for r in processed if not r.output.startswith("FAILED"))
            self.logger.info(
                "Parallel batch complete",
                extra={
                    "total": len(processed),
                    "success": success_count,
                    "failed": len(processed) - success_count,
                },
            )

            return processed

    async def _execute_worker(
        self,
        task: SubTask,
        prompt: str,
        context: Optional[Dict[str, Any]],
    ) -> WorkerResult:
        """Execute worker with the configured factory.

        Args:
            task: Task to execute.
            prompt: Worker prompt.
            context: Execution context.

        Returns:
            Worker result.
        """
        return await self.worker_factory(task, prompt, context)

    async def _default_worker(
        self,
        task: SubTask,
        prompt: str,
        context: Optional[Dict[str, Any]],
    ) -> WorkerResult:
        """Default worker implementation.

        In production, this delegates to actual LLM client or agent.
        This default simulates execution for testing.

        Args:
            task: Task to execute.
            prompt: Worker prompt.
            context: Execution context.

        Returns:
            Simulated worker result.
        """
        # Simulate async work
        await asyncio.sleep(0.1)

        return WorkerResult(
            task_id=task.id,
            agent_id=task.assigned_agent_id,
            provider=task.assigned_provider or "default",
            model=task.assigned_model or "default",
            output=f"Completed task: {task.description[:50]}...",
            latency_ms=100.0,
        )

    async def monitor_task(self, task_id: uuid.UUID) -> Optional[WorkerResult]:
        """Monitor task status and retrieve result when complete.

        Args:
            task_id: Task to monitor.

        Returns:
            Result if complete, None if still running or unknown.
        """
        async with self._lock:
            if task_id in self._completed_results:
                return self._completed_results[task_id]

            handle = self._active_workers.get(task_id)
            if handle and handle.future.done():
                try:
                    result = handle.future.result()
                    self._completed_results[task_id] = result
                    return result
                except Exception:
                    return None

        return None

    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        """Cancel a running task.

        Args:
            task_id: Task to cancel.

        Returns:
            True if cancellation succeeded.
        """
        async with self._lock:
            handle = self._active_workers.get(task_id)
            if not handle:
                return False

            handle.cancel_event.set()
            if not handle.future.done():
                handle.future.cancel()

            return True

    async def get_active_tasks(self) -> List[uuid.UUID]:
        """Get list of currently active task IDs.

        Returns:
            Active task IDs.
        """
        async with self._lock:
            return [
                tid for tid, handle in self._active_workers.items()
                if not handle.future.done()
            ]

    async def get_stats(self) -> Dict[str, Any]:
        """Get dispatcher statistics.

        Returns:
            Statistics dictionary.
        """
        async with self._lock:
            active = sum(1 for h in self._active_workers.values() if not h.future.done())
            completed = len(self._completed_results)

        return {
            "active_tasks": active,
            "completed_tasks": completed,
            "max_concurrent": self.max_concurrent,
            "semaphore_value": self._semaphore._value,  # type: ignore
        }

    async def shutdown(self, timeout_seconds: float = 30.0) -> None:
        """Gracefully shut down dispatcher.

        Args:
            timeout_seconds: Timeout for graceful shutdown.
        """
        self._shutdown = True
        self.logger.info("Dispatcher shutting down", extra={"timeout": timeout_seconds})

        async with self._lock:
            active = list(self._active_workers.values())

        if active:
            # Wait for active tasks with timeout
            pending = [h.future for h in active if not h.future.done()]
            if pending:
                done, pending = await asyncio.wait(
                    pending,  # type: ignore
                    timeout=timeout_seconds,
                    return_when=asyncio.ALL_COMPLETED,
                )

            # Cancel remaining
            for fut in pending:  # type: ignore
                fut.cancel()

        self.logger.info("Dispatcher shutdown complete")


# Factory
async def create_dispatcher(
    max_concurrent_tasks: int = 50,
    worker_factory: Optional[Callable[..., Coroutine[Any, Any, WorkerResult]]] = None,
    event_bus: Optional[Any] = None,
) -> DispatcherImpl:
    """Factory for creating configured dispatcher.

    Args:
        max_concurrent_tasks: Maximum concurrent executions.
        worker_factory: Optional custom worker factory.
        event_bus: Optional event bus.

    Returns:
        Configured DispatcherImpl.
    """
    return DispatcherImpl(
        max_concurrent_tasks=max_concurrent_tasks,
        worker_factory=worker_factory,
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
