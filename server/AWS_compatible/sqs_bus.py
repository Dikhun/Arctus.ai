"""AWS SQS async messaging bus integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import SQSError, ValidationError
from .metrics import AWSMetrics

class SQSBus:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("sqs", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def send_message(
        self,
        queue_url: str,
        body: str,
        message_group_id: Optional[str] = None,
    ) -> str:
        if not queue_url:
            raise ValidationError("queue_url is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"QueueUrl": queue_url, "MessageBody": body}
        if message_group_id:
            kwargs["MessageGroupId"] = message_group_id
        try:
            resp = await self._retry.execute(
                "sqs_send",
                lambda: asyncio.to_thread(client.send_message, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.sqs.send", 1, service="sqs", operation="send")
            return str(resp["MessageId"])
        except Exception as exc:
            raise SQSError(f"SQS send failed: {exc}", cause=exc) from exc

    async def send_json(self, queue_url: str, payload: Dict[str, Any], message_group_id: Optional[str] = None) -> str:
        return await self.send_message(queue_url, json.dumps(payload), message_group_id)

    async def receive_messages(
        self,
        queue_url: str,
        max_messages: int = 10,
        wait_time: int = 5,
        visibility_timeout: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not queue_url:
            raise ValidationError("queue_url is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "QueueUrl": queue_url,
            "MaxNumberOfMessages": max_messages,
            "WaitTimeSeconds": wait_time,
        }
        if visibility_timeout is not None:
            kwargs["VisibilityTimeout"] = visibility_timeout
        try:
            resp = await self._retry.execute(
                "sqs_receive",
                lambda: asyncio.to_thread(client.receive_message, **kwargs),
            )
            msgs = resp.get("Messages", [])
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.sqs.receive", len(msgs), service="sqs", operation="receive")
            return list(msgs)
        except Exception as exc:
            raise SQSError(f"SQS receive failed: {exc}", cause=exc) from exc

    async def delete_message(self, queue_url: str, receipt_handle: str) -> None:
        if not queue_url or not receipt_handle:
            raise ValidationError("queue_url and receipt_handle are required")
        client = await self._client()
        try:
            await self._retry.execute(
                "sqs_del",
                lambda: asyncio.to_thread(
                    client.delete_message,
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                ),
            )
        except Exception as exc:
            raise SQSError(f"SQS delete failed: {exc}", cause=exc) from exc

    async def get_queue_url(self, queue_name: str) -> str:
        client = await self._client()
        resp = await self._retry.execute(
            "sqs_url",
            lambda: asyncio.to_thread(client.get_queue_url, QueueName=queue_name),
        )
        return str(resp["QueueUrl"])

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_queues))
            return {"status": "healthy", "service": "sqs"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "sqs", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
