"""Enterprise-grade typed exception hierarchy for arctus_aws.

All exceptions carry structured diagnostic context, support chaining,
and expose a deterministic ``to_dict`` representation for integration
with the Arctus telemetry and persistent memory systems.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


class ArctusAWSException(Exception):
    """Base for every error raised by the AWS integration layer."""

    __slots__ = ("message", "code", "details", "cause", "retryable")

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or "AWS_ERROR"
        self.details = details or {}
        self.cause = cause
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }

    def __str__(self) -> str:
        payload = self.to_dict()
        return json.dumps(payload, default=str)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("            f"message={self.message!r}, "
            f"code={self.code!r}, "
            f"retryable={self.retryable}, "
            f"details={self.details!r})"
        )


class ConfigurationError(ArctusAWSException):
    """Raised when injected framework configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            code="CONFIG_ERROR",
            details=details,
            cause=cause,
            retryable=False,
        )


class AuthenticationError(ArctusAWSException):
    """Raised when AWS identity cannot be established."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            code="AUTH_ERROR",
            details=details,
            cause=cause,
            retryable=False,
        )


class AuthorizationError(ArctusAWSException):
    """Raised when the principal lacks permission."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            code="FORBIDDEN",
            details=details,
            cause=cause,
            retryable=False,
        )


class CredentialError(ArctusAWSException):
    """Raised when credential resolution or rotation fails."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            code="CREDENTIAL_ERROR",
            details=details,
            cause=cause,
            retryable=True,
        )


class TokenRefreshError(CredentialError):
    """Raised when an STS or identity-token refresh operation fails."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            cause=cause,
        )
        self.code = "TOKEN_REFRESH_ERROR"
        self.retryable = True


class ServiceError(ArctusAWSException):
    """Base for all AWS service-level errors."""

    def __init__(
        self,
        message: str,
        service: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            code=code or "SERVICE_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )
        self.service = service

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["service"] = self.service
        return base


class AWSServiceError(ServiceError):
    """Generic AWS SDK-wrapped error with automatic retry classification."""

    __slots__ = ("service", "operation", "status_code")

    def __init__(
        self,
        message: str,
        service: str,
        operation: str,
        status_code: int = 0,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            service,
            code=code,
            details=details,
            cause=cause,
            retryable=retryable,
        )
        self.operation = operation
        self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["operation"] = self.operation
        base["status_code"] = self.status_code
        return base


class AWSConnectionError(ServiceError):
    """Transient network-level connection failure."""

    def __init__(
        self,
        message: str,
        service: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            service,
            code="CONNECTION_ERROR",
            details=details,
            cause=cause,
            retryable=True,
        )


class AWSTimeoutError(ServiceError):
    """Transient timeout waiting for an AWS service."""

    def __init__(
        self,
        message: str,
        service: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            service,
            code="TIMEOUT_ERROR",
            details=details,
            cause=cause,
            retryable=True,
        )


class CircuitBreakerOpenError(ServiceError):
    """Raised when a circuit breaker prevents an AWS call."""

    def __init__(
        self,
        message: str,
        service: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            service,
            code="CIRCUIT_BREAKER_OPEN",
            details=details,
            retryable=False,
        )


class ValidationError(ArctusAWSException):
    """Raised when request pre-validation fails before an AWS call."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(
            message,
            code="VALIDATION_ERROR",
            details=details,
            cause=cause,
            retryable=False,
        )


class KMSError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "kms",
            code=code or "KMS_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class SecretError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "secretsmanager",
            code=code or "SECRET_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class ParameterStoreError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "ssm",
            code=code or "PARAMETER_STORE_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class S3Error(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "s3",
            code=code or "S3_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class DynamoDBError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "dynamodb",
            code=code or "DYNAMODB_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class SQSError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "sqs",
            code=code or "SQS_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class SNSError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "sns",
            code=code or "SNS_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class EventBridgeError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "events",
            code=code or "EVENTBRIDGE_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class CloudWatchError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "cloudwatch",
            code=code or "CLOUDWATCH_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class XRayError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "xray",
            code=code or "XRAY_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class LambdaError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "lambda",
            code=code or "LAMBDA_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class ECSError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "ecs",
            code=code or "ECS_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class EKSError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "eks",
            code=code or "EKS_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class BedrockError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "bedrock",
            code=code or "BEDROCK_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class OpenSearchError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "opensearch",
            code=code or "OPENSEARCH_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


class NeptuneError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            "neptune",
            code=code or "NEPTUNE_ERROR",
            details=details,
            cause=cause,
            retryable=retryable,
        )


__all__ = [
    "ArctusAWSException",
    "ConfigurationError",
    "AuthenticationError",
    "AuthorizationError",
    "CredentialError",
    "TokenRefreshError",
    "ServiceError",
    "AWSServiceError",
    "AWSConnectionError",
    "AWSTimeoutError",
    "CircuitBreakerOpenError",
    "ValidationError",
    "KMSError",
    "SecretError",
    "ParameterStoreError",
    "S3Error",
    "DynamoDBError",
    "SQSError",
    "SNSError",
    "EventBridgeError",
    "CloudWatchError",
    "XRayError",
    "LambdaError",
    "ECSError",
    "EKSError",
    "BedrockError",
    "OpenSearchError",
    "NeptuneError",
]
