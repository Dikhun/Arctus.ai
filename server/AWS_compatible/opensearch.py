"""Amazon OpenSearch Service async control-plane integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import OpenSearchError, ValidationError
from .metrics import AWSMetrics

class OpenSearchClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("opensearch", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def list_domain_names(self) -> List[Dict[str, Any]]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "os_list",
                lambda: asyncio.to_thread(client.list_domain_names),
            )
            return list(resp.get("DomainNames", []))
        except Exception as exc:
            raise OpenSearchError(f"ListDomainNames failed: {exc}", cause=exc) from exc

    async def describe_domain(self, domain_name: str) -> Dict[str, Any]:
        if not domain_name:
            raise ValidationError("domain_name is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "os_desc",
                lambda: asyncio.to_thread(client.describe_domain, DomainName=domain_name),
            )
            return dict(resp.get("DomainStatus", {}))
        except Exception as exc:
            raise OpenSearchError(f"DescribeDomain failed: {exc}", cause=exc) from exc

    async def create_domain(
        self,
        domain_name: str,
        engine_version: str,
        cluster_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not domain_name:
            raise ValidationError("domain_name is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "DomainName": domain_name,
            "EngineVersion": engine_version,
        }
        if cluster_config:
            kwargs["ClusterConfig"] = cluster_config
        try:
            resp = await self._retry.execute(
                "os_create",
                lambda: asyncio.to_thread(client.create_domain, **kwargs),
            )
            return dict(resp)
        except Exception as exc:
            raise OpenSearchError(f"CreateDomain failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_domain_names))
            return {"status": "healthy", "service": "opensearch"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "opensearch", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
