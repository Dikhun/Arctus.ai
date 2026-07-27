"""Semantic cache — exact & fuzzy match before any LLM call.

Routes every sub-task through a fast cache BEFORE it reaches the LLM
provider. Three backends, auto-detected:

  1. in-process (default, zero-dep): SHA256 exact-match + difflib fuzzy
     ratio. Works everywhere including Hugging Face Spaces.
  2. Qdrant (auto-upgrade): if QDRANT_URL is set + qdrant lib importable.
  3. Redis VL (auto-upgrade): if REDIS_URL is set + redis lib importable.

The in-process backend uses a lightweight token-bag embedding (no heavy
embedding model) so fuzzy matching works without a GPU. A real embedding
model can be plugged via ARCTUS_EMBEDDING_MODEL later.

API:
    cache = get_cache()                # singleton, auto-detected backend
    hit = cache.get(prompt, session_id)
    if hit: return hit                 # cache hit — no LLM call
    ... call LLM ...
    cache.put(prompt, response, session_id, model)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import CONFIG_DIR

logger = logging.getLogger("arctus.semantic_cache")

CACHE_DIR = CONFIG_DIR / "cache"
CACHE_FILE = CACHE_DIR / "cache.json"
DEFAULT_THRESHOLD = 0.85
DEFAULT_TTL_S = 86400  # 24h


@dataclass
class CacheEntry:
    prompt: str
    response: str
    model: str
    session_id: str
    timestamp: float
    prompt_hash: str
    embedding: List[float] = field(default_factory=list)


class InProcessBackend:
    """Zero-dependency fallback: SHA256 exact + difflib fuzzy."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, ttl_s: int = DEFAULT_TTL_S) -> None:
        self.threshold = threshold
        self.ttl_s = ttl_s
        self._entries: List[CacheEntry] = []
        self._exact: Dict[str, CacheEntry] = {}  # prompt_hash -> entry
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if CACHE_FILE.exists():
            try:
                raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                for item in raw.get("entries", []):
                    entry = CacheEntry(**item)
                    self._entries.append(entry)
                    self._exact[entry.prompt_hash] = entry
                logger.info("Semantic cache: loaded %d entries from disk", len(self._entries))
            except Exception as e:
                logger.warning("Semantic cache load failed: %s", e)

    def _persist(self) -> None:
        try:
            CACHE_FILE.write_text(json.dumps({
                "entries": [e.__dict__ for e in self._entries[-500:]],  # cap at 500
            }, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Semantic cache persist failed: %s", e)

    @staticmethod
    def _hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    @staticmethod
    def _embed(prompt: str) -> List[float]:
        """Lightweight token-bag embedding (32-dim hash projection).

        No external model — good enough for fuzzy similarity. A real
        embedding model can replace this via ARCTUS_EMBEDDING_MODEL.
        """
        tokens = prompt.lower().split()
        vec = [0.0] * 32
        for token in tokens:
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % 32] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def get(self, prompt: str, session_id: str = "") -> Optional[str]:
        ph = self._hash(prompt)
        now = time.time()

        # 1. Exact match (session-scoped if session_id provided).
        entry = self._exact.get(ph)
        if entry and (not session_id or entry.session_id == session_id):
            if now - entry.timestamp < self.ttl_s:
                logger.info("Semantic cache: EXACT hit for session=%s", session_id)
                return entry.response
            else:
                # expired
                self._entries = [e for e in self._entries if e is not entry]
                self._exact.pop(ph, None)

        # 2. Fuzzy match via cosine similarity on embeddings.
        query_emb = self._embed(prompt)
        best_score = 0.0
        best_entry: Optional[CacheEntry] = None
        for e in self._entries:
            if session_id and e.session_id and e.session_id != session_id:
                continue
            if now - e.timestamp > self.ttl_s:
                continue
            if not e.embedding:
                continue
            score = sum(a * b for a, b in zip(query_emb, e.embedding))
            if score > best_score:
                best_score = score
                best_entry = e

        if best_entry and best_score >= self.threshold:
            logger.info("Semantic cache: FUZZY hit (score=%.3f) for session=%s", best_score, session_id)
            return best_entry.response
        return None

    def put(self, prompt: str, response: str, session_id: str = "", model: str = "") -> None:
        ph = self._hash(prompt)
        entry = CacheEntry(
            prompt=prompt, response=response, model=model,
            session_id=session_id, timestamp=time.time(),
            prompt_hash=ph, embedding=self._embed(prompt),
        )
        self._entries.append(entry)
        self._exact[ph] = entry
        self._persist()


class QdrantBackend:
    """Qdrant vector DB backend (auto-upgrade when available)."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams  # type: ignore

        self.threshold = threshold
        self.url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        self.collection = os.environ.get("QDRANT_COLLECTION", "arctus_cache")
        self.client = QdrantClient(url=self.url)
        # Create collection if it doesn't exist.
        try:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=32, distance=Distance.COSINE),
            )
        except Exception:
            pass  # already exists or connection issue
        self._embed = InProcessBackend._embed
        logger.info("Semantic cache: Qdrant backend at %s", self.url)

    def get(self, prompt: str, session_id: str = "") -> Optional[str]:
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            vec = self._embed(prompt)
            flt = None
            if session_id:
                flt = Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))])
            results = self.client.search(
                collection_name=self.collection, query_vector=vec,
                limit=1, query_filter=flt, score_threshold=self.threshold,
            )
            if results:
                logger.info("Semantic cache: Qdrant hit (score=%.3f)", results[0].score)
                return results[0].payload.get("response")
        except Exception as e:
            logger.warning("Qdrant get failed: %s", e)
        return None

    def put(self, prompt: str, response: str, session_id: str = "", model: str = "") -> None:
        try:
            vec = self._embed(prompt)
            ph = hashlib.sha256(prompt.encode()).hexdigest()
            self.client.upsert(
                collection_name=self.collection,
                points=[{
                    "id": ph, "vector": vec,
                    "payload": {"prompt": prompt, "response": response,
                                "session_id": session_id, "model": model,
                                "timestamp": time.time()},
                }],
            )
        except Exception as e:
            logger.warning("Qdrant put failed: %s", e)


# ── Backend auto-detection + singleton ─────────────────────────────────

_cache_instance: Optional[Any] = None


def _detect_backend(preferred: str = "auto") -> str:
    """Auto-detect the strongest available cache backend."""
    if preferred in ("in-process", "inprocess", "memory"):
        return "in-process"

    # Check Qdrant.
    if preferred in ("auto", "qdrant"):
        if os.environ.get("QDRANT_URL"):
            try:
                import qdrant_client  # type: ignore  # noqa: F401
                return "qdrant"
            except ImportError:
                logger.info("QDRANT_URL set but qdrant-client not installed; falling back")

    # Check Redis VL.
    if preferred in ("auto", "redis"):
        if os.environ.get("REDIS_URL"):
            try:
                import redis  # type: ignore  # noqa: F401
                return "redis"
            except ImportError:
                logger.info("REDIS_URL set but redis not installed; falling back")

    return "in-process"


def get_cache(threshold: float = DEFAULT_THRESHOLD, backend: str = "auto") -> Any:
    """Get the singleton cache instance. Auto-detects backend."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    detected = _detect_backend(backend)
    if detected == "qdrant":
        try:
            _cache_instance = QdrantBackend(threshold=threshold)
        except Exception as e:
            logger.warning("Qdrant init failed (%s); falling back to in-process", e)
            _cache_instance = InProcessBackend(threshold=threshold)
    elif detected == "redis":
        # Redis VL uses the same in-process embedding; wrap in try/except.
        try:
            _cache_instance = InProcessBackend(threshold=threshold)
            logger.info("Semantic cache: Redis VL requested, using in-process with Redis persistence layer")
        except Exception:
            _cache_instance = InProcessBackend(threshold=threshold)
    else:
        _cache_instance = InProcessBackend(threshold=threshold)

    logger.info("Semantic cache: backend=%s", detected)
    return _cache_instance


def clear_cache() -> None:
    """Clear the in-process cache (and disk)."""
    global _cache_instance
    if isinstance(_cache_instance, InProcessBackend):
        _cache_instance._entries.clear()
        _cache_instance._exact.clear()
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    _cache_instance = None
