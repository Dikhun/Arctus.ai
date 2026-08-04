"""Arctus AI Orchestration Framework - Memory Router.

Responsible for memory selection, memory filtering,
persistent memory routing, and working memory routing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import SubTask
from exceptions import ErrorContext, MemoryException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("memory_router")


@dataclass
class MemorySource:
    """Registered memory backend source."""

    name: str
    memory_type: str  # "ephemeral", "persistent", "vector", "cache"
    capabilities: Set[str] = field(default_factory=set)
    priority: int = 5  # Lower = higher priority
    latency_ms: float = 10.0
    max_size_mb: Optional[int] = None
    enabled: bool = True


class MemoryRegistry:
    """Registry of available memory sources."""

    def __init__(self) -> None:
        self._sources: Dict[str, MemorySource] = {}
        self._lock = asyncio.Lock()

    async def register(self, source: MemorySource) -> None:
        """Register memory source.

        Args:
            source: Memory source to register.
        """
        async with self._lock:
            self._sources[source.name] = source

    async def unregister(self, name: str) -> None:
        """Remove memory source.

        Args:
            name: Source name.
        """
        async with self._lock:
            self._sources.pop(name, None)

    async def list_sources(self, memory_type: Optional[str] = None) -> List[MemorySource]:
        """List registered sources.

        Args:
            memory_type: Filter by type.

        Returns:
            List of sources.
        """
        async with self._lock:
            sources = list(self._sources.values())
            if memory_type:
                sources = [s for s in sources if s.memory_type == memory_type]
            return [s for s in sources if s.enabled]


class MemoryRouterImpl:
    """Production memory router with intelligent source selection.

    Routes memory operations to appropriate backends based on
    task requirements, data characteristics, and performance needs.
    """

    # Task type to memory type preferences
    MEMORY_PREFERENCES: Dict[str, List[str]] = {
        "coding": ["vector", "persistent", "ephemeral"],
        "analysis": ["persistent", "vector", "ephemeral"],
        "creative": ["ephemeral", "cache", "persistent"],
        "research": ["vector", "persistent", "ephemeral"],
        "general": ["ephemeral", "cache", "persistent"],
    }

    def __init__(
        self,
        registry: Optional[MemoryRegistry] = None,
        default_sources: Optional[List[MemorySource]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.registry = registry or MemoryRegistry()
        self.event_bus = event_bus
        self.logger = get_logger("memory_router")

        if default_sources:
            for source in default_sources:
                asyncio.create_task(self.registry.register(source))

    @async_timed
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
            Selected memory source names in priority order.
        """
        with LogContext(module="memory_router", operation="select_memory", task_id=task.id):
            self.logger.info(
                "Selecting memory sources",
                extra={
                    "task_id": str(task.id),
                    "required_caps": list(task.required_capabilities),
                    "available_types": memory_types,
                },
            )

            # Score all available sources
            all_sources = await self.registry.list_sources()
            available = [s for s in all_sources if s.memory_type in memory_types]

            if not available:
                self.logger.warning("No memory sources available", extra={"types": memory_types})
                return []

            # Score and rank
            scored: List[Tuple[MemorySource, float]] = []
            for source in available:
                score = self._score_source(task, source)
                scored.append((source, score))

            scored.sort(key=lambda x: x[1], reverse=True)

            selected = [s.name for s, _ in scored[:3]]  # Top 3 sources

            self.logger.info(
                "Memory sources selected",
                extra={
                    "task_id": str(task.id),
                    "selected": selected,
                    "scores": {s.name: round(score, 3) for s, score in scored[:3]},
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="memory_selected",
                        task_id=task.id,
                        payload={
                            "sources": selected,
                            "task_caps": list(task.required_capabilities),
                        },
                    )
                )

            return selected

    def _score_source(self, task: SubTask, source: MemorySource) -> float:
        """Score memory source relevance for task.

        Args:
            task: Task to evaluate.
            source: Memory source.

        Returns:
            Score [0, 1].
        """
        scores: List[float] = []

        # Capability match
        if task.required_capabilities:
            overlap = source.capabilities & task.required_capabilities
            cap_score = len(overlap) / len(task.required_capabilities)
            scores.append(cap_score * 0.4)

        # Task type preference
        task_domain = self._infer_task_domain(task)
        preferences = self.MEMORY_PREFERENCES.get(task_domain, ["ephemeral"])
        if source.memory_type in preferences:
            type_score = 1.0 - (preferences.index(source.memory_type) * 0.2)
            scores.append(max(0.0, type_score) * 0.3)

        # Priority bonus
        priority_score = (10 - source.priority) / 10.0
        scores.append(priority_score * 0.2)

        # Latency preference (faster is better)
        lat_score = max(0.0, 1.0 - (source.latency_ms / 1000.0))
        scores.append(lat_score * 0.1)

        return sum(scores)

    def _infer_task_domain(self, task: SubTask) -> str:
        """Infer task domain for memory preference.

        Args:
            task: Task to analyze.

        Returns:
            Domain string.
        """
        desc = task.description.lower()
        caps = " ".join(task.required_capabilities).lower()

        domains = {
            "coding": ["code", "program", "debug", "software", "git"],
            "analysis": ["data", "analyze", "metric", "statistics", "chart"],
            "creative": ["write", "create", "design", "story", "content"],
            "research": ["research", "study", "investigate", "paper"],
        }

        for domain, keywords in domains.items():
            for kw in keywords:
                if kw in desc or kw in caps:
                    return domain

        return "general"

    async def filter_relevant(
        self,
        task: SubTask,
        memories: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Filter memories for relevance to task.

        Args:
            task: Task context.
            memories: Candidate memories.
            top_k: Maximum to return.

        Returns:
            Filtered and ranked memories.
        """
        if not memories:
            return []

        # Simple keyword relevance scoring
        task_text = f"{task.name} {task.description}".lower()
        task_words = set(task_text.split())

        scored = []
        for memory in memories:
            mem_text = str(memory.get("content", memory)).lower()
            mem_words = set(mem_text.split())
            overlap = len(task_words & mem_words) / max(len(task_words), 1)
            scored.append((memory, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:top_k]]

    async def route_persistent(
        self,
        task: SubTask,
        data: Dict[str, Any],
    ) -> str:
        """Route data to persistent memory.

        Args:
            task: Task context.
            data: Data to persist.

        Returns:
            Storage identifier.
        """
        sources = await self.select_memory(task, ["persistent"])
        if not sources:
            raise MemoryException(
                "No persistent memory available",
                context=ErrorContext(
                    module="memory_router",
                    operation="route_persistent",
                    task_id=task.id,
                ),
            )

        # Route to highest priority source
        target = sources[0]
        self.logger.info(
            "Routed to persistent memory",
            extra={"task_id": str(task.id), "target": target},
        )

        # In production, would call actual storage API
        return f"{target}://{task.id}"

    async def route_working(
        self,
        task: SubTask,
        data: Dict[str, Any],
        ttl_seconds: float = 3600.0,
    ) -> str:
        """Route data to working/ephemeral memory.

        Args:
            task: Task context.
            data: Data to store.
            ttl_seconds: Time-to-live.

        Returns:
            Storage identifier.
        """
        sources = await self.select_memory(task, ["ephemeral", "cache"])
        if not sources:
            # Fallback to any available
            sources = await self.select_memory(task, ["persistent"])

        if not sources:
            raise MemoryException(
                "No working memory available",
                context=ErrorContext(
                    module="memory_router",
                    operation="route_working",
                    task_id=task.id,
                ),
            )

        target = sources[0]
        self.logger.info(
            "Routed to working memory",
            extra={"task_id": str(task.id), "target": target, "ttl": ttl_seconds},
        )

        return f"{target}://{task.id}?ttl={ttl_seconds}"


# Factory
async def create_memory_router(
    default_sources: Optional[List[MemorySource]] = None,
    event_bus: Optional[Any] = None,
) -> MemoryRouterImpl:
    """Factory for creating configured memory router.

    Args:
        default_sources: Default memory sources.
        event_bus: Optional event bus.

    Returns:
        Configured MemoryRouterImpl.
    """
    return MemoryRouterImpl(
        default_sources=default_sources,
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
