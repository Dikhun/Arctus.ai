"""Amazon ECS async container orchestration integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import ECSError, ValidationError
from .metrics import AWSMetrics

class ECSClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("ecs", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def list_clusters(self) -> List[str]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "ecs_clusters",
                lambda: asyncio.to_thread(client.list_clusters),
            )
            return list(resp.get("clusterArns", []))
        except Exception as exc:
            raise ECSError(f"ListClusters failed: {exc}", cause=exc) from exc

    async def describe_services(self, cluster: str, services: List[str]) -> List[Dict[str, Any]]:
        if not cluster or not services:
            raise ValidationError("cluster and services are required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "ecs_desc",
                lambda: asyncio.to_thread(
                    client.describe_services,
                    cluster=cluster,
                    services=services,
                ),
            )
            return list(resp.get("services", []))
        except Exception as exc:
            raise ECSError(f"DescribeServices failed: {exc}", cause=exc) from exc

    async def run_task(
        self,
        cluster: str,
        task_definition: str,
        launch_type: str = "FARGATE",
        network_configuration: Optional[Dict[str, Any]] = None,
        count: int = 1,
    ) -> List[Dict[str, Any]]:
        if not cluster or not task_definition:
            raise ValidationError("cluster and task_definition are required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "cluster": cluster,
            "taskDefinition": task_definition,
            "launchType": launch_type,
            "count": count,
        }
        if network_configuration:
            kwargs["networkConfiguration"] = network_configuration
        try:
            resp = await self._retry.execute(
                "ecs_run",
                lambda: asyncio.to_thread(client.run_task, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.ecs.run_task", count, service="ecs", operation="run_task")
            return list(resp.get("tasks", []))
        except Exception as exc:
            raise ECSError(f"RunTask failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_clusters, maxResults=1))
            return {"status": "healthy", "service": "ecs"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "ecs", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
