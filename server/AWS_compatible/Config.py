"""Immutable, deterministic, validated AWS configuration.

Configuration is delivered by the Arctus framework through injection.
All dataclasses are frozen; runtime updates are performed by swapping
the immutable instance held inside ``ConfigProvider``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .exceptions import ConfigurationError


def _str(data: Dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ConfigurationError(
            f"Expected str for '{key}', got {type(value).__name__}",
            details={"key": key, "received": value},
        )
    return value


def _str_optional(data: Dict[str, Any], key: str) -> Optional[str]:
 value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigurationError(
            f"Expected str or None for '{key}', got {type(value).__name__}",
            details={"key": key, "received": value},
        )
    return value


def _int(data: Dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(
            f"Expected int for '{key}', got {type(value).__name__}",
            details={"key": key, "received": value},
        )
    return value


def _float(data: Dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool):
        raise ConfigurationError(
            f"Expected float for '{key}', got bool",
            details={"key": key},
        )
    if not isinstance(value, (int, float)):
        raise ConfigurationError(
            f"Expected float for '{key}', got {type(value).__name__}",
            details={"key": key, "received": value},
        )
    return float(value)


def _bool(data: Dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigurationError(
            f"Expected bool for '{key}', got {type(value).__name__}",
            details={"key": key, "received": value},
        )
    return value


def _dict_str_str(data: Dict[str, Any], key: str) -> Dict[str, str]:
    value = data.get(key)
    if not value:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"Expected dict for '{key}', got {type(value).__name__}",
            details={"key": key},
        )
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ConfigurationError(
                f"Dict '{key}' must be Dict[str, str]",
 details={"bad_key": k, "bad_value": v},
            )
    return dict(value)


@dataclass(frozen=True)
class RetryConfig:
    """Adaptive retry policy shared across AWS service clients."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_statuses: Tuple[int, ...] = (429, 500, 502, 503, 504)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RetryConfig:
        return cls(
            max_attempts=_int(data, "max_attempts", 3),
            base_delay_seconds=_float(data, "base_delay_seconds", 0.5),
            max_delay_seconds=_float(data, "max_delay_seconds", 30.0),
            exponential_base=_float(data, "exponential_base", 2.0),
            jitter=_bool(data, "jitter", True),
            retryable_statuses=tuple(
                data.get("retryable_statuses", (429, 500, 502, 503, 504))
            ),
        )


@dataclass(frozen=True)
class PoolConfig:
    """Connection-pool tuning parameters."""

    max_connections: int = 50
    max_idle: int = 10
    idle_timeout_seconds: float = 60.0
    connection_timeout_seconds: float = 5.0    read_timeout_seconds: float = 30.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PoolConfig:
        return cls(
            max_connections=_int(data, "max_connections", 50),
            max_idle=_int(data, "max_idle", 10),
            idle_timeout_seconds=_float(data, "idle_timeout_seconds", 60.0),
            connection_timeout_seconds=_float(data, "connection_timeout_seconds", 5.0),
            read_timeout_seconds=_float(data, "read_timeout_seconds", 30.0),
        )


@dataclass(frozen=True)
class SecurityConfig:
    """Encryption, identity, and role-assumption settings."""

    kms_key_id: Optional[str] = None
    kms_key_region: Optional[str] = None
    encryption_context: Dict[str, str] = field(default_factory=dict)
    iam_role_arn: Optional[str] = None
    sts_external_id: Optional[str] = None
    session_name: str = "arctus-aws-session"
    use_identity_center: bool = False
    identity_center_start_url: Optional[str] = None
    identity_center_region: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SecurityConfig:
        return cls(
            kms_key_id=_str_optional(data, "kms_key_id"),
            kms_key_region=_str_optional(data, "kms_key_region"),
            encryption_context=_dict_str_str(data, "encryption_context"),
            iam_role_arn=_str_optional(data, "iam_role_arn"),
            sts_external_id=_str_optional(data, "sts_external_id"),
            session_name=_str(data, "session_name", "arctus-aws-session"),
            use_identity_center=_bool(data, "use_identity_center", False),
            identity_center_start_url=_str_optional(data, "identity_center_start_url"),
            identity_center_region=_str_optional(data, "identity_center_region"),
        )


@dataclass(frozen=True)
class AWSConfig:
    """Top-level AWS integration configuration."""

    region: str = "us-east-1"
    account_id: Optional[str] = None
    profile: Optional[str] = None
    endpoint_url: Optional[str] = None
    security: SecurityConfig = field(default_factory=SecurityConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    pool: PoolConfig = field(default_factory=PoolConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AWSConfig:
        return cls(
            region=_str(data, "region", "us-east-1"),
            account_id=_str_optional(data, "account_id"),
            profile=_str_optional(data, "profile"),
            endpoint_url=_str_optional(data, "endpoint_url"),
            security=SecurityConfig.from_dict(data.get("security") or {}),
            retry=RetryConfig.from_dict(data.get("retry") or {}),
            pool=PoolConfig.from_dict(data.get("pool") or {}),
        )


class ConfigProvider:
    """Thread-safe, atomic holder for an immutable AWSConfig.

    The Arctus framework may hot-reload configuration by calling
    ``replace()``; consumers always see a consistent snapshot via
    ``current()``.
    """

    __slots__ = ("_lock", "_config")

    def __init__(self, initial: AWSConfig) -> None:
        self._lock = threading.RLock()
        self._config = initial

    def current(self) -> AWSConfig:
        """Return the current immutable configuration snapshot."""
        with self._lock:
            return self._config

    def replace(self, new_config: AWSConfig) -> None:
        """Atomically swap the stored configuration."""
        with self._lock:
            self._config = new_config

    def mutate(self, mutator: Any) -> None:
        """Helper for framework-driven partial updates.

 ``mutator`` is a callable that receives the current ``AWSConfig``
        and returns a new ``AWSConfig`` instance.
        """
        with self._lock:
            self._config = mutator(self._config)


__all__ = [
    "ConfigProvider",
    "AWSConfig",
    "RetryConfig",
    "PoolConfig",
    "SecurityConfig",
           ]
