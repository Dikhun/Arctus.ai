"""Arctus AI Orchestration Framework - Learning Manager.

Responsible for execution analytics, strategy learning,
performance history, and adaptive optimization.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from domain_models import OrchestrationResult, WorkerResult
from exceptions import ErrorContext, LearningException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("learning_manager")


@dataclass
class ExecutionRecord:
    """Recorded execution for learning."""

    result: OrchestrationResult
    strategy_used: Dict[str, Any]
    outcomes: Dict[str, Any]  # success/failure per task
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StrategyProfile:
    """Learned strategy for a task type."""

    task_type: str
    preferred_providers: List[str]
    preferred_agents: List[str]
    optimal_parallelism: int
    avg_cost: float
    avg_latency_ms: float
    avg_quality: float
    success_rate: float
    sample_count: int = 0
    last_updated: Optional[datetime] = None


class LearningManagerImpl:
    """Production learning manager with strategy optimization.

    Tracks execution outcomes, learns optimal strategies,
    and adapts orchestration decisions over time.
    """

    def __init__(
        self,
        history_size: int = 1000,
        min_samples_for_strategy: int = 5,
        learning_rate: float = 0.1,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.history_size = history_size
        self.min_samples = min_samples_for_strategy
        self.learning_rate = learning_rate
        self.event_bus = event_bus
        self.logger = get_logger("learning_manager")

        self._history: List[ExecutionRecord] = []
        self._strategies: Dict[str, StrategyProfile] = {}
        self._provider_stats: Dict[str, Dict[str, Any]] = {}
        self._agent_stats: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    @async_timed
    async def record_execution(self, result: OrchestrationResult) -> None:
        """Record execution result for learning.

        Args:
            result: Completed orchestration result.
        """
        with LogContext(module="learning_manager", operation="record_execution"):
            # Determine outcomes
            outcomes: Dict[str, Any] = {}
            for wr in result.worker_results:
                outcomes[str(wr.task_id)] = {
                    "success": not wr.output.startswith("FAILED"),
                    "latency_ms": wr.latency_ms,
                    "provider": wr.provider,
                    "model": wr.model,
                    "cost": float(wr.cost_usd),
                }

            # Infer strategy used
            strategy = {
                "providers": result.providers_used,
                "agents": [str(a) for a in result.agents_used],
                "parallelism": len(result.worker_results),
                "execution_mode": result.status.name,
            }

            record = ExecutionRecord(
                result=result,
                strategy_used=strategy,
                outcomes=outcomes,
            )

            async with self._lock:
                self._history.append(record)
                if len(self._history) > self.history_size:
                    self._history = self._history[-self.history_size:]

                # Update provider stats
                for provider in result.providers_used:
                    if provider not in self._provider_stats:
                        self._provider_stats[provider] = {
                            "uses": 0, "successes": 0, "total_latency": 0.0, "total_cost": 0.0,
                        }
                    stats = self._provider_stats[provider]
                    stats["uses"] += 1
                    provider_results = [o for o in outcomes.values() if o.get("provider") == provider]
                    stats["successes"] += sum(1 for p in provider_results if p["success"])
                    stats["total_latency"] += sum(p["latency_ms"] for p in provider_results)
                    stats["total_cost"] += sum(p["cost"] for p in provider_results)

                # Update agent stats
                for agent_id in result.agents_used:
                    aid = str(agent_id)
                    if aid not in self._agent_stats:
                        self._agent_stats[aid] = {
                            "uses": 0, "successes": 0, "total_latency": 0.0,
                        }
                    stats = self._agent_stats[aid]
                    stats["uses"] += 1

            self.logger.info(
                "Execution recorded",
                extra={
                    "plan_id": str(result.plan_id),
                    "total_tasks": len(result.worker_results),
                    "successful": sum(1 for o in outcomes.values() if o["success"]),
                },
            )

            # Trigger strategy update
            await self._update_strategies()

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="execution_recorded",
                        plan_id=result.plan_id,
                        payload={
                            "total_tasks": len(result.worker_results),
                            "success_rate": sum(1 for o in outcomes.values() if o["success"]) / len(outcomes),
                        },
                    )
                )

    async def _update_strategies(self) -> None:
        """Update learned strategies from history."""
        async with self._lock:
            # Group by task characteristics (simplified: use provider combination as proxy)
            task_groups: Dict[str, List[ExecutionRecord]] = {}

            for record in self._history:
                key = self._classify_task(record.result)
                if key not in task_groups:
                    task_groups[key] = []
                task_groups[key].append(record)

            for task_type, records in task_groups.items():
                if len(records) < self.min_samples:
                    continue

                await self._learn_strategy(task_type, records)

    def _classify_task(self, result: OrchestrationResult) -> str:
        """Classify task type from result.

        Args:
            result: Execution result.

        Returns:
            Task type string.
        """
        # Use metadata or infer from providers/agents
        if result.metadata.get("task_type"):
            return result.metadata["task_type"]

        # Infer from provider mix
        providers = tuple(sorted(result.providers_used))
        return f"providers:{','.join(providers)}"

    async def _learn_strategy(
        self,
        task_type: str,
        records: List[ExecutionRecord],
    ) -> None:
        """Learn optimal strategy for task type.

        Args:
            task_type: Task classification.
            records: Historical records.
        """
        # Calculate aggregate statistics
        total = len(records)
        successful = [r for r in records if r.result.status.name == "COMPLETED"]

        if not successful:
            return

        # Provider preferences by success rate
        provider_success: Dict[str, List[bool]] = {}
        for r in successful:
            for wr in r.result.worker_results:
                p = wr.provider or "unknown"
                if p not in provider_success:
                    provider_success[p] = []
                provider_success[p].append(not wr.output.startswith("FAILED"))

        preferred_providers = sorted(
            provider_success.keys(),
            key=lambda p: sum(provider_success[p]) / len(provider_success[p]),
            reverse=True,
        )[:3]

        # Agent preferences
        agent_success: Dict[str, List[bool]] = {}
        for r in successful:
            for wr in r.result.worker_results:
                a = str(wr.agent_id) if wr.agent_id else "unknown"
                if a not in agent_success:
                    agent_success[a] = []
                agent_success[a].append(not wr.output.startswith("FAILED"))

        preferred_agents = sorted(
            agent_success.keys(),
            key=lambda a: sum(agent_success[a]) / len(agent_success[a]),
            reverse=True,
        )[:3]

        # Average metrics
        avg_cost = sum(float(r.result.total_cost_usd) for r in successful) / len(successful)
        avg_latency = sum(r.result.total_latency_ms for r in successful) / len(successful)
        avg_quality = sum(
            (r.result.quality_score.overall if r.result.quality_score else 0.5)
            for r in successful
        ) / len(successful)

        success_rate = len(successful) / total

        # Optimal parallelism
        parallelism_counts = [len(r.result.worker_results) for r in successful]
        optimal_parallel = int(sum(parallelism_counts) / len(parallelism_counts)) if parallelism_counts else 1

        strategy = StrategyProfile(
            task_type=task_type,
            preferred_providers=preferred_providers,
            preferred_agents=preferred_agents,
            optimal_parallelism=optimal_parallel,
            avg_cost=avg_cost,
            avg_latency_ms=avg_latency,
            avg_quality=avg_quality,
            success_rate=success_rate,
            sample_count=total,
            last_updated=datetime.utcnow(),
        )

        # Update with exponential moving average
        existing = self._strategies.get(task_type)
        if existing:
            alpha = self.learning_rate
            strategy = StrategyProfile(
                task_type=task_type,
                preferred_providers=preferred_providers,
                preferred_agents=preferred_agents,
                optimal_parallelism=int(alpha * optimal_parallel + (1 - alpha) * existing.optimal_parallelism),
                avg_cost=alpha * avg_cost + (1 - alpha) * existing.avg_cost,
                avg_latency_ms=alpha * avg_latency + (1 - alpha) * existing.avg_latency_ms,
                avg_quality=alpha * avg_quality + (1 - alpha) * existing.avg_quality,
                success_rate=alpha * success_rate + (1 - alpha) * existing.success_rate,
                sample_count=existing.sample_count + total,
                last_updated=datetime.utcnow(),
            )

        self._strategies[task_type] = strategy

        self.logger.info(
            "Strategy learned",
            extra={
                "task_type": task_type,
                "sample_count": total,
                "success_rate": round(success_rate, 3),
                "optimal_parallelism": optimal_parallel,
            },
        )

    async def get_strategy(self, task_type: str) -> Dict[str, Any]:
        """Get learned strategy for task type.

        Args:
            task_type: Classification of task.

        Returns:
            Strategy parameters.
        """
        async with self._lock:
            strategy = self._strategies.get(task_type)

        if not strategy:
            # Return default strategy
            return {
                "task_type": task_type,
                "preferred_providers": [],
                "preferred_agents": [],
                "optimal_parallelism": 1,
                "avg_cost": 0.0,
                "avg_latency_ms": 0.0,
                "avg_quality": 0.0,
                "success_rate": 0.0,
                "sample_count": 0,
                "confidence": "low",
            }

        return {
            "task_type": strategy.task_type,
            "preferred_providers": strategy.preferred_providers,
            "preferred_agents": strategy.preferred_agents,
            "optimal_parallelism": strategy.optimal_parallelism,
            "avg_cost": strategy.avg_cost,
            "avg_latency_ms": strategy.avg_latency_ms,
            "avg_quality": strategy.avg_quality,
            "success_rate": strategy.success_rate,
            "sample_count": strategy.sample_count,
            "last_updated": strategy.last_updated.isoformat() if strategy.last_updated else None,
            "confidence": "high" if strategy.sample_count > 50 else "medium" if strategy.sample_count > 10 else "low",
        }

    async def get_provider_ranking(self) -> List[Tuple[str, float]]:
        """Get providers ranked by learned performance.

        Returns:
            List of (provider, score) tuples.
        """
        async with self._lock:
            rankings = []
            for provider, stats in self._provider_stats.items():
                if stats["uses"] > 0:
                    success_rate = stats["successes"] / stats["uses"]
                    avg_latency = stats["total_latency"] / stats["uses"]
                    avg_cost = stats["total_cost"] / stats["uses"]

                    # Composite score
                    score = (
                        success_rate * 0.5 +
                        max(0, 1.0 - avg_latency / 10000) * 0.3 +
                        max(0, 1.0 - avg_cost / 10) * 0.2
                    )
                    rankings.append((provider, score))

            rankings.sort(key=lambda x: x[1], reverse=True)
            return rankings

    async def get_agent_ranking(self) -> List[Tuple[str, float]]:
        """Get agents ranked by learned performance.

        Returns:
            List of (agent_id, score) tuples.
        """
        async with self._lock:
            rankings = []
            for agent_id, stats in self._agent_stats.items():
                if stats["uses"] > 0:
                    success_rate = stats["successes"] / stats["uses"]
                    avg_latency = stats["total_latency"] / stats["uses"]
                    score = success_rate * 0.7 + max(0, 1.0 - avg_latency / 10000) * 0.3
                    rankings.append((agent_id, score))

            rankings.sort(key=lambda x: x[1], reverse=True)
            return rankings

    async def export_knowledge(self) -> Dict[str, Any]:
        """Export learned knowledge for persistence.

        Returns:
            Knowledge dictionary.
        """
        async with self._lock:
            return {
                "strategies": {
                    k: {
                        "task_type": v.task_type,
                        "preferred_providers": v.preferred_providers,
                        "preferred_agents": v.preferred_agents,
                        "optimal_parallelism": v.optimal_parallelism,
                        "avg_cost": v.avg_cost,
                        "avg_latency_ms": v.avg_latency_ms,
                        "avg_quality": v.avg_quality,
                        "success_rate": v.success_rate,
                        "sample_count": v.sample_count,
                    }
                    for k, v in self._strategies.items()
                },
                "provider_stats": dict(self._provider_stats),
                "agent_stats": dict(self._agent_stats),
                "history_count": len(self._history),
            }

    async def import_knowledge(self, knowledge: Dict[str, Any]) -> None:
        """Import learned knowledge from persistence.

        Args:
            knowledge: Knowledge dictionary.
        """
        async with self._lock:
            for task_type, data in knowledge.get("strategies", {}).items():
                self._strategies[task_type] = StrategyProfile(
                    task_type=data["task_type"],
                    preferred_providers=data["preferred_providers"],
                    preferred_agents=data["preferred_agents"],
                    optimal_parallelism=data["optimal_parallelism"],
                    avg_cost=data["avg_cost"],
                    avg_latency_ms=data["avg_latency_ms"],
                    avg_quality=data["avg_quality"],
                    success_rate=data["success_rate"],
                    sample_count=data["sample_count"],
                )

            self._provider_stats.update(knowledge.get("provider_stats", {}))
            self._agent_stats.update(knowledge.get("agent_stats", {}))

        self.logger.info("Knowledge imported", extra={"strategies": len(self._strategies)})


# Factory
async def create_learning_manager(
    history_size: int = 1000,
    learning_rate: float = 0.1,
    event_bus: Optional[Any] = None,
) -> LearningManagerImpl:
    """Factory for creating configured learning manager.

    Args:
        history_size: Maximum history records.
        learning_rate: Strategy update rate.
        event_bus: Optional event bus.

    Returns:
        Configured LearningManagerImpl.
    """
    return LearningManagerImpl(
        history_size=history_size,
        learning_rate=learning_rate,
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
