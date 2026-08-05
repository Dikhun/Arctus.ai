#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Checkpoint & Snapshot Engine
================================================================
Production-grade checkpoint system capturing complete orchestration
runtime state with atomic snapshots, incremental diffs, encryption,
deduplication, and cross-node restoration capabilities.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import pickle
import struct
import tempfile
import time
import uuid
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    Union,
)
from contextlib import asynccontextmanager
import heapq

# Optional crypto dependencies - falls back to AES via cryptography
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Configure enterprise logging
logger = logging.getLogger("arctus.checkpoint")
logger.setLevel(logging.DEBUG)

# ============================================================================
# ENUMERATIONS & CONSTANTS
# ============================================================================

class SnapshotType(Enum):
    FULL = auto()
    INCREMENTAL = auto()
    AUTOMATIC = auto()
    MANUAL = auto()
    SCHEDULED = auto()

class SnapshotStatus(Enum):
    PENDING = auto()
    CAPTURING = auto()
    VALIDATING = auto()
    COMPLETED = auto()
    FAILED = auto()
    RESTORING = auto()

class CompressionAlgorithm(Enum):
    NONE = auto()
    ZLIB = auto()
    LZ4 = auto()  # Placeholder for lz4
    ZSTD = auto()  # Placeholder for zstd

class EncryptionAlgorithm(Enum):
    NONE = auto()
    AES256_GCM = auto()
    CHACHA20_POLY1305 = auto()

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Immutable snapshot metadata for integrity verification."""
    snapshot_id: str
    version: int
    snapshot_type: SnapshotType
    status: SnapshotStatus
    created_at: datetime
    parent_snapshot_id: Optional[str] = None
    root_hash: str = ""
    size_bytes: int = 0
    compressed_size_bytes: int = 0
    compression: CompressionAlgorithm = CompressionAlgorithm.ZLIB
    encryption: EncryptionAlgorithm = EncryptionAlgorithm.NONE
    tenant_id: str = "default"
    workspace_id: str = "default"
    agent_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    capture_targets: List[str] = field(default_factory=list)

    def to_bytes(self) -> bytes:
        """Canonical serialization for signing/verification."""
        data = {
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "snapshot_type": self.snapshot_type.name,
            "created_at": self.created_at.isoformat(),
            "parent_snapshot_id": self.parent_snapshot_id,
            "root_hash": self.root_hash,
            "size_bytes": self.size_bytes,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "tags": dict(sorted(self.tags.items())),
            "capture_targets": sorted(self.capture_targets),
        }
        return json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def compute_hash(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


@dataclass(slots=True)
class RuntimeState:
    """Complete orchestration runtime state capture."""
    agent_state: Dict[str, Any]
    execution_plan: Dict[str, Any]
    memory_state: Dict[str, Any]
    filesystem_metadata: Dict[str, Any]
    browser_session_ref: Optional[str]
    terminal_session_ref: Optional[str]
    vm_state_ref: Optional[str]
    environment_variables: Dict[str, str]
    task_queue: List[Dict[str, Any]]
    resource_allocations: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    checkpoint_sequence: int = 0

    def fingerprint(self) -> str:
        """Compute deterministic fingerprint for deduplication."""
        canonical = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.blake2b(canonical.encode(), digest_size=16).hexdigest()


@dataclass(slots=True)
class Snapshot:
    """Complete snapshot with metadata and payload."""
    metadata: SnapshotMetadata
    state: Optional[RuntimeState] = None
    payload: bytes = b""  # Serialized, compressed, encrypted state
    manifest: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Verify snapshot integrity."""
        if not self.payload:
            return self.metadata.status == SnapshotStatus.FAILED
        computed = hashlib.sha256(self.payload).hexdigest()
        return computed == self.metadata.root_hash


# ============================================================================
# STORAGE BACKENDS (Protocol + Implementations)
# ============================================================================

