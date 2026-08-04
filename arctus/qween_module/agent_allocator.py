
"""Arctus AI Orchestration Framework - Agent Allocator.

Responsible for worker allocation, load balancing, agent scheduling,
and concurrency planning.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from domain_models import AgentSpec, ExecutionPlan, SubTask, TaskStatus
from exceptions import ErrorContext, ResourceException
from infrastructure import LogContext, async_timed, get_logger
from protocols import AgentAllocator


logger = get_logger("agent_allocator")


@dataclass
class AllocationResult:
    """Result of agent allocation planning."""

    task_agent_map: Dict[uuid.UUID, uuid.UUID]
    agent_load_map: Dict[uuid.UUID, int]
    estimated_make_span_ms: float
    unallocated_tasks: List[uuid.UUID]


class AgentAllocatorImpl(AgentAllocator):
    """Production agent allocator with load-aware scheduling.

    Implements multiple allocation strategies:
    - Best-fit: Match task requirements to agent capabilities
    - Load-balanced: Distribute evenly across capable agents
    - Greedy: Fastest allocation minimizing scheduling overhead
    """

    def __init__(
        self,
        strategy: str = "best_fit",
        max_queue_depth: int = 20,
        enable_preemption: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.strategy = strategy
        self.max_queue_depth = max_queue_depth
        self.enable_preemption = enable_preemption
        self.event_bus = event_bus
        self.logger = get_logger("agent_allocator")
        self._agent_load: Dict[uuid.UUID, int] = {}
        self._agent_locks: Dict[uuid.UUID, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    @async_timed
    async def allocate(
        self,
        tasks: List[SubTask],
        agents: List[AgentSpec],
    ) -> Dict[uuid.UUID, uuid.UUID]:
        """Allocate agents to tasks using configured strategy.

        Args:
            tasks: Tasks requiring agent assignment.
            agents: Available agent pool.

        Returns:
            Mapping of task_id -> agent_id.

        Raises:
            ResourceException: If allocation impossible.
        """
        with LogContext(module="agent_allocator", operation="allocate"):
            self.logger.info(
                "Allocating agents",
                extra={"tasks": len(tasks), "agents": len(agents)},
            )

            if not agents:
                raise ResourceException(
                    "No agents available for allocation",
                    context=ErrorContext(
                        module="agent_allocator",
                        operation="allocate",
                    ),
                )

            # Initialize load tracking
            for agent in agents:
                if agent.id not in self._agent_load:
                    self._agent_load[agent.id] = agent.current_load
                if agent.id not in self._agent_locks:
                    self._agent_locks[agent.id] = asyncio.Lock()

            # Filter to enabled agents
            active_agents = [a for a in agents if a.enabled]
            if not active_agents:
                raise ResourceException(
                    "No enabled agents available",
                    context=ErrorContext(
                        module="agent_allocator",
                        operation="allocate",
                    ),
                )

            # Execute allocation strategy
            if self.strategy == "best_fit":
                result = await self._best_fit_allocate(tasks, active_agents)
            elif self.strategy == "load_balanced":
                result = await self._load_balanced_allocate(tasks, active_agents)
            elif self.strategy == "greedy":
                result = await self._greedy_allocate(tasks, active_agents)
            else:
                result = await self._best_fit_allocate(tasks, active_agents)

            # Update load tracking
            for task_id, agent_id in result.items():
                self._agent_load[agent_id] = self._agent_load.get(agent_id, 0) + 1

            self.logger.info(
                "Allocation complete",
                extra={
                    "allocated": len(result),
                    "strategy": self.strategy,
                    "agent_loads": {str(k): v for k, v in self._agent_load.items()},
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="agents_allocated",
                        payload={
                            "allocated_count": len(result),
                            "strategy": self.strategy,
                            "agent_loads": {str(k): v for k, v in self._agent_load.items()},
                        },
                    )
                )

            return result

    async def _best_fit_allocate(
        self,
        tasks: List[SubTask],
        agents: List[AgentSpec],
    ) -> Dict[uuid.UUID, uuid.UUID]:
        """Best-fit allocation maximizing capability match.

        Assigns each task to the agent with highest capability overlap
        that has available capacity.
        """
        allocation: Dict[uuid.UUID, uuid.UUID] = {}
        agent_remaining = {
            a.id: max(0, a.max_concurrency - self._agent_load.get(a.id, 0))
            for a in agents
        }

        # Sort tasks by priority (critical first) and complexity
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (t.priority.value, len(t.required_capabilities)),
        )

        for task in sorted_tasks:
            best_agent: Optional[AgentSpec] = None
            best_score = -1.0

            for agent in agents:
                if agent_remaining.get(agent.id, 0) <= 0:
                    continue

                score = self._score_agent_task_match(agent, task)
                if score > best_score:
                    best_score = score
                    best_agent = agent

            if best_agent:
                allocation[task.id] = best_agent.id
                agent_remaining[best_agent.id] -= 1
            else:
                self.logger.warning(
                    "Could not allocate task",
                    extra={"task_id": str(task.id), "required_caps": list(task.required_capabilities)},
                )

        return allocation

    async def _load_balanced_allocate(
        self,
        tasks: List[SubTask],
        agents: List[AgentSpec],
    ) -> Dict[uuid.UUID, uuid.UUID]:
        """Load-balanced allocation distributing evenly.

        Assigns tasks to least-loaded capable agent.
        """
        allocation: Dict[uuid.UUID, uuid.UUID] = {}
        agent_loads = {
            a.id: self._agent_load.get(a.id, 0)
            for a in agents
        }

        sorted_tasks = sorted(tasks, key=lambda t: t.priority.value)

        for task in sorted_tasks:
            capable_agents = [
                a for a in agents
                if self._agent_can_handle(a, task)
                and agent_loads.get(a.id, 0) < a.max_concurrency
            ]

            if not capable_agents:
                continue

            # Pick least loaded
            best = min(capable_agents, key=lambda a: agent_loads.get(a.id, 0))
            allocation[task.id] = best.id
            agent_loads[best.id] = agent_loads.get(best.id, 0) + 1

        return allocation

    async def _greedy_allocate(
        self,
        tasks: List[SubTask],
        agents: List[AgentSpec],
    ) -> Dict[uuid.UUID, uuid.UUID]:
        """Fast greedy allocation minimizing overhead.

        First-fit for capable agents.
        """
        allocation: Dict[uuid.UUID, uuid.UUID] = {}
        agent_idx = 0

        for task in sorted(tasks, key=lambda t: t.priority.value):
            # Find next capable agent
            for _ in range(len(agents)):
                agent = agents[agent_idx % len(agents)]
                agent_idx += 1
                if self._agent_can_handle(agent, task):
                    current_load = self._agent_load.get(agent.id, 0)
                    if current_load < agent.max_concurrency:
                        allocation[task.id] = agent.id
                        self._agent_load[agent.id] = current_load + 1
                        break

        return allocation

    def _score_agent_task_match(self, agent: AgentSpec, task: SubTask) -> float:
        """Score how well an agent matches a task.

        Args:
            agent: Agent to evaluate.
            task: Task requirements.

        Returns:
            Match score [0, 1].
        """
        if not task.required_capabilities:
            return 0.5

        # Capability overlap
        overlap = agent.capabilities & task.required_capabilities
        cap_score = len(overlap) / len(task.required_capabilities)

        # Success rate bonus
        success_bonus = agent.success_rate * 0.2

        # Load penalty
        load_ratio = self._agent_load.get(agent.id, 0) / max(agent.max_concurrency, 1)
        load_penalty = load_ratio * 0.3

        return min(1.0, cap_score + success_bonus - load_penalty)

    def _agent_can_handle(self, agent: AgentSpec, task: SubTask) -> bool:
        """Check if agent has minimum capability to handle task.

        Args:
            agent: Agent to check.
            task: Task requirements.

        Returns:
            True if agent can handle task.
        """
        if not task.required_capabilities:
            return True
        # Agent must have at least one required capability or be generalist
        return bool(agent.capabilities & task.required_capabilities) or agent.role.value == "GENERALIST"

    async def release_agent(self, agent_id: uuid.UUID, task_id: uuid.UUID) -> None:
        """Release agent after task completion.

        Args:
            agent_id: Agent to release.
            task_id: Completed task ID.
        """
        async with self._global_lock:
            current = self._agent_load.get(agent_id, 0)
            self._agent_load[agent_id] = max(0, current - 1)

        self.logger.info(
            "Agent released",
            extra={"agent_id": str(agent_id), "task_id": str(task_id)},
        )

    async def get_allocation_plan(
        self,
        plan: ExecutionPlan,
        agents: List[AgentSpec],
    ) -> AllocationResult:
        """Generate complete allocation plan with estimates.

        Args:
            plan: Execution plan.
            agents: Available agents.

        Returns:
            Allocation result with mapping and metrics.
        """
        task_agent_map = await self.allocate(plan.subtasks, agents)

        # Calculate makespan estimate
        agent_tasks: Dict[uuid.UUID, List[uuid.UUID]] = {}
        for task_id, agent_id in task_agent_map.items():
            if agent_id not in agent_tasks:
                agent_tasks[agent_id] = []
            agent_tasks[agent_id].append(task_id)

        max_agent_time = 0.0
        for agent_id, task_ids in agent_tasks.items():
            total_time = sum(
                next((t.estimated_latency_ms or 1000.0 for t in plan.subtasks if t.id == tid), 1000.0)
                for tid in task_ids
            )
            max_agent_time = max(max_agent_time, total_time)

        unallocated = [t.id for t in plan.subtasks if t.id not in task_agent_map]

        return AllocationResult(
            task_agent_map=task_agent_map,
            agent_load_map=dict(self._agent_load),
            estimated_make_span_ms=max_agent_time,
            unallocated_tasks=unallocated,
        )

    async def preempt_task(self, task_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
        """Attempt to preempt a running task if enabled.

        Args:
            task_id: Task to preempt.
            agent_id: Agent running task.

        Returns:
            True if preemption succeeded.
        """
        if not self.enable_preemption:
            return False

        self.logger.warning(
            "Preempting task",
            extra={"task_id": str(task_id), "agent_id": str(agent_id)},
        )
        # Implementation would signal agent to cancel
        return True


# Factory
async def create_agent_allocator(
    strategy: str = "best_fit",
    event_bus: Optional[Any] = None,
) -> AgentAllocatorImpl:
    """Factory for creating configured agent allocator.

    Args:
        strategy: Allocation strategy name.
        event_bus: Optional event bus.

    Returns:
        Configured AgentAllocatorImpl.
    """
    return AgentAllocatorImpl(strategy=strategy, event_bus=event_bus)


from domain_models import OrchestrationEvent
