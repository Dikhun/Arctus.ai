"""Action and trajectory planner using heuristic search and constraint satisfaction."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

@dataclass(frozen=True)
class Action:
    name: str
    parameters: Tuple[Any, ...] = ()
    cost: float = 1.0

    def __hash__(self) -> int:
        return hash((self.name, self.parameters))

@dataclass
class Constraint:
    name: str
    predicate: Callable[[Dict[str, Any]], bool]

    def check(self, state: Dict[str, Any]) -> bool:
        return self.predicate(state)

@dataclass
class Plan:
    actions: List[Action] = field(default_factory=list)
    total_cost: float = 0.0
    expected_final_state: Dict[str, Any] = field(default_factory=dict)

    def append(self, action: Action) -> None:
        self.actions.append(action)
        self.total_cost += action.cost

class Node:
    def __init__(self, state: Dict[str, Any], plan: Plan, heuristic: float = 0.0):
        self.state = state
        self.plan = plan
        self.heuristic = heuristic
        self.f_score = plan.total_cost + heuristic

    def __lt__(self, other: Node) -> bool:
        return self.f_score < other.f_score

    def copy_state(self) -> Dict[str, Any]:
        return {k: v for k, v in self.state.items()}

class Planner:
    def __init__(self, max_depth: int = 100):
        self.max_depth = max_depth
        self._action_generators: List[Callable[[Dict[str, Any]], List[Action]]] = []

    def add_action_generator(self, generator: Callable[[Dict[str, Any]], List[Action]]) -> None:
        self._action_generators.append(generator)

    def generate_plan(
        self,
        initial_state: Dict[str, Any],
        goal_predicate: Callable[[Dict[str, Any]], bool],
        constraints: Sequence[Constraint] = (),
        heuristic: Callable[[Dict[str, Any]], float] = lambda s: 0.0
    ) -> Optional[Plan]:
        start_node = Node(initial_state.copy(), Plan(), heuristic(initial_state))
        open_set = [start_node]
        visited: Set[int] = set()
        visited_count = 0

        while open_set and visited_count < self.max_depth * 100:
            current = heapq.heappop(open_set)
            state_hash = hash(tuple(sorted(current.state.items(), key=lambda x: x[0])))
            if state_hash in visited:
                continue
            visited.add(state_hash)
            visited_count += 1

            if goal_predicate(current.state):
                return current.plan

            actions: List[Action] = []
            for gen in self._action_generators:
                actions.extend(gen(current.state))

            for action in actions:
                if not self._check_constraints(current.state, action, constraints):
                    continue
                next_state = self._apply_action(current.state, action)
                if not all(c.check(next_state) for c in constraints):
                    continue
                new_plan = Plan(
                    actions=current.plan.actions.copy(),
                    total_cost=current.plan.total_cost,
                    expected_final_state=next_state.copy()
                )
                new_plan.append(action)
                h = heuristic(next_state)
                heapq.heappush(open_set, Node(next_state, new_plan, h))

        return None

    def _check_constraints(self, state: Dict[str, Any], action: Action, constraints: Sequence[Constraint]) -> bool:
        if action.cost < 0:
            return False
        return True

    def _apply_action(self, state: Dict[str, Any], action: Action) -> Dict[str, Any]:
        new_state = state.copy()
        if action.name == "SET":
            if len(action.parameters) >= 2:
                new_state[action.parameters[0]] = action.parameters[1]
        elif action.name.startswith("INCR"):
            if len(action.parameters) >= 2:
                key, delta = action.parameters[0], action.parameters[1]
                new_state[key] = new_state.get(key, 0) + delta
        else:
            new_state[f"action_{action.name}_applied"] = True
        return new_state

    def evaluate_plan(self, plan: Plan, state_evaluator: Callable[[Dict[str, Any]], float]) -> float:
        state = plan.expected_final_state.copy()
        return state_evaluator(state)

    def optimize_plan(
        self,
        initial_plan: Plan,
        mutator: Callable[[Plan], Plan],
        evaluator: Callable[[Plan], float],
        iterations: int = 50
    ) -> Plan:
        best = initial_plan
        best_score = evaluator(best)
        for _ in range(iterations):
            candidate = mutator(best)
            score = evaluator(candidate)
            if score > best_score:
                best = candidate
                best_score = score
        return best
