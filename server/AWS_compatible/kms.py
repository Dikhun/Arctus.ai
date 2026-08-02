"""AWS KMS encryption/decryption integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import KMSError, ValidationError
from .metrics import AWSMetrics

class KMSClient:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("kms", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def encrypt(self, key_id: str, plaintext: bytes, encryption_context: Optional[Dict[str, str]] = None) -> bytes:
        if not key_id or not plaintext:
            raise ValidationError("key_id and plaintext are required", details={"operation": "encrypt"})
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "kms_encrypt",
                lambda: asyncio.to_thread(
                    client.encrypt,
                    KeyId=key_id,
                    Plaintext=plaintext,
                    EncryptionContext=encryption_context or {},
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.kms.encrypt", 1, service="kms", operation="encrypt")
            return resp["CiphertextBlob"]
        except Exception as exc:
            raise KMSError(f"Encrypt failed: {exc}", cause=exc) from exc

    async def decrypt(self, ciphertext: bytes, encryption_context: Optional[Dict[str, str]] = None) -> bytes:
        if not ciphertext:
            raise ValidationError("ciphertext is required", details={"operation": "decrypt"})
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "kms_decrypt",
                lambda: asyncio.to_thread(
                    client.decrypt,
                    CiphertextBlob=ciphertext,
                    EncryptionContext=encryption_context or {},
                ),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.kms.decrypt", 1, service="kms", operation="decrypt")
            return resp["Plaintext"]
        except Exception as exc:
            raise KMSError(f"Decrypt failed: {exc}", cause=exc) from exc

    async def generate_data_key(self, key_id: str, key_spec: str = "AES_256") -> Dict[str, bytes]:
        if not key_id:
            raise ValidationError("key_id is required", details={"operation": "generate_data_key"})
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "generate_data_key",
                lambda: asyncio.to_thread(client.generate_data_key, KeyId=key_id, KeySpec=key_spec),
            )
            return {"Plaintext": resp["Plaintext"], "CiphertextBlob": resp["CiphertextBlob"]}
        except Exception as exc:
            raise KMSError(f"GenerateDataKey failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_aliases, Limit=1))
            return {"status": "healthy", "service": "kms"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "kms", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
