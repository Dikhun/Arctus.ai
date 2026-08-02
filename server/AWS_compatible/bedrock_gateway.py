"""Amazon Bedrock async model-gateway integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import BedrockError, ValidationError
from .metrics import AWSMetrics

class BedrockGateway:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("bedrock-runtime", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def invoke_model(
        self,
        model_id: str,
        body: Dict[str, Any],
        content_type: str = "application/json",
        accept: str = "application/json",
    ) -> Dict[str, Any]:
        if not model_id:
            raise ValidationError("model_id is required")
        client = await self._client()
        try:
            payload = json.dumps(body).encode("utf-8")
            resp = await self._retry.execute(
                "bedrock_invoke",
                lambda: asyncio.to_thread(
                    client.invoke_model,
                    modelId=model_id,
                    body=payload,
                    contentType=content_type,
                    accept=accept,
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.bedrock.invoke", 1, service="bedrock", operation="invoke")
            raw = await asyncio.to_thread(resp["body"].read)
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise BedrockError(f"InvokeModel failed for {model_id}: {exc}", cause=exc) from exc

    async def converse(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        system: Optional[List[Dict[str, Any]]] = None,
        inference_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not model_id or not messages:
            raise ValidationError("model_id and messages are required")
        client = await self._client()
        payload: Dict[str, Any] = {
            "modelId": model_id,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if inference_config:
            payload["inferenceConfig"] = inference_config
        try:
            resp = await self._retry.execute(
                "bedrock_converse",
                lambda: asyncio.to_thread(client.converse, **payload),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.bedrock.converse", 1, service="bedrock", operation="converse")
            return dict(resp)
        except Exception as exc:
            raise BedrockError(f"Converse failed for {model_id}: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute(
                "health",
                lambda: asyncio.to_thread(client.list_foundation_models, maxResults=1),
            )
            return {"status": "healthy", "service": "bedrock"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "bedrock", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
