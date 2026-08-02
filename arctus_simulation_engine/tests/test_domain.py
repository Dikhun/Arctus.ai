import unittest

from arctus_simulation_engine.primitives import SimulationTime, Duration, SimState


class TestSimulationTime(unittest.TestCase):
    def test_arithmetic(self):
        t1 = SimulationTime.from_seconds(1.0)
        d = Duration.from_seconds(0.5)
        t2 = t1 + d
        self.assertEqual(t2.nanos, 1_500_000_000)
        diff = t2 - t1
        self.assertEqual(diff.nanos, 500_000_000)

    def test_comparison(self):
        t1 = SimulationTime(100)
        t2 = SimulationTime(200)
        self.assertTrue(t1 < t2)
        self.assertFalse(t1 == t2)
        self.assertTrue(t1 == SimulationTime(100))

    def test_hash(self):
        self.assertEqual(hash(SimulationTime(42)), hash(SimulationTime(42)))


class TestDuration(unittest.TestCase):
    def test_mul(self):
        d = Duration.from_seconds(2.0)
        d2 = d * 1.5
        self.assertEqual(d2.nanos, 3_000_000_000)


class TestSimState(unittest.TestCase):
    def test_members(self):
        self.assertEqual(SimState.RUNNING, "running")
