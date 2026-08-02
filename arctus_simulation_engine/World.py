```python
"""
artus/simulation/world.py
Simulation world aggregate and services.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

from artus.foundation.domain import AggregateRoot, DomainEvent
from artus.foundation.di import Injectable
from artus.foundation.telemetry import Logger, Telemetry
from artus.foundation.health import HealthCheck, HealthStatus


@dataclass(frozen=True)
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vector3) -> Vector3:
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3) -> Vector3:
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3:
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def magnitude(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)


@dataclass(frozen=True)
class WorldTime:
    tick: int = 0
    elapsed_seconds: float = 0.0
    time_scale: float = 1.0

    def advance(self, delta_seconds: float) -> WorldTime:
        scaled = delta_seconds * self.time_scale
        return WorldTime(
            tick=self.tick + 1,
            elapsed_seconds=self.elapsed_seconds + scaled,
            time_scale=self.time_scale,
        )


@dataclass(frozen=True)
class EntitySpawned(DomainEvent):
    entity_id: str
    position: Vector3


@dataclass(frozen=True)
class EntityDestroyed(DomainEvent):
    entity_id: str


@dataclass
class WorldEntity:
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    position: Vector3 = field(default_factory=Vector3)
    velocity: Vector3 = field(default_factory=Vector3)
    acceleration: Vector3 = field(default_factory=Vector3)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def distance_to(self, other: WorldEntity) -> float:
        return (self.position - other.position).magnitude()


class SpatialHash:
    def __init__(self, cell_size: float = 10.0) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self._cells: Dict[Tuple[int, int, int], Set[str]] = {}
        self._entity_cells: Dict[str, Tuple[int, int, int]] = {}

    def _key(self, position: Vector3) -> Tuple[int, int, int]:
        return (
            int(math.floor(position.x / self.cell_size)),
            int(math.floor(position.y / self.cell_size)),
            int(math.floor(position.z / self.cell_size)),
        )

    def insert(self, entity: WorldEntity) -> None:
        key = self._key(entity.position)
        self._entity_cells[entity.entity_id] = key
        if key not in self._cells:
            self._cells[key] = set()
        self._cells[key].add(entity.entity_id)

    def remove(self, entity_id: str) -> None:
        if entity_id not in self._entity_cells:
            return
        key = self._entity_cells.pop(entity_id)
        cell = self._cells.get(key)
        if cell is not None:
            cell.discard(entity_id)
            if not cell:
                del self._cells[key]

    def update(self, entity: WorldEntity) -> None:
        self.remove(entity.entity_id)
        self.insert(entity)

    def query_nearby(self, position: Vector3, radius: float) -> Set[str]:
        center = self._key(position)
        radius_cells = int(math.ceil(radius / self.cell_size))
        results: Set[str] = set()
        rng = range(-radius_cells, radius_cells + 1)
        for dx in rng:
            for dy in rng:
                for dz in rng:
                    key = (center[0] + dx, center[1] + dy, center[2] + dz)
                    cell = self._cells.get(key)
                    if cell:
                        results.update(cell)
        return results


@dataclass
class WorldConfig:
    max_entities: int = 10_000
    spatial_cell_size: float = 10.0
    time_scale: float = 1.0


class World(AggregateRoot):
    world_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    config: WorldConfig = field(default_factory=WorldConfig)
    time: WorldTime = field(default_factory=WorldTime)

    def __post_init__(self):
        self._entities: Dict[str, WorldEntity] = {}
        self._spatial = SpatialHash(self.config.spatial_cell_size)
        self._handlers: List[Callable[[DomainEvent], None]] = []

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    def subscribe(self, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.append(handler)

    def _emit(self, event: DomainEvent) -> None:
        for handler in self._handlers:
            handler(event)

    def spawn(self, entity: WorldEntity) -> None:
        if self.entity_count >= self.config.max_entities:
            raise WorldCapacityError(f"World at capacity: {self.config.max_entities}")
        if entity.entity_id in self._entities:
            raise DuplicateEntityError(f"Entity {entity.entity_id} exists")
        self._entities[entity.entity_id] = entity
        self._spatial.insert(entity)
        self._emit(EntitySpawned(entity_id=entity.entity_id, position=entity.position))

    def destroy(self, entity_id: str) -> None:
        if entity_id not in self._entities:
            raise EntityNotFoundError(f"Entity {entity_id} not found")
        del self._entities[entity_id]
        self._spatial.remove(entity_id)
        self._emit(EntityDestroyed(entity_id=entity_id))

    def get(self, entity_id: str) -> Optional[WorldEntity]:
        return self._entities.get(entity_id)

    def update(self, entity: WorldEntity) -> None:
        if entity.entity_id not in self._entities:
            raise EntityNotFoundError(f"Entity {entity.entity_id} not found")
        self._entities[entity.entity_id] = entity
        self._spatial.update(entity)

    def query_proximity(self, position: Vector3, radius: float) -> List[WorldEntity]:
        ids = self._spatial.query_nearby(position, radius)
        return [self._entities[eid] for eid in ids if eid in self._entities]

    def all_entities(self) -> List[WorldEntity]:
        return list(self._entities.values())

    def advance_time(self, delta_seconds: float) -> None:
        self.time = self.time.advance(delta_seconds)

    def step(self, delta_seconds: float, updater: Optional[Callable[[WorldEntity], WorldEntity]] = None) -> None:
        self.advance_time(delta_seconds)
        for old in list(self._entities.values()):
            updated = updater(old) if updater else old
            updated.position = updated.position + updated.velocity * delta_seconds
            updated.velocity = updated.velocity + updated.acceleration * delta_seconds
            self.update(updated)


class WorldError(Exception):
    pass


class WorldCapacityError(WorldError):
    pass


class DuplicateEntityError(WorldError):
    pass


class EntityNotFoundError(WorldError):
    pass


class WorldRepository(Protocol):
    def save(self, world: World) -> None:
        ...

    def get(self, world_id: str) -> Optional[World]:
        ...

    def delete(self, world_id: str) -> None:
        ...


@Injectable(singleton=True)
class WorldService:
    def __init__(self, repository: WorldRepository, telemetry: Telemetry, logger: Logger) -> None:
        self._repo = repository
        self._telemetry = telemetry
        self._logger = logger

    def create(self, config: Optional[WorldConfig] = None) -> World:
        world = World(config=config or WorldConfig())
        self._repo.save(world)
        self._telemetry.counter("world.created", tags={"id": world.world_id})
        self._logger.info("World created", extra={"world_id": world.world_id})
        return world

    def delete(self, world_id: str) -> None:
        self._repo.delete(world_id)
        self._telemetry.counter("world.deleted", tags={"id": world_id})

    def load(self, world_id: str) -> World:
        world = self._repo.get(world_id)
        if world is None:
            raise EntityNotFoundError(f"World {world_id} not found")
        return world

    def save(self, world: World) -> None:
        self._repo.save(world)
        self._telemetry.counter("world.saved", tags={"id": world.world_id})

    def spawn(self, world_id: str, entity: WorldEntity) -> None:
        world = self.load(world_id)
        world.spawn(entity)
        self._repo.save(world)
        self._telemetry.counter("world.entity_spawned", tags={"id": world_id})

    def advance_time(self, world_id: str, delta_seconds: float) -> None:
        world = self.load(world_id)
        world.advance_time(delta_seconds)
        self._repo.save(world)

    def step(self, world_id: str, delta_seconds: float, updater: Optional[Callable[[WorldEntity], WorldEntity]] = None) -> None:
        world = self.load(world_id)
        world.step(delta_seconds, updater)
        self._repo.save(world)
        self._telemetry.histogram("world.step_delta", delta_seconds, tags={"id": world_id})


@Injectable(singleton=True)
class WorldHealthCheck(HealthCheck):
    def __init__(self, service: WorldService) -> None:
        self._service = service

    def check(self) -> HealthStatus:
        try:
            w = self._service.create(WorldConfig(max_entities=1))
            self._service.delete(w.world_id)
            return HealthStatus.healthy("world")
        except Exception as exc:
            return HealthStatus.unhealthy("world", str(exc))
```
```python
"""
tests/simulation/test_world.py
"""
import pytest
from uuid import uuid4

from artus.simulation.world import (
    World,
    WorldConfig,
    WorldEntity,
    WorldService,
    Vector3,
    WorldTime,
    SpatialHash,
    WorldRepository,
    EntitySpawned,
    EntityDestroyed,
    EntityNotFoundError,
    DuplicateEntityError,
    WorldCapacityError,
    WorldHealthCheck,
)


class MemoryWorldRepo(WorldRepository):
    def __init__(self):
        self._data: dict = {}

    def save(self, world: World) -> None:
        self._data[world.world_id] = world

    def get(self, world_id: str):
        return self._data.get(world_id)

    def delete(self, world_id: str) -> None:
        self._data.pop(world_id, None)


class FakeTelemetry:
    def __init__(self):
        self.counters = []
        self.hists = []

    def counter(self, name, tags=None):
        self.counters.append((name, tags))

    def histogram(self, name, value, tags=None):
        self.hists.append((name, value))


class FakeLogger:
    def info(self, msg, extra=None):
        pass


@pytest.fixture
def repo():
    return MemoryWorldRepo()


@pytest.fixture
def tel():
    return FakeTelemetry()


@pytest.fixture
def log():
    return FakeLogger()


@pytest.fixture
def svc(repo, tel, log):
    return WorldService(repo, tel, log)


def test_vector_ops():
    a = Vector3(1, 2, 3)
    b = Vector3(4, 5, 6)
    assert (a + b) == Vector3(5, 7, 9)
    assert (a - b) == Vector3(-3, -3, -3)
    assert a * 2 == Vector3(2, 4, 6)
    assert Vector3(3, 4, 0).magnitude() == 5.0


def test_world_time_advance():
    t = WorldTime()
    t2 = t.advance(2.0)
    assert t2.tick == 1 and t2.elapsed_seconds == 2.0


def test_spatial_basic():
    sh = SpatialHash(10.0)
    e = WorldEntity(position=Vector3(5, 5, 5))
    sh.insert(e)
    assert e.entity_id in sh.query_nearby(Vector3(5, 5, 5), 1.0)
    sh.remove(e.entity_id)
    assert e.entity_id not in sh.query_nearby(Vector3(5, 5, 5), 1.0)


def test_world_spawn_destroy_and_events():
    w = World()
    e = WorldEntity()
    events = []
    w.subscribe(events.append)
    w.spawn(e)
    assert w.get(e.entity_id) is e
    assert any(isinstance(ev, EntitySpawned) for ev in events)
    w.destroy(e.entity_id)
    assert w.get(e.entity_id) is None
    assert any(isinstance(ev, EntityDestroyed) for ev in events)


def test_world_capacity():
    w = World(config=WorldConfig(max_entities=1))
    w.spawn(WorldEntity())
    with pytest.raises(WorldCapacityError):
        w.spawn(WorldEntity())


def test_world_duplicate():
    w = World()
    e = WorldEntity()
    w.spawn(e)
    with pytest.raises(DuplicateEntityError):
        w.spawn(e)


def test_world_proximity():
    w = World(config=WorldConfig(spatial_cell_size=100.0))
    a = WorldEntity(position=Vector3(0, 0, 0))
    b = WorldEntity(position=Vector3(5, 0, 0))
    c = WorldEntity(position=Vector3(500, 0, 0))
    for ent in (a, b, c):
        w.spawn(ent)
    near = w.query_proximity(Vector3(0, 0, 0), 10.0)
    ids = {e.entity_id for e in near}
    assert a.entity_id in ids
    assert b.entity_id in ids
    assert c.entity_id not in ids


def test_world_step_kinematics():
    w = World()
    e = WorldEntity(position=Vector3(0, 0, 0), velocity=Vector3(2, 0, 0))
    w.spawn(e)
    w.step(1.0)
    assert w.get(e.entity_id).position.x == 2.0


def test_world_step_with_updater():
    w = World()
    e = WorldEntity(position=Vector3(0, 0, 0), velocity=Vector3(1, 0, 0), acceleration=Vector3(1, 0, 0))
    w.spawn(e)

    def update(ent):
        ent.acceleration = Vector3(0, 0, 0)
        return ent

    w.step(1.0, update)
    ent = w.get(e.entity_id)
    assert ent.position.x == 1.0
    assert ent.velocity.x == 1.0


def test_service_crud(svc, repo):
    w = svc.create(WorldConfig(max_entities=5))
    assert repo.get(w.world_id) is w
    loaded = svc.load(w.world_id)
    assert loaded.world_id == w.world_id
    svc.delete(w.world_id)
    assert repo.get(w.world_id) is None


def test_service_load_missing(svc):
    with pytest.raises(EntityNotFoundError):
        svc.load(str(uuid4()))


def test_service_spawn_and_step(svc, repo):
    w = svc.create()
    e = WorldEntity()
    svc.spawn(w.world_id, e)
    assert repo.get(w.world_id).entity_count == 1
    svc.step(w.world_id, 0.1)
    assert repo.get(w.world_id).time.elapsed_seconds == 0.1


def test_health_check(svc):
    hc = WorldHealthCheck(svc)
    status = hc.check()
    assert status.is_healthy is True
```
