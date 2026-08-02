"""Arctus AWS Integration Package.

Enterprise-grade AWS integrations for the Arctus Agent Orchestration Framework.
This package exposes framework-compatible protocols and core exception types.
It does not perform side-effects on import and remains safe for framework-owned
lifecycle management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__version__ = "1.0.0"
__all__ = [
    # Version
    "__version__",
    # Framework-facing contracts (injected by Arctus runtime)
    "IEventBus",
    "IPersistentMemory",
    "ISecretResolver",
    "ITelemetry",
    "IModelGateway",
    "IPluginLoader",
    "IAgentMesh",
    "ILockProvider",
    "IKnowledgeGraph",
    "IHttpClient",
    # Base exceptions
    "ArctusAWSException",
    "ConfigurationError",
    "AuthenticationError",
    "AuthorizationError",
    "CredentialError",
    "TokenRefreshError",
    "ServiceError",
    "AWSServiceError",
    "AWSConnectionError",
    "AWSTimeoutError",
    "CircuitBreakerOpenError",
    "ValidationError",
    "KMSError",
    "SecretError",
    "ParameterStoreError",
    "S3Error",
    "DynamoDBError",
    "SQSError",
    "SNSError",
    "EventBridgeError",
    "CloudWatchError",
    "XRayError",
    "LambdaError",
    "ECSError",
    "EKSError",
    "BedrockError",
    "OpenSearchError",
    "NeptuneError",
]


# -----------------------------------------------------------------------------
# Framework Protocol Contracts
# -----------------------------------------------------------------------------
# The Arctus runtime injects implementations of these protocols.
# Defining them here avoids circular imports and provides discoverable
# static types for every submodule without leaking implementation detail.
# -----------------------------------------------------------------------------


@runtime_checkable
class IEventBus(Protocol):
    """Asynchronous event distribution contract."""

    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Emit an event to the bus."""

    async def subscribe(
        self,
        event_type: str,
        handler: Any,
    ) -> Any:
        """Register a handler and return a subscription token."""


@runtime_checkable
class IPersistentMemory(Protocol):
    """Key-value persistent store exposed by the framework."""

    async def get(self, key: str) -> Optional[Any]: ...

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: Optional[int] = None,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...
@runtime_checkable
class ISecretResolver(Protocol):
    """Framework-level secret resolution (Vault, SSM, etc.)."""

    async def resolve(self, secret_id: str) -> str: ...

    async def resolve_json(self, secret_id: str) -> Dict[str, Any]: ...


@runtime_checkable
class ITelemetry(Protocol):
    """Metrics, logging, and distributed-tracing façade."""

    async def emit_counter(
        self,
        name: str,
        value: int,
        *,
        tags: Optional[Dict[str, str]] = None,
    ) -> None: ...

    async def emit_gauge(
        self,
        name: str,
        value: float,
        *,
        tags: Optional[Dict[str, str]] = None,
    ) -> None: ...

    async def emit_histogram(
        self,
        name: str,
        value: float,
        *,
        tags: Optional[Dict[str, str]] = None,
    ) -> None: ...

    async def emit_trace_span(
        self,
        name: str,
        context: Dict[str, Any],
    ) -> None: ...

    async def log(
        self,
        level: str,
        message: str,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None: ...
@runtime_checkable
class IModelGateway(Protocol):
    """Abstraction over LLM / model inference runtimes."""

    async def invoke(
        self,
        model_id: str,
        prompt: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    async def embed(
        self,
        model_id: str,
        texts: List[str],
    ) -> List[List[float]]: ...
@runtime_checkable
class IPluginLoader(Protocol):
    """Framework plugin management contract."""

    async def load(self, plugin_id: str) -> Any: ...

    async def unload(self, plugin_id: str) -> None: ...

    async def health(self, plugin_id: str) -> Dict[str, Any]: ...
@runtime_checkable
class IAgentMesh(Protocol):
    """Inter-agent communication mesh."""

    async def dispatch(
        self,
        agent_id: str,
        message: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]: ...

    async def broadcast(
        self,
        channel: str,
        message: Dict[str, Any],
    ) -> None: ...


@runtime_checkable
class ILockProvider(Protocol):
    """Distributed locking contract."""

    async def acquire(
        self,
        resource: str,
        *,
        ttl: int = 30,
        blocking: bool = False,
        timeout: Optional[float] = None,
    ) -> bool: ...

    async def release(self, resource: str) -> None: ...

    async def renew(self, resource: str, *, ttl: int = 30) -> bool: ...
@runtime_checkable
class IKnowledgeGraph(Protocol):
    """Graph query interface (Cypher/Gremlin dialect agnostic)."""

    async def query(
        self,
        query: str,
        *,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]: ...

    async def mutate(
        self,
        statement: str,
        *,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...


@runtime_checkable
class IHttpClient(Protocol):
    """Typed async HTTP façade."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> Any: ...

    async def get(self, url: str, **kwargs: Any) -> Any: ...

    async def post(self, url: str, **kwargs: Any) -> Any: ...

    async def put(self, url: str, **kwargs: Any) -> Any: ...

    async def delete(self, url: str, **kwargs: Any) -> Any: ...
# -----------------------------------------------------------------------------
# Convenience re-exports (safe because exceptions has no intra-package deps)
# -----------------------------------------------------------------------------
from .exceptions import (
    ArctusAWSException,
    AuthenticationError,
    AuthorizationError,
    AWSConnectionError,
    AWSServiceError,
    AWSTimeoutError,
    BedrockError,
    CircuitBreakerOpenError,
    CloudWatchError,
    ConfigurationError,
    CredentialError,
    DynamoDBError,
    ECSError,
    EKSError,
    EventBridgeError,
    KMSError,
    LambdaError,
    NeptuneError,
    OpenSearchError,
    ParameterStoreError,
    S3Error,
    SecretError,
    ServiceError,
    SNSError,
    SQSError,
    TokenRefreshError,
    ValidationError,
    XRayError,
)
