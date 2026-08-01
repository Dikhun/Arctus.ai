from __future__ import annotations

import asyncio

import structlog

from .config import TwinConfig
from .health import HealthMonitor
from .installer import UvInstaller
from .models import BaseEntity, EntityType
from .restart_policy import ExponentialBackoff
from .signals import setup_signal_handlers
from .twin_engine import DigitalTwinEngine
from .uv_manager import UvManager

logger = structlog.get_logger()


class Supervisor:
    """
    Process supervisor that runs the Digital Twin as the single source of truth.
    All managed processes and workflows are themselves entities within the twin.
    """

    def __init__(self, config: TwinConfig | None = None):
        self.config = config or TwinConfig()
        self.twin = DigitalTwinEngine(self.config)
        self.backoff = ExponentialBackoff(
            base_delay=self.config.restart_base_delay,
            max_attempts=self.config.restart_max_attempts,
        )
        self.health = HealthMonitor()
        self.uv = UvManager(self.config)
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        # Ensure uv and all project dependencies are available
        await UvInstaller.ensure()

        setup_signal_handlers(self._shutdown_event)
        logger.info("supervisor_starting")

        await self.twin.bootstrap()
        await self.twin.start()

        await self.twin.graph.add_entity(
            BaseEntity(
                type=EntityType.RUNTIME_PROCESS,
                name="arctus_supervisor",
                metadata={"role": "supervisor"},
            )
        )

        try:
            while not self._shutdown_event.is_set():
                await self.health.check_all()

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.warning("supervisor_cancelled")

        except Exception:
            logger.exception("supervisor_runtime_failure")
            raise

        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("supervisor_shutting_down")

        await self.twin.stop()

        self._shutdown_event.set()

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(
                *self._tasks,
                return_exceptions=True,
            )

        logger.info("supervisor_shutdown_complete")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()
