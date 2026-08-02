"""Risk analysis module for quantifying simulation tail risk and exposures."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence

@dataclass
class RiskMetric:
    name: str
    value: float
    unit: str = ""
    confidence: float = 0.95
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RiskReport:
    scenario_id: str
    metrics: List[RiskMetric] = field(default_factory=list)
    overall_risk_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def get_metric(self, name: str) -> Optional[RiskMetric]:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

class RiskAnalyzer:
    def __init__(self, confidence_level: float = 0.95):
        if not 0 < confidence_level < 1:
            raise ValueError("Confidence level must be between 0 and 1")
        self.confidence_level = confidence_level
        self._stress_thresholds: Dict[str, Callable[[Any], float]] = {}

    def calculate_var(self, returns: Sequence[float]) -> RiskMetric:
        if not returns:
            return RiskMetric(name="Value_at_Risk", value=0.0, confidence=self.confidence_level)
        sorted_returns = sorted(returns)
        idx = int((1.0 - self.confidence_level) * len(sorted_returns))
        idx = max(0, min(idx, len(sorted_returns) - 1))
        var = -sorted_returns[idx]
        return RiskMetric(
            name="Value_at_Risk",
            value=var,
            confidence=self.confidence_level,
            unit="currency_equivalent"
        )

    def calculate_cvar(self, returns: Sequence[float]) -> RiskMetric:
        if not returns:
            return RiskMetric(name="Conditional_VaR", value=0.0, confidence=self.confidence_level)
        sorted_returns = sorted(returns)
        idx = int((1.0 - self.confidence_level) * len(sorted_returns))
        idx = max(0, idx)
        tail = sorted_returns[:idx+1] if idx >= 0 else sorted_returns
        if not tail:
            tail = sorted_returns[:1]
        cvar = -sum(tail) / len(tail)
        return RiskMetric(name="Conditional_VaR", value=cvar, confidence=self.confidence_level)

    def stress_test(
        self,
        baseline: Dict[str, Any],
        shocks: List[Dict[str, Any]],
        outcome_extractor: Callable[[Dict[str, Any]], float]
    ) -> List[RiskMetric]:
        metrics = []
        base_value = outcome_extractor(baseline)
        for i, shock in enumerate(shocks):
            shocked = {**baseline, **shock}
            shocked_value = outcome_extractor(shocked)
            delta = shocked_value - base_value
            pct = (delta / base_value * 100.0) if base_value != 0 else 0.0 metrics.append(RiskMetric(
                name=f"Stress_{i}",
                value=delta,
                unit="absolute_change",
                metadata={"percent_change": pct, "shock": shock}
            ))
        return metrics

    def tail_risk(self, distribution: Sequence[float]) -> RiskMetric:
        if len(distribution) < 2:
            return RiskMetric(name="Tail_Risk_Skew", value=0.0)
        mean_val = sum(distribution) / len(distribution)
        variance = sum((x - mean_val) ** 2 for x in distribution) / len(distribution)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        skew = sum(((x - mean_val) / std) ** 3 for x in distribution) / len(distribution)
        return RiskMetric(name="Tail_Risk_Skew", value=skew, unit="skewness")

    def default_probability(self, default_flags: Sequence[bool]) -> RiskMetric:
        if not default_flags:
            return RiskMetric(name="Default_Probability", value=0.0)
        count = sum(1 for f in default_flags if f)
        p = count / len(default_flags)
        return RiskMetric(name="Default_Probability", value=p, unit="probability")

    def aggregate_risk(self, reports: List[RiskReport]) -> RiskReport:
        aggregated = RiskReport(scenario_id="aggregate")
        all_values: Dict[str, List[RiskMetric]] = {}
        for rep in reports:
            for m in rep.metrics:
                all_values.setdefault(m.name, []).append(m)
        for name, metrics in all_values.items():
            avg_val = sum(m.value for m in metrics) / len(metrics)
            aggregated.metrics.append(RiskMetric(
                name=f"{name}_avg",
                value=avg_val,
                confidence=self.confidence_level
            ))
        total_score = sum(m.value for m in aggregated.metrics) / max(len(aggregated.metrics), 1)
        aggregated.overall_risk_score = total_score
        return aggregated
