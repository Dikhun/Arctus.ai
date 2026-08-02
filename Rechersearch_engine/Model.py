# arctus_research_engine/models.py
"""Immutable domain models for research workflows."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import enumimport hashlib
import json


class EventType(enum.Enum):
    RESEARCH_REQUEST = "research.request"
    RESEARCH_COMPLETION = "research.completion"
    RESEARCH_FAILURE = "research.failure"
    RESEARCH_FRAGMENT = "research.fragment"
    STAGE_CHECKPOINT = "stage.checkpoint"


@dataclass(frozen=True)
class ResearchEvent:
    correlation_id: str
    event_type: str  # EventType value
    payload: Dict[str, Any]
    origin_timestamp: datetime
    processing_counter: int = 0
    sender_agent_id: Optional[str] = None def with_counter(self, value: int) -> ResearchEvent:
        return replace(self, processing_counter=value)


@dataclass(frozen=True)
class SearchQuery:
    text: str
    filters: Dict[str, Any] = field(default_factory=dict)
    top_k: int = 10


@dataclass(frozen=True)
class RawDocument:
    source_uri: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    content_hash: str
    source_uri: str
    raw_content: str
    retrieval_adapter: str
    relevance_score: float
    credibility_score: float
    evidential_utility: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RankedEvidenceCollection:
    records: List[EvidenceRecord] = field(default_factory=list)

    def merge(self, other: RankedEvidenceCollection) -> RankedEvidenceCollection:
        seen = {r.content_hash for r in self.records}
        merged = list(self.records)
        for r in other.records:
            if r.content_hash not in seen:
                merged.append(r)
        return RankedEvidenceCollection(records=merged)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    evidence_hashes: List[str]
    stance: Literal["support", "oppose", "neutral"]
    confidence: float  # 0.0 - 1.0    source_uris: List[str]


@dataclass(frozen=True)
class AnalysisReport:
    claims: List[Claim] = field(default_factory=list)
    contradictions: List[tuple[str, str]] = field(default_factory=list)  # (claim_id_a, claim_id_b)
    overall_confidence: float = 0.0


@dataclass(frozen=True)
class Citation:
    citation_id: str
    format_type: Literal["apa", "mla", "chicago", "ieee", "bibtex", "json-ld"]
    formatted_text: str
    provenance_chain: List[str]  # ordered list of content_hashes
    integrity_hash: str


@dataclass(frozen=True)
class ReportSection:
    title: str
    narrative: str
    supporting_claims: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchReport:
    correlation_id: str
    title: str
    sections: List[ReportSection] = field(default_factory=list)
    bibliography: List[Citation] = field(default_factory=list)
    integrity_hash: str
    generated_at: datetime


@dataclass(frozen=True)
class ResearchDirective:
    query: str
    depth: Literal["shallow", "standard", "deep"] = "standard"
    required_citation_format: Literal["apa", "mla", "chicago", "ieee", "bibtex", "json-ld"] = "apa"
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchPlanStep:
    step_type: Literal["retrieve", "analyze", "synthesize", "cite", "delegate"]
    query_override: Optional[str] = None
    target_agent_id: Optional[str] = None


@dataclass(frozen=True)
class WorkflowManifest:
    correlation_id: str
    directive: ResearchDirective
    execution_mode: Literal["standard", "deterministic"]
    plan: List[ResearchPlanStep] = field(default_factory=list)
    evidence: RankedEvidenceCollection = field(default_factory=RankedEvidenceCollection)
    analysis: Optional[AnalysisReport] = None
    report: Optional[ResearchReport] = None
    current_stage_index: int = 0
    is_complete: bool = False

    def advance_stage(self) -> WorkflowManifest:
        return replace(self, current_stage_index=self.current_stage_index + 1)

    def with_evidence(self, evidence: RankedEvidenceCollection) -> WorkflowManifest:
        return replace(self, evidence=self.evidence.merge(evidence))

    def with_analysis(self, analysis: AnalysisReport) -> WorkflowManifest:
        return replace(self, analysis=analysis)

    def with_plan(self, plan: List[ResearchPlanStep]) -> WorkflowManifest:
        return replace(self, plan=plan)

    def as_checkpoint(self) -> bytes:
        # Simplified serialization; framework may supply a typed serializer interface
        return json.dumps({
            "correlation_id": self.correlation_id,
            "stage": self.current_stage_index,
            "is_complete": self.is_complete,
        }).encode("utf-8")


@dataclass(frozen=True)
class ResearchFragment:
    message_type: Literal["RESEARCH_FRAGMENT"] = "RESEARCH_FRAGMENT"
    correlation_id: str = ""
    sender_agent_id: str = ""
    recipient_agent_id: str = ""
    sub_task_id: str = ""
    artifact_uri: str = ""
    integrity_hash: str = ""
    causality_vector: Dict[str, int] = field(default_factory=dict)
