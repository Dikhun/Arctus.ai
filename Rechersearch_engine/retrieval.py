# arctus_research_engine/pipeline/retrieval.py
"""Multi-source retrieval with deduplication and hybrid ranking."""

import asyncio
from datetime import datetime
from typing import Listfrom arctus_research_engine.interfaces import IModelGateway, ITelemetry
from arctus_research_engine.models import (
    EvidenceRecord,
    ExecutionMode,
    RankedEvidenceCollection,
    RawDocument,
    SearchQuery,
)
from arctus_research_engine.plugins.base import ExecutionContext, RankingStrategy, RetrievalAdapter


class RetrievalSubsystem:
    """Stateless retrieval executor. Scales horizontally with engine replicas."""

    def __init__(
        self,
        adapters: List[RetrievalAdapter],
        ranking_strategy: RankingStrategy,
        embedder: IModelGateway,
        telemetry: ITelemetry,
        max_concurrent_adapters: int = 10,
    ):
        self._adapters = adapters
        self._ranking = ranking_strategy
        self._embedder = embedder
        self._telemetry = telemetry
        self._semaphore = asyncio.Semaphore(max_concurrent_adapters)

    async def execute(
        self,
        query: SearchQuery,
        context: ExecutionContext,
 http_client: Any,  # IHttpClient injected by orchestrator
    ) -> RankedEvidenceCollection:
        async with self._telemetry.start_span("research.retrieve", {
            "correlation_id": context.correlation_id,
            "query": query.text,
        }):
            # Concurrent recall across all adapters
            recall_tasks = [
                self._retrieve_with_limit(adapter, query, http_client, context)
                for adapter in self._adapters
            ]
            results_per_adapter = await asyncio.gather(*recall_tasks, return_exceptions=True)
            all_docs: List[RawDocument] = []
            for res in results_per_adapter:
                if isinstance(res, Exception):
                    await self._telemetry.log("warning", "Adapter retrieval failed", {
                        "error": str(res),
                        "correlation_id": context.correlation_id,
                    })
 continue
                all_docs.extend(res)

            # Deduplicate by content hash
            unique_docs: List[RawDocument] = []
            seen_hashes = set()
            for doc in all_docs:
                if doc.content_hash not in seen_hashes:
                    seen_hashes.add(doc.content_hash)
                    unique_docs.append(doc)

            # Rank
            ranked_records = await self._ranking.rank(
                unique_docs, query, self._embedder, context
            )
            return RankedEvidenceCollection(records=ranked_records)

    async def _retrieve_with_limit(
        self,
        adapter: RetrievalAdapter,
        query: SearchQuery,
        http_client: Any,
        context: ExecutionContext,
    ) -> List[RawDocument]:
        async with self._semaphore:
            return await adapter.retrieve(query, http_client, context)
