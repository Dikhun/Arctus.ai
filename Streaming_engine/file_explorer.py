#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Filesystem Explorer Engine
==============================================================
Secure filesystem explorer with workspace isolation, real-time sync,
version history, and support for multiple file types.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# Optional dependencies
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

try:
    import watchfiles
    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False

logger = logging.getLogger("arctus.filesystem")
logger.setLevel(logging.DEBUG)

# ============================================================================
# DATA MODELS
# ============================================================================

class FileType(Enum):
    TEXT = auto()
    IMAGE = auto()
    PDF = auto()
    WORD = auto()
    EXCEL = auto()
    CSV = auto()
    JSON = auto()
    MARKDOWN = auto()
    CODE = auto()
    ARCHIVE = auto()
    UNKNOWN = auto()

@dataclass(frozen=True, slots=True)
class FilePermissions:
    """File permission model (POSIX-style)."""
    owner_read: bool = True
    owner_write: bool = True
    owner_execute: bool = False
    group_read: bool = True
    group_write: bool = False
    group_execute: bool = False
    other_read: bool = False
    other_write: bool = False
    other_execute: bool = False
    
    @property
    def mode(self) -> int:
        """Convert to POSIX mode."""
        mode = 0
        if self.owner_read: mode |= 0o400
        if self.owner_write: mode |= 0o200
        if self.owner_execute: mode |= 0o100
        if self.group_read: mode |= 0o040
        if self.group_write: mode |= 0o020
        if self.group_execute: mode |= 0o010
        if self.other_read: mode |= 0o004
        if self.other_write: mode |= 0o002
        if self.other_execute: mode |= 0o001
        return mode
    
    @classmethod
    def from_mode(cls, mode: int) -> FilePermissions:
        """Create from POSIX mode."""
        return cls(
            owner_read=bool(mode & 0o400),
            owner_write=bool(mode & 0o200),
            owner_execute=bool(mode & 0o100),
            group_read=bool(mode & 0o040),
            group_write=bool(mode & 0o020),
            group_execute=bool(mode & 0o010),
            other_read=bool(mode & 0o004),
            other_write=bool(mode & 0o002),
            other_execute=bool(mode & 0o001),
        )

@dataclass(slots=True)
class FileMetadata:
    """Complete file metadata."""
    path: str
    name: str
    size: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    modified_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    file_type: FileType = FileType.UNKNOWN
    mime_type: str = "application/octet-stream"
    is_directory: bool = False
    is_symlink: bool = False
    permissions: FilePermissions = field(default_factory=FilePermissions)
    owner: str = "user"
    group: str = "user"
    checksum: str = ""
    version: int = 1
    tags: Dict[str, str] = field(default_factory=dict)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FileVersion:
    """File version entry."""
    version_id: str
    version_number: int
    created_at: datetime
    size: int
    checksum: str
    created_by: str = "system"
    comment: str = ""

@dataclass
class FileNode:
    """Node in file tree."""
    metadata: FileMetadata
    children: Dict[str, FileNode] = field(default_factory=dict)
    parent: Optional[FileNode] = field(default=None, repr=False)

# ============================================================================
# WORKSPACE ISOLATION
# ============================================================================

class WorkspaceIsolator:
    """Enforce workspace filesystem isolation."""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path).resolve()
        self._workspace_roots: Dict[str, Path] = {}
    
    def register_workspace(self, workspace_id: str, root_path: Optional[Path] = None):
        """Register workspace with isolated root."""
        if root_path:
            wp = self.base_path / workspace_id
            wp.mkdir(parents=True, exist_ok=True)
            self._workspace_roots[workspace_id] = wp.resolve()
        else:
            wp = self.base_path / workspace_id
            wp.mkdir(parents=True, exist_ok=True)
            self._workspace_roots[workspace_id] = wp.resolve()
    
    def resolve_path(
        self,
        workspace_id: str,
        relative_path: str,
    ) -> Path:
        """Resolve relative path within workspace, preventing escape."""
        if workspace_id not in self._workspace_roots:
            raise ValueError(f"Workspace not found: {workspace_id}")
        
        root = self._workspace_roots[workspace_id]
        # Resolve and normalize
        target = (root / relative_path).resolve()
        
        # Security check: ensure path is within workspace
        try:
            target.relative_to(root)
        except ValueError:
            raise PermissionError(f"Path escape attempt: {relative_path}")
        
        return target
    
    def get_relative_path(self, workspace_id: str, absolute_path: Path) -> str:
        """Convert absolute path to workspace-relative."""
        root = self._workspace_roots.get(workspace_id)
        if not root:
            return str(absolute_path)
        
        try:
            return str(Path(absolute_path).relative_to(root))
        except ValueError:
            return str(absolute_path)

