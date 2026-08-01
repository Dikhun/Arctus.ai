import subprocess
import sys
import shutil

PACKAGES = [
    "pydantic",
    "pydantic-settings",
    "typer",
    "structlog",
    "watchfiles",
    "gitpython",
    "networkx",
    "rich",
    "aiofiles",
]

def ensure_uv():
    if shutil.which("uv") is None:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-U", "uv"]
        )

def ensure_dependencies():
    ensure_uv()

    for pkg in PACKAGES:
        try:
            subprocess.check_call(
                ["uv", "add", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            pass

    subprocess.check_call(["uv", "sync"])

if __name__ == "__main__":
    ensure_dependencies()
[project]
name = "arctus-supervisor"
version = "0.1.0"
description = "Arctus AI OS — Digital Twin Engine & Process Supervisor"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "typer>=0.12",
    "structlog>=24.1",
    "watchfiles>=0.21",
    "gitpython>=3.1",
    "networkx>=3.2",
    "rich>=13.7",
    "aiofiles>=23.2",
]

[project.scripts]
arctus = "arctus_supervisor.bootstrap:main"

[tool.ruff]
target-version = "py311"
line-length = 120
"""Arctus AI Operating System — Digital Twin Engine & Supervisor."""
__version__ = "0.1.0"
class ArctusError(Exception):
    """Base Arctus exception."""

class TwinSyncError(ArctusError):
    """State synchronization failure."""

class GraphConsistencyError(ArctusError):
    """Graph invariant violation."""

class PredictionError(ArctusError):
    """Prediction engine failure."""

class ValidationError(ArctusError):
    """Event or model validation failure."""

class ConfigError(ArctusError):
    """Configuration error."""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class TwinConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCTUS_", extra="ignore")

    project_root: Path = Field(default=Path("."), description="Root path to model")
    graph_backend: str = Field(default="memory", description="Graph backend: memory, neo4j, rdf")
    snapshot_dir: Path = Field(default=Path(".arctus/snapshots"))
    log_level: str = Field(default="INFO")
    sync_interval: float = Field(default=5.0, description="Seconds between sync polls")
    enable_prediction: bool = True
    enable_history: bool = True
    max_entities: int = 1_000_000
    event_queue_maxsize: int = 10_000

    restart_max_attempts: int = 5
    restart_base_delay: float = 1.0
    uv_path: str | None = None
import logging
import structlog
from rich.console import Console
from rich.logging import RichHandler

def configure_logging(log_level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True, show_path=False)],
    )
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    PROJECT = "project"
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    SOURCE_CODE = "source_code"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    PACKAGE = "package"
    DEPENDENCY = "dependency"
    API = "api"
    DATABASE_SCHEMA = "database_schema"
    INFRASTRUCTURE = "infrastructure"
    CONTAINER = "container"
    VIRTUAL_MACHINE = "virtual_machine"
    CLOUD_RESOURCE = "cloud_resource"
    AGENT = "agent"
    CAPABILITY = "capability"
    SKILL = "skill"
    PLUGIN = "plugin"
    MEMORY_LAYER = "memory_layer"
    EXECUTION_GRAPH = "execution_graph"
    TEST = "test"
    CI_CD_PIPELINE = "ci_cd_pipeline"
    DOCUMENTATION = "documentation"
    ASSET = "asset"
    CONFIGURATION = "configuration"
    SECRETS_METADATA = "secrets_metadata"
    ENVIRONMENT_VARIABLE = "environment_variable"
    USER_WORKFLOW = "user_workflow"
    RUNTIME_PROCESS = "runtime_process"


class RelationType(str, Enum):
    DEPENDS_ON = "depends_on"
    IMPORTS = "imports"
    IMPLEMENTS = "implements"
    USES = "uses"
    CALLS = "calls"
    CREATES = "creates"
    OWNS = "owns"
    DEPLOYS = "deploys"
    TESTS = "tests"
    DOCUMENTS = "documents"
    COMMUNICATES_WITH = "communicates_with"
    SECURES = "secures"
    REFERENCES = "references"
    EXTENDS = "extends"
    OVERRIDES = "overrides"


