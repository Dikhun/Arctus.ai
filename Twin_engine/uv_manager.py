from __future__ import annotations

import asyncio
import platform
import shutil
from pathlib import Path

import structlog

logger = structlog.get_logger()


class UvManager:
    def __init__(self, config):
        self.config = config
        self._uv_bin = config.uv_path or shutil.which("uv")

    async def sync(self, cwd: Path | None = None) -> None:
        if not self._uv_bin:
            await self._auto_install()

        self._uv_bin = self.config.uv_path or shutil.which("uv")

        if not self._uv_bin:
            raise RuntimeError("uv installation failed")

        proc = await asyncio.create_subprocess_exec(
            self._uv_bin,
            "sync",
            cwd=cwd or self.config.project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"uv sync failed:\n{stderr.decode()}")

        logger.info("uv_sync_complete")

    async def run(
        self,
        command: list[str],
        cwd: Path |None = None,
    ) -> asyncio.subprocess.Process:

        if not self._uv_bin:
            await self._auto_install()

        self._uv_bin = self.config.uv_path or shutil.which("uv")

        return await asyncio.create_subprocess_exec(
            self._uv_bin,
            "run",
            *command,
            cwd=cwd or self.config.project_root,
        )

    async def _auto_install(self) -> None:
        logger.info("attempting_uv_install")

        if platform.system() == "Windows":
            cmd = (
                'powershell -ExecutionPolicy ByPass -c '
                '"irm https://astral.sh/uv/install.ps1 | iex"'
            )
        else:
            cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to install uv:\n{stderr.decode()}"
            )

        self._uv_bin = shutil.which("uv")

        if not self._uv_bin:
            raise RuntimeError("uv installed but executable not found")

        logger.info("uv_install_complete")
