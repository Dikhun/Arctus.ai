from __future__ import annotationsimport uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConfidenceTier(Enum):
    HIGH = 1.0
    MEDIUM = 0.8
    LOW = 0.5
    VERY_LOW = 0.3
    UNVERIFIED = 0.0


class SourceType(Enum):
    SCIP = "scip"
    FRAMEWORK_ADAPTER = "framework_adapter"
    AST_DIRECT = "ast_direct"
    NAME_MATCH = "name_match"
    HUMAN_VERIFIED = "human_verified"
    MODEL_INFERENCE = "model_inference"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class Provenance:
    source_type: SourceType
    source_uri: str
    extracted_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Node:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    node_type: str = "generic"
    confidence: float = 0.0
    provenance: Provenance = field(
 default_factory=lambda: Provenance(SourceType.FALLBACK, "")
    )
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def tier(self) -> ConfidenceTier:
        if self.confidence >= 0.9:
            return ConfidenceTier.HIGH
        if self.confidence >= 0.7:
            return ConfidenceTier.MEDIUM
        if self.confidence >= 0.4:
            return ConfidenceTier.LOW
        if self.confidence >= 0.1:
            return ConfidenceTier.VERY_LOW
        return ConfidenceTier.UNVERIFIED


@dataclass(slots=True)
class Edge:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    relation: str = ""
    confidence: float = 0.0
    provenance: Provenance = field(
        default_factory=lambda: Provenance(SourceType.FALLBACK, "")
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tier(self) -> ConfidenceTier:
        if self.confidence >= 0.9:
            return ConfidenceTier.HIGH
        if self.confidence >= 0.7:
            return ConfidenceTier.MEDIUM
        if self.confidence >= 0.4:
            return ConfidenceTier.LOW
        if self.confidence >= 0.1:
            return ConfidenceTier.VERY_LOW
        return ConfidenceTier.UNVERIFIED
