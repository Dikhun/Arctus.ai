from __future__ import annotations

import asyncio

import structlog

from .analysis import AnalysisEngine
from .config import TwinConfig
from .event_bus import EventBus
from .graph_store import GraphStore
from .history import HistoricalEngine
from .models import (
    BaseEntity,
    ChangeEvent,
    ChangeType,
    EntityType,
    ImpactLevel,
    StateSnapshot,
)
from .prediction import PredictionEngine
from .query import QueryEngine
from .state_sync import BaseSyncAdapter, FilesystemAdapter

logger = structlog.get_logger()


class DigitalTwinEngine:
    """
    The core Digital Twin orchestrator:
    - Owns the graph, event bus, and sync adapters
    - Maintains one source of truth
    - Predicts impact before reality changes
    - Historizes every significant state change
    """

    def __init__(self, config: TwinConfig | None = None):
        self.config = config or TwinConfig()
        self.graph = GraphStore()
        self.events = EventBus(maxsize=self.config.event_queue_maxsize)
        self.history = HistoricalEngine(self.config.snapshot_dir)
        self.queries = QueryEngine(self.graph)
        self.predictions = PredictionEngine(self.graph)
        self.analysis = AnalysisEngine(self.graph)
        self._adapters: list[BaseSyncAdapter] = []
        self._running = False
        self._snapshot_task: asyncio.Task | None = None

    async def bootstrap(self) -> None:
        logger.info("twin_bootstrap_start")
        root = BaseEntity(
            type=EntityType.PROJECT,
            name=self.config.project_root.name or "root",
            metadata={"path": str(self.config.project_root)},
        )
        root.checksum = root.compute_checksum()
        await self.graph.add_entity(root)
        self.register_adapter(FilesystemAdapter(self.events, self.config.project_root))
        snap = await self.history.load_latest()
        if snap:
            logger.info("history_loaded", version=snap.version)
        logger.info("twin_bootstrap_complete", root_entity=root.id)

    def register_adapter(self, adapter: BaseSyncAdapter) -> None:
        self._adapters.append(adapter)

    async def start(self) -> None:
        self._running = True
        await self.events.start()
        self.events.subscribe(self._on_change_event)
        for adapter in self._adapters:
            await adapter.start()
        self._snapshot_task = asyncio.create_task(self._periodic_snapshot())
        logger.info("twin_engine_started")

    async def stop(self) -> None:
        self._running = False
        for adapter in self._adapters:
            await adapter.stop()
        await self.events.stop()
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass
        await self._snapshot()
        logger.info("twin_engine_stopped")

    async def _on_change_event(self, event: ChangeEvent) -> None:
        logger.debug(
            "twin_processing_event",
            event_id=event.event_id,
            entity=event.entity_name,
            action=event.change_type.value,
        )

        if event.change_type == ChangeType.CREATE:
            entity = BaseEntity(
    id=event.entity_id or str(uuid.uuid4()),
    type=event.entity_type,
    name=event.entity_name or "unknown",
    metadata=event.payload,
    source_system=event.source_adapter,
            )
            )
            entity.checksum = entity.compute_checksum()
            await self.graph.add_entity(entity)
        elif event.change_type == ChangeType.UPDATE and event.entity_id:
            existing = await self.graph.get_entity(event.entity_id)
            if existing:
                existing.metadata.update(event.payload)
                existing.touch()
                await self.graph.update_entity(existing)
        elif event.change_type == ChangeType.DELETE and event.entity_id:
            await self.graph.remove_entity(event.entity_id)

        await self._auto_link(event)

        if self.config.enable_prediction and event.entity_id:
            try:
                pred = await self.predictions.predict_dependency_breakage(event.entity_id)
                if pred.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL):
                    logger.warning(
                        "prediction_alert",
                        type=pred.prediction_type,
                        impact=pred.impact_level.value,
                        description=pred.description,
                    )
            except Exception as exc:
                logger.error("prediction_failed", error=str(exc))

    async def _auto_link(self, event: ChangeEvent) -> None:
        """Heuristic relationship builder (e.g., file -> directory ownership)."""
        path_str = event.payload.get("path")
        if not path_str:
            return

# Placeholder: future integration with AST parsing for IMPORTS/CALLS edges
        pass

    async def _periodic_snapshot(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(max(30.0, self.config.sync_interval * 6))
                await self._snapshot()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("prediction_failed")
    async def _snapshot(self) -> None:
        snap_data = await self.graph.to_snapshot()
        snap = StateSnapshot.from_graph(
            entities=snap_data["entities"],
            relationships=snap_data["relationships"],
            version=await self._get_next_version(),
        )
        await self.history.save_snapshot(snap)

    async def _get_next_version(self) -> int:
        # In a distributed system this would be a vector-clock / CRDT.
        return 1

    async def query(self, q: str) -> dict:
        """Structured query interface. Expandable to NLQ via Intent Compiler."""
        if q.startswith("impact"):
            parts = q.split()
            if len(parts) > 1:
                return (await self.queries.query_impact(parts[1])).model_dump()
        return (await self.queries.query_entity_by_name(q)).model_dump()

    async def get_status(self) -> dict:
        return {
            "running": self._running,
            "entities": self.graph.entity_count,
            "relationships": self.graph.relation_count,
            "adapters": [a.name for a in self._adapters],
            "predictions_enabled": self.config.enable_prediction,
            "history_enabled": self.config.enable_history,
          }
