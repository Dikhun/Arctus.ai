from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from arctus_simulation_engine.primitives import EntityId, EntityState, SimulationTime
from arctus_simulation_engine.events import SimulationEvent
from arctus_simulation_engine.ports import EventBus
from arctus_simulation_engine.core.virtual_time import VirtualTime


@dataclass(slots=True)
class Entity:
    entity_id: EntityId
    state: EntityState
    created_at: SimulationTime
    metadata: dict[str, Any] = field(default_factory=dict)


class EntityLifecycleManager:
    def __init__(self, event_bus: EventBus, virtual_time: VirtualTime) -> None:
        self._entities: dict[EntityId, Entity] = {}
        self._event_bus = event_bus
        self._virtual_time = virtual_time
        self._handlers: dict[EntityState, list[Callable[[Entity], Awaitable[None]]]] = {s: [] for s in EntityState}

    async def spawn(self, entity_id: EntityId, metadata: dict[str, Any] | None = None) -> Entity:
        if entity_id in self._entities:
            raise ValueError(f"Entity {entity_id} already exists")
        entity = Entity(
            entity_id=entity_id,
            state=EntityState.SPAWNING,
            created_at=self._virtual_time.now,
            metadata=metadata or {},
        )
        self._entities[entity_id] = entity
        await self._transition(entity, EntityState.ALIVE)
        return entity

    async def transition(self, entity_id: EntityId, new_state: EntityState) -> Entity:
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity {entity_id} not found")
        await self._transition(entity, new_state)
        return entity

    async def destroy(self, entity_id: EntityId) -> None:
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity {entity_id} not found")
        await self._transition(entity, EntityState.DESTROYING)
        await self._transition(entity, EntityState.DESTROYED)
        del self._entities[entity_id]

    def get(self, entity_id: EntityId) -> Entity | None:
        return self._entities.get(entity_id)

    def list_active(self) -> list[Entity]:
        return [e for e in self._entities.values() if e.state not in {EntityState.DESTROYED, EntityState.DESTROYING}]

    def on_transition(self, state: EntityState, handler: Callable[[Entity], Awaitable[None]]) -> None:
        self._handlers[state].append(handler)

    async def _transition(self, entity: Entity, new_state: EntityState) -> None:
        old_state = entity.state
        entity.state = new_state
        await self._event_bus.publish(SimulationEvent(
            event_type="entity.transition",
            timestamp=self._virtual_time.now,
            source="EntityLifecycleManager",
            payload={
                "entity_id": entity.entity_id,
                "from": old_state.value,
                "to": new_state.value,
            },
        ))
        for handler in self._handlers.get(new_state, []):
            await handler(entity)
