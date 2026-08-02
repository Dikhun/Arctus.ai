"""AWS credential resolution with STS AssumeRole support."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import boto3

from .config import ConfigProvider
from .exceptions import AuthenticationError, TokenRefreshError

class CredentialsProvider:
    __slots__ = ("_cfg_prov", "_session", "_lock")

    def __init__(self, config_provider: ConfigProvider) -> None:
        self._cfg_prov = config_provider
        self._session: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def session(self) -> boto3.Session:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            cfg = self._cfg_prov.current()
            sec = cfg.security
            try:
                if sec.iam_role_arn:
                    sts = boto3.client("sts", region_name=cfg.region, endpoint_url=cfg.endpoint_url)
                    assume_kwargs = {
                        "RoleArn": sec.iam_role_arn,
                        "RoleSessionName": sec.session_name or "arctus-aws",
                    }
                    if sec.sts_external_id:
                        assume_kwargs["ExternalId"] = sec.sts_external_id
                    resp = await asyncio.to_thread(sts.assume_role, **assume_kwargs)
                    creds = resp["Credentials"]
                    self._session = boto3.Session(
                        aws_access_key_id=creds["AccessKeyId"],
                        aws_secret_access_key=creds["SecretAccessKey"],
                        aws_session_token=creds["SessionToken"],
                        region_name=cfg.region,
                    )
                else:
                    kwargs: dict[str, Any] = {"region_name": cfg.region}
                    if cfg.profile:
                        kwargs["profile_name"] = cfg.profile
                    self._session = boto3.Session(**kwargs)
            except Exception as exc:
                raise AuthenticationError(
                    f"Failed to create AWS session: {exc}",
                    cause=exc,
                ) from exc
            return self._session

    async def reset(self) -> None:
        async with self._lock:
            self._session = None

    async def refresh(self) -> None:
        await self.reset()
        await self.session()
