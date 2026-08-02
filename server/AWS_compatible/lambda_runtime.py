"""AWS Lambda async invocation integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import LambdaError, ValidationError
from .metrics import AWSMetrics

class LambdaRuntime:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("lambda", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def invoke(
        self,
        function_name: str,
        payload: Optional[Dict[str, Any]] = None,
        invocation_type: str = "RequestResponse",
    ) -> Dict[str, Any]:
        if not function_name:
            raise ValidationError("function_name is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "FunctionName": function_name,
            "InvocationType": invocation_type,
        }
        if payload is not None:
            kwargs["Payload"] = json.dumps(payload).encode("utf-8")
        try:
            resp = await self._retry.execute(
                "lambda_invoke",
                lambda: asyncio.to_thread(client.invoke, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.lambda.invoke", 1, service="lambda", operation="invoke")
            result: Dict[str, Any] = {
                "StatusCode": resp.get("StatusCode"),
                "LogResult": resp.get("LogResult"),
            }
            if "Payload" in resp:
                body = await asyncio.to_thread(resp["Payload"].read)
                try:
                    result["Payload"] = json.loads(body.decode("utf-8"))
                except Exception:
                    result["Payload"] = body.decode("utf-8")
            return result
        except Exception as exc:
            raise LambdaError(f"Invoke failed for {function_name}: {exc}", cause=exc) from exc

    async def get_function(self, function_name: str) -> Dict[str, Any]:
        if not function_name:
            raise ValidationError("function_name is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "lambda_get",
                lambda: asyncio.to_thread(client.get_function, FunctionName=function_name),
            )
            return dict(resp.get("Configuration", {}))
        except Exception as exc:
            raise LambdaError(f"GetFunction failed for {function_name}: {exc}", cause=exc) from exc

    async def list_functions(self, limit: int = 50) -> List[Dict[str, Any]]:
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "lambda_list",
                lambda: asyncio.to_thread(client.list_functions, MaxItems=limit),
            )
            return list(resp.get("Functions", []))
        except Exception as exc:
            raise LambdaError(f"ListFunctions failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_functions, MaxItems=1))
            return {"status": "healthy", "service": "lambda"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "lambda", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
