from __future__ import annotations

import asyncio
import platform
import shutil

import structlog

logger = structlog.get_logger()


class UvInstaller:
    @staticmethod
    async def install() -> bool:
        """Install uv if it is not already available."""

        if shutil.which("uv"):
            logger.info("uv_already_installed")
            return True

        system = platform.system()
        logger.info("uv_install_start", system=system)

        if system == "Windows":
            proc = await asyncio.create_subprocess_shell(
                'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("uv_install_failed", stderr=stderr.decode())
            return False

        logger.info("uv_installed")
        return True

    @staticmethod
    async def sync() -> bool:
        """Install all dependencies from pyproject.toml."""

        proc = await asyncio.create_subprocess_exec(
            "uv",
            "sync",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("uv_sync_failed", stderr=stderr.decode())
            return False

        logger.info("uv_sync_completed")
        return True

    @staticmethod
    async def ensure() -> None:
        """Ensure uv and all project dependencies are installed."""

        ok = await UvInstaller.install()
        if not ok:
            raise RuntimeError("Failed to install uv")

        ok = await UvInstaller.sync()
        if not ok:
            raise RuntimeError("Failed to synchronize dependencies")
