"""Amazon CloudWatch direct metric and alarm integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import CloudWatchError, ValidationError
from .metrics import AWSMetrics

class CloudWatchClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("cloudwatch", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def put_metric_data(self, namespace: str, metric_data: List[Dict[str, Any]]) -> None:
        if not namespace or not metric_data:
            raise ValidationError("namespace and metric_data are required")
        client = await self._client()
        try:
            await self._retry.execute(
                "cw_put",
                lambda: asyncio.to_thread(
                    client.put_metric_data,
                    Namespace=namespace,
                    MetricData=metric_data,
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.cloudwatch.put", len(metric_data), service="cloudwatch", operation="put_metric_data")
        except Exception as exc:
            raise CloudWatchError(f"PutMetricData failed: {exc}", cause=exc) from exc

    async def put_alarm(
        self,
        alarm_name: str,
        metric_name: str,
        namespace: str,
        threshold: float,
        comparison: str = "GreaterThanThreshold",
        evaluation_periods: int = 1,
    ) -> None:
        if not alarm_name or not metric_name or not namespace:
            raise ValidationError("alarm_name, metric_name, namespace are required")
        client = await self._client()
        try:
            await self._retry.execute(
                "cw_alarm",
                lambda: asyncio.to_thread(
                    client.put_metric_alarm,
                    AlarmName=alarm_name,
                    MetricName=metric_name,
                    Namespace=namespace,
                    Threshold=threshold,
                    ComparisonOperator=comparison,
                    EvaluationPeriods=evaluation_periods,
                    Statistic="Average",
                ),
            )
        except Exception as exc:
            raise CloudWatchError(f"PutAlarm failed: {exc}", cause=exc) from exc

    async def get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        start_time: str,
        end_time: str,
        period: int = 60,
        statistics: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not namespace or not metric_name:
            raise ValidationError("namespace and metric_name are required")
        client = await self._client()
        stats = statistics or ["Average"]
        try:
            resp = await self._retry.execute(
                "cw_stats",
                lambda: asyncio.to_thread(
                    client.get_metric_statistics,
                    Namespace=namespace,
                    MetricName=metric_name,
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=stats,
                ),
            )
            return list(resp.get("Datapoints", []))
        except Exception as exc:
            raise CloudWatchError(f"GetMetricStatistics failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_metrics, Limit=1))
            return {"status": "healthy", "service": "cloudwatch"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "cloudwatch", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
