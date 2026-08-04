"""Arctus AI Orchestration Framework - Dependency Graph.

Responsible for dependency detection, cycle detection,
topological sorting, and execution ordering.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import SubTask
from exceptions import (
    CycleDetectedException,
    DependencyException,
    ErrorContext,
)
from infrastructure import LogContext, async_timed, get_logger
from protocols import DependencyResolver


logger = get_logger("dependency_graph")


class DependencyGraphImpl(DependencyResolver):
    """Production dependency resolver with cycle detection and topological sorting.

    Implements efficient graph algorithms for task dependency management
    with comprehensive error reporting.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self.event_bus = event_bus
        self.logger = get_logger("dependency_graph")

    @async_timed
    async def detect_cycles(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
    ) -> Optional[List[uuid.UUID]]:
        """Detect cycles in dependency graph using DFS with color marking.

        Args:
            graph: Adjacency list where edges represent dependencies.
                   Key: task_id, Value: set of task_ids it depends on.

        Returns:
            Cycle path if found, None if acyclic.

        Raises:
            CycleDetectedException: If cycle detected with full context.
        """
        with LogContext(module="dependency_graph", operation="detect_cycles"):
            WHITE, GRAY, BLACK = 0, 1, 2
            color: Dict[uuid.UUID, int] = {node: WHITE for node in graph}
            parent: Dict[uuid.UUID, Optional[uuid.UUID]] = {node: None for node in graph}
            path: List[uuid.UUID] = []

            def dfs(node: uuid.UUID) -> Optional[List[uuid.UUID]]:
                color[node] = GRAY
                path.append(node)

                for neighbor in graph.get(node, set()):
                    if neighbor not in color:
                        continue  # Skip unknown nodes
                    if color[neighbor] == GRAY:
                        # Cycle found - extract cycle from path
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        return cycle
                    if color[neighbor] == WHITE:
                        parent[neighbor] = node
                        result = dfs(neighbor)
                        if result:
                            return result

                path.pop()
                color[node] = BLACK
                return None

            for node in graph:
                if color[node] == WHITE:
                    cycle = dfs(node)
                    if cycle:
                        cycle_str = " -> ".join(str(n) for n in cycle)
                        self.logger.error(
                            "Cycle detected",
                            extra={"cycle": cycle_str, "cycle_length": len(cycle)},
                        )
                        if self.event_bus:
                            asyncio.create_task(self.event_bus.publish(
                                OrchestrationEvent(
                                    event_type="cycle_detected",
                                    payload={"cycle": [str(n) for n in cycle]},
                                )
                            ))
                        raise CycleDetectedException(
                            f"Circular dependency detected: {cycle_str}",
                            cycle_path=[str(n) for n in cycle],
                            context=ErrorContext(
                                module="dependency_graph",
                                operation="detect_cycles",
                            ),
                        )

            self.logger.debug("No cycles detected")
            return None

    @async_timed
    async def topological_sort(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
        tasks: Dict[uuid.UUID, SubTask],
    ) -> List[List[uuid.UUID]]:
        """Generate execution levels via Kahn's topological sort algorithm.

        Produces levels where all tasks in a level can execute in parallel.

        Args:
            graph: Adjacency list of dependencies.
            tasks: Mapping of task_id to SubTask.

        Returns:
            List of execution levels, each containing parallelizable task IDs.

        Raises:
            CycleDetectedException: If graph contains cycle.
        """
        with LogContext(module="dependency_graph", operation="topological_sort"):
            # First validate no cycles
            try:
                await self.detect_cycles(graph)
            except CycleDetectedException:
                raise

            # Kahn's algorithm
            # Calculate in-degrees
            in_degree: Dict[uuid.UUID, int] = {node: 0 for node in graph}
            for node, deps in graph.items():
                for dep in deps:
                    if dep in in_degree:
                        in_degree[node] += 1

            # Find all starting nodes (in-degree 0)
            levels: List[List[uuid.UUID]] = []
            current = deque([node for node, deg in in_degree.items() if deg == 0])

            while current:
                level = list(current)
                levels.append(level)
                current.clear()

                for node in level:
                    # Find nodes that depend on this node
                    for other_node, other_deps in graph.items():
                        if node in other_deps:
                            in_degree[other_node] -= 1
                            if in_degree[other_node] == 0:
                                current.append(other_node)

            # Verify all nodes processed
            processed = set()
            for level in levels:
                processed.update(level)

            unprocessed = set(graph.keys()) - processed
            if unprocessed:
                self.logger.error(
                    "Topological sort incomplete",
                    extra={"unprocessed": [str(n) for n in unprocessed]},
                )
                raise DependencyException(
                    f"Could not order {len(unprocessed)} tasks due to unresolved dependencies",
                    context=ErrorContext(
                        module="dependency_graph",
                        operation="topological_sort",
                    ),
                )

            self.logger.info(
                "Topological sort complete",
                extra={"levels": len(levels), "total_tasks": len(graph)},
            )

            if self.event_bus:
                asyncio.create_task(self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="topological_sort_complete",
                        payload={"levels": len(levels), "total_tasks": len(graph)},
                    )
                ))

            return levels

    async def get_execution_order(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
        tasks: Dict[uuid.UUID, SubTask],
    ) -> List[uuid.UUID]:
        """Get flat execution order respecting dependencies.

        Args:
            graph: Dependency adjacency list.
            tasks: Task mapping.

        Returns:
            Ordered list of task IDs.
        """
        levels = await self.topological_sort(graph, tasks)
        order: List[uuid.UUID] = []
        for level in levels:
            # Sort within level by priority
            sorted_level = sorted(
                level,
                key=lambda tid: tasks.get(tid, SubTask(id=tid, name="", description="")).priority.value
            )
            order.extend(sorted_level)
        return order

    async def find_dependents(
        self,
        task_id: uuid.UUID,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
    ) -> Set[uuid.UUID]:
        """Find all tasks that directly or indirectly depend on given task.

        Args:
            task_id: Task to find dependents for.
            graph: Dependency adjacency list.

        Returns:
            Set of dependent task IDs.
        """
        dependents: Set[uuid.UUID] = set()
        to_process = deque([task_id])

        while to_process:
            current = to_process.popleft()
            for node, deps in graph.items():
                if current in deps and node not in dependents:
                    dependents.add(node)
                    to_process.append(node)

        return dependents - {task_id}

    async def find_dependencies(
        self,
        task_id: uuid.UUID,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
    ) -> Set[uuid.UUID]:
        """Find all direct and transitive dependencies of a task.

        Args:
            task_id: Task to analyze.
            graph: Dependency adjacency list.

        Returns:
            Set of dependency task IDs.
        """
        visited: Set[uuid.UUID] = set()
        to_process = deque([task_id])

        while to_process:
            current = to_process.popleft()
            deps = graph.get(current, set())
            for dep in deps:
                if dep not in visited:
                    visited.add(dep)
                    to_process.append(dep)

        return visited - {task_id}

    async def add_dependency(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
        from_task: uuid.UUID,
        to_task: uuid.UUID,
    ) -> Dict[uuid.UUID, Set[uuid.UUID]]:
        """Safely add dependency with cycle validation.

        Args:
            graph: Current dependency graph.
            from_task: Task that depends on to_task.
            to_task: Task that must complete first.

        Returns:
            Updated graph.

        Raises:
            CycleDetectedException: If adding dependency creates cycle.
        """
        new_graph = {k: set(v) for k, v in graph.items()}
        if from_task not in new_graph:
            new_graph[from_task] = set()
        new_graph[from_task].add(to_task)

        # Validate
        try:
            await self.detect_cycles(new_graph)
        except CycleDetectedException as e:
            self.logger.warning(
                "Dependency addition rejected - would create cycle",
                extra={"from": str(from_task), "to": str(to_task)},
            )
            raise

        self.logger.info(
            "Dependency added",
            extra={"from": str(from_task), "to": str(to_task)},
        )
        return new_graph

    async def remove_dependency(
        self,
        graph: Dict[uuid.UUID, Set[uuid.UUID]],
        from_task: uuid.UUID,
        to_task: uuid.UUID,
    ) -> Dict[uuid.UUID, Set[uuid.UUID]]:
        """Remove dependency from graph.

        Args:
            graph: Current dependency graph.
            from_task: Source task.
            to_task: Dependency to remove.

        Returns:
            Updated graph.
        """
        new_graph = {k: set(v) for k, v in graph.items()}
        if from_task in new_graph:
            new_graph[from_task].discard(to_task)

        self.logger.info(
            "Dependency removed",
            extra={"from": str(from_task), "to": str(to_task)},
        )
        return new_graph


# Factory
async def create_dependency_graph(event_bus: Optional[Any] = None) -> DependencyGraphImpl:
    """Factory for creating configured dependency graph resolver.

    Args:
        event_bus: Optional event bus.

    Returns:
        Configured DependencyGraphImpl.
    """
    return DependencyGraphImpl(event_bus=event_bus)


# Need this import for the event publish
import asyncio
from domain_models import OrchestrationEvent
