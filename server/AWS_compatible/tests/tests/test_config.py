"""Tests for immutable configuration and the ConfigProvider."""

from __future__ import annotations

import pytestfrom arctus_aws.config import AWSConfig, ConfigProvider, RetryConfig, SecurityConfig
from arctus_aws.exceptions import ConfigurationError


def test_default_aws_config() -> None:
    cfg = AWSConfig()
    assert cfg.region == "us-east-1"
    assert cfg.security.kms_key_id is None

def test_config_from_dict() -> None:
    raw = {
        "region": "eu-west-1",
        "security": {"kms_key_id": "alias/my-key", "iam_role_arn": "arn:aws:iam::123:role/Admin"},
        "retry": {"max_attempts": 5},
    }
    cfg = AWSConfig.from_dict(raw)
    assert cfg.region == "eu-west-1"
    assert cfg.security.kms_key_id == "alias/my-key"
    assert cfg.retry.max_attempts == 5

def test_invalid_type_raises() -> None:
    with pytest.raises(ConfigurationError):
        AWSConfig.from_dict({"region": 123})  # type: ignoredef test_config_provider_replace() -> None:
 p = ConfigProvider(AWSConfig())
    assert p.current().region == "us-east-1"
    p.replace(AWSConfig(region="ap-south-1"))
 assert p.current().region == "ap-south-1"

def test_config_is_frozen() -> None:
    cfg = AWSConfig()
    with pytest.raises(AttributeError):
        object.__setattr__(cfg, "region", "us-west-2")