class StorageBackend(Protocol):
    """Abstract storage backend for snapshot persistence."""
    
    async def write(self, key: str, data: bytes, metadata: Dict[str, Any]) -> bool: ...
    async def read(self, key: str) -> Tuple[bytes, Dict[str, Any]]: ...
    async def delete(self, key: str) -> bool: ...
    async def list_keys(self, prefix: str = "") -> List[str]: ...
    async def exists(self, key: str) -> bool: ...


class FilesystemStorageBackend:
    """Local filesystem storage backend."""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.base_path / ".meta"
        self.meta_path.mkdir(exist_ok=True)
    
    def _path(self, key: str) -> Path:
        # Shard by first 2 chars of key for filesystem performance
        shard = key[:2] if len(key) >= 2 else "xx"
        shard_dir = self.base_path / shard
        shard_dir.mkdir(exist_ok=True)
        return shard_dir / f"{key}.snap"
    
    async def write(self, key: str, data: bytes, metadata: Dict[str, Any]) -> bool:
        loop = asyncio.get_event_loop()
        path = self._path(key)
        meta_file = self.meta_path / f"{key}.json"
        
        def _write():
            path.write_bytes(data)
            meta_file.write_text(json.dumps(metadata, default=str))
            return True
        
        return await loop.run_in_executor(None, _write)
    
    async def read(self, key: str) -> Tuple[bytes, Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        path = self._path(key)
        meta_file = self.meta_path / f"{key}.json"
        
        def _read():
            data = path.read_bytes()
            meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
            return data, meta
        
        return await loop.run_in_executor(None, _read)
    
    async def delete(self, key: str) -> bool:
        loop = asyncio.get_event_loop()
        path = self._path(key)
        meta_file = self.meta_path / f"{key}.json"
        
        def _delete():
            try:
                path.unlink(missing_ok=True)
                meta_file.unlink(missing_ok=True)
                return True
            except Exception:
                return False
        
        return await loop.run_in_executor(None, _delete)
    
    async def list_keys(self, prefix: str = "") -> List[str]:
        loop = asyncio.get_event_loop()
        
        def _list():
            keys = []
            for snap_file in self.base_path.rglob("*.snap"):
                key = snap_file.stem
                if key.startswith(prefix):
                    keys.append(key)
            return keys
        
        return await loop.run_in_executor(None, _list)
    
    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


# ============================================================================
# COMPRESSION & ENCRYPTION
# ============================================================================

class CompressionEngine:
    """Pluggable compression engine."""
    
    ALGORITHMS: Dict[CompressionAlgorithm, Callable[[bytes], bytes]] = {
        CompressionAlgorithm.NONE: lambda d: d,
        CompressionAlgorithm.ZLIB: lambda d: zlib.compress(d, level=6),
    }
    
    DECOMPRESSORS: Dict[CompressionAlgorithm, Callable[[bytes], bytes]] = {
        CompressionAlgorithm.NONE: lambda d: d,
        CompressionAlgorithm.ZLIB: zlib.decompress,
    }
    
    @classmethod
    def compress(cls, data: bytes, algo: CompressionAlgorithm) -> bytes:
        compressor = cls.ALGORITHMS.get(algo, cls.ALGORITHMS[CompressionAlgorithm.ZLIB])
        return compressor(data)
    
    @classmethod
    def decompress(cls, data: bytes, algo: CompressionAlgorithm) -> bytes:
        decompressor = cls.DECOMPRESSORS.get(algo, cls.DECOMPRESSORS[CompressionAlgorithm.ZLIB])
        return decompressor(data)


class EncryptionEngine:
    """AES-256-GCM encryption engine."""
    
    def __init__(self, master_key: Optional[bytes] = None):
        self.master_key = master_key or os.urandom(32)
        self._key_cache: Dict[str, bytes] = {}
    
    def _derive_key(self, salt: bytes) -> bytes:
        if not CRYPTO_AVAILABLE:
            # Fallback: simple XOR-based obfuscation (NOT for production without cryptography)
            return bytes(a ^ b for a, b in zip(self.master_key, salt * (32 // len(salt) + 1)))
        cache_key = salt.hex()
        if cache_key not in self._key_cache:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            self._key_cache[cache_key] = kdf.derive(self.master_key)
        return self._key_cache[cache_key]
    
    def encrypt(self, data: bytes) -> Tuple[bytes, bytes]:  # (ciphertext, nonce+tag)
        if not CRYPTO_AVAILABLE:
            # Obfuscation fallback
            salt = os.urandom(16)
            key = self._derive_key(salt)
            obfuscated = bytes(a ^ b for a, b in zip(data, key * (len(data) // 32 + 1)))
            return salt + obfuscated, b""
        
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        salt = os.urandom(16)
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return salt + nonce + ciphertext, b""
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        if not CRYPTO_AVAILABLE:
            salt = ciphertext[:16]
            obfuscated = ciphertext[16:]
            key = self._derive_key(salt)
            return bytes(a ^ b for a, b in zip(obfuscated, key * (len(obfuscated) // 32 + 1)))
        
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt = ciphertext[:16]
        nonce = ciphertext[16:28]
        encrypted = ciphertext[28:]
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, encrypted, None)


# ============================================================================
# DEDUPLICATION ENGINE
# ============================================================================

class DeduplicationEngine:
    """Content-addressable deduplication using Merkle-style chunking."""
    
    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size
        self.chunk_store: Dict[str, bytes] = {}
        self.ref_count: Dict[str, int] = defaultdict(int)
    
    def chunk_data(self, data: bytes) -> List[str]:
        """Simple fixed-size chunking with Rabin fingerprinting placeholder."""
        chunks = []
        for i in range(0, len(data), self.chunk_size):
            chunk = data[i:i + self.chunk_size]
            chunk_hash = hashlib.blake2b(chunk, digest_size=16).hexdigest()
            if chunk_hash not in self.chunk_store:
                self.chunk_store[chunk_hash] = chunk
            self.ref_count[chunk_hash] += 1
            chunks.append(chunk_hash)
        return chunks
    
    def reassemble(self, chunk_hashes: List[str]) -> bytes:
        """Reassemble data from chunk hashes."""
        return b"".join(self.chunk_store[h] for h in chunk_hashes if h in self.chunk_store)
    
    def get_manifest(self, data: bytes) -> Dict[str, Any]:
        """Get deduplication manifest for data."""
        chunks = self.chunk_data(data)
        unique = len(set(chunks))
        return {
            "chunk_hashes": chunks,
            "total_chunks": len(chunks),
            "unique_chunks": unique,
            "dedup_ratio": (len(chunks) - unique) / max(len(chunks), 1),
        }


# ============================================================================
# CHECKPOINT ENGINE CORE
# ============================================================================

class CheckpointEngine:
    """
    Production-grade checkpoint and snapshot engine.
    
    Features:
    - Automatic, manual, and scheduled checkpoints
    - Full and incremental snapshots
    - Atomic snapshot capture with consistency validation
    - Compression, encryption, deduplication
    - Cross-node restoration and crash recovery
    - Snapshot versioning and garbage collection
    """
    
    def __init__(
        self,
        storage: StorageBackend,
        encryption_engine: Optional[EncryptionEngine] = None,
        dedup_engine: Optional[DeduplicationEngine] = None,
        checkpoint_interval_seconds: float = 300.0,
        retention_count: int = 10,
        retention_days: int = 30,
    ):
        self.storage = storage
        self.encryption = encryption_engine or EncryptionEngine()
        self.dedup = dedup_engine or DeduplicationEngine()
        self.checkpoint_interval = checkpoint_interval_seconds
        self.retention_count = retention_count
        self.retention_days = retention_days
        
        # Runtime state
        self._current_state: Optional[RuntimeState] = None
        self._last_snapshot: Optional[SnapshotMetadata] = None
        self._snapshot_chain: List[str] = []
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._auto_checkpoint_task: Optional[asyncio.Task] = None
        self._gc_task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="checkpoint")
        
        # Event callbacks
        self._on_checkpoint: List[Callable[[SnapshotMetadata], Coroutine]] = []
        self._on_restore: List[Callable[[SnapshotMetadata], Coroutine]] = []
        
        # State change tracking for incremental snapshots
        self._state_history: List[Tuple[datetime, str, Any]] = []  # (time, path, value)
        self._dirty_paths: Set[str] = set()
    
    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------
    
    async def start(self):
        """Start automatic checkpointing and garbage collection."""
        self._auto_checkpoint_task = asyncio.create_task(self._auto_checkpoint_loop())
        self._gc_task = asyncio.create_task(self._garbage_collection_loop())
        logger.info("Checkpoint engine started")
    
    async def stop(self):
        """Stop all background tasks."""
        if self._auto_checkpoint_task:
            self._auto_checkpoint_task.cancel()
            try:
                await self._auto_checkpoint_task
            except asyncio.CancelledError:
                pass
        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=True)
        logger.info("Checkpoint engine stopped")
    
    # -------------------------------------------------------------------------
    # STATE MANAGEMENT
    # -------------------------------------------------------------------------
    
    def update_state(self, path: str, value: Any):
        """Update a state path and mark for incremental tracking."""
        if self._current_state is None:
            return
        self._state_history.append((datetime.utcnow(), path, value))
        self._dirty_paths.add(path)
    
    def set_full_state(self, state: RuntimeState):
        """Set the complete runtime state."""
        self._current_state = state
        self._sequence += 1
        self._dirty_paths = set()  # Reset dirty tracking
    
    # -------------------------------------------------------------------------
    # CHECKPOINT OPERATIONS
    # -------------------------------------------------------------------------
    
    async def checkpoint(
        self,
        snapshot_type: SnapshotType = SnapshotType.MANUAL,
        force_full: bool = False,
        tags: Optional[Dict[str, str]] = None,
    ) -> SnapshotMetadata:
        """
        Create a checkpoint snapshot.
        
        Args:
            snapshot_type: Type of snapshot to create
            force_full: Force a full snapshot even if incremental would suffice
            tags: Optional metadata tags
        
        Returns:
            SnapshotMetadata of the created snapshot
        """
        async with self._lock:
            if self._current_state is None:
                raise RuntimeError("No runtime state set")
            
            # Determine if incremental or full
            is_incremental = (
                not force_full
                and self._last_snapshot is not None
                and len(self._dirty_paths) > 0
                and snapshot_type not in (SnapshotType.FULL,)
            )
            
            snapshot_id = f"snap-{uuid.uuid4().hex[:16]}"
            version = len(self._snapshot_chain) + 1
            
            metadata = SnapshotMetadata(
                snapshot_id=snapshot_id,
                version=version,
                snapshot_type=snapshot_type if not is_incremental else SnapshotType.INCREMENTAL,
                status=SnapshotStatus.CAPTURING,
                created_at=datetime.utcnow(),
                parent_snapshot_id=self._last_snapshot.snapshot_id if is_incremental else None,
                tenant_id=getattr(self._current_state, 'tenant_id', 'default'),
                workspace_id=getattr(self._current_state, 'workspace_id', 'default'),
                tags=tags or {},
                capture_targets=list(self._dirty_paths) if is_incremental else ["*"],
            )
            
            # Capture state
            try:
                if is_incremental:
                    state = self._capture_incremental()
                else:
                    state = self._current_state
                
                # Serialize
                raw_payload = self._serialize_state(state)
                metadata.size_bytes = len(raw_payload)
                
                # Deduplicate
                manifest = self.dedup.get_manifest(raw_payload)
                
                # Compress
                compressed = CompressionEngine.compress(raw_payload, CompressionAlgorithm.ZLIB)
                metadata.compressed_size_bytes = len(compressed)
                
                # Encrypt
                encrypted, _ = self.encryption.encrypt(compressed)
               
