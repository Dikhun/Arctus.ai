import asyncio
import datetime
import hashlib
import math
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

import aiofiles
import datasets
import duckdb
import fsspec
import httpx
import polars as pl
import structlog
from huggingface_hub import HfApi
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import retry, stop_after_attempt, wait_exponential

# --- CONFIGURATION ---
class ServiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCTUS_HF_", env_file=".env", extra="ignore")
    HF_TOKEN: str = Field(default="", description="Hugging Face API Access Token")
    STORAGE_BACKEND: Literal["local", "s3", "gcs", "azure"] = "local"
    LOCAL_CACHE_DIR: Path = Path("./agent_workspace/datasets")
    CHUNK_SIZE_MB: int = 8
    DOWNLOAD_TIMEOUT_SECONDS: float = 600.0

config = ServiceConfig()
logger = structlog.get_logger()

# --- MODELS ---
class DatasetFormat(str, Enum):
    PARQUET = "parquet"
    CSV = "csv"
    JSONL = "jsonl"
    DUCKDB = "duckdb"

class DatasetMetadata(BaseModel):
    id: str
    author: str
    dataset_name: str
    description: Optional[str] = None
    downloads: int = 0
    likes: int = 0
    tags: List[str] = Field(default_factory=list)
    last_modified: datetime.datetime
    score: float = 0.0

class SearchQuery(BaseModel):
    natural_language_query: str
    limit: int = 10

class DatasetReference(BaseModel):
    dataset_id: str
    session_id: str
    ref_count: int = 1

# --- CORE ENGINES ---
class DatasetRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, DatasetReference] = {}
        self._global_lock = asyncio.Lock()

    async def register(self, dataset_id: str, session_id: str) -> DatasetReference:
        key = f"{session_id}:{dataset_id}"
        async with self._global_lock:
            if key in self._registry:
                self._registry[key].ref_count += 1
            else:
                self._registry[key] = DatasetReference(dataset_id=dataset_id, session_id=session_id)
            return self._registry[key]

class DatasetRanker:
    @staticmethod
    def rank_datasets(datasets: List[DatasetMetadata], query: str) -> List[DatasetMetadata]:
        terms = [t for t in query.split() if len(t) > 2]
        for ds in datasets:
            score = math.log10(ds.downloads + 1) * 2.0 + math.log10(ds.likes + 1) * 3.0
            searchable_text = f"{ds.id} {ds.description or ''} {' '.join(ds.tags)}".lower()
            for term in terms:
                if term.lower() in searchable_text:
                    score += 10.0
            ds.score = round(score, 4)
        return sorted(datasets, key=lambda x: x.score, reverse=True)

class SearchEngine:
    def __init__(self) -> None:
        self.api = HfApi(token=config.HF_TOKEN or None)

    async def search(self, query: SearchQuery) -> List[DatasetMetadata]:
        loop = asyncio.get_running_loop()
        def _fetch() -> List[DatasetMetadata]:
            raw = self.api.list_datasets(search=query.natural_language_query, limit=query.limit * 2, full=True)
            return [
                DatasetMetadata(
                    id=ds.id, author=ds.author or "unknown", dataset_name=ds.id.split("/")[-1],
                    description=ds.description, downloads=ds.downloads or 0, likes=ds.likes or 0,
                    tags=ds.tags or [], last_modified=ds.lastModified
                ) for ds in raw
            ]
        results = await loop.run_in_executor(None, _fetch)
        return DatasetRanker.rank_datasets(results, query.natural_language_query)[:query.limit]

class DownloadEngine:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=config.DOWNLOAD_TIMEOUT_SECONDS)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def download_file(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            async with aiofiles.open(destination, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=config.CHUNK_SIZE_MB * 1024 * 1024):
                    await f.write(chunk)
        return destination
          # Inside this existing agent script
import aiofiles
import httpx
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from hf_dataset_tool import SearchEngine, SearchQuery, DownloadEngine

class DownloadEngine:
    async def download_file(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        async with httpx.AsyncClient(timeout=config.DOWNLOAD_TIMEOUT_SECONDS) as client:
            @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
            async def _stream():
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    async with aiofiles.open(destination, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=config.CHUNK_SIZE_MB * 1024 * 1024):
                            await f.write(chunk)

            await _stream()
        return destination

async def agent_task():
    search = SearchEngine()
    
    query = SearchQuery(natural_language_query="finance data", limit=1)
    results = await search.search(query)
    
    if results:
        print(f"Found dataset: {results[0].id}")
