"""Arctus AI Orchestration Framework - Capability Router.

Responsible for matching tasks with specialist agents, maintaining
capability registry, capability scoring, and expert selection.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from domain_models import AgentRole, AgentSpec, CapabilityScore, SubTask
from exceptions import (
    CapabilityRouterException,
    ErrorContext,
    NoAgentAvailableException,
)
from infrastructure import LogContext, async_timed, get_logger
from protocols import CapabilityRouter


logger = get_logger("capability_router")


@dataclass
class CapabilityRegistryEntry:
    """Registered capability with metadata."""

    name: str
    description: str
    required_skills: Set[str] = field(default_factory=set)
    example_tasks: List[str] = field(default_factory=list)


class CapabilityRegistry:
    """Central registry of system capabilities and their mappings.

    Maintains bidirectional indexes for fast capability lookup.
    """

    DEFAULT_CAPABILITIES: Dict[str, CapabilityRegistryEntry] = {
        "coding": CapabilityRegistryEntry(
            name="coding",
            description="Software development and code generation",
            required_skills={"python", "javascript", "typescript", "rust", "go", "java"},
            example_tasks=["Write a function", "Debug code", "Refactor class", "Review PR"],
        ),
        "data_analysis": CapabilityRegistryEntry(
            name="data_analysis",
            description="Data processing, statistics, and visualization",
            required_skills={"pandas", "sql", "statistics", "matplotlib", "numpy"},
            example_tasks=["Analyze CSV", "Build dashboard", "Statistical test", "ETL pipeline"],
        ),
        "system_design": CapabilityRegistryEntry(
            name="system_design",
            description="Architecture and system design",
            required_skills={"distributed_systems", "databases", "microservices", "cloud"},
            example_tasks=["Design API", "Scale system", "Database schema", "Service mesh"],
        ),
        "devops": CapabilityRegistryEntry(
            name="devops",
            description="Infrastructure and deployment automation",
            required_skills={"docker", "kubernetes", "terraform", "ci_cd", "aws", "gcp"},
            example_tasks=["Deploy service", "Configure pipeline", "Infrastructure as code", "Monitor alerts"],
        ),
        "research": CapabilityRegistryEntry(
            name="research",
            description="Information gathering and synthesis",
            required_skills={"search", "synthesis", "citation", "critical_analysis"},
            example_tasks=["Literature review", "Market research", "Competitive analysis", "Trend analysis"],
        ),
        "creative_writing": CapabilityRegistryEntry(
            name="creative_writing",
            description="Content creation and creative writing",
            required_skills={"storytelling", "copywriting", "editing", "seo"},
            example_tasks=["Write blog post", "Draft email", "Create story", "Marketing copy"],
        ),
        "verification": CapabilityRegistryEntry(
            name="verification",
            description="Quality assurance and fact checking",
            required_skills={"testing", "review", "fact_checking", "consistency_check"},
            example_tasks=["Verify answer", "Check facts", "Review code", "Validate output"],
        ),
        "planning": CapabilityRegistryEntry(
            name="planning",
            description="Strategic planning and task decomposition",
            required_skills={"analysis", "prioritization", "scheduling", "risk_assessment"},
            example_tasks=["Create roadmap", "Estimate effort", "Resource allocation", "Timeline planning"],
        ),
        "general": CapabilityRegistryEntry(
            name="general",
            description="General purpose reasoning and assistance",
            required_skills={"reasoning", "communication", "problem_solving"},
            example_tasks=["Answer question", "Explain concept", "Summarize text", "Brainstorm ideas"],
        ),
    }

    def __init__(self, custom_capabilities: Optional[Dict[str, CapabilityRegistryEntry]] = None) -> None:
        self._capabilities: Dict[str, CapabilityRegistryEntry] = {}
        self._capabilities.update(self.DEFAULT_CAPABILITIES)
        if custom_capabilities:
            self._capabilities.update(custom_capabilities)
        self._agent_index: Dict[str, Set[str]] = {}  # agent_id -> capabilities
        self._capability_index: Dict[str, Set[str]] = {}  # capability -> agent_ids
        self._lock = asyncio.Lock()

    async def register_agent(self, agent: AgentSpec) -> None:
        """Register agent capabilities in indexes.

        Args:
            agent: Agent specification to register.
        """
        async with self._lock:
            self._agent_index[str(agent.id)] = set(agent.capabilities)
            for cap in agent.capabilities:
                if cap not in self._capability_index:
                    self._capability_index[cap] = set()
                self._capability_index[cap].add(str(agent.id))

    async def unregister_agent(self, agent_id: str) -> None:
        """Remove agent from capability indexes.

        Args:
            agent_id: Agent identifier.
        """
        async with self._lock:
            caps = self._agent_index.pop(agent_id, set())
            for cap in caps:
                if cap in self._capability_index:
                    self._capability_index[cap].discard(agent_id)

    async def find_agents_with_capability(self, capability: str) -> Set[str]:
        """Find all agents with a specific capability.

        Args:
            capability: Capability name.

        Returns:
            Set of agent IDs.
        """
        async with self._lock:
            return self._capability_index.get(capability, set()).copy()

    def get_capability_info(self, capability: str) -> Optional[CapabilityRegistryEntry]:
        """Get capability registry entry.

        Args:
            capability: Capability name.

        Returns:
            Registry entry or None.
        """
        return self._capabilities.get(capability)

    def list_capabilities(self) -> List[str]:
        """List all registered capabilities.

        Returns:
            List of capability names.
        """
        return list(self._capabilities.keys())


class CapabilityScorer:
    """Scores agent-task capability matches with explainable scoring."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    @async_timed
    async def score(
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
        scores: List[CapabilityScore] = []
        task_caps = task.required_capabilities

        for cap in task_caps:
            score = await self._score_capability(cap, agent, task)
            scores.append(score)

        # Score role alignment
        role_score = self._score_role_alignment(task, agent)
        scores.append(role_score)

        return scores

    async def _score_capability(
        self,
        capability: str,
        agent: AgentSpec,
        task: SubTask,
    ) -> CapabilityScore:
        """Score single capability match.

        Args:
            capability: Capability name.
            agent: Agent to score.
            task: Task context.

        Returns:
            Capability score with evidence.
        """
        cap_info = self.registry.get_capability_info(capability)

        # Base: does agent have capability?
        if capability in agent.capabilities:
            base_score = 0.8
        elif capability == "general" and agent.role == AgentRole.GENERALIST:
            base_score = 0.7
        else:
            # Check for related capabilities
            related = self._find_related_capabilities(capability)
            overlap = agent.capabilities & related
            base_score = 0.3 + (0.4 * len(overlap) / max(len(related), 1))

        # Adjust for agent performance
        performance_multiplier = agent.success_rate
        score = base_score * performance_multiplier

        # Penalize overloaded agents
        load_ratio = agent.current_load / max(agent.max_concurrency, 1)
        if load_ratio > 0.8:
            score *= 0.7
        elif load_ratio > 0.5:
            score *= 0.9

        evidence = (
            f"Agent has capability={capability in agent.capabilities}, "
            f"success_rate={agent.success_rate:.2f}, "
            f"load={load_ratio:.2f}"
        )

        return CapabilityScore(
            capability=capability,
            score=min(1.0, max(0.0, score)),
            evidence=evidence,
        )

    def _score_role_alignment(self, task: SubTask, agent: AgentSpec) -> CapabilityScore:
        """Score how well agent role aligns with task needs.

        Args:
            task: Task to evaluate.
            agent: Agent to evaluate.

        Returns:
            Role alignment score.
        """
        role_map: Dict[AgentRole, Set[str]] = {
            AgentRole.CODER: {"coding", "system_design", "devops", "verification"},
            AgentRole.ANALYST: {"data_analysis", "research", "verification", "planning"},
            AgentRole.CREATIVE: {"creative_writing", "general"},
            AgentRole.RESEARCHER: {"research", "data_analysis", "general"},
            AgentRole.REVIEWER: {"verification", "research", "general"},
            AgentRole.PLANNER: {"planning", "system_design", "research"},
            AgentRole.EXECUTOR: {"coding", "devops", "data_analysis"},
            AgentRole.GENERALIST: {"general", "planning", "research"},
        }

        task_caps = task.required_capabilities
        aligned_caps = role_map.get(agent.role, set())

        overlap = task_caps & aligned_caps
        if not task_caps:
            score = 0.5
        else:
            score = len(overlap) / len(task_caps)

        return CapabilityScore(
            capability="role_alignment",
            score=min(1.0, score),
            evidence=f"Role={agent.role.name}, aligned_caps={len(overlap)}/{len(task_caps)}",
        )

    def _find_related_capabilities(self, capability: str) -> Set[str]:
        """Find capabilities related to given capability.

        Args:
            capability: Source capability.

        Returns:
            Set of related capability names.
        """
        # Simple taxonomy
        related_groups: List[Set[str]] = [
            {"coding", "system_design", "devops", "verification"},
            {"data_analysis", "research", "verification"},
            {"creative_writing", "general", "research"},
            {"planning", "system_design", "research"},
        ]
        for group in related_groups:
            if capability in group:
                return group - {capability}
        return set()


class CapabilityRouterImpl(CapabilityRouter):
    """Production capability router with scoring and load balancing.

    Matches tasks to specialist agents using multi-factor scoring
    with explainable decisions and automatic failover.
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        scorer: Optional[CapabilityScorer] = None,
        min_match_threshold: float = 0.4,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.scorer = scorer or CapabilityScorer(self.registry)
        self.min_match_threshold = min_match_threshold
        self.event_bus = event_bus
        self.logger = get_logger("capability_router")
        self._agent_cache: Dict[str, AgentSpec] = {}

    @async_timed
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

        Raises:
            NoAgentAvailableException: If no agent meets threshold.
        """
        with LogContext(
            module="capability_router",
            operation="match_agent",
            task_id=task.id,
        ):
            self.logger.info(
                "Matching agent for task",
                extra={
                    "task_id": str(task.id),
                    "required_caps": list(task.required_capabilities),
                    "available_agents": len(available_agents),
                },
            )

            if not available_agents:
                raise NoAgentAvailableException(
                    "No agents available in pool",
                    required_capabilities=list(task.required_capabilities),
                    context=ErrorContext(
                        module="capability_router",
                        operation="match_agent",
                        task_id=task.id,
                    ),
                )

            # Score all agents
            scored: List[Tuple[AgentSpec, float, List[CapabilityScore]]] = []
            for agent in available_agents:
                if not agent.enabled:
                    continue
                scores = await self.scorer.score(task, agent)
                avg_score = sum(s.score for s in scores) / len(scores) if scores else 0.0
                scored.append((agent, avg_score, scores))

            # Filter by threshold and sort
            viable = [(a, s, scores) for a, s, scores in scored if s >= self.min_match_threshold]
            viable.sort(key=lambda x: x[1], reverse=True)

            if not viable:
                best = max(scored, key=lambda x: x[1])
                self.logger.warning(
                    "No agent meets threshold, best match below minimum",
                    extra={
                        "best_score": best[1],
                        "threshold": self.min_match_threshold,
                        "agent": best[0].name,
                    },
                )
                # Return best effort if above absolute minimum
                if best[1] >= 0.2:
                    return best[0]
                raise NoAgentAvailableException(
                    f"No agent meets minimum capability threshold {self.min_match_threshold}",
                    required_capabilities=list(task.required_capabilities),
                    context=ErrorContext(
                        module="capability_router",
                        operation="match_agent",
                        task_id=task.id,
                    ),
                )

            best_agent, best_score, best_scores = viable[0]

            self.logger.info(
                "Agent matched",
                extra={
                    "agent_id": str(best_agent.id),
                    "agent_name": best_agent.name,
                    "score": best_score,
                    "scores": [
                        {"cap": s.capability, "score": round(s.score, 3)}
                        for s in best_scores
                    ],
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="agent_matched",
                        task_id=task.id,
                        agent_id=best_agent.id,
                        payload={
                            "score": best_score,
                            "capabilities": list(best_agent.capabilities),
                        },
                    )
                )

            return best_agent

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
        return await self.scorer.score(task, agent)

    async def register_agents(self, agents: List[AgentSpec]) -> None:
        """Bulk register agents in capability registry.

        Args:
            agents: Agents to register.
        """
        for agent in agents:
            await self.registry.register_agent(agent)
            self._agent_cache[str(agent.id)] = agent

    async def update_agent_load(self, agent_id: str, delta: int) -> None:
        """Update agent load tracking.

        Args:
            agent_id: Agent identifier.
            delta: Load change (+1 for new task, -1 for completion).
        """
        agent = self._agent_cache.get(agent_id)
        if agent:
            # Create updated copy
            new_load = max(0, agent.current_load + delta)
            updated = agent.model_copy(update={"current_load": new_load})
            self._agent_cache[agent_id] = updated

    async def get_agent_stats(self) -> Dict[str, Any]:
        """Get capability routing statistics.

        Returns:
            Statistics dictionary.
        """
        total = len(self._agent_cache)
        by_role: Dict[str, int] = {}
        by_capability: Dict[str, int] = {}
        for agent in self._agent_cache.values():
            role = agent.role.name
            by_role[role] = by_role.get(role, 0) + 1
            for cap in agent.capabilities:
                by_capability[cap] = by_capability.get(cap, 0) + 1

        return {
            "total_agents": total,
            "by_role": by_role,
            "by_capability": by_capability,
            "registered_capabilities": len(self.registry.list_capabilities()),
        }


# Factory
async def create_capability_router(
    custom_capabilities: Optional[Dict[str, CapabilityRegistryEntry]] = None,
    min_match_threshold: float = 0.4,
    event_bus: Optional[Any] = None,
) -> CapabilityRouterImpl:
    """Factory for creating configured capability router.

    Args:
        custom_capabilities: Custom capability definitions.
        min_match_threshold: Minimum match score threshold.
        event_bus: Optional event bus.

    Returns:
        Configured CapabilityRouterImpl.
    """
    registry = CapabilityRegistry(custom_capabilities)
    scorer = CapabilityScorer(registry)
    return CapabilityRouterImpl(
        registry=registry,
        scorer=scorer,
        min_match_threshold=min_match_threshold,
        event_bus=event_bus,
  )
