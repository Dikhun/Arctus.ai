import unittest

from arctus_simulation_engine.adapters import (
    InMemoryEventBus,
    InMemoryTelemetry,
    InMemoryHealthMonitor,
    InMemoryCheckpointService,
    InMemoryConfigurationManager,
)
from arctus_simulation_engine.core import (
    VirtualTime,
    DiscreteEventScheduler,
    EntityLifecycleManager,
    SimulationRuntime,
    RuntimeConfig,
)
from arctus_simulation_engine.primitives import SimState, SimulationTime, Duration


class TestSimulationRuntime(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = InMemoryEventBus()
        self.telemetry = InMemoryTelemetry()
        self.health_monitor = InMemoryHealthMonitor()
        self.checkpoint_service = InMemoryCheckpointService()
        self.config_manager = InMemoryConfigurationManager()

 self.vt = VirtualTime()
        self.sched = DiscreteEventScheduler(self.vt, self.bus)
        self.entities = EntityLifecycleManager(self.bus, self.vt)

        self.runtime = SimulationRuntime(
            runtime_id="test-rt",
            virtual_time=self.vt,
            scheduler=self.sched,
            entities=self.entities,
            event_bus=self.bus,
            telemetry=self.telemetry,
            health_monitor=self.health_monitor,
            checkpoint_service=self.checkpoint_service,
            config_manager=self.config_manager,
        )

    async def test_initialize(self):
        self.assertEqual(self.runtime.state, SimState.IDLE)
        await self.runtime.initialize()
        self.assertEqual(self.runtime.state, SimState.PAUSED)

    async def test_start_pause_stop(self):
        await self.runtime.initialize()
        await self.runtime.start()
        self.assertEqual(self.runtime.state, SimState.RUNNING)
        await self.runtime.pause()
        self.assertEqual(self.runtime.state, SimState.PAUSED)
        await self.runtime.stop()
        self.assertEqual(self.runtime.state, SimState.STOPPED)

    async def test_step_advances_time(self):
        await self.runtime.initialize()

        async def tick():
            pass

        self.sched.schedule_relative(Duration.from_seconds(2.0), tick)
        await self.runtime.step()
        self.assertEqual(self.vt.now, SimulationTime.from_seconds(2.0))

    async def test_checkpoint_restore(self):
        await self.runtime.initialize()
        await self.entities.spawn("e1")
        cp_id = await self.runtime.checkpoint()
        self.assertTrue(cp_id.startswith("checkpoint-test-rt"))
        loaded = await self.checkpoint_service.load(cp_id)
        self.assertIsNotNone(loaded)
        await self.runtime.restore(cp_id)
        self.assertEqual(self.runtime.current_time.nanos, self.vt.now.nanos)

    async def test_health(self):
        await self.runtime.initialize()
        report = await self.runtime.health()
        self.assertEqual(report["status"], "healthy")
        self.assertIn("test-rt", report["checks"])

    async def test_telemetry_emitted(self):
        await self.runtime.initialize()
        self.assertTrue(any(m["name"] == "simulation.runtime.initialized" for m in self.telemetry._metrics))

    async def test_reset(self):
        await self.runtime.initialize()
        await self.entities.spawn("e1")
        await self.runtime.start()
        await self.runtime.reset()
        self.assertEqual(self.runtime.state, SimState.IDLE)
        self.assertEqual(self.vt.now, SimulationTime(0))
        self.assertEqual(len(self.entities.list_active()), 0)

    async def test_autonomous_bootstrap(self):
        from arctus_simulation_engine.autonomous_runtime import AutonomousRuntime
        art = AutonomousRuntime("auto-rt")
        rt = await art.bootstrap()
        self.assertIsInstance(rt, SimulationRuntime)
        h = await art.health()
        self.assertIn("status", h)
