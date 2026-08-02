"""AWS Secrets Manager integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import SecretError, ValidationError
from .metrics import AWSMetrics

class SecretsManagerClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("secretsmanager", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def get_secret(self, secret_id: str, version_stage: str = "AWSCURRENT") -> str:
        if not secret_id:
            raise ValidationError("secret_id is required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "get_secret",
                lambda: asyncio.to_thread(
                    client.get_secret_value,
                    SecretId=secret_id,
                    VersionStage=version_stage,
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.secrets.get", 1, service="secretsmanager", operation="get")
            if "SecretString" in resp:
                return str(resp["SecretString"])
            return resp["SecretBinary"].decode("utf-8")
        except Exception as exc:
            raise SecretError(f"Failed to retrieve secret {secret_id}: {exc}", cause=exc) from exc

    async def get_secret_json(self, secret_id: str, version_stage: str = "AWSCURRENT") -> Dict[str, Any]:
        raw = await self.get_secret(secret_id, version_stage)
        try:
            return json.loads(raw)
        except Exception as exc:
            raise SecretError(f"Secret {secret_id} is not valid JSON", cause=exc) from exc

    async def put_secret(self, secret_id: str, value: str, kms_key_id: Optional[str] = None) -> None:
        if not secret_id:
            raise ValidationError("secret_id is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"SecretId": secret_id, "SecretString": value}
        if kms_key_id:
            kwargs["KmsKeyId"] = kms_key_id
        try:
            await self._retry.execute(
                "put_secret",
                lambda: asyncio.to_thread(client.put_secret_value, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.secrets.put", 1, service="secretsmanager", operation="put")
        except Exception as exc:
            raise SecretError(f"Failed to store secret {secret_id}: {exc}", cause=exc) from exc

    async def create_secret(self, secret_id: str, value: str, kms_key_id: Optional[str] = None, description: Optional[str] = None) -> None:
        if not secret_id:
            raise ValidationError("secret_id is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"Name": secret_id, "SecretString": value}
        if kms_key_id:
            kwargs["KmsKeyId"] = kms_key_id
        if description:
            kwargs["Description"] = description
        try:
            await self._retry.execute(
                "create_secret",
                lambda: asyncio.to_thread(client.create_secret, **kwargs),
            )
        except Exception as exc:
            raise SecretError(f"Failed to create secret {secret_id}: {exc}", cause=exc) from exc

    async def delete_secret(self, secret_id: str, recovery_window: int = 30, force: bool = False) -> None:
        if not secret_id:
            raise ValidationError("secret_id is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"SecretId": secret_id}
        if force:
            kwargs["ForceDeleteWithoutRecovery"] = True
        else:
            kwargs["RecoveryWindowInDays"] = recovery_window
        try:
            await self._retry.execute(
                "delete_secret",
                lambda: asyncio.to_thread(client.delete_secret, **kwargs),
            )
        except Exception as exc:
            raise SecretError(f"Failed to delete secret {secret_id}: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_secrets, MaxResults=1))
            return {"status": "healthy", "service": "secretsmanager"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "secretsmanager", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
