"""Tests for the typed exception hierarchy."""

import json

import pytest

from arctus_aws.exceptions import (
    ArctusAWSException,
    AuthenticationError,
    DynamoDBError,
    KMSError,
    ServiceError,
)


def test_base_exception_serializes() -> None:
 exc = ArctusAWSException("boom", code="TEST", retryable=True)
    d = exc.to_dict()
    assert d["message"] == "boom"
    assert d["code"] == "TEST"
    assert d["retryable"] is True
    assert "TEST" in str(exc)

def test_service_exception_includes_service() -> None:
    exc = DynamoDBError("table gone", code="NOT_FOUND", retryable=False)
    assert exc.service == "dynamodb"
    assert exc.to_dict()["service"] == "dynamodb"

def test_kms_error_default_code() -> None:
 exc = KMSError("key disabled")
    assert exc.code == "KMS_ERROR"
    assert exc.service == "kms"

def test_exception_with_details() -> None:
    exc = AuthenticationError("nope", details={"mfa": "missing"})
    assert exc.details == {"mfa": "missing"}
