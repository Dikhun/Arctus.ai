import asyncio
import logging
import sys
from typing import Any, Dict, Optional

from .types import SystemInfo
from .di import DIContainer
from .discovery import EnvironmentDiscovery
from .installer import PackageInstaller
from .configuration import ConfigurationManager
from .storage import StorageManager
from .health import PureAsyncioTelemetryServer, AioHttpTelemetryServer
from .registration import FrameworkRegistry
from .recovery import RecoveryOrchestrator
from .integrations import IntegrationManager
from .plugins import PluginLoader
from .executor import DistributedExecutor
from .autonomous_management import AutonomousManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("CausalEngineBootstrap")

class CausalEngineBootstrap:
    def __init__(self) -> None:
        self.container = DIContainer()
        self.discovery = EnvironmentDiscovery()
        self.installer: Optional[PackageInstaller] = None
        self.config_manager = ConfigurationManager()
        self.storage_manager: Optional[StorageManager] = None
        self.telemetry: Any = None
        self.registry = FrameworkRegistry()
        self.recovery: Optional[RecoveryOrchestrator] = None
        self.integrations = IntegrationManager()
        self.plugin_loader = PluginLoader()
        self.executor = DistributedExecutor()
        self.autonomous = AutonomousManager(self)
        self.state: Dict[str, Any] = {}

    async def run(self) -> None:
        try:
            await self.phase_discover()
            await self.phase_install()
            await self.phase_configure()
            await self.phase_initialize_storage()
            await self.phase_register()
            await self.phase_integrate()
            await self.phase_start_services()
            await self.phase_self_manage()
        except Exception as exc:
            logger.exception("Bootstrap cycle encountered error")
            if self.recovery:
                await self.recovery.perform_recovery(self.state)

    async def phase_discover(self) -> None:
        logger.info("=== Phase: Environment Discovery ===")
        info = await self.discovery.discover_all()
        self.state["system_info"] = info
        logger.info(
            f"OS={info.os_name} Python={info.python_version} "
            f"CPU={info.cpu_count} RAM_MB={info.total_memory_mb}"
        )

    async def phase_install(self) -> None:
        logger.info("=== Phase: Installation ===")
        required_packages = [
            "aiohttp",
            "asyncpg",
            "redis",
            "neo4j",
            "psutil",
        ]
        self.installer = PackageInstaller()
        await self.installer.install(required_packages)
        self.installer.install_requirements_txt()
        await self._init_telemetry_server()

    async def phase_configure(self) -> None:
        logger.info("=== Phase: Configuration ===")
        info: SystemInfo = self.state["system_info"]
        config = await self.config_manager.generate(info)
        self.state["config"] = config
        self.storage_manager = StorageManager(config.get("storage", {}))

    async def phase_initialize_storage(self) -> None:
        logger.info("=== Phase: Storage Initialization ===")
        if self.storage_manager:
            results = await self.storage_manager.initialize_all()
            for name, ok in results.items():
                if not ok:
                    logger.warning(f"Storage backend initialization failed: {name}")

    async def phase_register(self) -> None:
        logger.info("=== Phase: Registration ===")
        await self.registry.register_engine(
            {
                "name": "causal-engine",
                "version": "1.0.0",
                "environment": self.state["system_info"].__dict__,
            }
        )
        from .types import CapabilityMeta
        self.registry.add_capability(
            CapabilityMeta(
                name="causal-inference",
                version="1.0.0",
                endpoint="/api/v1/infer",
            )
        )
        self.registry.add_capability(
            CapabilityMeta(
                name="graph-reasoning",
                version="1.0.0",
                endpoint="/api/v1/graph",
            )
        )
        await self.registry.publish_capabilities()

    async def phase_integrate(self) -> None:
        logger.info("=== Phase: Integration ===")
        available = await self.integrations.discover_and_connect()
        self.state["integrations"] = available
        await self.integrations.publish_capabilities(
            self.registry.expose_capability_metadata()
        )

    async def phase_start_services(self) -> None:
        logger.info("=== Phase: Start Services ===")
        if self.telemetry:
            await self.telemetry.start()
            logger.info("Telemetry server started")
        asyncio.create_task(self._monitoring_loop())
        asyncio.create_task(self._continuous_health_loop())

    async def phase_self_manage(self) -> None:
        logger.info("=== Phase: Continuous Self-Management ===")
        while True:
            await asyncio.sleep(30)
            await self.autonomous.run_cycle()

    async def _init_telemetry_server(self) -> None:
        try:
            import aiohttp
            logger.info("Using aiohttp telemetry server")
            self.telemetry = AioHttpTelemetryServer()
        except ImportError:
            logger.info("Falling back to pure asyncio telemetry server")
            self.telemetry = PureAsyncioTelemetryServer()

    async def _monitoring_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            if self.storage_manager:
                health = await self.storage_manager.health_all()
                for name, status in health.items():
 logger.debug(f"Storage {name} status: {status.value}")

    async def _continuous_health_loop(self) -> None:
        if not self.telemetry:
            return
        while True:
            await asyncio.sleep(5)
            if self.storage_manager:
                metrics: Dict[str, Any] = {}
                health = await self.storage_manager.health_all()
                for name, status in health.items():
                    metrics[f"storage_{name}"] = status.value
                self.telemetry.update_metrics(metrics)