# ============================================================================
# FILE TYPE DETECTION
# ============================================================================

class FileTypeDetector:
    """Detect file type from content and extension."""
    
    EXTENSION_MAP: Dict[str, FileType] = {
        ".txt": FileType.TEXT,
        ".md": FileType.MARKDOWN,
        ".json": FileType.JSON,
        ".csv": FileType.CSV,
        ".py": FileType.CODE,
        ".js": FileType.CODE,
        ".ts": FileType.CODE,
        ".html": FileType.CODE,
        ".css": FileType.CODE,
        ".java": FileType.CODE,
        ".go": FileType.CODE,
        ".rs": FileType.CODE,
        ".jpg": FileType.IMAGE,
        ".jpeg": FileType.IMAGE,
        ".png": FileType.IMAGE,
        ".gif": FileType.IMAGE,
        ".svg": FileType.IMAGE,
        ".pdf": FileType.PDF,
        ".doc": FileType.WORD,
        ".docx": FileType.WORD,
        ".xls": FileType.EXCEL,
        ".xlsx": FileType.EXCEL,
        ".zip": FileType.ARCHIVE,
        ".tar": FileType.ARCHIVE,
        ".gz": FileType.ARCHIVE,
    }
    
    MAGIC_BYTES: Dict[bytes, FileType] = {
        b"%PDF": FileType.PDF,
        b"\x89PNG": FileType.IMAGE,
        b"\xff\xd8\xff": FileType.IMAGE,
        b"PK": FileType.ARCHIVE,
    }
    
    @classmethod
    def detect(cls, path: Path, content: Optional[bytes] = None) -> FileType:
        """Detect file type."""
        # By extension
        ext = path.suffix.lower()
        if ext in cls.EXTENSION_MAP:
            return cls.EXTENSION_MAP[ext]
        
        # By magic bytes
        if content:
            for magic, ftype in cls.MAGIC_BYTES.items():
                if content.startswith(magic):
                    return ftype
        
        # By mime type
        mime, _ = mimetypes.guess_type(str(path))
        if mime:
            if mime.startswith("image/"):
                return FileType.IMAGE
            elif mime == "text/plain":
                return FileType.TEXT
            elif mime == "application/json":
                return FileType.JSON
        
        return FileType.UNKNOWN

# ============================================================================
# VERSION CONTROL
# ============================================================================

class VersionManager:
    """Manage file versions."""
    
    def __init__(self, versions_path: Path):
        self.versions_path = Path(versions_path)
        self.versions_path.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, List[FileVersion]] = defaultdict(list)
    
    async def create_version(
        self,
        file_path: Path,
        source_path: Path,
        created_by: str = "system",
        comment: str = "",
    ) -> FileVersion:
        """Create new version of file."""
        version_id = f"v-{uuid.uuid4().hex[:12]}"
        version_num = len(self._versions[str(file_path)]) + 1
        
        # Copy file to versions storage
        version_path = self.versions_path / version_id
        shutil.copy2(source_path, version_path)
        
        # Calculate checksum
        checksum = hashlib.sha256(version_path.read_bytes()).hexdigest()
        
        version = FileVersion(
            version_id=version_id,
            version_number=version_num,
            created_at=datetime.utcnow(),
            size=version_path.stat().st_size,
            checksum=checksum,
            created_by=created_by,
            comment=comment,
        )
        
        self._versions[str(file_path)].append(version)
        return version
    
    def get_versions(self, file_path: Path) -> List[FileVersion]:
        """Get all versions of file."""
        return list(self._versions.get(str(file_path), []))
    
    async def restore_version(
        self,
        file_path: Path,
        version_id: str,
        target_path: Path,
    ) -> bool:
        """Restore specific version."""
        version_path = self.versions_path / version_id
        if not version_path.exists():
            return False
        
        shutil.copy2(version_path, target_path)
        return True

