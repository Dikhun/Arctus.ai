from __future__ import annotations

import json
import zlib
from datetime import datetime
from pathlib import Path

import aiofiles
import structlog

from .models import StateSnapshot

logger = structlog.get_logger()


class HistoricalEngine:
    def __init__(self, snapshot_dir: Path):
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._version = 0

    async def save_snapshot(self, snapshot: StateSnapshot) -> Path:
        self._version += 1
        snapshot.version = self._version
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"snapshot_v{self._version}_{timestamp}.json.zlib"
        path = self.snapshot_dir / filename
        raw = snapshot.model_dump_json().encode("utf-8")
        compressed = zlib.compress(raw)
        async with aiofiles.open(path, "wb") as f:
            await f.write(compressed)
        logger.info(
            "snapshot_saved",
            path=str(path),
            entities=snapshot.entity_count,
            relations=snapshot.relation_count,
        )
        return path

    async def load_latest(self) -> StateSnapshot | None:
        files = sorted(self.snapshot_dir.glob("snapshot_*.json.zlib"), reverse=True)
        if not files:
            return None
        latest = files[0]
        async with aiofiles.open(latest, "rb") as f:
            compressed = await f.read()
        raw = zlib.decompress(compressed)
        data = json.loads(raw)
        self._version = data.get("version", 0)
        return StateSnapshot.model_validate(data)
