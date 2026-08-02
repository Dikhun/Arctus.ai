"""AWS Systems Manager Parameter Store integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import ParameterStoreError, ValidationError
from .metrics import AWSMetrics

class ParameterStoreClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("ssm", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def get_parameter(self, name: str, with_decryption: bool = True) -> str:
        if not name:
            raise ValidationError("name is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "get_parameter",
                lambda: asyncio.to_thread(
                    client.get_parameter,
                    Name=name,
                    WithDecryption=with_decryption,
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.ssm.get", 1, service="ssm", operation="get_parameter")
            return str(resp["Parameter"]["Value"])
        except Exception as exc:
            raise ParameterStoreError(f"Failed to get parameter {name}: {exc}", cause=exc) from exc

    async def get_parameters(self, names: List[str], with_decryption: bool = True) -> Dict[str, str]:
        if not names:
            return {}
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "get_parameters",
                lambda: asyncio.to_thread(
                    client.get_parameters,
                    Names=names,
                    WithDecryption=with_decryption,
                ),
            )
            result: Dict[str, str] = {}
            for p in resp.get("Parameters", []):
                result[p["Name"]] = p["Value"]
            return result
        except Exception as exc:
            raise ParameterStoreError(f"Failed to get parameters: {exc}", cause=exc) from exc

    async def put_parameter(
        self,
        name: str,
        value: str,
        param_type: str = "SecureString",
        kms_key_id: Optional[str] = None,
        overwrite: bool = True,
    ) -> None:
        if not name:
            raise ValidationError("name is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "Name": name,
            "Value": value,
            "Type": param_type,
            "Overwrite": overwrite,
        }
        if kms_key_id:
            kwargs["KeyId"] = kms_key_id
        try:
            await self._retry.execute(
                "put_parameter",
                lambda: asyncio.to_thread(client.put_parameter, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.ssm.put", 1, service="ssm", operation="put_parameter")
        except Exception as exc:
            raise ParameterStoreError(f"Failed to put parameter {name}: {exc}", cause=exc) from exc

    async def delete_parameter(self, name: str) -> None:
        if not name:
            raise ValidationError("name is required")
        client = await self._client()
        try:
            await self._retry.execute(
                "delete_parameter",
                lambda: asyncio.to_thread(client.delete_parameter, Name=name),
            )
        except Exception as exc:
            raise ParameterStoreError(f"Failed to delete parameter {name}: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.describe_parameters, MaxResults=1))
            return {"status": "healthy", "service": "ssm"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "ssm", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
