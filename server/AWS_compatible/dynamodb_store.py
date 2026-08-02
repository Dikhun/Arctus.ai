"""AWS DynamoDB async document store integration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from ._core import AsyncBoto3Client, RetryController
from .exceptions import DynamoDBError, ValidationError
from .metrics import AWSMetrics

class DynamoDBStore:
    __slots__ = ("_holder", "_retry", "_metrics")

    def __init__(
        self,
        config_provider: ConfigProvider,
        credentials_provider: Optional[CredentialsProvider] = None,
        metrics: Optional[AWSMetrics] = None,
    ) -> None:
        self._holder = AsyncBoto3Client("dynamodb", config_provider, credentials_provider)
        self._retry = RetryController(config_provider.current().retry)
        self._metrics = metrics

    async def _client(self) -> Any:
        return await self._holder.get()

    async def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not table_name or not key:
            raise ValidationError("table_name and key are required")
        client = await self._client()
        try:
            resp = await self._retry.execute(
                "ddb_get",
                lambda: asyncio.to_thread(client.get_item, TableName=table_name, Key=key),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.get", 1, service="dynamodb", operation="get_item")
            return resp.get("Item")
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB get_item failed: {exc}", cause=exc) from exc

    async def put_item(
        self,
        table_name: str,
        item: Dict[str, Any],
        condition: Optional[str] = None,
    ) -> None:
        if not table_name or not item:
            raise ValidationError("table_name and item are required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"TableName": table_name, "Item": item}
        if condition:
            kwargs["ConditionExpression"] = condition
        try:
            await self._retry.execute(
                "ddb_put",
                lambda: asyncio.to_thread(client.put_item, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.put", 1, service="dynamodb", operation="put_item")
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB put_item failed: {exc}", cause=exc) from exc

    async def delete_item(self, table_name: str, key: Dict[str, Any]) -> None:
        if not table_name or not key:
            raise ValidationError("table_name and key are required")
        client = await self._client()
        try:
            await self._retry.execute(
                "ddb_delete",
                lambda: asyncio.to_thread(client.delete_item, TableName=table_name, Key=key),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.delete", 1, service="dynamodb", operation="delete_item")
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB delete_item failed: {exc}", cause=exc) from exc

    async def query(
        self,
        table_name: str,
        key_condition: str,
        expression_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not table_name or not key_condition:
            raise ValidationError("table_name and key_condition are required")
        client = await self._client()
        kwargs: Dict[str, Any] = {
            "TableName": table_name,
            "KeyConditionExpression": key_condition,
            "ExpressionAttributeValues": expression_values,
        }
        if index_name:
            kwargs["IndexName"] = index_name
        if limit:
            kwargs["Limit"] = limit
        try:
            resp = await self._retry.execute(
                "ddb_query",
                lambda: asyncio.to_thread(client.query, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.query", 1, service="dynamodb", operation="query")
            return list(resp.get("Items", []))
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB query failed: {exc}", cause=exc) from exc

    async def scan(self, table_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not table_name:
            raise ValidationError("table_name is required")
        client = await self._client()
        kwargs: Dict[str, Any] = {"TableName": table_name}
        if limit:
            kwargs["Limit"] = limit
        try:
            resp = await self._retry.execute(
                "ddb_scan",
                lambda: asyncio.to_thread(client.scan, **kwargs),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.scan", 1, service="dynamodb", operation="scan")
            return list(resp.get("Items", []))
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB scan failed: {exc}", cause=exc) from exc

    async def batch_write(self, table_name: str, items: List[Dict[str, Any]]) -> None:
        if not table_name or not items:
            raise ValidationError("table_name and items are required")
        client = await self._client()
        request_items = {table_name: [{"PutRequest": {"Item": item}} for item in items]}
        try:
            await self._retry.execute(
                "ddb_batch_write",
                lambda: asyncio.to_thread(client.batch_write_item, RequestItems=request_items),
            )
            if self._metrics:
                await self._metrics.record_counter("arctus.aws.dynamodb.batch_write", len(items), service="dynamodb", operation="batch_write")
        except Exception as exc:
            raise DynamoDBError(f"DynamoDB batch_write failed: {exc}", cause=exc) from exc

    async def health(self) -> Dict[str, Any]:
        try:
            client = await self._client()
            await self._retry.execute("health", lambda: asyncio.to_thread(client.list_tables, Limit=1))
            return {"status": "healthy", "service": "dynamodb"}
        except Exception as exc:
            return {"status": "unhealthy", "service": "dynamodb", "error": str(exc)}

    async def close(self) -> None:
        await self._holder.close()
