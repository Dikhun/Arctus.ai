"""Objective-based parameter and trajectory optimizer."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

@dataclass
class Objective:
    name: str
    evaluator: Callable[[Dict[str, Any]], float]
    maximize: bool = True

    def evaluate(self, params: Dict[str, Any]) -> float:
        val = self.evaluator(params)
        return val if self.maximize else -val

@dataclass
class OptimizationResult:
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_score: float = 0.0
    iterations: int = 0
    history: List[Tuple[float, Dict[str, Any]]] = field(default_factory=list)

class Optimizer:
    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.objectives: List[Objective] = []

    def add_objective(self, objective: Objective) -> None:
        self.objectives.append(objective)

    def evaluate_objective(self, params: Dict[str, Any]) -> float:
        if not self.objectives:
            return 0.0
        scores = [obj.evaluate(params) for obj in self.objectives]
        return sum(scores) / len(scores)

    def optimize(
        self,
        parameter_space: Dict[str, Tuple[float, float]],
        method: str = "hill_climb",
        iterations: int = 100,
        initial_guess: Optional[Dict[str, Any]] = None
    ) -> OptimizationResult:
        if method == "hill_climb":
            return self.hill_climb(parameter_space, iterations, initial_guess)
        elif method == "random_search":
            return self.random_search(parameter_space, iterations)
        elif method == "genetic":
            return self.genetic_algorithm(parameter_space, iterations)
        else:
            return self.random_search(parameter_space, iterations)

    def hill_climb(
        self,
        parameter_space: Dict[str, Tuple[float, float]],
        iterations: int,
        initial_guess: Optional[Dict[str, Any]] = None
    ) -> OptimizationResult:
        current = initial_guess.copy() if initial_guess else self._random_params(parameter_space)
        current_score = self.evaluate_objective(current)
        best = current.copy()
        best_score = current_score
        history = [(best_score, best.copy())]

        step_size = 0.1
        for i in range(iterations):
            neighbor = self._neighbor(current, parameter_space, step_size)
            neighbor_score = self.evaluate_objective(neighbor)
            if neighbor_score > current_score:
                current = neighbor
                current_score = neighbor_score
                if current_score > best_score:
                    best = current.copy()
                    best_score = current_score
            else:
                step_size *= 0.95
            history.append((current_score, current.copy()))

        return OptimizationResult(best_params=best, best_score=best_score, iterations=iterations, history=history)

    def random_search(
        self,
        parameter_space: Dict[str, Tuple[float, float]],
        iterations: int
    ) -> OptimizationResult:
        best = self._random_params(parameter_space)
        best_score = self.evaluate_objective(best)
        history = [(best_score, best.copy())]
        for _ in range(iterations):
            candidate = self._random_params(parameter_space)
            score = self.evaluate_objective(candidate)
            if score > best_score:
                best = candidate
                best_score = score
            history.append((score, candidate.copy()))
        return OptimizationResult(best_params=best, best_score=best_score, iterations=iterations, history=history)

    def genetic_algorithm(
        self,
        parameter_space: Dict[str, Tuple[float, float]],
        iterations: int,
        population_size: int = 20,
        mutation_rate: float = 0.1
    ) -> OptimizationResult:
        population = [self._random_params(parameter_space) for _ in range(population_size)]
        best = population[0].copy()
        best_score = self.evaluate_objective(best)
        history = [(best_score, best.copy())]

        for gen in range(iterations):
            scored = [(p, self.evaluate_objective(p)) for p in population]
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored[0][1] > best_score:
                best = scored[0][0].copy()
                best_score = scored[0][1]
            history.append((best_score, best.copy()))

            survivors = [s[0] for s in scored[:population_size // 2]]
            next_gen = survivors.copy()
            while len(next_gen) < population_size:
                p1 = survivors[self.rng.randint(0, len(survivors) - 1)]
                p2 = survivors[self.rng.randint(0, len(survivors) - 1)]
                child = self._crossover(p1, p2)
                child = self._mutate(child, parameter_space, mutation_rate)
                next_gen.append(child)
            population = next_gen

        return OptimizationResult(best_params=best, best_score=best_score, iterations=iterations, history=history)

    def _random_params(self, space: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
        return {k: self.rng.uniform(v[0], v[1]) for k, v in space.items()}

    def _neighbor(self, current: Dict[str, Any], space: Dict[str, Tuple[float, float]], step: float) -> Dict[str, Any]:
        neighbor = current.copy()
        key = self.rng.choice(list(space.keys()))
        low, high = space[key]
        delta = (high - low) * step * self.rng.uniform(-1, 1)
        neighbor[key] = max(low, min(high, neighbor.get(key, 0.0) + delta))
        return neighbor

    def _crossover(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        child = {}
        for key in a:
            child[key] = a[key] if self.rng.random() < 0.5 else b.get(key, a[key])
        return child

    def _mutate(self, individual: Dict[str, Any], space: Dict[str, Tuple[float, float]], rate: float) -> Dict[str, Any]:
        mutated = individual.copy()
        for key, (low, high) in space.items():
            if self.rng.random() < rate:
                mutated[key] = self.rng.uniform(low, high)
        return mutated

    def constrain(self, params: Dict[str, Any], constraints: Sequence[Callable[[Dict[str, Any]], bool]]) -> Dict[str, Any]:
        for c in constraints:
            if not c(params):
                for key in params:
                    if isinstance(params[key], (int, float)):
                        params[key] = max(0.0, params[key] * 0.9)
        return params
