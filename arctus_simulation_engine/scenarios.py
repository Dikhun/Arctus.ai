```python
"""
artus/simulation/scenarios.py
Scenario definitions, execution engine, validation.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union

from artus.foundation.di import Injectable
from artus.foundation.telemetry import Logger, Telemetry

from artus.simulation.world import World, WorldConfig, WorldEntity, Vector3, WorldService
from artus.simulation.environment import EnvironmentConfig, EnvironmentService, EnvironmentState
from artus.simulation.physics import PhysicsService, PhysicsConfig, RigidBody, Collider, SphereCollider, Force


@dataclass
class SpawnAction:
    entity: WorldEntity


@dataclass
class ApplyForceAction:
    entity_id: str
    force: Force


@dataclass
class SetEnvironmentAction:
    state: EnvironmentState


@dataclass
class WaitAction:
    seconds: float


@dataclass
class AssertStateAction:
    predicate: str
    expected: Any


ScenarioAction = Union[SpawnAction, ApplyForceAction, SetEnvironmentAction, WaitAction, AssertStateAction]


@dataclass
class ScenarioConfig:
    name: str = "unnamed"
    initial_world: Optional[WorldConfig] = None
    initial_environment: Optional[EnvironmentConfig] = None
    initial_physics: Optional[PhysicsConfig] = None


@dataclass
class ScenarioStep:
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: ScenarioAction = field(default_factory=lambda: WaitAction(0.0))
    description: str = ""


@dataclass
class Scenario:
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    config: ScenarioConfig = field(default_factory=ScenarioConfig)
    steps: List[ScenarioStep] = field(default_factory=list)


@dataclass
class ScenarioContext:
    scenario_id: str
    world_id: Optional[str] = None
    environment_id: Optional[str] = None
    current_step_index: int = 0
    variables: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.monotonic)
    completed: bool = False
    failed: bool = False
    failure_reason: str = ""


class ScenarioValidationError(Exception):
    pass


class ScenarioExecutionError(Exception):
    pass


class ScenarioValidator:
    def validate(self, scenario: Scenario) -> None:
        if not scenario.steps:
            raise ScenarioValidationError("Scenario has no steps")
        for step in scenario.steps:
            if isinstance(step.action, ApplyForceAction):
                if not step.action.entity_id:
                    raise ScenarioValidationError("ApplyForceAction missing entity_id")
            elif isinstance(step.action, AssertStateAction):
                if not step.action.predicate:
                    raise ScenarioValidationError("AssertStateAction missing predicate")


class ScenarioRepository(Protocol):
    def save(self, scenario: Scenario) -> None:
        ...

    def get(self, scenario_id: str) -> Optional[Scenario]:
        ...

    def delete(self, scenario_id: str) -> None:
        ...
@Injectable(singleton=True)
class ScenarioEngine:
    def __init__(
        self,
        world_service: WorldService,
        environment_service: EnvironmentService,
        physics_service: PhysicsService,
        telemetry: Telemetry,
        logger: Logger,
    ) -> None:
        self._worlds = world_service
        self._envs = environment_service
        self._physics = physics_service
        self._telemetry = telemetry
        self._logger = logger
        self._validator = ScenarioValidator()
        self._contexts: Dict[str, ScenarioContext] = {}

    def compile(self, scenario: Scenario) -> ScenarioContext:
        self._validator.validate(scenario)
        ctx = ScenarioContext(scenario_id=scenario.scenario_id)
        self._contexts[ctx.scenario_id] = ctx
        self._telemetry.counter("scenario.compiled")
        return ctx

    def initialize(self, ctx: ScenarioContext, scenario: Scenario) -> None:
        world = self._worlds.create(scenario.config.initial_world)
        ctx.world_id = world.world_id
        self._worlds.spawn(world.world_id, WorldEntity(position=Vector3(0, 0, 0)))
        env = self._envs.create(world.world_id, scenario.config.initial_environment)
        ctx.environment_id = env.environment_id
        self._physics.bind(world, scenario.config.initial_physics)
        self._telemetry.counter("scenario.initialized")

    def execute_step(self, ctx: ScenarioContext, scenario: Scenario) -> None:
        if ctx.completed or ctx.failed:
            return
        if ctx.current_step_index >= len(scenario.steps):
            ctx.completed = True
            self._telemetry.counter("scenario.completed")
            return

        step = scenario.steps[ctx.current_step_index]
        try:
            self._run_action(ctx, step.action)
        except Exception as exc:
            ctx.failed = True
            ctx.failure_reason = str(exc)
            self._telemetry.counter("scenario.step_failed")
            raise ScenarioExecutionError(f"Step {step.step_id} failed: {exc}") from exc
        ctx.current_step_index += 1

    def run_all(self, scenario: Scenario) -> ScenarioContext:
        ctx = self.compile(scenario)
        self.initialize(ctx, scenario)
        while not ctx.completed and not ctx.failed:
            self.execute_step(ctx, scenario)
        return ctx

    def _run_action(self, ctx: ScenarioContext, action: ScenarioAction) -> None:
        if isinstance(action, SpawnAction):
            if ctx.world_id is None:
                raise ScenarioExecutionError("No world initialized")
            self._worlds.spawn(ctx.world_id, action.entity)
        elif isinstance(action, ApplyForceAction):
            if ctx.world_id is None:
                raise ScenarioExecutionError("No world initialized")
            self._physics.apply_force(ctx.world_id, action.entity_id, action.force)
        elif isinstance(action, SetEnvironmentAction):
            if ctx.environment_id is None:
                raise ScenarioExecutionError("No environment initialized")
            self._envs.set_global_state(ctx.environment_id, action.state)
        elif isinstance(action, WaitAction):
            if ctx.world_id:
                self._worlds.advance_time(ctx.world_id, action.seconds)
                self._physics.step(ctx.world_id, action.seconds)
        elif isinstance(action, AssertStateAction):
            if action.predicate == "world_exists":
                try:
                    self._worlds.load(ctx.world_id)
                except Exception:
                    raise ScenarioExecutionError("Assert failed: world does not exist")
            else:
                actual = ctx.variables.get(action.predicate)
                if actual != action.expected:
                    raise ScenarioExecutionError(f"Assert failed: {actual} != {action.expected}")
```
```python
"""
tests/simulation/test_scenarios.py
"""
import pytest

from artus.simulation.scenarios import (
    Scenario,
    ScenarioConfig,
    ScenarioStep,
    ScenarioEngine,
    ScenarioContext,
    ScenarioValidationError,
    ScenarioExecutionError,
    SpawnAction,
    ApplyForceAction,
    WaitAction,
    AssertStateAction,
    ScenarioValidator,
    SetEnvironmentAction,
)
from artus.simulation.world import WorldService, WorldEntity, WorldConfig, Vector3
from artus.simulation.environment import EnvironmentService
from artus.simulation.physics import PhysicsService, Force

from tests.simulation.test_world import MemoryWorldRepo, FakeTel, FakeLog
from tests.simulation.test_environment import MemoryEnvRepo


@pytest.fixture
def world_svc():
    return WorldService(MemoryWorldRepo(), FakeTel(), FakeLog())


@pytest.fixture
def env_svc():
    return EnvironmentService(MemoryEnvRepo(), FakeTel(), FakeLog())


@pytest.fixture
def phys_svc():
    return PhysicsService(FakeTel(), FakeLog())


@pytest.fixture
def engine(world_svc, env_svc, phys_svc):
    return ScenarioEngine(world_svc, env_svc, phys_svc, FakeTel(), FakeLog())


def test_validator_empty_scenario():
    v = ScenarioValidator()
    with pytest.raises(ScenarioValidationError):
        v.validate(Scenario())


def test_validator_good_scenario():
    v = ScenarioValidator()
    s = Scenario(steps=[ScenarioStep(action=WaitAction(1.0))])
    v.validate(s)


def test_compile_and_initialize(engine):
    s = Scenario(
        config=ScenarioConfig(initial_world=WorldConfig(max_entities=5)),
        steps=[ScenarioStep(action=WaitAction(0.1))],
    )
    ctx = engine.compile(s)
    assert isinstance(ctx, ScenarioContext)
    engine.initialize(ctx, s)
    assert ctx.world_id is not None
    assert ctx.environment_id is not None


def test_run_spawn_step(engine):
    s = Scenario(
        config=ScenarioConfig(initial_world=WorldConfig(max_entities=5)),
        steps=[
            ScenarioStep(action=SpawnAction(WorldEntity(position=Vector3(1, 0, 0)))),
            ScenarioStep(action=WaitAction(0.1)),
        ],
    )
    ctx = engine.run_all(s)
    assert ctx.completed is True
    world = engine._worlds.load(ctx.world_id)
    assert world.entity_count == 2  # ground ref + spawned


def test_run_assert_fail(engine):
    s = Scenario(
        config=ScenarioConfig(initial_world=WorldConfig(max_entities=5)),
        steps=[ScenarioStep(action=AssertStateAction(predicate="world_exists", expected=True))],
    )
    ctx = engine.run_all(s)
    assert ctx.completed


def test_apply_force_step(engine):
    s = Scenario(
        config=ScenarioConfig(initial_world=WorldConfig(max_entities=5)),
        steps=[
            ScenarioStep(action=SpawnAction(WorldEntity(entity_id="ball", position=Vector3(0, 0, 0)))),
            ScenarioStep(
                action=ApplyForceAction(
                    entity_id="ball",
                    force=Force(vector=Vector3(10, 0, 0)),
                )
            ),
            ScenarioStep(action=WaitAction(1.0)),
        ],
    )
    ctx = engine.run_all(s)
    world = engine._worlds.load(ctx.world_id)
    ball = world.get("ball")
    assert ball.velocity.x > 0
```
