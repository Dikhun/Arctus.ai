"""Arctus AI Orchestration Framework - Workflow Planner.

Responsible for creating execution workflows, generating DAGs,
pipeline optimization, and execution graph construction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import ExecutionMode, ExecutionPlan, SubTask, TaskStatus
from exceptions import ErrorContext, PlanningException
from infrastructure import LogContext, async_timed, get_logger
from protocols import WorkflowPlanner


logger = get_logger("workflow_planner")


@dataclass
class DAGNode:
    """Node in execution DAG."""

    task_id: uuid.UUID
    level: int = 0
    dependencies: Set[uuid.UUID] = field(default_factory=set)
    dependents: Set[uuid.UUID] = field(default_factory=set)


@dataclass
class ExecutionGraph:
    """Complete execution graph with scheduling metadata."""

    plan_id: uuid.UUID
    nodes: Dict[uuid.UUID, DAGNode]
    levels: List[List[uuid.UUID]]
    critical_path: List[uuid.UUID]
    estimated_duration_ms: float
    max_parallelism: int


class WorkflowPlannerImpl(WorkflowPlanner):
    """Generates optimized execution workflows and DAGs from plans.

    Transforms execution plans into runnable execution graphs with
    pipeline optimization and parallelism maximization.
    """

    def __init__(
        self,
        enable_pipeline_optimization: bool = True,
        max_pipeline_stages: int = 10,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.enable_pipeline = enable_pipeline_optimization
        self.max_pipeline_stages = max_pipeline_stages
        self.event_bus = event_bus
        self.logger = get_logger("workflow_planner")

    @async_timed
    async def build_dag(self, plan: ExecutionPlan) -> Dict[uuid.UUID, Set[uuid.UUID]]:
        """Build dependency DAG from execution plan.

        Args:
            plan: Execution plan containing subtasks.

        Returns:
            Adjacency list mapping task_id -> set of dependent task_ids
            (tasks that depend on this task).
        """
        with LogContext(module="workflow_planner", operation="build_dag", plan_id=plan.id):
            # Build forward adjacency (task -> tasks that depend on it)
            adj: Dict[uuid.UUID, Set[uuid.UUID]] = {t.id: set() for t in plan.subtasks}

            for task in plan.subtasks:
                for dep_id in task.dependencies:
                    if dep_id in adj:
                        adj[dep_id].add(task.id)

            self.logger.info(
                "DAG built",
                extra={
                    "plan_id": str(plan.id),
                    "nodes": len(adj),
                    "edges": sum(len(v) for v in adj.values()),
                },
            )

            return adj

    async def build_execution_graph(self, plan: ExecutionPlan) -> ExecutionGraph:
        """Build complete execution graph with levels and critical path.

        Args:
            plan: Validated execution plan.

        Returns:
            Execution graph with scheduling information.

        Raises:
            PlanningException: If graph construction fails.
        """
        with LogContext(
            module="workflow_planner",
            operation="build_execution_graph",
            plan_id=plan.id,
        ):
            # Build DAG
            dag = await self.build_dag(plan)

            # Calculate levels via topological sort
            levels = self._calculate_levels(dag, plan)

            # Build nodes with dependency info
            nodes: Dict[uuid.UUID, DAGNode] = {}
            for level_idx, level_tasks in enumerate(levels):
                for task_id in level_tasks:
                    # Find dependents (tasks that have this as dependency)
                    dependents = {
                        tid for tid, deps in dag.items()
                        if task_id in self._get_all_deps(plan, tid)
                    }
                    # Actual deps from plan
                    task = next((t for t in plan.subtasks if t.id == task_id), None)
                    deps = task.dependencies if task else set()

                    nodes[task_id] = DAGNode(
                        task_id=task_id,
                        level=level_idx,
                        dependencies=deps,
                        dependents=dependents,
                    )

            # Calculate critical path
            critical_path = self._find_critical_path(plan, nodes, levels)

            # Estimate duration
            duration = self._estimate_duration(plan, levels)

            # Max parallelism
            max_parallel = max(len(level) for level in levels) if levels else 1

            graph = ExecutionGraph(
                plan_id=plan.id,
                nodes=nodes,
                levels=levels,
                critical_path=critical_path,
                estimated_duration_ms=duration,
                max_parallelism=max_parallel,
            )

            self.logger.info(
                "Execution graph built",
                extra={
                    "plan_id": str(plan.id),
                    "levels": len(levels),
                    "critical_path_length": len(critical_path),
                    "max_parallelism": max_parallel,
                    "duration_ms": duration,
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="execution_graph_built",
                        plan_id=plan.id,
                        payload={
                            "levels": len(levels),
                            "critical_path_length": len(critical_path),
                            "max_parallelism": max_parallel,
                        },
                    )
                )

            return graph

    def _calculate_levels(
        self,
        dag: Dict[uuid.UUID, Set[uuid.UUID]],
        plan: ExecutionPlan,
    ) -> List[List[uuid.UUID]]:
        """Calculate execution levels via Kahn's algorithm.

        Args:
            dag: Forward adjacency list.
            plan: Execution plan.

        Returns:
            List of levels, each containing parallelizable task IDs.
        """
        # Build in-degree map
        in_degree: Dict[uuid.UUID, int] = {t.id: 0 for t in plan.subtasks}
        for task in plan.subtasks:
            for dep in task.dependencies:
                if dep in in_degree:
                    in_degree[task.id] += 1

        # Kahn's algorithm
        levels: List[List[uuid.UUID]] = []
        current = [tid for tid, deg in in_degree.items() if deg == 0]

        while current:
            levels.append(current)
            next_level: List[uuid.UUID] = []
            for tid in current:
                # Find tasks that depend on tid
                for task in plan.subtasks:
                    if tid in task.dependencies:
                        in_degree[task.id] -= 1
                        if in_degree[task.id] == 0:
                            next_level.append(task.id)
            current = next_level

        return levels

    def _get_all_deps(self, plan: ExecutionPlan, task_id: uuid.UUID) -> Set[uuid.UUID]:
        """Get all direct dependencies for a task."""
        task = next((t for t in plan.subtasks if t.id == task_id), None)
        return task.dependencies if task else set()

    def _find_critical_path(
        self,
        plan: ExecutionPlan,
        nodes: Dict[uuid.UUID, DAGNode],
        levels: List[List[uuid.UUID]],
    ) -> List[uuid.UUID]:
        """Find critical path through execution graph.

        Critical path is the longest path from start to finish.

        Args:
            plan: Execution plan.
            nodes: DAG nodes.
            levels: Execution levels.

        Returns:
            List of task IDs on critical path.
        """
        # Simple: path with most levels
        if not levels:
            return []

        # Find longest dependency chain
        task_durations: Dict[uuid.UUID, float] = {
            t.id: t.estimated_latency_ms or 1000.0 for t in plan.subtasks
        }

        # Dynamic programming: longest path to each node
        longest_to: Dict[uuid.UUID, Tuple[float, List[uuid.UUID]]] = {}

        for level in levels:
            for tid in level:
                node = nodes.get(tid)
                if not node:
                    continue

                if not node.dependencies:
                    longest_to[tid] = (task_durations.get(tid, 1000.0), [tid])
                else:
                    # Take longest path from any dependency
                    best = max(
                        (longest_to.get(dep, (0.0, [])) for dep in node.dependencies),
                        key=lambda x: x[0],
                        default=(0.0, []),
                    )
                    duration = best[0] + task_durations.get(tid, 1000.0)
                    path = best[1] + [tid]
                    longest_to[tid] = (duration, path)

        if not longest_to:
            return []

        # Find overall longest
        _, critical_path = max(longest_to.values(), key=lambda x: x[0])
        return critical_path

    def _estimate_duration(self, plan: ExecutionPlan, levels: List[List[uuid.UUID]]) -> float:
        """Estimate total execution duration.

        Args:
            plan: Execution plan.
            levels: Execution levels.

        Returns:
            Estimated duration in milliseconds.
        """
        # Sum of level durations (parallel tasks within level)
        total = 0.0
        task_durations = {t.id: t.estimated_latency_ms or 1000.0 for t in plan.subtasks}

        for level in levels:
            level_duration = max(task_durations.get(tid, 1000.0) for tid in level) if level else 0.0
            total += level_duration

        return total

    async def optimize_pipeline(self, graph: ExecutionGraph, plan: ExecutionPlan) -> ExecutionGraph:
        """Optimize graph for pipeline execution.

        Args:
            graph: Current execution graph.
            plan: Execution plan.

        Returns:
            Optimized execution graph.
        """
        if not self.enable_pipeline:
            return graph

        with LogContext(module="workflow_planner", operation="optimize_pipeline"):
            # Pipeline optimization: merge compatible sequential stages
            # Identify tasks that can be pipelined (stream output to next)
            # This is a simplified version

            merged_levels: List[List[uuid.UUID]] = []
            current_level: List[uuid.UUID] = []

            for level in graph.levels:
                if len(current_level) + len(level) <= 5:  # Merge small levels
                    current_level.extend(level)
                else:
                    if current_level:
                        merged_levels.append(current_level)
                    current_level = list(level)

            if current_level:
                merged_levels.append(current_level)

            # Rebuild graph with merged levels
            new_nodes = dict(graph.nodes)
            for level_idx, level in enumerate(merged_levels):
                for tid in level:
                    if tid in new_nodes:
                        node = new_nodes[tid]
                        new_nodes[tid] = DAGNode(
                            task_id=tid,
                            level=level_idx,
                            dependencies=node.dependencies,
                            dependents=node.dependents,
                        )

            optimized = ExecutionGraph(
                plan_id=graph.plan_id,
                nodes=new_nodes,
                levels=merged_levels,
                critical_path=graph.critical_path,
                estimated_duration_ms=graph.estimated_duration_ms * 0.9,  # Assume 10% improvement
                max_parallelism=max(len(l) for l in merged_levels) if merged_levels else 1,
            )

            self.logger.info(
                "Pipeline optimized",
                extra={
                    "original_levels": len(graph.levels),
                    "optimized_levels": len(merged_levels),
                },
            )

            return optimized

    async def to_execution_mode(
        self,
        graph: ExecutionGraph,
        plan: ExecutionPlan,
    ) -> ExecutionMode:
        """Determine optimal execution mode from graph structure.

        Args:
            graph: Execution graph.
            plan: Original plan.

        Returns:
            Recommended execution mode.
        """
        if len(graph.levels) == 1:
            return ExecutionMode.PARALLEL
        if graph.max_parallelism == 1:
            return ExecutionMode.SEQUENTIAL
        if plan.execution_mode == ExecutionMode.PIPELINE:
            return ExecutionMode.PIPELINE
        if len(graph.critical_path) > len(graph.levels) * 0.8:
            return ExecutionMode.DAG
        return ExecutionMode.PIPELINE


# Factory
async def create_workflow_planner(
    enable_pipeline_optimization: bool = True,
    event_bus: Optional[Any] = None,
) -> WorkflowPlannerImpl:
    """Factory for creating configured workflow planner.

    Args:
        enable_pipeline_optimization: Enable pipeline stage merging.
        event_bus: Optional event bus.

    Returns:
        Configured WorkflowPlannerImpl.
    """
    return WorkflowPlannerImpl(
        enable_pipeline_optimization=enable_pipeline_optimization,
        event_bus=event_bus,
            )
