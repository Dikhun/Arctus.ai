"""Digital Twin synchronization layer for artus.ai simulation engine."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optionalclass SynchronizationPolicy(Enum):
    EVENTUAL = auto()
    IMMEDIATE = auto()
    SCHEDULED = auto()

@dataclass
class TwinEntity:
    entity_id: str
    source_state: Dict[str, Any] = field(default_factory=dict)
    shadow_state: Dict[str, Any] = field(default_factory=dict)
    last_sync_time: float = field(default_factory=time.time)
    sync_policy: SynchronizationPolicy = SynchronizationPolicy.EVENTUAL
    divergence_threshold: float = 0.01

class DigitalTwin:
    """Maintains a synchronized virtual representation of entities.
    
    The world_provider argument must expose:
      - get_entity_state(entity_id: str) -> Dict[str, Any]
      - set_entity_state(entity_id: str, state: Dict[str, Any]) -> None
      - list_entities() -> List[str]
    """

    def __init__(self, world_provider: Any):
        self._provider = world_provider
        self._twins: Dict[str, TwinEntity] = {}
        self._sync_hooks: List[Callable[[TwinEntity], None]] = []
        self._divergence_history: Dict[str, List[float]] = {}

    def register(
        self,
        entity_id: str,
        policy: SynchronizationPolicy = SynchronizationPolicy.EVENTUAL,
        threshold: float = 0.01
    ) -> TwinEntity:
        state = self._provider.get_entity_state(entity_id)
        twin = TwinEntity(
            entity_id=entity_id,
            source_state=state.copy(),
            shadow_state=state.copy(),
            sync_policy=policy,
            divergence_threshold=threshold
        )
        self._twins[entity_id] = twin
        self._divergence_history[entity_id] = []
        return twin

    def synchronize(self, entity_id: str) -> bool:
        if entity_id not in self._twins:
            raise KeyError(f"Entity {entity_id} not registered")
        twin = self._twins[entity_id]
        current = self._provider.get_entity_state(entity_id)
        twin.source_state = current.copy()
        twin.shadow_state = current.copy()
        twin.last_sync_time = time.time()
        for hook in self._sync_hooks:
            hook(twin)
        return True

    def update_shadow(self, entity_id: str, state_patch: Dict[str, Any]) -> None:
        if entity_id not in self._twins:
            raise KeyError(f"Entity {entity_id} not registered")
        twin = self._twins[entity_id]
        twin.shadow_state.update(state_patch)
        if twin.sync_policy == SynchronizationPolicy.IMMEDIATE:
            self.apply_shadow_to_source(entity_id)

    def apply_shadow_to_source(self, entity_id: str) -> None:
        twin = self._twins[entity_id]
        self._provider.set_entity_state(entity_id, twin.shadow_state.copy())
        twin.source_state = twin.shadow_state.copy()
        twin.last_sync_time = time.time()

    def detect_divergence(self, entity_id: str) -> float:
        twin = self._twins[entity_id]
        current = self._provider.get_entity_state(entity_id)
        div = self._compute_divergence(current, twin.shadow_state)
        self._divergence_history[entity_id].append(div)
        return div

    def _compute_divergence(self, state_a: Dict[str, Any], state_b: Dict[str, Any]) -> float:
        keys = set(state_a.keys()) | set(state_b.keys())
        if not keys:
            return 0.0
        total = 0.0
        for k in keys:
            va = state_a.get(k, 0.0)
            vb = state_b.get(k, 0.0)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                maxv = max(abs(va), abs(vb), 1.0)
                total += abs(va - vb) / maxv
            else:
                total += 0.0 if va == vb else 1.0
        return total / len(keys)

    def get_shadow_state(self, entity_id: str) -> Dict[str, Any]:
        return self._twins[entity_id].shadow_state.copy()

    def get_source_state(self, entity_id: str) -> Dict[str, Any]:
        return self._twins[entity_id].source_state.copy()

    def bulk_sync(self) -> Dict[str, float]:
        results = {}
        for eid in self._twins:
            self.synchronize(eid)
            results[eid] = self.detect_divergence(eid)
        return results

    def add_sync_hook(self, hook: Callable[[TwinEntity], None]) -> None:
        self._sync_hooks.append(hook)

    def get_divergence_history(self, entity_id: str) -> List[float]:
        return self._divergence_history.get(entity_id, []).copy()

    def is_diverged(self, entity_id: str) -> bool:
        if entity_id not in self._twins:
            return False
        current = self._provider.get_entity_state(entity_id)
        return self._compute_divergence(current, self._twins[entity_id].shadow_state) > self._twins[entity_id].divergence_threshold
