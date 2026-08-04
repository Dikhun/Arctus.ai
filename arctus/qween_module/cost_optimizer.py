"""Arctus AI Orchestration Framework - Cost Optimizer.

Responsible for token optimization, API cost optimization,
budget enforcement, and cost estimation.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from domain_models import CostEstimate, ExecutionPlan, SubTask, TokenCount
from exceptions import BudgetExceededException, ErrorContext, ResourceException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("cost_optimizer")


class CostOptimizerImpl:
    """Production cost optimizer with budget enforcement.

    Estimates, tracks, and optimizes execution costs with
    configurable budgets and token optimization strategies.
    """

    # Provider cost table: (input_per_1k, output_per_1k) in USD
    COST_TABLE: Dict[str, Dict[str, tuple]] = {
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

    def __init__(
        self,
        budget_usd: Optional[Decimal] = None,
        budget_type: str = "per_request",
        token_optimization_enabled: bool = True,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.budget = budget_usd
        self.budget_type = budget_type
        self.token_optimization_enabled = token_optimization_enabled
        self.event_bus = event_bus
        self.logger = get_logger("cost_optimizer")
        self._spent: Dict[str, Decimal] = {}  # budget_key -> amount
        self._lock = asyncio.Lock()

    @async_timed
    async def estimate_cost(self, plan: ExecutionPlan) -> CostEstimate:
        """Estimate total cost for executing a plan.

        Args:
            plan: The execution plan.

        Returns:
            Aggregated cost estimate.
        """
        with LogContext(module="cost_optimizer", operation="estimate_cost", plan_id=plan.id):
            total_input = 0
            total_output = 0
            total_cost = Decimal("0")

            for task in plan.subtasks:
                provider = task.assigned_provider or "openai"
                model = task.assigned_model or "gpt-4o-mini"

                est_tokens = task.estimated_tokens or TokenCount(prompt=500, completion=500)
                total_input += est_tokens.prompt
                total_output += est_tokens.completion

                cost = self._calculate_cost(provider, model, est_tokens.prompt, est_tokens.completion)
                total_cost += cost

            estimate = CostEstimate(
                provider="aggregate",
                model="mixed",
                estimated_tokens=TokenCount(prompt=total_input, completion=total_output),
                estimated_cost_usd=total_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            )

            self.logger.info(
                "Cost estimated",
                extra={
                    "plan_id": str(plan.id),
                    "estimated_usd": float(estimate.estimated_cost_usd),
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                },
            )

            return estimate

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """Calculate cost for token usage.

        Args:
            provider: Provider name.
            model: Model name.
            input_tokens: Input token count.
            output_tokens: Output token count.

        Returns:
            Cost in USD.
        """
        provider_costs = self.COST_TABLE.get(provider, {})
        input_rate, output_rate = provider_costs.get(model, (Decimal("0.01"), Decimal("0.03")))

        input_cost = Decimal(input_tokens) / 1000 * input_rate
        output_cost = Decimal(output_tokens) / 1000 * output_rate

        return input_cost + output_cost

    @async_timed
    async def optimize_tokens(self, text: str, target_tokens: int) -> str:
        """Compress text to fit token budget.

        Args:
            text: Source text.
            target_tokens: Target token count.

        Returns:
            Optimized text.
        """
        with LogContext(module="cost_optimizer", operation="optimize_tokens"):
            if not self.token_optimization_enabled:
                return text

            current_tokens = self._estimate_tokens(text)
            if current_tokens <= target_tokens:
                return text

            self.logger.info(
                "Optimizing tokens",
                extra={"current": current_tokens, "target": target_tokens},
            )

            # Strategy 1: Remove redundant whitespace
            optimized = re.sub(r'\n{3,}', '\n\n', text)

            # Strategy 2: Remove filler words
            fillers = ["very", "really", "quite", "rather", "just", "actually",
                      "basically", "literally", "definitely", "certainly"]
            for filler in fillers:
                optimized = re.sub(rf'\b{filler}\b\s+', '', optimized, flags=re.IGNORECASE)

            # Strategy 3: Shorten common phrases
            replacements = {
                "in order to": "to",
                "due to the fact that": "because",
                "at this point in time": "now",
                "in the event that": "if",
                "for the purpose of": "for",
                "with regard to": "about",
                "in relation to": "about",
            }
            for long, short in replacements.items():
                optimized = re.sub(rf'\b{long}\b', short, optimized, flags=re.IGNORECASE)

            # Strategy 4: Truncate if still over
            current = self._estimate_tokens(optimized)
            if current > target_tokens:
                # Keep most important parts (beginning and end)
                words = optimized.split()
                target_words = int(target_tokens / 1.3)

                if len(words) > target_words:
                    keep_start = int(target_words * 0.6)
                    keep_end = int(target_words * 0.2)
                    optimized = (
                        " ".join(words[:keep_start]) +
                        f"\n\n... [{len(words) - keep_start - keep_end} words truncated] ...\n\n" +
                        " ".join(words[-keep_end:])
                    )

            final_tokens = self._estimate_tokens(optimized)
            self.logger.info(
                "Token optimization complete",
                extra={"original": current_tokens, "final": final_tokens, "reduction": current_tokens - final_tokens},
            )

            return optimized

    async def check_budget(
        self,
        estimated_cost: CostEstimate,
        budget_key: str = "default",
    ) -> bool:
        """Check if estimated cost fits within budget.

        Args:
            estimated_cost: Cost to check.
            budget_key: Budget identifier.

        Returns:
            True if within budget.

        Raises:
            BudgetExceededException: If over budget.
        """
        if self.budget is None:
            return True

        async with self._lock:
            spent = self._spent.get(budget_key, Decimal("0"))
            projected = spent + estimated_cost.estimated_cost_usd

            if projected > self.budget:
                raise BudgetExceededException(
                    f"Budget exceeded: projected ${projected} > limit ${self.budget}",
                    budget_type=self.budget_type,
                    limit=float(self.budget),
                    current=float(spent),
                    context=ErrorContext(
                        module="cost_optimizer",
                        operation="check_budget",
                    ),
                )

            return True

    async def record_spend(
        self,
        cost_usd: Decimal,
        budget_key: str = "default",
    ) -> None:
        """Record actual spend against budget.

        Args:
            cost_usd: Actual cost incurred.
            budget_key: Budget identifier.
        """
        async with self._lock:
            current = self._spent.get(budget_key, Decimal("0"))
            self._spent[budget_key] = current + cost_usd

        self.logger.info(
            "Spend recorded",
            extra={"budget_key": budget_key, "amount": float(cost_usd), "total": float(self._spent.get(budget_key, Decimal("0")))},
        )

        if self.event_bus:
            await self.event_bus.publish(
                OrchestrationEvent(
                    event_type="cost_recorded",
                    payload={
                        "budget_key": budget_key,
                        "amount": float(cost_usd),
                        "total_spent": float(self._spent[budget_key]),
                    },
                )
            )

    async def get_budget_status(self, budget_key: str = "default") -> Dict[str, Any]:
        """Get current budget status.

        Args:
            budget_key: Budget identifier.

        Returns:
            Status dictionary.
        """
        async with self._lock:
            spent = self._spent.get(budget_key, Decimal("0"))

        return {
            "budget_limit": float(self.budget) if self.budget else None,
            "spent": float(spent),
            "remaining": float(self.budget - spent) if self.budget else None,
            "budget_type": self.budget_type,
            "utilization": float(spent / self.budget) if self.budget else 0.0,
        }

    async def suggest_cheaper_alternative(
        self,
        provider: str,
        model: str,
    ) -> Optional[tuple]:
        """Suggest cheaper alternative model.

        Args:
            provider: Current provider.
            model: Current model.

        Returns:
            Tuple of (cheaper_provider, cheaper_model) or None.
        """
        current_cost = self._get_model_cost(provider, model)
        if current_cost is None:
            return None

        best_alternative: Optional[tuple] = None
        best_cost: Optional[Decimal] = None

        for p, models in self.COST_TABLE.items():
            for m, (input_rate, output_rate) in models.items():
                # Skip current
                if p == provider and m == model:
                    continue

                # Rough comparison using average
                avg_cost = (input_rate + output_rate) / 2
                if best_cost is None or avg_cost < best_cost:
                    best_cost = avg_cost
                    best_alternative = (p, m)

        if best_alternative and best_cost and best_cost < current_cost:
            return best_alternative

        return None

    def _get_model_cost(self, provider: str, model: str) -> Optional[Decimal]:
        """Get average cost for model.

        Args:
            provider: Provider name.
            model: Model name.

        Returns:
            Average cost or None.
        """
        provider_costs = self.COST_TABLE.get(provider, {})
        rates = provider_costs.get(model)
        if rates:
            return (rates[0] + rates[1]) / 2
        return None

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate.

        Returns:
            Estimated tokens.
        """
        return int(len(text.split()) * 1.3)


# Factory
async def create_cost_optimizer(
    budget_usd: Optional[Decimal] = None,
    token_optimization_enabled: bool = True,
    event_bus: Optional[Any] = None,
) -> CostOptimizerImpl:
    """Factory for creating configured cost optimizer.

    Args:
        budget_usd: Budget limit in USD.
        token_optimization_enabled: Enable token compression.
        event_bus: Optional event bus.

    Returns:
        Configured CostOptimizerImpl.
    """
    return CostOptimizerImpl(
        budget_usd=budget_usd,
        token_optimization_enabled=token_optimization_enabled,
        event_bus=event_bus,
    )


import asyncio
from domain_models import OrchestrationEvent
