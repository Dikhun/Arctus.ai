from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from watchfiles import Change, awatch

from .event_bus import EventBus
from .models import ChangeEvent, ChangeType, EntityType

logger = structlog.get_logger()


class BaseSyncAdapter:
    def __init__(self, name: str, bus: EventBus):
        self.name = name
        self.bus = bus

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        pass


class FilesystemAdapter(BaseSyncAdapter):
    def __init__(
        self,
        bus: EventBus,
        root: Path,
        watched_patterns: list[str] | None = None,
    ):
        super().__init__("filesystem", bus)
        self.root = root.resolve()
        self.patterns = watched_patterns or ["*.py", "*.toml", "*.md", "*.json", "*.yaml", "*.yml"]
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        try:
            async for changes in awatch(self.root, stop_event=self._stop_event, force_polling=False):
                for change, path_str in changes:
 path = Path(path_str)
                    if not any(path.match(p) for p in self.patterns):
                        continue
                    event_type = (
                        ChangeType.UPDATE
                        if change == Change.modified
                        else ChangeType.CREATE
                        if change == Change.added
                        else ChangeType.DELETE
                    )
                    entity_type = (
                        EntityType.FILE
                        if path.is_file() or event_type == ChangeType.DELETE
                        else EntityType.DIRECTORY
                    )
 event = ChangeEvent(
                        source_adapter=self.name,
                        change_type=event_type,
                        entity_type=entity_type,
                        entity_name=path.name,
                        payload={
                            "path": str(path.relative_to(self.root)),
                            "absolute": str(path),
                        },
                    )
                    await self.bus.emit(event)
                    logger.debug("filesystem_change", path=str(path), change=change.name)
        except Exception as exc:
            logger.error("filesystem_adapter_error", error=str(exc))
