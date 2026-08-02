"""Amazon Neptune async cluster management and endpoint resolution."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import NeptuneError, ValidationError
from .metrics import AWSMetrics

class NeptuneGraphClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("neptune", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def list_db_clusters(self) -> List[Dict[str, Any]]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "neptune_list",
                lambda: asyncio.to_thread(client.describe_db_clusters, MaxRecords=100),
            )
            return list(resp.get("DBClusters", []))
        except Exception as exc:
            raise NeptuneError(f"DescribeDBClusters failed: {exc}", cause=exc) from exc

    async def describe_db_cluster(self, db_cluster_identifier: str) -> Dict[str, Any]:
        if not db_cluster_identifier:
            raise ValidationError("db_cluster_identifier is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "neptune_desc",
                lambda: asyncio.to_thread(
                    client.describe_db_clusters,
                    DBClusterIdentifier=db_cluster_identifier,
                ),
            )
            clusters = resp.get("DBClusters", [])
            if not clusters:
                raise NeptuneError(f"Cluster {db_cluster_identifier} not found", code="NOT_FOUND")
            return dict(clusters[0])
        except Exception as exc:
            raise NeptuneError(f"DescribeDBClusters failed: {exc}", cause=exc) from exc

    async def get_cluster_endpoint(self, db_cluster_identifier: str) -> Dict[str, str]:
        cluster = await self.describe_db_cluster(db_cluster_identifier)
        return {
            "writer": cluster.get("Endpoint", ""),
            "reader": cluster.get("ReaderEndpoint", ""),
        }

    async def is_cluster_available(self, db_cluster_identifier: str) -> bool:
        cluster = await self.describe_db_cluster(db_cluster_identifier)
        return cluster.get("Status") == "available"

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute(
                "health",
                lambda: asyncio.to_thread(client.describe_db_clusters, MaxRecords=1),
            )
            return {"status": "healthy", "service": "neptune"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "neptune", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
