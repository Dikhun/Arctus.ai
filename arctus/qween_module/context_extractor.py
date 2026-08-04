"""Arctus AI Orchestration Framework - Context Extractor.

Responsible for relevant context selection, conversation compression,
context isolation, and token optimization.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from domain_models import SubTask
from exceptions import ErrorContext, MemoryException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("context_extractor")


class ContextExtractorImpl:
    """Production context extractor with semantic relevance scoring.

    Selects and compresses conversation history to fit within token
    budgets while preserving task-relevant information.
    """

    # Approximate tokens per word
    TOKENS_PER_WORD = 1.3

    def __init__(
        self,
        max_context_tokens: int = 8000,
        relevance_threshold: float = 0.3,
        compression_ratio: float = 0.5,
        enable_summarization: bool = True,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.relevance_threshold = relevance_threshold
        self.compression_ratio = compression_ratio
        self.enable_summarization = enable_summarization
        self.logger = get_logger("context_extractor")

    @async_timed
    async def extract(
        self,
        task: SubTask,
        conversation_history: List[Dict[str, Any]],
        max_tokens: int,
    ) -> str:
        """Extract relevant context for a task.

        Args:
            task: The subtask requiring context.
            conversation_history: Full conversation history.
            max_tokens: Maximum tokens for context window.

        Returns:
            Optimized context string.
        """
        with LogContext(module="context_extractor", operation="extract", task_id=task.id):
            if not conversation_history:
                return ""

            self.logger.info(
                "Extracting context",
                extra={
                    "task_id": str(task.id),
                    "history_items": len(conversation_history),
                    "max_tokens": max_tokens,
                },
            )

            # Score relevance of each history item
            scored = [
                (item, self._score_relevance(task, item))
                for item in conversation_history
            ]

            # Filter by threshold and sort by relevance
            relevant = [
                (item, score) for item, score in scored
                if score >= self.relevance_threshold
            ]
            relevant.sort(key=lambda x: x[1], reverse=True)

            # Build context within token budget
            selected: List[Dict[str, Any]] = []
            current_tokens = 0
            budget = min(max_tokens, self.max_context_tokens)

            for item, score in relevant:
                item_tokens = self._estimate_tokens(item)
                if current_tokens + item_tokens <= budget:
                    selected.append(item)
                    current_tokens += item_tokens
                else:
                    break

            # Sort selected back to chronological order
            selected.sort(key=lambda x: x.get("timestamp", ""))

            # Compress if still over budget
            result = self._format_context(selected)
            result_tokens = self._estimate_text_tokens(result)

            if result_tokens > budget and self.enable_summarization:
                result = await self._summarize(result, budget)

            self.logger.info(
                "Context extracted",
                extra={
                    "task_id": str(task.id),
                    "selected_items": len(selected),
                    "output_tokens": self._estimate_text_tokens(result),
                },
            )

            return result

    def _score_relevance(self, task: SubTask, history_item: Dict[str, Any]) -> float:
        """Score relevance of history item to task.

        Args:
            task: Current task.
            history_item: Conversation history entry.

        Returns:
            Relevance score [0, 1].
        """
        text = self._extract_text(history_item).lower()
        task_text = f"{task.name} {task.description}".lower()
        task_caps = " ".join(task.required_capabilities).lower()

        scores: List[float] = []

        # Keyword overlap
        task_words = set(re.findall(r'\b\w+\b', task_text))
        text_words = set(re.findall(r'\b\w+\b', text))
        if task_words:
            overlap = len(task_words & text_words) / len(task_words)
            scores.append(overlap)

        # Capability mention
        cap_words = set(re.findall(r'\b\w+\b', task_caps))
        if cap_words:
            cap_overlap = len(cap_words & text_words) / len(cap_words)
            scores.append(cap_overlap * 1.5)  # Boost capability matches

        # Recency boost (if timestamp available)
        if "timestamp" in history_item:
            # Would calculate actual recency; simplified
            scores.append(0.5)

        # User vs assistant weighting
        if history_item.get("role") == "user":
            scores.append(0.3)  # User messages slightly more relevant

        return min(1.0, sum(scores) / max(len(scores), 1)) if scores else 0.0

    def _extract_text(self, history_item: Dict[str, Any]) -> str:
        """Extract text content from history item.

        Args:
            history_item: History entry.

        Returns:
            Extracted text.
        """
        if isinstance(history_item, dict):
            return history_item.get("content", "") or history_item.get("text", "")
        return str(history_item)

    def _estimate_tokens(self, history_item: Dict[str, Any]) -> int:
        """Estimate token count for history item.

        Args:
            history_item: History entry.

        Returns:
            Estimated tokens.
        """
        text = self._extract_text(history_item)
        return self._estimate_text_tokens(text)

    def _estimate_text_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate.

        Returns:
            Estimated tokens.
        """
        words = len(text.split())
        return int(words * self.TOKENS_PER_WORD)

    def _format_context(self, items: List[Dict[str, Any]]) -> str:
        """Format selected items into context string.

        Args:
            items: Selected history items.

        Returns:
            Formatted context string.
        """
        parts: List[str] = []
        for item in items:
            role = item.get("role", "unknown")
            content = self._extract_text(item)
            parts.append(f"[{role.upper()}]: {content}")

        return "\n\n".join(parts)

    async def _summarize(self, text: str, target_tokens: int) -> str:
        """Summarize text to fit target token budget.

        Args:
            text: Text to summarize.
            target_tokens: Target token count.

        Returns:
            Summarized text.
        """
        current_tokens = self._estimate_text_tokens(text)
        if current_tokens <= target_tokens:
            return text

        # Simple extractive summarization: keep first and last parts, truncate middle
        target_words = int(target_tokens / self.TOKENS_PER_WORD)

        words = text.split()
        if len(words) <= target_words:
            return text

        # Keep 30% from start, 20% from end
        start_keep = int(target_words * 0.3)
        end_keep = int(target_words * 0.2)
        middle = target_words - start_keep - end_keep

        summary = (
            " ".join(words[:start_keep]) +
            f"\n\n... [{len(words) - start_keep - end_keep} words omitted] ...\n\n" +
            " ".join(words[-end_keep:])
        )

        return summary

    async def compress_conversation(
        self,
        conversation_history: List[Dict[str, Any]],
        compression_target: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Compress conversation history while preserving semantics.

        Args:
            conversation_history: Full conversation history.
            compression_target: Target compression ratio.

        Returns:
            Compressed history.
        """
        if not conversation_history:
            return []

        # Remove redundant or low-value turns
        filtered: List[Dict[str, Any]] = []
        last_content = ""

        for item in conversation_history:
            content = self._extract_text(item)
            # Skip duplicate or near-duplicate content
            if self._similarity(content, last_content) < 0.8:
                filtered.append(item)
                last_content = content

        # If still too long, summarize chunks
        total_tokens = sum(self._estimate_tokens(i) for i in filtered)
        target_tokens = total_tokens * compression_target

        if total_tokens <= target_tokens:
            return filtered

        # Summarize in chunks
        compressed: List[Dict[str, Any]] = []
        chunk: List[Dict[str, Any]] = []
        chunk_tokens = 0

        for item in filtered:
            item_tokens = self._estimate_tokens(item)
            if chunk_tokens + item_tokens > target_tokens / 3 and chunk:
                # Summarize chunk
                chunk_text = self._format_context(chunk)
                summary_text = await self._summarize(chunk_text, int(target_tokens / 3))
                compressed.append({
                    "role": "system",
                    "content": f"Summary of previous conversation: {summary_text}",
                    "timestamp": chunk[0].get("timestamp"),
                })
                chunk = []
                chunk_tokens = 0

            chunk.append(item)
            chunk_tokens += item_tokens

        if chunk:
            compressed.extend(chunk)

        return compressed

    def _similarity(self, a: str, b: str) -> float:
        """Calculate simple word overlap similarity.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity score [0, 1].
        """
        words_a = set(re.findall(r'\b\w+\b', a.lower()))
        words_b = set(re.findall(r'\b\w+\b', b.lower()))
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    async def isolate_context(
        self,
        task: SubTask,
        full_context: str,
    ) -> str:
        """Isolate context specific to task, removing irrelevant parts.

        Args:
            task: Task to isolate context for.
            full_context: Full context string.

        Returns:
            Isolated context.
        """
        # Extract sentences most relevant to task
        sentences = re.split(r'(?<=[.!?])\s+', full_context)
        task_words = set(re.findall(r'\b\w+\b', f"{task.name} {task.description}".lower()))

        scored = []
        for sentence in sentences:
            words = set(re.findall(r'\b\w+\b', sentence.lower()))
            overlap = len(words & task_words) / max(len(words), 1)
            scored.append((sentence, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Take top sentences up to context window
        selected = []
        total_tokens = 0
        budget = task.context_window_size

        for sentence, score in scored:
            tokens = self._estimate_text_tokens(sentence)
            if total_tokens + tokens <= budget:
                selected.append(sentence)
                total_tokens += tokens

        return " ".join(selected)


# Factory
async def create_context_extractor(
    max_context_tokens: int = 8000,
    relevance_threshold: float = 0.3,
    event_bus: Optional[Any] = None,
) -> ContextExtractorImpl:
    """Factory for creating configured context extractor.

    Args:
        max_context_tokens: Maximum context window size.
        relevance_threshold: Minimum relevance score.
        event_bus: Optional event bus.

    Returns:
        Configured ContextExtractorImpl.
    """
    return ContextExtractorImpl(
        max_context_tokens=max_context_tokens,
        relevance_threshold=relevance_threshold,
    )


from domain_models import OrchestrationEvent
