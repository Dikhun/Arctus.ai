```python
"""
artus/simulation/physics.py
Physics engine, collision detection, rigid body dynamics.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from artus.foundation.di import Injectable
from artus.foundation.telemetry import Logger, Telemetry

from artus.simulation.world import World, WorldEntity, Vector3


@dataclass(frozen=True)
class AABB:
    min: Vector3
    max: Vector3

    def intersects(self, other: AABB) -> bool:
        return (
            self.max.x >= other.min.x and self.min.x <= other.max.x
            and self.max.y >= other.min.y and self.min.y <= other.max.y
            and self.max.z >= other.min.z and self.min.z <= other.max.z
        )

    def center(self) -> Vector3:
        return (self.min + self.max) * 0.5

    def size(self) -> Vector3:
        return self.max - self.min


@dataclass
class SphereCollider:
    radius: float = 1.0


@dataclass
class BoxCollider:
    half_extents: Vector3 = field(default_factory=lambda: Vector3(0.5, 0.5, 0.5))


@dataclass
class Collider:
    shape: Optional[object] = None
    offset: Vector3 = field(default_factory=Vector3)


@dataclass
class PhysicsMaterial:
    restitution: float = 0.5
    friction: float = 0.5
    density: float = 1.0


@dataclass
class RigidBody:
    mass: float = 1.0
    inverse_mass: float = field(init=False)
    collider: Collider = field(default_factory=Collider)
    material: PhysicsMaterial = field(default_factory=PhysicsMaterial)
    is_static: bool = False

    def __post_init__(self):
        self.inverse_mass = 0.0 if self.is_static or self.mass == 0.0 else 1.0 / self.mass


@dataclass
class Force:
    vector: Vector3 = field(default_factory=Vector3)
    application_point: Vector3 = field(default_factory=Vector3)
    duration: float = 0.0


@dataclass
class Contact:
    entity_a: str
    entity_b: str
    normal: Vector3
    penetration: float
    point: Vector3


@dataclass
class PhysicsConfig:
    gravity: Vector3 = field(default_factory=lambda: Vector3(0, -9.81, 0))
    substeps: int = 4
    sleep_threshold: float = 0.01


class PhysicsWorld:
    def __init__(self, world: World, config: Optional[PhysicsConfig] = None) -> None:
        self.world = world
        self.config = config or PhysicsConfig()
        self._bodies: Dict[str, RigidBody] = {}
        self._forces: Dict[str, List[Force]] = {}
        self._contacts: List[Contact] = []

    def register(self, entity_id: str, body: RigidBody) -> None:
        self._bodies[entity_id] = body

    def unregister(self, entity_id: str) -> None:
        self._bodies.pop(entity_id, None)
        self._forces.pop(entity_id, None)

    def apply_force(self, entity_id: str, force: Force) -> None:
        if entity_id not in self._forces:
            self._forces[entity_id] = []
        self._forces[entity_id].append(force)

    def step(self, delta_seconds: float) -> List[Contact]:
        self._contacts.clear()
        dt = delta_seconds / self.config.substeps
        for _ in range(self.config.substeps):
            self._integrate_forces(dt)
            self._detect_collisions()
            self._resolve_collisions(dt)
            self._integrate_velocities(dt)
        return list(self._contacts)

    def _integrate_forces(self, dt: float) -> None:
        for entity_id, body in self._bodies.items():
            if body.is_static:
                continue
            entity = self.world.get(entity_id)
            if entity is None:
                continue
            total_force = self.config.gravity * body.mass
            for force in self._forces.get(entity_id, []):
                total_force = total_force + force.vector
            entity.acceleration = total_force * body.inverse_mass
            self.world.update(entity)
        self._forces.clear()

    def _detect_collisions(self) -> None:
        entities = self.world.all_entities()
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                a, b = entities[i], entities[j]
                contact = self._check_pair(a, b)
                if contact:
                    self._contacts.append(contact)

    def _check_pair(self, a: WorldEntity, b: WorldEntity) -> Optional[Contact]:
        body_a = self._bodies.get(a.entity_id)
        body_b = self._bodies.get(b.entity_id)
        if not body_a or not body_b:
            return None
        dist = a.distance_to(b)
        radius_a = body_a.collider.shape.radius if isinstance(body_a.collider.shape, SphereCollider) else 0.5
        radius_b = body_b.collider.shape.radius if isinstance(body_b.collider.shape, SphereCollider) else 0.5
        penetration = radius_a + radius_b - dist
        if penetration > 0:
            normal = b.position - a.position
            mag = normal.magnitude()
            if mag > 0:
                normal = Vector3(normal.x / mag, normal.y / mag, normal.z / mag)
            else:
                normal = Vector3(1, 0, 0)
            point = a.position + normal * radius_a
            return Contact(entity_a=a.entity_id, entity_b=b.entity_id, normal=normal, penetration=penetration, point=point)
        return None

    def _resolve_collisions(self, dt: float) -> None:
        for contact in self._contacts:
            body_a = self._bodies.get(contact.entity_a)
            body_b = self._bodies.get(contact.entity_b)
            if not body_a or not body_b:
                continue
            correction = contact.normal * (contact.penetration * 0.5)
            ent_a = self.world.get(contact.entity_a)
            ent_b = self.world.get(contact.entity_b)
            if ent_a and not body_a.is_static:
                ent_a.position = ent_a.position - correction
                self.world.update(ent_a)
            if ent_b and not body_b.is_static:
                ent_b.position = ent_b.position + correction
                self.world.update(ent_b)

    def _integrate_velocities(self, dt: float) -> None:
        for entity_id, body in self._bodies.items():
            if body.is_static:
                continue
            entity = self.world.get(entity_id)
            if entity is None:
                continue
            entity.velocity = entity.velocity + entity.acceleration * dt
            entity.velocity = entity.velocity * 0.99
            entity.position = entity.position + entity.velocity * dt
            self.world.update(entity)


class PhysicsEngine(Protocol):
    def create_physics_world(self, world: World) -> PhysicsWorld:
        ...


@Injectable(singleton=True)
class PhysicsService:
    def __init__(self, telemetry: Telemetry, logger: Logger) -> None:
        self._telemetry = telemetry
        self._logger = logger
        self._physics_worlds: Dict[str, PhysicsWorld] = {}

    def bind(self, world: World, config: Optional[PhysicsConfig] = None) -> PhysicsWorld:
        pw = PhysicsWorld(world, config)
        self._physics_worlds[world.world_id] = pw
        self._telemetry.counter("physics.bound", tags={"world_id": world.world_id})
        return pw

    def step(self, world_id: str, delta_seconds: float) -> List[Contact]:
        pw = self._physics_worlds.get(world_id)
        if pw is None:
            raise PhysicsError(f"No physics world bound to {world_id}")
        contacts = pw.step(delta_seconds)
        self._telemetry.histogram("physics.contacts", len(contacts), tags={"world_id": world_id})
        return contacts

    def apply_force(self, world_id: str, entity_id: str, force: Force) -> None:
        pw = self._physics_worlds.get(world_id)
        if pw is None:
            raise PhysicsError(f"No physics world bound to {world_id}")
        pw.apply_force(entity_id, force)

    def register_body(self, world_id: str, entity_id: str, body: RigidBody) -> None:
        pw = self._physics_worlds.get(world_id)
        if pw is None:
            raise PhysicsError(f"No physics world bound to {world_id}")
        pw.register(entity_id, body)


class PhysicsError(Exception):
    pass
```
```python
"""
tests/simulation/test_physics.py
"""
import pytest

from artus.simulation.physics import (
    PhysicsWorld,
    PhysicsConfig,
    PhysicsService,
    RigidBody,
    SphereCollider,
    BoxCollider,
    Collider,
    Force,
    Vector3,
    AABB,
    Contact,
    PhysicsError,
)
from artus.simulation.world import World, WorldEntity, WorldConfig


class FakeTel:
    def counter(self, name, tags=None):
        pass

    def histogram(self, name, value, tags=None):
        pass


class FakeLog:
    def info(self, msg, extra=None):
        pass


def test_aabb_intersection():
    a = AABB(Vector3(0, 0, 0), Vector3(2, 2, 2))
    b = AABB(Vector3(1, 1, 1), Vector3(3, 3, 3))
    assert a.intersects(b)
    c = AABB(Vector3(5, 5, 5), Vector3(6, 6, 6))
    assert not a.intersects(c)


def test_rigid_body_inverse_mass():
    rb = RigidBody(mass=2.0)
    assert rb.inverse_mass == 0.5
    static = RigidBody(mass=100, is_static=True)
    assert static.inverse_mass == 0.0


def test_physics_world_step_gravity():
    world = World(config=WorldConfig(spatial_cell_size=100))
    ent = WorldEntity(position=Vector3(0, 10, 0), velocity=Vector3(0, 0, 0))
    world.spawn(ent)

    pw = PhysicsWorld(world, PhysicsConfig(gravity=Vector3(0, -10, 0)))
    pw.register(ent.entity_id, RigidBody(mass=1.0))
    pw.step(1.0)
    stepped_ent = world.get(ent.entity_id)
    assert stepped_ent.velocity.y < 0
    assert stepped_ent.position.y < 10


def test_collision_detection():
    world = World(config=WorldConfig(spatial_cell_size=10))
    a = WorldEntity(position=Vector3(0, 0, 0))
    b = WorldEntity(position=Vector3(1.5, 0, 0))
    world.spawn(a)
    world.spawn(b)

    pw = PhysicsWorld(world)
    pw.register(a.entity_id, RigidBody(mass=1, collider=Collider(shape=SphereCollider(radius=1.0))))
    pw.register(b.entity_id, RigidBody(mass=1, collider=Collider(shape=SphereCollider(radius=1.0))))
    contacts = pw.step(1.0)
    assert len(contacts) == 1
    assert contacts[0].penetration > 0


def test_service_bind_and_step():
    svc = PhysicsService(FakeTel(), FakeLog())
    world = World()
    pw = svc.bind(world)
    assert pw is not None
    ent = WorldEntity(position=Vector3(0, 0, 0))
    world.spawn(ent)
    svc.register_body(world.world_id, ent.entity_id, RigidBody())
    contacts = svc.step(world.world_id, 1.0)
    assert isinstance(contacts, list)


def test_service_missing_world_raises():
    svc = PhysicsService(FakeTel(), FakeLog())
    with pytest.raises(PhysicsError):
        svc.step("missing", 1.0)
```
