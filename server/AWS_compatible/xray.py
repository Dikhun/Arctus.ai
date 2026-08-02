"""AWS X-Ray trace and telemetry integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import ValidationError, XRayError
from .metrics import AWSMetrics

class XRayClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("xray", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def put_trace_segments(self, trace_segment_documents: List[str]) -> Dict[str, Any]:
        if not trace_segment_documents:
            raise ValidationError("trace_segment_documents are required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "xray_put",
                lambda: asyncio.to_thread(
                    client.put_trace_segments,
                    TraceSegmentDocuments=trace_segment_documents,
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.xray.put", len(trace_segment_documents), service="xray", operation="put_trace_segments")
            return dict(resp)
        except Exception as exc:
            raise XRayError(f"PutTraceSegments failed: {exc}", cause=exc) from exc

    async def put_telemetry_records(self, telemetry_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not telemetry_records:
            raise ValidationError("telemetry_records are required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "xray_telemetry",
                lambda: asyncio.to_thread(
                    client.put_telemetry_records,
                    TelemetryRecords=telemetry_records,
                ),
            )
            return dict(resp)
        except Exception as exc:
            raise XRayError(f"PutTelemetryRecords failed: {exc}", cause=exc) from exc

    async def get_service_graph(self, start_time: str, end_time: str) -> Dict[str, Any]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "xray_graph",
                lambda: asyncio.to_thread(
                    client.get_service_graph,
                    StartTime=start_time,
                    EndTime=end_time,
                ),
            )
            return dict(resp)
        except Exception as exc:
            raise XRayError(f"GetServiceGraph failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.get_encryption_config))
            return {"status": "healthy", "service": "xray"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "xray", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
