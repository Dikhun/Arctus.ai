"""State persistence and checkpoint management."""

from __future__ import annotations

import gzip
import hashlib
import json
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

@dataclass
class Checkpoint:
    checkpoint_id: str
    timestamp: float
    tags: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        data = f"{self.checkpoint_id}:{self.timestamp}:{sorted(self.tags)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

@dataclass
class Snapshot:
    checkpoint: Checkpoint
    state_data: bytes

    def checksum(self) -> str:
        return hashlib.sha256(self.state_data).hexdigest()

class CheckpointManager:
    def __init__(self, base_path: str, compression: bool = True):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.compression = compression
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._load_index()

    def _load_index(self) -> None:
        index_path = self.base_path / "index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cp_data in data:
                cp = Checkpoint(
                    checkpoint_id=cp_data["id"],
                    timestamp=cp_data["timestamp"],
                    tags=cp_data.get("tags", []),
                    parent_id=cp_data.get("parent"),
                    metadata=cp_data.get("metadata", {})
                )
                self._checkpoints[cp.checkpoint_id] = cp

    def _save_index(self) -> None:
        index_path = self.base_path / "index.json"
        records = []
        for cp in self._checkpoints.values():
            records.append({
                "id": cp.checkpoint_id,
                "timestamp": cp.timestamp,
                "tags": cp.tags,
                "parent": cp.parent_id,
                "metadata": cp.metadata
            })
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    def save(
        self,
        state: Dict[str, Any],
        checkpoint_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        custom_serializer: Optional[Callable[[Dict[str, Any]], bytes]] = None
    ) -> Checkpoint:
        cid = checkpoint_id or f"cp_{int(time.time() * 1000)}"
        cp = Checkpoint(
            checkpoint_id=cid,
            timestamp=time.time(),
            tags=tags or [],
            parent_id=parent_id,
            metadata={"size_estimate": len(str(state))}
        )
        raw = custom_serializer(state) if custom_serializer else pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
        if self.compression:
            raw = gzip.compress(raw)
        snapshot = Snapshot(checkpoint=cp, state_data=raw)
        self._write_snapshot(snapshot)
        self._checkpoints[cid] = cp
        self._save_index()
        return cp

    def _write_snapshot(self, snapshot: Snapshot) -> None:
        path = self.base_path / f"{snapshot.checkpoint.checkpoint_id}.bin"
        with open(path, "wb") as f:
            f.write(snapshot.state_data)

    def load(
        self,
        checkpoint_id: str,
        custom_deserializer: Optional[Callable[[bytes], Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        if checkpoint_id not in self._checkpoints:
            raise FileNotFoundError(f"Checkpoint {checkpoint_id} not found")
        path = self.base_path / f"{checkpoint_id}.bin"
        if not path.exists():
            raise FileNotFoundError(f"Snapshot file for {checkpoint_id} missing")
        with open(path, "rb") as f:
            raw = f.read()
        if self.compression:
            raw = gzip.decompress(raw)
        return custom_deserializer(raw) if custom_deserializer else pickle.loads(raw)

    def list_checkpoints(self, tag_filter: Optional[str] = None) -> List[Checkpoint]:
        cps = list(self._checkpoints.values())
        if tag_filter:
            cps = [c for c in cps if tag_filter in c.tags]
        return sorted(cps, key=lambda x: x.timestamp, reverse=True)

    def incremental_save(
        self,
        state: Dict[str, Any],
        base_checkpoint_id: str,
        checkpoint_id: Optional[str] = None
    ) -> Checkpoint:
        base_state = self.load(base_checkpoint_id)
        diff = self._compute_diff(base_state, state)
        cid = checkpoint_id or f"inc_{int(time.time() * 1000)}"
        cp = Checkpoint(
            checkpoint_id=cid,
            timestamp=time.time(),
            tags=["incremental"],
            parent_id=base_checkpoint_id,
            metadata={"diff_keys": list(diff.keys())}
        )
        raw = pickle.dumps({"parent": base_checkpoint_id, "diff": diff}, protocol=pickle.HIGHEST_PROTOCOL)
        if self.compression:
            raw = gzip.compress(raw)
        self._write_snapshot(Snapshot(checkpoint=cp, state_data=raw))
        self._checkpoints[cid] = cp
        self._save_index()
        return cp

    def _compute_diff(self, base: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        diff = {}
        all_keys = set(base.keys()) | set(current.keys())
        for k in all_keys:
            bv = base.get(k)
            cv = current.get(k)
            if bv != cv:
                diff[k] = cv
        return diff

    def prune(self, keep_last: int = 10, tag_must_keep: Optional[str] = None) -> int:
        removed = 0
        cps = sorted(self._checkpoints.values(), key=lambda x: x.timestamp, reverse=True)
        for cp in cps[keep_last:]:
            if tag_must_keep and tag_must_keep in cp.tags:
                continue
            path = self.base_path / f"{cp.checkpoint_id}.bin"
            if path.exists():
                path.unlink()
            del self._checkpoints[cp.checkpoint_id]
            removed += 1
        if removed:
            self._save_index()
        return removed

    def verify(self, checkpoint_id: str) -> bool:
        try:
            self.load(checkpoint_id)
            return True
        except Exception:
            return False
