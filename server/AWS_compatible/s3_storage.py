"""AWS S3 asynchronous object storage integration."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import S3Error, ValidationError
from .metrics import AWSMetrics

class S3Storage:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("s3", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def upload(
        self,
        bucket: str,
        key: str,
        body: bytes,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        if not bucket or not key:
            raise ValidationError("bucket and key are required", details={"operation": "upload"})
        client = await self._client()
        extra: Dict[str, Any] = {}
        if metadata:
            extra["Metadata"] = metadata
        try:
            await self._retry.execute(
                "s3_put",
                lambda: asyncio.to_thread(client.put_object, Bucket=bucket, Key=key, Body=body, **extra),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.s3.put", 1, service="s3", operation="put")
        except Exception as exc:
            raise S3Error(f"S3 upload failed for s3://{bucket}/{key}: {exc}", cause=exc) from exc

    async def download(self, bucket: str, key: str) -> bytes:
        if not bucket or not key:
            raise ValidationError("bucket and key are required", details={"operation": "download"})
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "s3_get",
                lambda: asyncio.to_thread(client.get_object, Bucket=bucket, Key=key),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.s3.get", 1, service="s3", operation="get")
            return await asyncio.to_thread(resp["Body"].read)
        except Exception as exc:
            raise S3Error(f"S3 download failed for s3://{bucket}/{key}: {exc}", cause=exc) from exc

    async def stream_download(
        self,
        bucket: str,
        key: str,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        if not bucket or not key:
            raise ValidationError("bucket and key are required", details={"operation": "stream_download"})
        client = await self._client()
        resp = await self._retry.execute(
 "s3_stream",
            lambda: asyncio.to_thread(client.get_object, Bucket=bucket, Key=key),
        )
        body = resp["Body"]
        while True:
            chunk = await asyncio.to_thread(body.read, chunk_size)
            if not chunk:
                break
            yield chunk

    async def delete(self, bucket: str, key: str) -> None:
        if not bucket or not key:
            raise ValidationError("bucket and key are required", details={"operation": "delete"})
        client = await self._client()
        try:
            await self._retry.execute(
                "s3_delete",
                lambda: asyncio.to_thread(client.delete_object, Bucket=bucket, Key=key),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.s3.delete", 1, service="s3", operation="delete")
        except Exception as exc:
            raise S3Error(f"S3 delete failed for s3://{bucket}/{key}: {exc}", cause=exc) from exc

    async def list_objects(self, bucket: str, prefix: Optional[str] = None, max_keys: int = 1000) -> List[Dict[str, Any]]:
        if not bucket:
            raise ValidationError("bucket is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"Bucket": bucket, "MaxKeys": max_keys}
        if prefix:
            kwargs["Prefix"] = prefix
        try:
            resp = await self._retry.execute(
                "s3_list",
                lambda: asyncio.to_thread(client.list_objects_v2, **kwargs),
            )
            return list(resp.get("Contents", []))
        except Exception as exc:
            raise S3Error(f"S3 list failed for {bucket}: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_buckets))
            return {"status": "healthy", "service": "s3"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "s3", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
