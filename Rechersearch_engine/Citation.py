# arctus_research_engine/pipeline/citation.py
"""Provenance-rich bibliography generation."""

import hashlib
from datetime import datetime
from typing import List

from arctus_research_engine.interfaces import ITelemetry
from arctus_research_engine.models import (
    Citation,
    EvidenceRecord,
    RankedEvidenceCollection,
    ResearchReport,
    ReportSection,
)
from arctus_research_engine.plugins.base import CitationFormatter, ExecutionContext


class CitationEngine:
    def __init__(self, formatter: CitationFormatter, telemetry: ITelemetry):
        self._formatter = formatter
        self._telemetry = telemetry

    async def execute(
        self,
        evidence: RankedEvidenceCollection,
        sections: List[ReportSection],
        required_format: str,
        correlation_id: str,
        context: ExecutionContext,
    ) -> ResearchReport:
        async with self._telemetry.start_span("research.cite", {
            "correlation_id": context.correlation_id,
        }):
            citations = await self._formatter.format_citations(
                evidence, required_format, context
            )
            
            # Bind citations into sections
            enriched_sections = list(sections)
            bibliography = citations            report = ResearchReport(
                correlation_id=correlation_id,
                title=f"Research Report: {correlation_id}",
                sections=enriched_sections,
                bibliography=bibliography,
                integrity_hash="",
                generated_at=datetime.utcnow(),
            )
            # Deterministic integrity hash over canonical JSON of content
            import json
            canonical = json.dumps({
                "cid": report.correlation_id,
                "sections": [(s.title, s.narrative) for s in report.sections],
                "bib": [c.formatted_text for c in report.bibliography],
            }, sort_keys=True)
            report = report.__class__(
 correlation_id=report.correlation_id,
                title=report.title,
                sections=report.sections,
                bibliography=report.bibliography,
                integrity_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                generated_at=report.generated_at,
            )
            return report
