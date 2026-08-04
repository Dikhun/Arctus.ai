"""Arctus AI Orchestration Framework - Synthesizer.

Responsible for merging worker outputs, conflict resolution,
duplicate removal, and final answer generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import TaskIntent, WorkerResult
from exceptions import ConflictResolutionException, ErrorContext, SynthesisException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("synthesizer")


@dataclass
class Conflict:
    """Detected conflict between outputs."""

    sources: List[str]
    description: str
    severity: str  # "minor", "major", "critical"
    resolution: Optional[str] = None


class SynthesizerImpl:
    """Production synthesizer with conflict detection and resolution.

    Merges multiple worker outputs into coherent, consistent
    final answers with quality guarantees.
    """

    def __init__(
        self,
        enable_conflict_detection: bool = True,
        deduplication_threshold: float = 0.85,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.enable_conflict_detection = enable_conflict_detection
        self.deduplication_threshold = deduplication_threshold
        self.event_bus = event_bus
        self.logger = get_logger("synthesizer")

    @async_timed
    async def synthesize(
        self,
        results: List[WorkerResult],
        original_intent: TaskIntent,
    ) -> str:
        """Synthesize final answer from worker results.

        Args:
            results: Collected worker outputs.
            original_intent: Original user intent.

        Returns:
            Synthesized final answer.

        Raises:
            SynthesisException: If synthesis fails.
            ConflictResolutionException: If unresolvable conflicts.
        """
        with LogContext(module="synthesizer", operation="synthesize"):
            if not results:
                raise SynthesisException(
                    "No worker results to synthesize",
                    context=ErrorContext(
                        module="synthesizer",
                        operation="synthesize",
                    ),
                )

            self.logger.info(
                "Synthesizing results",
                extra={
                    "result_count": len(results),
                    "intent_goals": len(original_intent.goals),
                },
            )

            # Step 1: Deduplicate similar outputs
            unique_results = self._deduplicate(results)

            # Step 2: Detect conflicts
            conflicts: List[Conflict] = []
            if self.enable_conflict_detection:
                conflicts = await self._detect_conflicts(unique_results)

            # Step 3: Resolve conflicts
            resolved = await self._resolve_conflicts(unique_results, conflicts)

            # Step 4: Merge into final answer
            final = await self._merge_outputs(resolved, original_intent)

            # Step 5: Post-process
            final = self._post_process(final, original_intent)

            self.logger.info(
                "Synthesis complete",
                extra={
                    "original_results": len(results),
                    "unique_results": len(unique_results),
                    "conflicts": len(conflicts),
                    "output_length": len(final),
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="synthesis_complete",
                        payload={
                            "input_count": len(results),
                            "conflicts_detected": len(conflicts),
                            "output_length": len(final),
                        },
                    )
                )

            return final

    def _deduplicate(self, results: List[WorkerResult]) -> List[WorkerResult]:
        """Remove near-duplicate outputs.

        Args:
            results: Worker results.

        Returns:
            Deduplicated results.
        """
        if len(results) <= 1:
            return results

        unique: List[WorkerResult] = [results[0]]

        for result in results[1:]:
            is_duplicate = False
            for existing in unique:
                similarity = self._text_similarity(result.output, existing.output)
                if similarity >= self.deduplication_threshold:
                    is_duplicate = True
                    # Keep the higher quality one
                    if getattr(result, 'quality', None) and getattr(existing, 'quality', None):
                        if result.quality.overall > existing.quality.overall:
                            unique[unique.index(existing)] = result
                    break

            if not is_duplicate:
                unique.append(result)

        self.logger.debug(
            "Deduplication complete",
            extra={"original": len(results), "unique": len(unique)},
        )

        return unique

    async def _detect_conflicts(self, results: List[WorkerResult]) -> List[Conflict]:
        """Detect conflicts between outputs.

        Args:
            results: Worker results.

        Returns:
            List of detected conflicts.
        """
        conflicts: List[Conflict] = []

        # Check pairwise
        for i, r1 in enumerate(results):
            for r2 in results[i + 1:]:
                # Check for numerical contradictions
                nums1 = self._extract_numbers(r1.output)
                nums2 = self._extract_numbers(r2.output)

                for n1, ctx1 in nums1:
                    for n2, ctx2 in nums2:
                        # Same context, different values
                        if self._similar_context(ctx1, ctx2) and abs(n1 - n2) > max(abs(n1), abs(n2)) * 0.1:
                            if n1 != 0 and n2 != 0:
                                conflicts.append(Conflict(
                                    sources=[str(r1.task_id), str(r2.task_id)],
                                    description=f"Numerical discrepancy: {n1} vs {n2} in '{ctx1}'",
                                    severity="major" if abs(n1 - n2) / max(abs(n1), abs(n2)) > 0.5 else "minor",
                                ))

                # Check for direct contradictions
                contradiction_phrases = [
                    ("is", "is not"), ("can", "cannot"), ("will", "will not"),
                    ("should", "should not"), ("must", "must not"),
                ]
                for affirm, negate in contradiction_phrases:
                    if affirm in r1.output.lower() and negate in r2.output.lower():
                        # Check if same subject
                        if self._similar_context(r1.output[:100], r2.output[:100]):
                            conflicts.append(Conflict(
                                sources=[str(r1.task_id), str(r2.task_id)],
                                description=f"Contradiction: '{affirm}' vs '{negate}'",
                                severity="critical",
                            ))

        self.logger.debug(
            "Conflict detection complete",
            extra={"conflicts_found": len(conflicts)},
        )

        return conflicts

    async def _resolve_conflicts(
        self,
        results: List[WorkerResult],
        conflicts: List[Conflict],
    ) -> List[WorkerResult]:
        """Resolve detected conflicts.

        Args:
            results: Worker results.
            conflicts: Detected conflicts.

        Returns:
            Results with conflicts resolved.
        """
        if not conflicts:
            return results

        # Strategy: vote or trust higher quality
        resolved_results = list(results)

        for conflict in conflicts:
            # Find source results
            source_results = [
                r for r in results
                if str(r.task_id) in conflict.sources
            ]

            if not source_results:
                continue

            # Resolution by quality score
            if len(source_results) >= 2:
                best = max(source_results, key=lambda r: getattr(r, 'quality', None).overall if getattr(r, 'quality', None) else 0)
                # Remove conflicting lower-quality results
                for r in source_results:
                    if r != best and r in resolved_results:
                        if conflict.severity == "critical":
                            resolved_results.remove(r)
                            self.logger.warning(
                                "Removed conflicting result",
                                extra={"task_id": str(r.task_id), "conflict": conflict.description},
                            )

            conflict.resolution = f"Trusted result from {best.task_id}"

        # Check if too many results removed
        if len(resolved_results) < len(results) * 0.5:
            raise ConflictResolutionException(
                "Too many conflicts, cannot reliably synthesize",
                conflicting_sources=[c.sources for c in conflicts],
                context=ErrorContext(
                    module="synthesizer",
                    operation="_resolve_conflicts",
                ),
            )

        return resolved_results

    async def _merge_outputs(
        self,
        results: List[WorkerResult],
        intent: TaskIntent,
    ) -> str:
        """Merge outputs into coherent text.

        Args:
            results: Resolved results.
            intent: Original intent.

        Returns:
            Merged text.
        """
        if len(results) == 1:
            return results[0].output

        parts: List[str] = []

        # Determine merge strategy from intent
        if intent.desired_output_format == "json":
            return self._merge_json(results)
        elif intent.desired_output_format == "table":
            return self._merge_table(results)
        elif intent.desired_output_format == "code":
            return self._merge_code(results)

        # Default: concatenate with section headers
        for i, result in enumerate(results):
            header = f"## Section {i + 1}"
            if result.agent_id:
                header += f" (Agent: {result.agent_id})"
            parts.append(f"{header}\n\n{result.output}")

        return "\n\n---\n\n".join(parts)

    def _merge_json(self, results: List[WorkerResult]) -> str:
        """Merge JSON outputs.

        Args:
            results: Results to merge.

        Returns:
            Merged JSON string.
        """
        import json
        merged: Dict[str, Any] = {}
        for result in results:
            try:
                data = json.loads(result.output)
                if isinstance(data, dict):
                    merged.update(data)
            except json.JSONDecodeError:
                merged[f"section_{result.task_id}"] = result.output

        return json.dumps(merged, indent=2)

    def _merge_table(self, results: List[WorkerResult]) -> str:
        """Merge table outputs.

        Args:
            results: Results to merge.

        Returns:
            Merged markdown table.
        """
        # Extract tables and combine
        tables: List[str] = []
        for result in results:
            # Find markdown tables
            lines = result.output.split("\n")
            in_table = False
            table_lines: List[str] = []
            for line in lines:
                if "|" in line:
                    table_lines.append(line)
                    in_table = True
                elif in_table:
                    break

            if table_lines:
                tables.append("\n".join(table_lines))

        if tables:
            return tables[0]  # Return first valid table

        return results[0].output if results else ""

    def _merge_code(self, results: List[WorkerResult]) -> str:
        """Merge code outputs.

        Args:
            results: Results to merge.

        Returns:
            Merged code string.
        """
        # For code, prefer longest or most complete
        codes = [r.output for r in results]
        return max(codes, key=len) if codes else ""

    def _post_process(self, text: str, intent: TaskIntent) -> str:
        """Post-process synthesized output.

        Args:
            text: Raw synthesis.
            intent: Original intent.

        Returns:
            Processed text.
        """
        # Remove redundant headers if single
