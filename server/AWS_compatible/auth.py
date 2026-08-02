"""High-level identity and authorization helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .config import ConfigProvider
from .credentials import CredentialsProvider
from .exceptions import AuthenticationError, AuthorizationError

class AWSIdentity:
    __slots__ = ("_cfg_prov", "_cred_prov", "_cache")

    def __init__(self, config_provider: ConfigProvider, credentials_provider: CredentialsProvider) -> None:
        self._cfg_prov = config_provider
        self._cred_prov = credentials_provider
        self._cache: Optional[Dict[str, Any]] = None

    async def whoami(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        session = await self._cred_prov.session()
        sts = session.client("sts")
        try:
            resp = await asyncio.to_thread(sts.get_caller_identity)
            self._cache = {
                "account": resp.get("Account"),
                "arn": resp.get("Arn"),
                "user_id": resp.get("UserId"),
            }
            return self._cache
        except Exception as exc:
            raise AuthenticationError("STS GetCallerIdentity failed", cause=exc) from exc

    async def validate_principal(self, required_role_arn: Optional[str] = None) -> None:
        identity = await self.whoami()
        if required_role_arn and identity.get("arn") != required_role_arn:
            raise AuthorizationError(
                "Principal ARN mismatch",
                details={"expected": required_role_arn, "actual": identity.get("arn")},
            )
