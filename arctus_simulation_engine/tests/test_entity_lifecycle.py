import unittest

from arctus_simulation_engine.adapters import InMemoryEventBus
from arctus_simulation_engine.core import VirtualTime, EntityLifecycleManager
from arctus_simulation_engine.primitives import EntityState, SimulationTime


class TestEntityLifecycleManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = InMemoryEventBus()
        self.vt = VirtualTime()
        self.mgr = EntityLifecycleManager(self.bus, self.vt)

    async def test_spawn_and_active(self):
        e = await self.mgr.spawn("ent-1", {"role": "test"})
        self.assertEqual(e.state, EntityState.ALIVE)
        self.assertEqual(self.mgr.get("ent-1").entity_id, "ent-1")
        self.assertEqual(len(self.mgr.list_active()), 1)

    async def test_transition(self):
        await self.mgr.spawn("ent-1")
        e = await self.mgr.transition("ent-1", EntityState.SUSPENDED)
        self.assertEqual(e.state, EntityState.SUSPENDED)

    async def test_destroy(self):
        await self.mgr.spawn("ent-1")
        await self.mgr.destroy("ent-1")
        self.assertIsNone(self.mgr.get("ent-1"))
        self.assertEqual(len(self.mgr.list_active()), 0)

    async def test_duplicate_spawn_raises(self):
        await self.mgr.spawn("ent-1")
        with self.assertRaises(ValueError):
            await self.mgr.spawn("ent-1")

    async def test_handler_invoked(self):
        calls = []

        async def handler(entity):
            calls.append(entity.entity_id)

        self.mgr.on_transition(EntityState.ALIVE, handler)
        await self.mgr.spawn("ent-2")
        self.assertIn("ent-2", calls)
