```python
"""
artus/simulation/environment.py
Environmental state and services.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Callable

from artus.foundation.domain import AggregateRoot, DomainEvent, ValueObject
from artus.foundation.di import Injectable
from artus.foundation.telemetry import Logger, Telemetry

from artus.simulation.world import World, WorldEntity, Vector3


@dataclass(frozen=True)
class Temperature(ValueObject):
    celsius: float = 20.0

    @property
    def kelvin(self) -> float:
        return self.celsius + 273.15


@dataclass(frozen=True)
class Wind(Vector3):
    pass


@dataclass(frozen=True)
class Atmosphere(ValueObject):
    pressure_pa: float = 101325.0
    humidity: float = 0.5
    temperature: Temperature = field(default_factory=Temperature)
    wind: Wind = field(default_factory=Wind)


@dataclass(frozen=True)
class Lighting(ValueObject):
    intensity: float = 1.0
    direction: Vector3 = field(default_factory=lambda: Vector3(0, -1, 0))


@dataclass(frozen=True)
class TerrainType(ValueObject):
    name: str = "default"
    friction: float = 0.5
    elevation: float = 0.0


@dataclass(frozen=True)
class EnvironmentState(ValueObject):
    atmosphere: Atmosphere = field(default_factory=Atmosphere)
    lighting: Lighting = field(default_factory=Lighting)
    gravity: Vector3 = field(default_factory=lambda: Vector3(0, -9.81, 0))


@dataclass
class EnvironmentZone:
    zone_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bounds_min: Vector3 = field(default_factory=Vector3)
    bounds_max: Vector3 = field(default_factory=Vector3)
    state: EnvironmentState = field(default_factory=EnvironmentState)

    def contains(self, position: Vector3) -> bool:
        return (
            self.bounds_min.x <= position.x <= self.bounds_max.x
            and self.bounds_min.y <= position.y <= self.bounds_max.y
            and self.bounds_min.z <= position.z <= self.bounds_max.z
        )


@dataclass
class EnvironmentConfig:
    zones: List[EnvironmentZone] = field(default_factory=list)
    global_state: EnvironmentState = field(default_factory=EnvironmentState)


@dataclass
class EnvironmentChanged(DomainEvent):
    environment_id: str
    new_state: EnvironmentState


class Environment(AggregateRoot):
    environment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: Optional[str] = None
    config: EnvironmentConfig = field(default_factory=EnvironmentConfig)

    def __post_init__(self):
        self._handlers: List[Callable[[DomainEvent], None]] = []

    def subscribe(self, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.append(handler)

    def _emit(self, event: DomainEvent) -> None:
        for h in self._handlers:
            h(event)

    def state_at(self, position: Vector3) -> EnvironmentState:
        for zone in self.config.zones:
            if zone.contains(position):
                return zone.state
        return self.config.global_state

    def update_global(self, state: EnvironmentState) -> None:
        self.config.global_state = state
        self._emit(EnvironmentChanged(environment_id=self.environment_id, new_state=state))

    def add_zone(self, zone: EnvironmentZone) -> None:
        self.config.zones.append(zone)

    def remove_zone(self, zone_id: str) -> None:
        self.config.zones = [z for z in self.config.zones if z.zone_id != zone_id]

    def apply_to_entity(self, entity: WorldEntity) -> WorldEntity:
        state = self.state_at(entity.position)
        entity.velocity = entity.velocity + state.atmosphere.wind * 0.01
        return entity


class EnvironmentRepository(Protocol):
    def save(self, env: Environment) -> None:
        ...

    def get(self, env_id: str) -> Optional[Environment]:
        ...

    def delete(self, env_id: str) -> None:
        ...

    def by_world(self, world_id: str) -> Optional[Environment]:
        ...
@Injectable(singleton=True)
class EnvironmentService:
    def __init__(self, repository: EnvironmentRepository, telemetry: Telemetry, logger: Logger) -> None:
        self._repo = repository
        self._telemetry = telemetry
        self._logger = logger

    def create(self, world_id: str, config: Optional[EnvironmentConfig] = None) -> Environment:
        env = Environment(world_id=world_id, config=config or EnvironmentConfig())
        self._repo.save(env)
        self._telemetry.counter("environment.created", tags={"world_id": world_id})
        return env

    def get(self, env_id: str) -> Environment:
        env = self._repo.get(env_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment {env_id} not found")
        return env

    def for_world(self, world_id: str) -> Environment:
        env = self._repo.by_world(world_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment for world {world_id} not found")
        return env

    def set_global_state(self, env_id: str, state: EnvironmentState) -> None:
        env = self.get(env_id)
        env.update_global(state)
        self._repo.save(env)

    def apply_environmental_forces(self, world: World) -> None:
        env = self._repo.by_world(world.world_id)
        if env is None:
            return
        for entity in world.all_entities():
            updated = env.apply_to_entity(entity)
            world.update(updated)
        self._telemetry.counter("environment.forces_applied", tags={"world_id": world.world_id})


class EnvironmentError(Exception):
    pass


class EnvironmentNotFoundError(EnvironmentError):
    pass
```
```python
"""
tests/simulation/test_environment.py
"""
import pytest

from artus.simulation.environment import (
    Environment,
    EnvironmentConfig,
    EnvironmentService,
    EnvironmentZone,
    EnvironmentState,
    Atmosphere,
    Temperature,
    Wind,
    Vector3,
    EnvironmentRepository,
    EnvironmentNotFoundError,
)
from artus.simulation.world import WorldEntity, World, WorldConfig


class MemoryEnvRepo(EnvironmentRepository):
    def __init__(self):
        self._data = {}

    def save(self, env):
        self._data[env.environment_id] = env

    def get(self, env_id):
        return self._data.get(env_id)

    def delete(self, env_id):
        self._data.pop(env_id, None)

    def by_world(self, world_id):
        for env in self._data.values():
            if env.world_id == world_id:
                return env
        return None


class FakeTel:
    def counter(self, name, tags=None):
        pass


class FakeLog:
    def info(self, msg, extra=None):
        pass


@pytest.fixture
def repo():
    return MemoryEnvRepo()


@pytest.fixture
def svc(repo):
    return EnvironmentService(repo, FakeTel(), FakeLog())


def test_temperature_conversion():
    t = Temperature(celsius=27)
    assert t.kelvin == 300.15


def test_zone_contains():
    zone = EnvironmentZone(
        bounds_min=Vector3(0, 0, 0),
        bounds_max=Vector3(10, 10, 10),
    )
    assert zone.contains(Vector3(5, 5, 5))
    assert not zone.contains(Vector3(11, 5, 5))


def test_state_at_returns_zone_or_global():
    env = Environment()
    z = EnvironmentZone(
        bounds_min=Vector3(0, 0, 0),
        bounds_max=Vector3(1, 1, 1),
        state=EnvironmentState(atmosphere=Atmosphere(pressure_pa=90000)),
    )
    env.add_zone(z)
    global_state = env.state_at(Vector3(100, 0, 0))
    assert global_state.atmosphere.pressure_pa == 101325.0
    zone_state = env.state_at(Vector3(0.5, 0.5, 0.5))
    assert zone_state.atmosphere.pressure_pa == 90000.0


def test_apply_wind_changes_velocity():
    env = Environment()
    env.update_global(
        EnvironmentState(atmosphere=Atmosphere(wind=Wind(10, 0, 0)))
    )
    ent = WorldEntity(position=Vector3(0, 0, 0), velocity=Vector3(0, 0, 0))
    updated = env.apply_to_entity(ent)
    assert updated.velocity.x == 0.1


def test_service_create_and_get(svc, repo):
    env = svc.create("world-1")
    assert env.world_id == "world-1"
    assert svc.get(env.environment_id) is env


def test_service_not_found(svc):
    with pytest.raises(EnvironmentNotFoundError):
        svc.get("missing")


def test_service_apply_forces(svc, repo):
    world = World(config=WorldConfig(spatial_cell_size=100))
    world.spawn(WorldEntity(position=Vector3(0, 0, 0), velocity=Vector3(1, 0, 0)))

    env = svc.create(world.world_id)
    env.update_global(EnvironmentState(atmosphere=Atmosphere(wind=Wind(5, 0, 0))))
    repo.save(env)

    svc.apply_environmental_forces(world)
    ent = world.all_entities()[0]
    assert ent.velocity.x == 1.05
```