# ============================================================================
# REAL-TIME SYNCHRONIZATION
# ============================================================================

class FileWatcher:
    """Watch filesystem for changes."""
    
    def __init__(self):
        self._watchers: Dict[str, asyncio.Task] = {}
        self._callbacks: List[Callable[[str, str, str], Coroutine]] = []
    
    def on_change(self, callback: Callable[[str, str, str], Coroutine]):
        """Register change callback (workspace_id, path, event_type)."""
        self._callbacks.append(callback)
    
    async def watch_workspace(self, workspace_id: str, root_path: Path):
        """Start watching workspace."""
        if not WATCHFILES_AVAILABLE:
            logger.warning("watchfiles not installed, file watching disabled")
            return
        
        async def _watch():
            async for changes in watchfiles.awatch(root_path):
                for change_type, path in changes:
                    for callback in self._callbacks:
                        try:
                            await callback(workspace_id, path, change_type)
                        except Exception as e:
                            logger.error(f"Watch callback error: {e}")
        
        self._watchers[workspace_id] = asyncio.create_task(_watch())
    
    async def stop_watching(self, workspace_id: str):
        """Stop watching workspace."""
        task = self._watchers.pop(workspace_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

# ============================================================================
# MAIN FILESYSTEM ENGINE
# ============================================================================

class FilesystemExplorerEngine:
    """
    Production filesystem explorer engine.
    
    Features:
    - Workspace isolation
    - Tree navigation
    - File preview
    - Upload/download
    - CRUD operations
    - Version history
    - Search
    - Real-time sync
    """
    
    def __init__(
        self,
        base_path: Optional[Path] = None,
    ):
        self.base_path = Path(base_path or tempfile.gettempdir()) / "arctus" / "workspaces"
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.isolator = WorkspaceIsolator(self.base_path)
        self.version_manager: Optional[VersionManager] = None
        self.file_watcher = FileWatcher()
        self._lock = asyncio.Lock()
        
        # Cache
        self._tree_cache: Dict[str, FileNode] = {}
        self._metadata_cache: Dict[str, FileMetadata] = {}
    
    async def initialize(self):
        """Initialize engine components."""
        versions_path = self.base_path / ".versions"
        versions_path.mkdir(exist_ok=True)
        self.version_manager = VersionManager(versions_path)
        
        # Setup file watching
        self.file_watcher.on_change(self._on_file_change)
    
    async def _on_file_change(self, workspace_id: str, path: str, event_type: str):
        """Handle file system change."""
        logger.debug(f"File change: {workspace_id}/{path} [{event_type}]")
        # Invalidate cache
        rel_path = self.isolator.get_relative_path(workspace_id, Path(path))
        cache_key = f"{workspace_id}:{rel_path}"
        self._metadata_cache.pop(cache_key, None)
        self._tree_cache.pop(workspace_id, None)
    
    # -------------------------------------------------------------------------
    # WORKSPACE MANAGEMENT
    # -------------------------------------------------------------------------
    
    async def create_workspace(
        self,
        workspace_id: str,
        owner: str = "system",
    ) -> Dict[str, Any]:
        """Create new isolated workspace."""
        self.isolator.register_workspace(workspace_id)
        
        # Create standard directories
        root = self.isolator.resolve_path(workspace_id, ".")
        (root / "uploads").mkdir(exist_ok=True)
        (root / "outputs").mkdir(exist_ok=True)
        (root / "shared").mkdir(exist_ok=True)
        
        # Start watching
        await self.file_watcher.watch_workspace(workspace_id, root)
        
        return {
            "workspace_id": workspace_id,
            "root_path": str(root),
            "created_at": datetime.utcnow().isoformat(),
        }
    
    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete workspace and all contents."""
        try:
            root = self.isolator.resolve_path(workspace_id, ".")
            await self.file_watcher.stop_watching(workspace_id)
            shutil.rmtree(root)
            self._tree_cache.pop(workspace_id, None)
            return True
        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")
            return False
    
    # -------------------------------------------------------------------------
    # TREE EXPLORATION
    # -------------------------------------------------------------------------
    
    async def get_tree(
        self,
        workspace_id: str,
        path: str = ".",
        depth: int = 3,
    ) -> FileNode:
        """Get file tree starting from path."""
        cache_key = f"{workspace_id}:{path}"
        if cache_key in self._tree_cache:
            return self._tree_cache[cache_key]
        
        target = self.isolator.resolve_path(workspace_id, path)
        
        async def _build_tree(current: Path, current_depth: int) -> FileNode:
            meta = await self._get_metadata(workspace_id, current)
            node = FileNode(metadata=meta)
            
            if current.is_dir() and current_depth > 0:
                try:
                    for child in current.iterdir():
                        child_node = await _build_tree(child, current_depth - 1)
                        child_node.parent = node
                        node.children[child.name] = child_node
                except PermissionError:
                    pass
            
            return node
        
        tree = await _build_tree(target, depth)
        self._tree_cache[cache_key] = tree
        return tree
    
    async def list_directory(
        self,
        workspace_id: str,
        path: str = ".",
    ) -> List[FileMetadata]:
        """List directory contents."""
        target = self.isolator.resolve_path(workspace_id, path)
        
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        
        items = []
        for child in target.iterdir():
            meta = await self._get_metadata(workspace_id, child)
            items.append(meta)
        
        return sorted(items, key=lambda x: (not x.is_directory, x.name))
    
    # -------------------------------------------------------------------------
    # FILE OPERATIONS
    # -------------------------------------------------------------------------
    
    async def read_file(
        self,
        workspace_id: str,
        path: str,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> Union[str, bytes]:
        """Read file content."""
        target = self.isolator.resolve_path(workspace_id, path)
        
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        if target.is_dir():
            raise IsADirectoryError(f"Is a directory: {path}")
        
        # Update access time
        meta = await self._get_metadata(workspace_id, target)
        meta.accessed_at = datetime.utcnow()
        
        # Read content
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(target, "rb") as f:
                if offset:
                    await f.seek(offset)
                content = await f.read(limit or -1)
        else:
            content = target.read_bytes()
            if offset or limit:
                content = content[offset:offset + limit if limit else None]
        
        # Return text or bytes based on type
        file_type = FileTypeDetector.detect(target, content[:1024])
        if file_type in (FileType.TEXT, FileType.CODE, FileType.MARKDOWN, FileType.JSON, FileType.CSV):
            return content.decode("utf-8", errors="replace")
        
        return content
    
    async def write_file(
        self,
        workspace_id: str,
        path: str,
        content: Union[str, bytes],
        create_version: bool = True,
        created_by: str = "system",
    ) -> FileMetadata:
        """Write file content."""
        target = self.isolator.resolve_path(workspace_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Create version if file exists
        if target.exists() and create_version and self.version_manager:
            await self.version_manager.create_version(
                target, target, created_by, "Before overwrite"
            )
        
        # Write content
        if isinstance(content, str):
            content = content.encode("utf-8")
        
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(target, "wb") as f:
                await f.write(content)
        else:
            target.write_bytes(content)
        
        # Update metadata
        meta = await self._get_metadata(workspace_id, target)
        meta.size = len(content)
        meta.checksum = hashlib.sha256(content).hexdigest()
        meta.modified_at = datetime.utcnow()
        meta.version += 1
        
        # Invalidate cache
        self._invalidate_cache(workspace_id, path)
        
        return meta
    
    a
