"""Monte Carlo simulation engine for stochastic scenario evaluation."""

from __future__ import annotations

import concurrent.futures
import math
import random
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Any, Callable, Dict, List, Optional, Sequence

@dataclass
class SimulationResult:
    scenario_id: str
    outcomes: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def expected_value(self) -> float:
        if not self.outcomes:
            return 0.0
        return mean(self.outcomes)

    @property
    def volatility(self) -> float:
        if len(self.outcomes) < 2:
            return 0.0
        return stdev(self.outcomes)

@dataclass
class ParameterSampler:
    def uniform(self, low: float, high: float) -> float:
        return random.uniform(low, high)

    def normal(self, mu: float, sigma: float) -> float:
        return random.gauss(mu, sigma)

    def discrete(self, choices: Sequence[Any], weights: Optional[Sequence[float]] = None) -> Any:
        if weights is None:
            return random.choice(list(choices))
        return random.choices(list(choices), weights=list(weights), k=1)[0]

class MonteCarloEngine:
    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers
        self._results: List[SimulationResult] = []
        self._convergence_history: List[float] = []

    def run(
        self,
        scenario_factory: Callable[[], Dict[str, Any]],
        simulator: Callable[[Dict[str, Any]], float],
        iterations: int = 1000,
        convergence_tolerance: Optional[float] = None,
        track_every: int = 100
    ) -> SimulationResult:
        outcomes: List[float] = []
        for i in range(iterations):
            params = scenario_factory()
            outcome = simulator(params)
            outcomes.append(outcome)
            if i > 0 and i % track_every == 0:
                current_mean = mean(outcomes)
                self._convergence_history.append(current_mean)
                if convergence_tolerance is not None and len(self._convergence_history) >= 3:
                    recent = self._convergence_history[-3:]
                    span = max(recent) - min(recent)
                    if span < convergence_tolerance:
                        break
        result = SimulationResult(
            scenario_id=f"mc_{random.randint(0, 999999)}",
            outcomes=outcomes,
            metadata={"iterations": len(outcomes)}
        )
        self._results.append(result)
        return result

    def run_parallel(
        self,
        scenario_factory: Callable[[], Dict[str, Any]],
        simulator: Callable[[Dict[str, Any]], float],
        iterations: int = 1000
    ) -> SimulationResult:
        worker_count = self.max_workers or 4
        chunk = max(1, iterations // worker_count)
        with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(self._run_chunk, scenario_factory, simulator, chunk)
                for _ in range(worker_count)
            ]
            outcomes: List[float] = []
            for future in concurrent.futures.as_completed(futures):
                outcomes.extend(future.result())
        result = SimulationResult(
            scenario_id=f"mc_parallel_{random.randint(0, 999999)}",
            outcomes=outcomes,
            metadata={"iterations": len(outcomes), "parallel": True}
        )
        self._results.append(result)
        return result

    @staticmethod
    def _run_chunk(
        scenario_factory: Callable[[], Dict[str, Any]],
        simulator: Callable[[Dict[str, Any]], float],
        count: int
    ) -> List[float]:
        return [simulator(scenario_factory()) for _ in range(count)]

    def sample_parameters(self, definitions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        sampler = ParameterSampler()
        params = {}
        for name, spec in definitions.items():
            dist = spec.get("distribution", "uniform")
            if dist == "uniform":
                params[name] = sampler.uniform(spec["low"], spec["high"])
            elif dist == "normal":
                params[name] = sampler.normal(spec["mu"], spec["sigma"])
            elif dist == "discrete":
                params[name] = sampler.discrete(spec["choices"], spec.get("weights"))
            else:
                params[name] = spec.get("default", 0.0)
        return params

    def aggregate_results(self, results: Optional[List[SimulationResult]] = None) -> Dict[str, float]:
        target = results or self._results
        all_outcomes: List[float] = []
        for r in target:
            all_outcomes.extend(r.outcomes)
        if not all_outcomes:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean": mean(all_outcomes),
            "std": stdev(all_outcomes) if len(all_outcomes) > 1 else 0.0,
            "min": min(all_outcomes),
            "max": max(all_outcomes)
        }

    def convergence_check(self, window: int = 5) -> bool:
        if len(self._convergence_history) < window:
            return False
        recent = self._convergence_history[-window:]
        return (max(recent) - min(recent)) < 1e-3
