"""AWS SNS async notification integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import SNSError, ValidationError
from .metrics import AWSMetrics

class SNSClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("sns", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def publish(self, topic_arn: str, message: str, subject: Optional[str] = None) -> str:
        if not topic_arn:
            raise ValidationError("topic_arn is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"TopicArn": topic_arn, "Message": message}
        if subject:
            kwargs["Subject"] = subject
        try:
            resp = await self._retry.execute(
                "sns_publish",
                lambda: asyncio.to_thread(client.publish, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.sns.publish", 1, service="sns", operation="publish")
            return str(resp["MessageId"])
        except Exception as exc:
            raise SNSError(f"SNS publish failed: {exc}", cause=exc) from exc

    async def publish_json(self, topic_arn: str, payload: Dict[str, Any], subject: Optional[str] = None) -> str:
        return await self.publish(topic_arn, json.dumps(payload), subject)

    async def publish_to_phone(self, phone_number: str, message: str) -> str:
        if not phone_number:
            raise ValidationError("phone_number is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "sns_sms",
                lambda: asyncio.to_thread(client.publish, PhoneNumber=phone_number, Message=message),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.sns.sms", 1, service="sns", operation="sms")
            return str(resp["MessageId"])
        except Exception as exc:
            raise SNSError(f"SNS SMS failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_topics))
            return {"status": "healthy", "service": "sns"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "sns", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