class ChangeType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SYNC = "sync"


class ImpactLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BaseEntity(BaseModel):
    model_config = ConfigDict(strict=False, extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EntityType
    name: str
    version: int = 1
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_system: str = "unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False

    def compute_checksum(self) -> str:
        payload = self.model_dump_json(include={"name", "type", "metadata", "version"})
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def touch(self) -> Self:
        self.updated_at = datetime.utcnow()
        self.version += 1
        self.checksum = self.compute_checksum()
        return self


class Relationship(BaseModel):
    model_config = ConfigDict(strict=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    target_id: str
    type: RelationType
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1


class ChangeEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_adapter: str
    change_type: ChangeType
    entity_type: EntityType
    entity_id: str | None = None
    entity_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    prior_checksum: str | None = None
    new_checksum: str | None = None


class StateSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    entity_count: int = 0
    relation_count: int = 0
    entities: dict[str, BaseEntity] = Field(default_factory=dict)
    relationships: dict[str, Relationship] = Field(default_factory=dict)
    version: int = 1

    @classmethod
    def from_graph(cls, entities: dict, relationships: dict, version: int = 1) -> Self:
        return cls(
            timestamp=datetime.utcnow(),
            entity_count=len(entities),
            relation_count=len(relationships),
            entities=entities,
            relationships=relationships,
            version=version,
        )


class PredictionResult(BaseModel):
    prediction_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    impact_level: ImpactLevel
    affected_entity_ids: list[str] = Field(default_factory=list)
    description: str
    recommended_action: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisReport(BaseModel):
    analysis_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    summary: str = ""


class QueryResult(BaseModel):
    query: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    execution_ms: float = 0.0
from __future__ import annotations

import asyncio
from typing import Any

import networkx as nx

from .exceptions import GraphConsistencyError
from .models import BaseEntity, EntityType, RelationType, Relationship


class GraphStore:
    """
    Thread-safe asynchronous graph backend using NetworkX.
    Abstracted so a production deployment can swap in Neo4j/RDF/ArangoDB
    without changing consumer code.
    """

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()
        self._lock = asyncio.Lock()

    async def add_entity(self, entity: BaseEntity) -> None:
        async with self._lock:
            self._graph.add_node(
                entity.id,
                __entity=entity,
                type=entity.type.value,
                name=entity.name,
                version=entity.version,
                updated_at=entity.updated_at.isoformat(),
            )

    async def get_entity(self, entity_id: str) -> BaseEntity | None:
        async with self._lock:
            data = self._graph.nodes.get(entity_id)
            return data.get("__entity") if data else None

    async def update_entity(self, entity: BaseEntity) -> None:
        async with self._lock:
            if entity.id not in self._graph:
                raise KeyError(f"Entity {entity.id} not found")
            self._graph.nodes[entity.id]["__entity"] = entity
            self._graph.nodes[entity.id]["version"] = entity.version
            self._graph.nodes[entity.id]["updated_at"] = entity.updated_at.isoformat()

    async def remove_entity(self, entity_id: str) -> None:
        async with self._lock:
            if entity_id in self._graph:
                self._graph.remove_node(entity_id)

    async def add_relationship(self, rel: Relationship) -> None:
        async with self._lock:
            if rel.source_id not in self._graph or rel.target_id not in self._graph:
                raise GraphConsistencyError("Source or target entity missing from graph")
            self._graph.add_edge(
                rel.source_id,
                rel.target_id,
                key=rel.id,
                __relation=rel,
                type=rel.type.value,
                weight=rel.weight,
            )

    async def remove_relationship(self, rel_id: str) -> None:
        async with self._lock:
            for u, v, key, data in self._graph.edges(keys=True, data=True):
                rel = data.get("__relation")
                if rel and rel.id == rel_id:
                    self._graph.remove_edge(u, v, key)
                    break

    async def get_neighbors(
        self,
        entity_id: str,
        rel_type: RelationType | None = None,
        direction: str = "both",
    ) -> list[BaseEntity]:
        async with self._lock:
            results: list[BaseEntity] = []
            if direction in ("out", "both"):
                for _, target, _, data in self._graph.out_edges(entity_id, keys=True, data=True):
                    if rel_type is None or data.get("type") == rel_type.value:
                        ent = self._graph.nodes[target].get("__entity")
                        if ent:
                            results.append(ent)
            if direction in ("in", "both"):
                for source, _, _, data in self._graph.in_edges(entity_id, keys=True, data=True):
                    if rel_type is None or data.get("type") == rel_type.value:
                        ent = self._graph.nodes[source].get("__entity")
                        if ent:
                            results.append(ent)
            return results

    async def find_by_type(self, entity_type: EntityType, limit: int = 100) -> list[BaseEntity]:
        async with self._lock:
            results = []
            for _, data in self._graph.nodes(data=True):
                if data.get("type") == entity_type.value:
                    ent = data.get("__entity")
                    if ent:
                        results.append(ent)
                    if len(results) >= limit:
                        break
            return results

    async def traverse_impact(self, entity_id: str, max_depth: int = 5) -> dict[str, int]:
        """
        BFS downstream traversal following DEPENDS_ON / USES / IMPORTS / CALLS edges.
        Returns {entity_id: depth}.
        """
        async with self._lock:
            impacted: dict[str, int] = {}
            if entity_id not in self._graph:
                return impacted

            queue = [(entity_id, 0)]
            visited = {entity_id}
            while queue:
                current, depth = queue.pop(0)
                if depth >= max_depth:
                    continue
                for _, neighbor, _, data in self._graph.out_edges(current, keys=True, data=True):
                    if neighbor in visited:
                        continue
                    rel_type = data.get("type")
                    if rel_type in {
                        RelationType.DEPENDS_ON.value,
                        RelationType.USES.value,
                        RelationType.IMPORTS.value,
                        RelationType.CALLS.value,
                    }:
                        visited.add(neighbor)
                        impacted[neighbor] = depth + 1
                        queue.append((neighbor, depth + 1))
            return impacted

    async def to_snapshot(self) -> dict[str, Any]:
        async with self._lock:
            entities = {}
            relationships = {}
            for node, data in self._graph.nodes(data=True):
                ent = data.get("__entity")
                if ent:
                    entities[node] = ent
            for u, v, _, data in self._graph.edges(keys=True, data=True):
                rel = data.get("__relation")
                if rel:
                    relationships[rel.id] = rel
            return {
                "entities": entities,
                "relationships": relationships,
                "node_count": self._graph.number_of_nodes(),
                "edge_count": self._graph.number_of_edges(),
            }

    @property
    def entity_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relation_count(self) -> int:
        return self._graph.number_of_edges()
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

import structlog

from .models import ChangeEvent

logger = structlog.get_logger()


class EventBus:
    """
    Async publish-subscribe pipeline for ChangeEvents.
    Subscribers are async callables; delivery is concurrent.
    """

    def __init__(self, maxsize: int = 10_000):
        self._queue: asyncio.Queue[ChangeEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: list[Callable[[ChangeEvent], Coroutine[Any, Any, None]]] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, handler: Callable[[ChangeEvent], Coroutine[Any, Any, None]]) -> None:
        self._subscribers.append(handler)

    async def emit(self, event: ChangeEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("event_queue_overflow", dropped_event=event.event_id)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await self._dispatch(event)
            self._queue.task_done()

    async def _dispatch(self, event: ChangeEvent) -> None:
        if not self._subscribers:
            return
        results = await asyncio.gather(
            *[self._safe_call(h, event) for h in self._subscribers],
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, Exception):
                logger.error("event_handler_failed", exception=str(exc))

    async def _safe_call(self, handler: Callable, event: ChangeEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.error("subscriber_error", handler=handler.__name__, error=str(exc))
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
 from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import structlog

logger = structlog.get_logger()


class HealthCheck(Protocol):
    name: str
    async def check(self) -> bool: ...
class HealthMonitor:
    def __init__(self):
        self.checks: list[HealthCheck] = []
        self.last_results: dict[str, tuple[bool, datetime]] = {}

    def register(self, check: HealthCheck) -> None:
        self.checks.append(check)

    async def check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        outputs = await asyncio.gather(
            *[self._run_check(c) for c in self.checks],
            return_exceptions=True,
        )
        for c, out in zip(self.checks, outputs):
            if isinstance(out, Exception):
                results[c.name] = False
                logger.warning("health_check_failed", check=c.name, error=str(out))
            else:
                results[c.name] = out
                self.last_results[c.name] = (out, datetime.utcnow())
        return results

    async def _run_check(self, check: HealthCheck) -> bool:
        try:
            return await asyncio.wait_for(check.check(), timeout=10.0)
        except asyncio.TimeoutError:
            return False
from __future__ import annotations

import asyncio
import signal

import structlog

logger = structlog.get_logger()


def setup_signal_handlers(
    shutdown_event: asyncio.Event,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    _loop = loop or asyncio.get_running_loop()

    def _handler(sig: signal.Signals):
        logger.info("signal_received", signal=sig.name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        _loop.add_signal_handler(sig, lambda s=sig: _handler(s))
from __future__ import annotations

import asyncio
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
        cmd = [self._uv_bin, "sync"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd or self.config.project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"uv sync failed: {stderr.decode()}")
        logger.info("uv_sync_complete")

    async def run(self, command: list[str], cwd: Path | None = None) -> asyncio.subprocess.Process:
        if not self._uv_bin:
            await self._auto_install()
        full_cmd = [self._uv_bin, "run", *command]
        return await asyncio.create_subprocess_exec(
            *full_cmd,
            cwd=cwd or self.config.project_root,
        )

    async def _auto_install(self) -> None:
        logger.info("attempting_uv_install")
        raise FileNotFoundError("uv not found and auto-install not yet implemented")
from __future__ import annotations

import asyncio
import platform

import structlog

logger = structlog.get_logger()


class UvInstaller:
    @staticmethod
    async def install() -> str | None:
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
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("uv_installed")
            return stdout.decode().splitlines()[-1]
        logger.error("uv_install_failed", stderr=stderr.decode())
        return None
from __future__ import annotations

import asyncio

import structlog

from .config import TwinConfig
from .health import HealthMonitor
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
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("supervisor_shutting_down")
        await self.twin.stop()
        self._shutdown_event.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("supervisor_shutdown_complete")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()
from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Add these imports here
import subprocess
import sys
import shutil

# Existing imports
from .config import TwinConfig
from .logger import configure_logging
from .supervisor import Supervisor
from .twin_engine import DigitalTwinEngine

# Add these here
PACKAGES = [
    "pydantic",
    "pydantic-settings",
    "typer",
    "structlog",
    "watchfiles",
    "gitpython",
    "networkx",
    "rich",
    "aiofiles",
]

def ensure_uv():
    ...

def ensure_dependencies():
    ...

# Existing code continues
app = typer.Typer(...)
console = Console()
state: dict = {}
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    project_root: Path = typer.Option(Path("."), "--root", "-r"),
):
    configure_logging("DEBUG" if verbose else "INFO")
    state["config"] = TwinConfig(project_root=project_root)


@app.command()
def start():
    """Start the Digital Twin Engine & Supervisor."""
    supervisor = Supervisor(state["config"])

    async def _run():
        await supervisor.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")


@app.command()
def status():
    """Report current twin graph status."""
    async def _get():
        twin = DigitalTwinEngine(state["config"])
        await twin.bootstrap()
        st = await twin.get_status()
        table = Table(title="Arctus Digital Twin Status")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        for k, v in st.items():
            table.add_row(k, str(v))
        console.print(table)

    asyncio.run(_get())


@app.command()
def query(q: str):
    """Run a structured query against the twin."""
    async def _query():
        twin = DigitalTwinEngine(state["config"])
        await twin.bootstrap()
        result = await twin.query(q)
        console.print_json(data=result)

    asyncio.run(_query())


if __name__ == "__main__":
    ensure_dependencies()
    app()
from __future__ import annotations

import hashlib
from datetime import datetime


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> datetime:
    return datetime.utcnow()


