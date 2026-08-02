# arctus_research_engine/interfaces.py
"""Contracts for orchestration framework capabilities injected at runtime."""

from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)
from contextlib import AbstractAsyncContextManager
import enum


class IEventBus(Protocol):
    """Framework-managed event transport. Exactly-once semantics provided by framework."""

    async def consume(
        self,
        topic: str,
        handler: Callable[[Dict[str, Any], str], Awaitable[None]],
    ) -> None:
        """Begin consuming messages from a topic. handler(payload, delivery_tag)."""
        ...

    async def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        ordering_key: Optional[str] = None,
    ) -> None:
        ...

    async def ack(self, delivery_tag: str) -> None:
        ...

    async def nack(self, delivery_tag: str, requeue: bool = False) -> None:
        ...
class IPersistentMemory(Protocol):
    """Key-value working storage for checkpoints and intermediate artifacts."""

    async def get(self, key: str) -> Optional[bytes]:
        ...

    async def set(self, key: str, value: bytes, ttl_seconds: Optional[int] = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...
class ISecretResolver(Protocol):
    """Secrets, credentials, and signing material owned by framework."""

    async def resolve(self, secret_id: str) -> str:
        ...
class ITelemetry(Protocol):
    """Distributed tracing and metrics provided by framework."""

    def start_span(self, name: str, context: Optional[Dict[str, Any]] = None) -> AbstractAsyncContextManager[Any]:
        ...

    async def log(self, level: str, message: str, fields: Optional[Dict[str, Any]] = None) -> None:
        ...

    async def increment_counter(self, metric_name: str, tags: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        ...
class IModelGateway(Protocol):
    """LLM and embedding inference endpoints provisioned by framework."""

    async def complete(
        self,
        prompt: str,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> str:
        ...

    async def embed(self, texts: List[str], model_id: str) -> List[List[float]]:
        ...
class IPluginLoader(Protocol):
    """Framework plugin registry. All plugins are pre-installed and catalogued."""

    async def list_plugins(self, plugin_type: Optional[str] = None) -> List["PluginManifest"]:
        ...

    async def load(self, plugin_name: str) -> Any:
        ...

    async def health(self, plugin_name: str) -> "HealthStatus":
        ...
class IAgentMesh(Protocol):
    """Inter-agent communication bus for partitioned collaborative research."""

    async def send(self, target_agent_id: str, message: Dict[str, Any]) -> None:
        ...

    async def broadcast(self, channel: str, message: Dict[str, Any]) -> None:
        ...

    async def declare_capability(self, capability: str, metadata: Dict[str, Any]) -> None:
        ...


class ILockProvider(Protocol):
    """Distributed locking for shared knowledge graph mutations."""

    async def acquire(self, lock_key: str, ttl_seconds: int = 30) -> AbstractAsyncContextManager[bool]:
        ...
class IKnowledgeGraph(Protocol):
    """Graph storage interface; lifecycle managed by framework."""

    async def query(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        ...

    async def merge_node(self, label: str, properties: Dict[str, Any]) -> str:
        ...

    async def merge_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...
class IHttpClient(Protocol):
    """Authenticated, proxied, and traced HTTP client provided by framework."""

    async def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> "HttpResponse":
        ...

    async def post(self, url: str, body: bytes, headers: Optional[Dict[str, str]] = None) -> "HttpResponse":
        ...
class HttpResponse:
    status: int
    body: bytes
    headers: Dict[str, str]


class PluginManifest:
    name: str
    version: str
    plugin_type: str
    entry_point: str


class HealthStatus(enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ExecutionMode(enum.Enum):
    STANDARD = "standard"
    DETERMINISTIC = "deterministic"
