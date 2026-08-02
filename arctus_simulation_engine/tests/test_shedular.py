import unittest

from arctus_simulation_engine.primitives import SimulationTime, Duration
from arctus_simulation_engine.adapters import InMemoryEventBus
from arctus_simulation_engine.core import VirtualTime, DiscreteEventScheduler


class TestDiscreteEventScheduler(unittest.IsolatedAsyncioTestCase):
    async def test_scheduling_order(self):
        bus = InMemoryEventBus()
        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, bus)
        results = []

        async def cb1():
            results.append(1)

        async def cb2():
            results.append(2)

        sched.schedule_absolute(SimulationTime(10), cb2)
        sched.schedule_absolute(SimulationTime(5), cb1)
        await sched.run()
        self.assertEqual(results, [1, 2])
        self.assertEqual(vt.now.nanos, 10)

    async def test_relative_scheduling(self):
        bus = InMemoryEventBus()
        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, bus)
        triggered = []

        async def cb():
            triggered.append(vt.now.nanos)

        sched.schedule_relative(Duration.from_seconds(1.0), cb)
        await sched.step()
        self.assertEqual(triggered[0], 1_000_000_000)

    async def test_cancellation(self):
        bus = InMemoryEventBus()
        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, bus)
        triggered = []

        async def cb():
            triggered.append(True)

        eid = sched.schedule_absolute(SimulationTime(5), cb)
        self.assertTrue(sched.cancel(eid))
        await sched.step()
        self.assertEqual(len(triggered), 0)

    async def test_priority_tiebreak(self):
        bus = InMemoryEventBus()
        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, bus)
        results = []

        async def low():
            results.append("low")

        async def high():
            results.append("high")

        sched.schedule_absolute(SimulationTime(1), low, priority=10)
        sched.schedule_absolute(SimulationTime(1), high, priority=1)
        await sched.run()
        self.assertEqual(results, ["high", "low"])

    async def test_event_count(self):
        bus = InMemoryEventBus()
        vt = VirtualTime()
        sched = DiscreteEventScheduler(vt, bus)
        self.assertEqual(sched.event_count, 0)
        sched.schedule_absolute(SimulationTime(5), lambda: None)
        self.assertEqual(sched.event_count, 1)
 sched.clear()
        self.assertEqual(sched.event_count, 0)
