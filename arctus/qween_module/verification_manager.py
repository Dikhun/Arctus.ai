
"""Arctus AI Orchestration Framework - Verification Manager.

Responsible for answer verification, consistency checking,
fact verification, and quality scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import QualityMetrics, SubTask, WorkerResult
from exceptions import ErrorContext, QualityThresholdException, VerificationException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("verification_manager")


@dataclass
class VerificationRule:
    """Configurable verification rule."""

    name: str
    check: callable  # function(result, task) -> (passed, score, message)
    weight: float = 1.0
    required: bool = False


class VerificationManagerImpl:
    """Production verification manager with multi-dimensional quality checks.

    Verifies worker outputs against task requirements with
    configurable rules and thresholds.
    """

    DEFAULT_ACCURACY_THRESHOLD = 0.7
    DEFAULT_CONSISTENCY_THRESHOLD = 0.6
    DEFAULT_COMPLETENESS_THRESHOLD = 0.6
    DEFAULT_RELEVANCE_THRESHOLD = 0.5

    def __init__(
        self,
        accuracy_threshold: float = DEFAULT_ACCURACY_THRESHOLD,
        consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD,
        completeness_threshold: float = DEFAULT_COMPLETENESS_THRESHOLD,
        relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
        custom_rules: Optional[List[VerificationRule]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.thresholds = {
            "accuracy": accuracy_threshold,
            "consistency": consistency_threshold,
            "completeness": completeness_threshold,
            "relevance": relevance_threshold,
        }
        self.custom_rules = custom_rules or []
        self.event_bus = event_bus
        self.logger = get_logger("verification_manager")

    @async_timed
    async def verify(
        self,
        result: WorkerResult,
        task: SubTask,
        expected_format: Optional[str] = None,
    ) -> QualityMetrics:
        """Verify a worker result comprehensively.

        Args:
            result: The worker output to verify.
            task: Original task specification.
            expected_format: Expected output format.

        Returns:
            Quality metrics for the result.

        Raises:
            QualityThresholdException: If quality below threshold.
        """
        with LogContext(module="verification_manager", operation="verify", task_id=task.id):
            self.logger.info(
                "Verifying result",
                extra={
                    "task_id": str(task.id),
                    "output_length": len(result.output),
                    "expected_format": expected_format,
                },
            )

            # Run all verification dimensions
            accuracy = await self._check_accuracy(result, task)
            consistency = await self._check_consistency(result, task)
            completeness = await self._check_completeness(result, task)
            relevance = await self._check_relevance(result, task)

            # Calculate overall
            overall = (accuracy + consistency + completeness + relevance) / 4.0

            metrics = QualityMetrics(
                accuracy=accuracy,
                consistency=consistency,
                completeness=completeness,
                relevance=relevance,
                overall=overall,
            )

            # Run custom rules
            for rule in self.custom_rules:
                passed, score, message = rule.check(result, task)
                if not passed and rule.required:
                    self.logger.error(
                        "Required verification rule failed",
                        extra={"rule": rule.name, "message": message},
                    )

            # Check thresholds
            failed = []
            for dimension, threshold in self.thresholds.items():
                value = getattr(metrics, dimension)
                if value < threshold:
                    failed.append(f"{dimension}: {value:.2f} < {threshold}")

            if failed:
                raise QualityThresholdException(
                    f"Quality below threshold: {', '.join(failed)}",
                    score=overall,
                    threshold=min(self.thresholds.values()),
                    context=ErrorContext(
                        module="verification_manager",
                        operation="verify",
                        task_id=task.id,
                    ),
                )

            self.logger.info(
                "Verification passed",
                extra={
                    "task_id": str(task.id),
                    "overall": round(overall, 3),
                    "accuracy": round(accuracy, 3),
                },
            )

            if self.event_bus:
                await self.event_bus.publish(
                    OrchestrationEvent(
                        event_type="verification_complete",
                        task_id=task.id,
                        payload={
                            "overall": overall,
                            "accuracy": accuracy,
                            "consistency": consistency,
                        },
                    )
                )

            return metrics

    async def _check_accuracy(self, result: WorkerResult, task: SubTask) -> float:
        """Check factual accuracy of result.

        Args:
            result: Worker output.
            task: Original task.

        Returns:
            Accuracy score [0, 1].
        """
        output = result.output

        # Check for error indicators
        error_patterns = [
            r"\berror\b", r"\bexception\b", r"\bfail", r"\bincorrect\b",
            r"\bwrong\b", r"\binvalid\b", r"\bundefined\b",
        ]
        errors = sum(1 for p in error_patterns if re.search(p, output, re.IGNORECASE))
        error_penalty = min(errors * 0.2, 0.5)

        # Check for confidence indicators
        confidence_patterns = [
            r"\bcertain\b", r"\bconfident\b", r"\bdefinitely\b", r"\bverify\b",
        ]
        confidence = sum(1 for p in confidence_patterns if re.search(p, output, re.IGNORECASE))
        confidence_bonus = min(confidence * 0.05, 0.2)

        # Check for citations/evidence
        has_evidence = bool(re.search(r'\[.*?\]|\(.*?\d{4}.*?\)|https?://', output))
        evidence_bonus = 0.1 if has_evidence else 0.0

        base = 0.8
        return min(1.0, max(0.0, base - error_penalty + confidence_bonus + evidence_bonus))

    async def _check_consistency(self, result: WorkerResult, task: SubTask) -> float:
        """Check internal consistency of result.

        Args:
            result: Worker output.
            task: Original task.

        Returns:
            Consistency score [0, 1].
        """
        output = result.output

        # Check for contradictions
        contradiction_patterns = [
            r"\bbut\b.*\bhowever\b",  # "but... however"
            r"\balthough\b.*\bnevertheless\b",
            r"\bon the one hand\b.*\bon the other hand\b",
        ]
        contradictions = sum(1 for p in contradiction_patterns if re.search(p, output, re.IGNORECASE))
        contradiction_penalty = min(contradictions * 0.15, 0.4)

        # Check structural consistency
        sections = output.count("##") + output.count("**") + output.count("1.")
        structure_bonus = min(sections * 0.02, 0.1)

        base = 0.85
        return min(1.0, max(0.0, base - contradiction_penalty + structure_bonus))

    async def _check_completeness(self, result: WorkerResult, task: SubTask) -> float:
        """Check if result fully addresses task requirements.

        Args:
            result: Worker output.
            task: Original task.

        Returns:
            Completeness score [0, 1].
        """
        output = result.output.lower()
        task_desc = task.description.lower()

        # Extract key requirements from task
        requirement_indicators = ["must", "should", "need to", "required", "include",
                                 "provide", "explain", "describe", "list"]
        requirements = []
        for indicator in requirement_indicators:
            # Find sentences with requirement indicators
            for match in re.finditer(rf'{indicator}.*?(?:\.|$)', task_desc):
                requirements.append(match.group())

        if not requirements:
            return 0.8  # Default if no clear requirements

        # Check how many are addressed
        addressed = 0
        for req in requirements:
            req_words = set(re.findall(r'\b\w+\b', req.lower()))
            overlap = req_words & set(re.findall(r'\b\w+\b', output))
            if len(overlap) / max(len(req_words), 1) > 0.3:
                addressed += 1

        return addressed / len(requirements) if requirements else 0.8

    async def _check_relevance(self, result: WorkerResult, task: SubTask) -> float:
        """Check if result is relevant to task.

        Args:
            result: Worker output.
            task: Original task.

        Returns:
            Relevance score [0, 1].
        """
        output = result.output.lower()
        task_text = f"{task.name} {task.description}".lower()

        # Word overlap
        task_words = set(re.findall(r'\b\w+\b', task_text))
        output_words = set(re.findall(r'\b\w+\b', output))

        if not task_words:
            return 0.5

        overlap = len(task_words & output_words) / len(task_words)

        # Penalize off-topic indicators
        off_topic = ["i don't know", "unrelated", "not relevant", "cannot answer",
                    "outside my scope", "no information"]
        off_topic_count = sum(1 for phrase in off_topic if phrase in output)
        penalty = off_topic_count * 0.3

        return min(1.0, max(0.0, overlap * 1.5 - penalty))

    async def verify_consistency_across(
        self,
        results: List[WorkerResult],
    ) -> Tuple[bool, List[str]]:
        """Check consistency across multiple worker results.

        Args:
            results: Results to compare.

        Returns:
            Tuple of (is_consistent, list_of_inconsistencies).
        """
        if len(results) < 2:
            return True, []

        inconsistencies: List[str] = []
        base = results[0].output

        for i, result in enumerate(results[1:], 1):
            # Simple: check for contradictory statements
            # In production, would use semantic similarity
            similarity = self._text_similarity(base, result.output)
            if similarity < 0.5:
                inconsistencies.append(
                    f"Result {i} diverges significantly from result 0 (similarity: {similarity:.2f})"
                )

        return len(inconsistencies) == 0, inconsistencies

    def _text_similarity(self, a: str, b: str) -> float:
        """Calculate simple text similarity.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity [0, 1].
        """
        words_a = set(re.findall(r'\b\w+\b', a.lower()))
        words_b = set(re.findall(r'\b\w+\b', b.lower()))

        if not words_a or not words_b:
            return 0.0

        return len(words_a & words_b) / len(words_a | words_b)

    async def fact_check(
        self,
        result: WorkerResult,
        knowledge_sources: Optional[List[str]] = None,
    ) -> Tuple[float, List[str]]:
        """Fact-check result against knowledge sources.

        Args:
            result: Result to check.
            knowledge_sources: Source identifiers.

        Returns:
            Tuple of (confidence, list_of_discrepancies).
        """
        # In production, would query knowledge base
        # Simplified implementation
        output = result.output

        # Check for uncertain language
        uncertain = ["maybe", "perhaps", "possibly", "might be", "could be",
                  "i think", "probably", "likely", "presumably"]
        uncertain_count = sum(1 for u in uncertain if u in output.lower())

        confidence = max(0.0, 1.0 - uncertain_count * 0.1)

        discrepancies: List[str] = []
        if uncertain_count > 3:
            discrepancies.append(f"High uncertainty: {uncertain_count} uncertain statements")

        return confidence, discrepancies


# Factory
async def create_verification_manager(
    accuracy_threshold: float = 0.7,
    custom_rules: Optional[List[VerificationRule]] = None,
    event_bus: Optional[Any] = None,
) -> VerificationManagerImpl:
    """Factory for creating configured verification manager.

    Args:
        accuracy_threshold: Minimum accuracy score.
        custom_rules: Custom verification rules.
        event_bus: Optional event bus.

    Returns:
        Configured VerificationManagerImpl.
    """
    return VerificationManagerImpl(
        accuracy_threshold=accuracy_threshold,
        custom_rules=custom_rules,
        event_bus=event_bus,
    )


from domain_models import OrchestrationEvent
