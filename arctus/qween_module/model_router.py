"""Arctus AI Orchestration Framework - Model Router.

Responsible for provider selection, model capability scoring,
latency-aware routing, cost-aware routing, quality-aware routing,
and automatic model fallback.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import (
    CostEstimate,
    LatencyEstimate,
    ProviderModel,
    ProviderStatus,
    SubTask,
    TokenCount,
)
from exceptions import (
    ErrorContext,
    ModelRouterException,
    NoProviderAvailableException,
)
from infrastructure import AtomicCounter, LogContext, async_timed, get_logger
from protocols import ModelRouter


logger = get_logger("model_router")


@dataclass
class RoutingScore:
    """Composite score for provider-model selection."""

    provider: str
    model: str
    latency_score: float = 0.0
    cost_score: float = 0.0
    quality_score: float = 0.0
    capability_score: float = 0.0
    composite: float = 0.0


class ModelCapabilityScorer:
    """Scores model capabilities against task requirements."""

    CAPABILITY_REGISTRY: Dict[str, Dict[str, float]] = {
        "openai": {
            "gpt-4o": {"coding": 0.95, "analysis": 0.95, "creative": 0.90, "reasoning": 0.95, "vision": 0.95},
            "gpt-4o-mini": {"coding": 0.85, "analysis": 0.85, "creative": 0.80, "reasoning": 0.85, "vision": 0.85},
            "gpt-4-turbo": {"coding": 0.93, "analysis": 0.94, "creative": 0.92, "reasoning": 0.95, "vision": 0.90},
        },
        "anthropic": {
            "claude-3-5-sonnet-20241022": {"coding": 0.96, "analysis": 0.96, "creative": 0.94, "reasoning": 0.96, "vision": 0.95},
            "claude-3-opus-20240229": {"coding": 0.97, "analysis": 0.97, "creative": 0.95, "reasoning": 0.98, "vision": 0.95},
            "claude-3-haiku-20240307": {"coding": 0.82, "analysis": 0.83, "creative": 0.80, "reasoning": 0.82, "vision": 0.80},
        },
        "google": {
            "gemini-1.5-pro": {"coding": 0.90, "analysis": 0.92, "creative": 0.88, "reasoning": 0.91, "vision": 0.95},
            "gemini-1.5-flash": {"coding": 0.85, "analysis": 0.86, "creative": 0.84, "reasoning": 0.85, "vision": 0.90},
        },
        "groq": {
            "llama-3.1-70b-versatile": {"coding": 0.88, "analysis": 0.87, "creative": 0.85, "reasoning": 0.88, "vision": 0.0},
            "mixtral-8x7b-32768": {"coding": 0.82, "analysis": 0.84, "creative": 0.83, "reasoning": 0.84, "vision": 0.0},
        },
        "deepseek": {
            "deepseek-chat": {"coding": 0.90, "analysis": 0.91, "creative": 0.87, "reasoning": 0.92, "vision": 0.0},
            "deepseek-reasoner": {"coding": 0.88, "analysis": 0.93, "creative": 0.85, "reasoning": 0.95, "vision": 0.0},
        },
        "ollama": {
            "llama3.1": {"coding": 0.80, "analysis": 0.78, "creative": 0.75, "reasoning": 0.79, "vision": 0.0},
            "mistral": {"coding": 0.78, "analysis": 0.77, "creative": 0.76, "reasoning": 0.78, "vision": 0.0},
        },
    }

    def __init__(self, custom_scores: Optional[Dict[str, Dict[str, float]]] = None) -> None:
        self.scores = custom_scores or {}

    def score(self, provider: str, model: str, required_caps: Set[str]) -> float:
        """Score how well a model matches required capabilities.

        Args:
            provider: Provider name.
            model: Model identifier.
            required_caps: Required capability names.

        Returns:
            Normalized capability match score [0, 1].
        """
        registry = self.CAPABILITY_REGISTRY.get(provider, {})
        model_scores = registry.get(model, {})
        custom = self.scores.get(provider, {}).get(model, {})

        if not required_caps:
            return 0.8  # Default good score when no specific caps

        scores: List[float] = []
        for cap in required_caps:
            score = custom.get(cap, model_scores.get(cap, 0.5))
            scores.append(score)

        return sum(scores) / len(scores) if scores else 0.5


class LatencyAwareRouter:
    """Routes based on predicted latency performance."""

    def __init__(self, history_window: int = 100) -> None:
        self.latency_history: Dict[str, List[float]] = {}
        self.history_window = history_window

    def record(self, provider: str, model: str, latency_ms: float) -> None:
        """Record observed latency for learning.

        Args:
            provider: Provider name.
            model: Model name.
            latency_ms: Observed latency.
        """
        key = f"{provider}:{model}"
        if key not in self.latency_history:
            self.latency_history[key] = []
        self.latency_history[key].append(latency_ms)
        if len(self.latency_history[key]) > self.history_window:
            self.latency_history[key] = self.latency_history[key][-self.history_window:]

    def predict(self, provider: str, model: str) -> LatencyEstimate:
        """Predict latency for provider-model combination.

        Args:
            provider: Provider name.
            model: Model name.

        Returns:
            Latency estimate with confidence.
        """
        key = f"{provider}:{model}"
        history = self.latency_history.get(key, [])

        if len(history) >= 5:
            avg = sum(history) / len(history)
            p95 = sorted(history)[int(len(history) * 0.95)] if len(history) > 20 else avg * 1.5
            return LatencyEstimate(
                provider=provider,
                model=model,
                estimated_ms=avg,
                confidence=min(0.95, 0.5 + len(history) * 0.01),
                percentile_95_ms=p95,
            )

        # Default estimates by provider tier
        defaults = {
            "groq": 500.0,
            "openai": 2000.0,
            "anthropic": 2500.0,
            "google": 1800.0,
            "deepseek": 3000.0,
            "ollama": 5000.0,
        }
        default = defaults.get(provider, 3000.0)
        return LatencyEstimate(
            provider=provider,
            model=model,
            estimated_ms=default,
            confidence=0.5,
        )


class CostAwareRouter:
    """Routes based on cost optimization."""

    # Cost per 1K tokens (input, output) in USD
    COST_TABLE: Dict[str, Dict[str, Tuple[Decimal, Decimal]]] = {
        "openai": {
            "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
            "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
            "gpt-4-turbo": (Decimal("0.01"), Decimal("0.03")),
        },
        "anthropic": {
            "claude-3-5-sonnet-20241022": (Decimal("0.003"), Decimal("0.015")),
            "claude-3-opus-20240229": (Decimal("0.015"), Decimal("0.075")),
            "claude-3-haiku-20240307": (Decimal("0.00025"), Decimal("0.00125")),
        },
        "google": {
            "gemini-1.5-pro": (Decimal("0.0035"), Decimal("0.0105")),
            "gemini-1.5-flash": (Decimal("0.00035"), Decimal("0.00105")),
        },
        "groq": {
            "llama-3.1-70b-versatile": (Decimal("0.00059"), Decimal("0.00079")),
            "mixtral-8x7b-32768": (Decimal("0.00027"), Decimal("0.00027")),
        },
        "deepseek": {
            "deepseek-chat": (Decimal("0.00014"), Decimal("0.00028")),
            "deepseek-reasoner": (Decimal("0.00014"), Decimal("0.00028")),
        },
        "ollama": {
            "llama3.1": (Decimal("0"), Decimal("0")),
            "mistral": (Decimal("0"), Decimal("0")),
        },
    }

    def estimate(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> CostEstimate:
        """Estimate cost for token usage.

        Args:
            provider: Provider name.
            model: Model name.
            prompt_tokens: Expected prompt tokens.
            completion_tokens: Expected completion tokens.

        Returns:
            Cost estimate.
        """
        provider_costs = self.COST_TABLE.get(provider, {})
        input_cost, output_cost = provider_costs.get(model, (Decimal("0.01"), Decimal("0.03")))

        total = (Decimal(prompt_tokens) / 1000 * input_cost +
                 Decimal(completion_tokens) / 1000 * output_cost)

        return CostEstimate(
            provider=provider,
            model=model,
            estimated_tokens=TokenCount(prompt=prompt_tokens, completion=completion_tokens),
            estimated_cost_usd=total.quantize(Decimal("0.000001")),
        )


class QualityAwareRouter:
    """Routes based on quality requirements and model performance."""

    QUALITY_TIERS: Dict[str, Dict[str, float]] = {
        "coding": {"openai": 0.95, "anthropic": 0.96, "google": 0.90, "deepseek": 0.90, "groq": 0.88, "ollama": 0.80},
        "analysis": {"openai": 0.95, "anthropic": 0.96, "google": 0.92, "deepseek": 0.91, "groq": 0.87, "ollama": 0.78},
        "creative": {"openai": 0.90, "anthropic": 0.94, "google": 0.88, "deepseek": 0.87, "groq": 0.85, "ollama": 0.75},
        "reasoning": {"openai": 0.95, "anthropic": 0.96, "google": 0.91, "deepseek": 0.92, "groq": 0.88, "ollama": 0.79},
        "vision": {"openai": 0.95, "anthropic": 0.95, "google": 0.95, "deepseek": 0.0, "groq": 0.0, "ollama": 0.0},
    }

    def score(self, provider: str, task_domain: str) -> float:
        """Score provider quality for a task domain.

        Args:
            provider: Provider name.
            task_domain: Task domain/capability.

        Returns:
            Quality score [0, 1].
        """
        domain_scores = self.QUALITY_TIERS.get(task_domain, {})
        return domain_scores.get(provider, 0.5)


class ModelRouterImpl(ModelRouter):
    """Production model router with multi-factor scoring and fallback.

    Integrates latency, cost, quality, and capability awareness to
    select optimal provider-model pairs with automatic fallback chains.
    """

    def __init__(
        self,
        providers: List[ProviderModel],
        capability_scorer: Optional[ModelCapabilityScorer] = None,
        latency_router: Optional[LatencyAwareRouter] = None,
        cost_router: Optional[CostAwareRouter] = None,
        quality_router: Optional[QualityAwareRouter] = None,
        default_weights: Optional[Dict[str, float]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.providers = {p.name: p for p in providers}
        self.capability_scorer = capability_scorer or ModelCapabilityScorer()
        self.latency_router = latency_router or LatencyAwareRouter()
        self.cost_router = cost_router or CostAwareRouter()
        self.quality_router = quality_router or QualityAwareRouter()
        self.weights = default_weights or {
            "latency": 0.25,
            "cost": 0.25,
            "quality": 0.30,
            "capability": 0.20,
        }
        self.event_bus = event_bus
        self._fallback_counter = AtomicCounter()
        self.logger = get_logger("model_router")

    @async_timed
    async def route(
        self,
        task: SubTask,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """Select optimal provider and model for task execution.

        Args:
            task: The subtask requiring model assignment.
            preferences: Optional routing preferences with keys:
                - prioritize: "latency" | "cost" | "quality" | "capability"
                - exclude_providers: List[str]
                - require_vision: bool
                - max_cost_usd: float
                - max_latency_ms: float

        Returns:
            Selected (provider_name, model_name).

        Raises:
            NoProviderAvailableException: If no suitable provider found.
        """
        prefs = preferences or {}
        with LogContext(
            module="model_router",
            operation="route",
            task_id=task.id,
        ):
            self.logger.info(
                "Routing task",
                extra={
                    "task_id": str(task.id),
                    "required_caps": list(task.required_capabilities),
                    "preferences": prefs,
                },
            )

            # Filter available providers
            candidates = self._filter_providers(prefs)
            if not candidates:
                raise NoProviderAvailableException(
                    "No providers match routing criteria",
                    attempted_providers=list(self.providers.keys()),
                    context=ErrorContext(
                        module="model_router",
                        operation="route",
                        task_id=task.id,
                    ),
                )

            # Score all provider-model combinations
            scores: List[RoutingScore] = []
            for provider_name, provider in candidates.items():
                for model in provider.models:
                    score = self._score_combination(
                        provider_name, model, task, prefs
                    )
                    scores.append(score)

            # Sort by composite score descending
            scores.sort(key=lambda s: s.composite, reverse=True)

            # Try candidates in order with fallback
            attempted: List[str] = []
            for score in scores:
                provider = score.provider
                model = score.model
                key = f"{provider}:{model}"

                # Check health via provider_health module integration
                if await self._is_healthy(provider, model):
                    self.logger.info(
                        "Routed to provider",
                        extra={
                            "provider": provider,
                            "model": model,
                            "score": score.composite,
                            "task_id": str(task.id),
                        },
                    )
                    if self.event_bus:
                        await self.event_bus.publish(
                            OrchestrationEvent(
                                event_type="model_routed",
                                task_id=task.id,
                                provider=provider,
                                payload={
                                    "model": model,
                                    "score": score.composite,
                                    "latency_score": score.latency_score,
                                    "cost_score": score.cost_score,
                                    "quality_score": score.quality_score,
                                },
                            )
                        )
                    return provider, model

                attempted.append(key)
                self.logger.warning(
                    "Provider unhealthy, trying fallback",
                    extra={"provider": provider, "model": model, "task_id": str(task.id)},
                )
                await self._fallback_counter.increment()

            # All candidates exhausted
            raise NoProviderAvailableException(
                f"All {len(scores)} provider-model combinations unavailable",
                attempted_providers=attempted,
                context=ErrorContext(
                    module="model_router",
                    operation="route",
                    task_id=task.id,
                ),
            )

    def _filter_providers(self, prefs: Dict[str, Any]) -> Dict[str, ProviderModel]:
        """Filter providers based on preferences."""
        exclude = set(prefs.get("exclude_providers", []))
        require_vision = prefs.get("require_vision", False)

        filtered: Dict[str, ProviderModel] = {}
        for name, provider in self.providers.items():
            if name in exclude:
                continue
            if provider.status in (ProviderStatus.OFFLINE, ProviderStatus.CIRCUIT_OPEN):
                continue
            if require_vision and "vision" not in provider.capabilities:
                continue
            filtered[name] = provider

        return filtered

    def _score_combination(
        self,
        provider: str,
        model: str,
        task: SubTask,
        prefs: Dict[str, Any],
    ) -> RoutingScore:
        """Calculate composite routing score for provider-model."""
        # Adjust weights if preference specified
        weights = dict(self.weights)
        prioritize = prefs.get("prioritize")
        if prioritize and prioritize in weights:
            # Boost preferred factor
            weights[prioritize] *= 2.0
            # Renormalize
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}

        # Latency score (lower is better, invert)
        lat = self.latency_router.predict(provider, model)
        max_lat = prefs.get("max_latency_ms", 10000.0)
        latency_score = max(0.0, 1.0 - (lat.estimated_ms / max_lat)) if max_lat > 0 else 0.5

        # Cost score (lower is better, invert)
        est_tokens = task.estimated_tokens or TokenCount(total=1000)
        cost = self.cost_router.estimate(provider, model, est_tokens.prompt, est_tokens.completion)
        max_cost = Decimal(str(prefs.get("max_cost_usd", 1.0)))
        cost_score = max(0.0, 1.0 - float(cost.estimated_cost_usd / max_cost)) if max_cost > 0 else 0.5

        # Quality score
        domain = next(iter(task.required_capabilities), "general") if task.required_capabilities else "general"
        quality_score = self.quality_router.score(provider, domain)

        # Capability score
        cap_score = self.capability_scorer.score(provider, model, task.required_capabilities)

        # Composite
        composite = (
            weights["latency"] * latency_score +
            weights["cost"] * cost_score +
            weights["quality"] * quality_score +
            weights["capability"] * cap_score
        )

        return RoutingScore(
            provider=provider,
            model=model,
            latency_score=latency_score,
            cost_score=cost_score,
            quality_score=quality_score,
            capability_score=cap_score,
            composite=composite,
        )

    async def _is_healthy(self, provider: str, model: str) -> bool:
        """Check if provider-model is healthy for routing.

        In production, delegates to provider_health module.
        """
        provider_obj = self.providers.get(provider)
        if not provider_obj:
            return False
        return provider_obj.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)

    async def get_fallback_chain(
        self,
        primary_provider: str,
        primary_model: str,
        task: SubTask,
    ) -> List[Tuple[str, str]]:
        """Generate ordered fallback chain for a task.

        Args:
            primary_provider: Primary selected provider.
            primary_model: Primary selected model.
            task: Task for context.

        Returns:
            Ordered list of (provider, model) fallback options.
        """
        scores: List[RoutingScore] = []
        for name, provider in self.providers.items():
            for model in provider.models:
                if name == primary_provider and model == primary_model:
                    continue
                score = self._score_combination(name, model, task, {})
                scores.append(score)

        scores.sort(key=lambda s: s.composite, reverse=True)
        return [(s.provider, s.model) for s in scores[:5]]

    def record_latency(self, provider: str, model: str, latency_ms: float) -> None:
        """Record observed latency for future routing decisions.

        Args:
            provider: Provider name.
            model: Model name.
            latency_ms: Observed latency.
        """
        self.latency_router.record(provider, model,
