import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = ".causal_checkpoints") -> None:
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    async def save(self, state: Dict[str, Any], name: str) -> str:
        filename = f"{name}_{datetime.now(timezone.utc).isoformat()}.json"
        path = os.path.join(self.checkpoint_dir, filename)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: json.dump(state, open(path, "w"), indent=2)
        )
        logger.info(f"Checkpoint saved: {path}")
        return path

    async def load_latest(self, name: str) -> Optional[Dict[str, Any]]:
        files = [
            f
            for f in os.listdir(self.checkpoint_dir)
            if f.startswith(name) and f.endswith(".json")
        ]
        if not files:
            return None
        files.sort()
        path = os.path.join(self.checkpoint_dir, files[-1])
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: json.load(open(path, "r"))
        )

    async def rollback_storage(self, storage_manager: Any) -> bool:
        logger.warning("Rolling back storage to last known good state")
        result = await storage_manager.recover_all()
        return all(result.values()) if result else False async def restart_service(self) -> bool:
        logger.info("Restarting service via sys.executable replacement")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as exc:
            logger.error(f"Restart failed: {exc}")
            return False

class RecoveryOrchestrator:
    def __init__(
        self,
        storage_manager: Any,
        registry: FrameworkRegistry,
        checkpoint_dir: str = ".causal_checkpoints",
    ) -> None:
        self.storage = storage_manager
        self.registry = registry
        self.checkpoint = CheckpointManager(checkpoint_dir)

    async def perform_recovery(self, state: Dict[str, Any]) -> bool:
        await self.checkpoint.save(state, "pre_recovery")
        storage_ok = await self.checkpoint.rollback_storage(self.storage)
        registry_ok = await self.registry.register_engine(
            {"status": "recovered", "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        return storage_ok and registry_ok
