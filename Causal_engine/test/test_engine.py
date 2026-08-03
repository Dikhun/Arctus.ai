import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from arctus_causal_engine.types import SystemInfo, ServiceStatus
from arctus_causal_engine.di import DIContainer
from arctus_causal_engine.discovery import EnvironmentDiscovery
from arctus_causal_engine.configuration import ConfigurationManager
from arctus_causal_engine.storage import StorageManager, RedisBackend, PostgreSQLBackend
from arctus_causal_engine.health import PureAsyncioTelemetryServer
from arctus_causal_engine.bootstrap import CausalEngineBootstrap


class TestDIContainer(unittest.IsolatedAsyncioTestCase):
    async def test_singleton_resolution(self):
        class IDummy:
            pass

        class Dummy(IDummy):
            def __init__(self):
                self.val = 42

        container = DIContainer()
        container.register(IDummy, lambda c: Dummy(), singleton=True)
        a = await container.resolve(IDummy)
        b = await container.resolve(IDummy)
        self.assertIs(a, b)
        self.assertEqual(a.val, 42)


class TestDiscovery(unittest.IsolatedAsyncioTestCase):
    async def test_detect_os(self):
        d = EnvironmentDiscovery()
        await d.detect_os()
        self.assertIn(d.info.os_name, ["Linux", "Darwin", "Windows", "Java"])

    async def test_detect_python(self):
        d = EnvironmentDiscovery()
        await d.detect_python()
        self.assertTrue(d.info.python_version.startswith("3."))

    async def test_detect_cpu(self):
        d = EnvironmentDiscovery()
        await d.detect_cpu()
        self.assertGreaterEqual(d.info.cpu_count, 1)

    async def test_memory_and_cloud_env(self):
        d = EnvironmentDiscovery()
        await d.detect_memory()
        self.assertIsInstance(d.info.total_memory_mb, int)

    async def test_tcp_reachable_localhost(self):
        d = EnvironmentDiscovery()
        result = await d._tcp_reachable("127.0.0.1", 65530)
        self.assertFalse(result)


class TestConfiguration(unittest.IsolatedAsyncioTestCase):
    async def test_generate_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            cm = ConfigurationManager("test_config.json")
            info = SystemInfo(os_name="Linux", cpu_count=8, postgresql=True, redis=False)
            config = await cm.generate(info)
            self.assertEqual(config["engine"]["workers"], 8)
            self.assertTrue(config["storage"]["postgresql"]["enabled"])
            loaded = cm.load()
            self.assertEqual(loaded["engine"]["name"], "causal-engine")


class TestStorage(unittest.IsolatedAsyncioTestCase):
    async def test_postgresql_failover(self):
        backend = PostgreSQLBackend("postgresql://invalid:1234/db")
        result = await backend.initialize()
        self.assertFalse(result)
        self.assertEqual(await backend.health(), ServiceStatus.FAILED)

    async def test_redis_failover(self):
        backend = RedisBackend("redis://invalid:1234")
        result = await backend.initialize()
        self.assertFalse(result)
        self.assertEqual(await backend.health(), ServiceStatus.FAILED)

    async def test_storage_manager_empty(self):
        sm = StorageManager({})
        self.assertEqual(sm.backends, {})
        result = await sm.initialize_all()
        self.assertEqual(result, {})


class TestHealthServer(unittest.IsolatedAsyncioTestCase):
    async def test_pure_server_start_stop(self):
        srv = PureAsyncioTelemetryServer(host="127.0.0.1", port=0)
        await srv.start()
        self.assertIsNotNone(srv.server)
        await srv.stop()

    async def test_metrics_update(self):
        srv = PureAsyncioTelemetryServer()
        srv.update_metrics({"cpu": 0.5})
        self.assertEqual(srv.metrics["cpu"], 0.5)


class TestBootstrapPhases(unittest.IsolatedAsyncioTestCase):
    async def test_phase_discover(self):
        be = CausalEngineBootstrap()
        await be.phase_discover()
        self.assertIn("system_info", be.state)

    async def test_phase_configure(self):
        be = CausalEngineBootstrap()
        be.state["system_info"] = SystemInfo(os_name="Linux", cpu_count=4)
        await be.phase_configure()
        self.assertIn("config", be.state)

    async def test_install_mock(self):
        import unittest.mock as mock
        be = CausalEngineBootstrap()
        with mock.patch.object(PackageInstaller, "install", return_value=True):
            be.installer = PackageInstaller()
            result = await be.installer.install(["aiohttp"])
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
