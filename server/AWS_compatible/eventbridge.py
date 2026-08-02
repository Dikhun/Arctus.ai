"""Amazon EventBridge async event-bus integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import EventBridgeError, ValidationError
from .metrics import AWSMetrics

class EventBridgeClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("events", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def put_events(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not entries:
            raise ValidationError("entries are required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "eb_put",
                lambda: asyncio.to_thread(client.put_events, Entries=entries),
            )
            failed = resp.get("FailedEntryCount", 0)
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.events.put", len(entries), service="events", operation="put_events")
                if failed:
                    await self._metrics.record_counter("arctus.aws.events.failed", failed, service="events", operation="put_events")
            return dict(resp)
        except Exception as exc:
            raise EventBridgeError(f"PutEvents failed: {exc}", cause=exc) from exc

    async def put_custom_event(
        self,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
        event_bus_name: Optional[str] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "Source": source,
            "DetailType": detail_type,
            "Detail": json.dumps(detail),
        }
        if event_bus_name:
            entry["EventBusName"] = event_bus_name
        await self.put_events([entry])

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_event_buses, Limit=1))
            return {"status": "healthy", "service": "events"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "events", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
