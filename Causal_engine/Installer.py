import asyncio
import logging
import os
import subprocess
import sys
import venv
from typing import List, Optional

logger = logging.getLogger(__name__)

class PackageInstaller:
    def __init__(self, venv_path: Optional[str] = None) -> None:
        self.venv_path: str = venv_path or ".causal_engine_venv"
        self.python_executable: str = sys.executable
        self._ensure_venv()

    def _ensure_venv(self) -> None:
        if not os.path.exists(self.venv_path):
            logger.info(f"Creating virtual environment at {self.venv_path}")
            venv.create(self.venv_path, with_pip=True)
        if os.name == "nt":
            self.python_executable = os.path.join(self.venv_path, "Scripts", "python.exe")
        else:
            self.python_executable = os.path.join(self.venv_path, "bin", "python")

    async def install(
        self, packages: List[str], index_url: Optional[str] = None
    ) -> bool:
        cmd = [self.python_executable, "-m", "pip", "install", "--upgrade"] + packages
        if index_url:
            cmd.extend(["--index-url", index_url])
        logger.info(f"Installing packages: {packages}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"Installation failed: {stderr.decode()}")
            return False
        logger.info(f"Installation succeeded: {stdout.decode()[-500:]}")
        return True

    def install_requirements_txt(self, path: str = "requirements.txt") -> bool:
        if not os.path.exists(path):
            logger.warning(f"{path} not found; skipping.")
            return True
        cmd = [self.python_executable, "-m", "pip", "install", "-r", path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Requirements install failed: {result.stderr}")
            return False
        return True
