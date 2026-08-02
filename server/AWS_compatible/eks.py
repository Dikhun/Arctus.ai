"""Amazon EKS async Kubernetes control-plane integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import EKSError, ValidationError
from .metrics import AWSMetrics

class EKSClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("eks", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def list_clusters(self) -> List[str]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "eks_list",
                lambda: asyncio.to_thread(client.list_clusters),
            )
            return list(resp.get("clusters", []))
        except Exception as exc:
            raise EKSError(f"ListClusters failed: {exc}", cause=exc) from exc

    async def describe_cluster(self, name: str) -> Dict[str, Any]:
        if not name:
            raise ValidationError("name is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "eks_desc",
                lambda: asyncio.to_thread(client.describe_cluster, name=name),
            )
            return dict(resp.get("cluster", {}))
        except Exception as exc:
            raise EKSError(f"DescribeCluster failed: {exc}", cause=exc) from exc

    async def list_nodegroups(self, cluster_name: str) -> List[str]:
        if not cluster_name:
            raise ValidationError("cluster_name is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "eks_ng",
                lambda: asyncio.to_thread(client.list_nodegroups, clusterName=cluster_name),
            )
            return list(resp.get("nodegroups", []))
        except Exception as exc:
            raise EKSError(f"ListNodegroups failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_clusters, maxResults=1))
            return {"status": "healthy", "service": "eks"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "eks", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
