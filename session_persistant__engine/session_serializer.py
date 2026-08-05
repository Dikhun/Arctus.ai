"""
session_serializer.py
Handles serialization, compression, and encryption of session state.
Supports multiple storage tiers and encryption backends.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import lzma
import pickle
import struct
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from session_models import SessionState, SessionSnapshot


class CompressionAlgorithm(str, Enum):
    """Supported compression algorithms."""
    NONE = "none"
    GZIP = "gzip"
    LZMA = "lzma"


class SerializationFormat(str, Enum):
    """Supported serialization formats."""
    JSON = "json"
    PICKLE = "pickle"
    MESSAGEPACK = "msgpack"


class EncryptionBackend(str, Enum):
    """Supported encryption backends."""
    NONE = "none"
    FERNET = "fernet"
    AES_GCM = "aes_gcm"


class SerializedSession:
    """Container for serialized session data with metadata."""
    
    def __init__(
        self,
        data: bytes,
        format: SerializationFormat,
        compression: CompressionAlgorithm,
        encrypted: bool,
        encryption_backend: EncryptionBackend,
        original_size: int,
        compressed_size: int,
        state_hash: str,
        version: int,
        tenant_id: str,
        session_id: str
    ) -> None:
        self.data = data
        self.format = format
        self.compression = compression
        self.encrypted = encrypted
        self.encryption_backend = encryption_backend
        self.original_size = original_size
        self.compressed_size = compressed_size
        self.state_hash = state_hash
        self.version = version
        self.tenant_id = tenant_id
        self.session_id = session_id
    
    def to_storage_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "data": base64.b64encode(self.data).decode(),
            "format": self.format,
            "compression": self.compression,
            "encrypted": self.encrypted,
            "encryption_backend": self.encryption_backend,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "state_hash": self.state_hash,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
        }
    
    @classmethod
    def from_storage_dict(cls, data: Dict[str, Any]) -> SerializedSession:
        """Reconstruct from storage dictionary."""
        return cls(
            data=base64.b64decode(data["data"]),
            format=SerializationFormat(data["format"]),
            compression=CompressionAlgorithm(data["compression"]),
            encrypted=data["encrypted"],
            encryption_backend=EncryptionBackend(data["encryption_backend"]),
            original_size=data["original_size"],
            compressed_size=data["compressed_size"],
            state_hash=data["state_hash"],
            version=data["version"],
            tenant_id=data["tenant_id"],
            session_id=data["session_id"],
        )
    
    def size_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.original_size == 0:
            return 1.0
        return self.compressed_size / self.original_size


class SessionSerializer:
    """
    Production-grade session serializer with:
    - Multiple serialization formats
    - Configurable compression
    - Strong encryption with tenant isolation
    - Integrity verification via hashes
    """
    
    def __init__(
        self,
        encryption_key: Optional[bytes] = None,
        encryption_backend: EncryptionBackend = EncryptionBackend.FERNET,
        compression: CompressionAlgorithm = CompressionAlgorithm.GZIP,
        format: SerializationFormat = SerializationFormat.JSON,
        compression_level: int = 6
    ) -> None:
        self.encryption_backend = encryption_backend
        self.compression = compression
        self.format = format
        self.compression_level = compression_level
        
        # Initialize encryption
        self._cipher: Optional[Fernet] = None
        if encryption_backend != EncryptionBackend.NONE:
            if encryption_key is None:
                raise ValueError("Encryption key required when encryption is enabled")
            self._cipher = self._init_fernet(encryption_key)
    
    def _init_fernet(self, key: bytes) -> Fernet:
        """Initialize Fernet cipher from key."""
        # If key is not 32-byte URL-safe base64, derive it
        try:
            return Fernet(key)
        except ValueError:
            # Derive proper key using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'arctus-session-v1',
                iterations=480000,
            )
            derived = base64.urlsafe_b64encode(kdf.derive(key))
            return Fernet(derived)
    
    def _derive_tenant_key(self, master_key: bytes, tenant_id: str) -> bytes:
        """
        Derive tenant-specific encryption key from master key.
        Ensures cryptographic isolation between tenants.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"arctus-tenant-{tenant_id}".encode(),
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(master_key))
    
    def serialize(
        self,
        state: SessionState,
        tenant_key: Optional[bytes] = None
    ) -> SerializedSession:
        """
        Serialize session state to bytes with optional encryption.
        
        Args:
            state: Session state to serialize
            tenant_key: Optional tenant-specific encryption key override
        
        Returns:
            SerializedSession container with metadata
        """
        # Step 1: Serialize to intermediate format
        if self.format == SerializationFormat.JSON:
            raw_data = self._to_json(state)
        elif self.format == SerializationFormat.PICKLE:
            raw_data = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
        elif self.format == SerializationFormat.MESSAGEPACK:
            raw_data = self._to_msgpack(state)
        else:
            raise ValueError(f"Unsupported format: {self.format}")
        
        original_size = len(raw_data)
        
        # Step 2: Compress
        compressed = self._compress(raw_data)
        compressed_size = len(compressed)
        
        # Step 3: Calculate hash before encryption
        state_hash = hashlib.sha256(compressed).hexdigest()
        
        # Step 4: Encrypt if enabled
        encrypted = False
        encryption_backend = EncryptionBackend.NONE
        final_data = compressed
        
        if self.encryption_backend != EncryptionBackend.NONE and self._cipher:
            cipher = self._cipher
            if tenant_key:
                # Use tenant-derived key for additional isolation
                tenant_cipher = Fernet(self._derive_tenant_key(
                    base64.urlsafe_b64decode(cipher._signing_key.key),
                    state.tenant_id
                ))
                cipher = tenant_cipher
            
            final_data = cipher.encrypt(compressed)
            encrypted = True
            encryption_backend = self.encryption_backend
        
        return SerializedSession(
            data=final_data,
            format=self.format,
            compression=self.compression,
            encrypted=encrypted,
            encryption_backend=encryption_backend,
            original_size=original_size,
            compressed_size=compressed_size,
            state_hash=state_hash,
            version=state.version,
            tenant_id=state.tenant_id,
            session_id=state.session_id
        )
    
    def deserialize(
        self,
        serialized: SerializedSession,
        tenant_key: Optional[bytes] = None
    ) -> SessionState:
        """
        Deserialize session state from bytes.
        
        Args:
            serialized: SerializedSession container
            tenant_key: Optional tenant-specific key override
        
        Returns:
            Reconstructed SessionState
        """
        data = serialized.data
        
        # Step 1: Decrypt if needed
        if serialized.encrypted and self._cipher:
            cipher = self._cipher
            if tenant_key:
                tenant_cipher = Fernet(self._derive_tenant_key(
                    base64.urlsafe_b64decode(cipher._signing_key.key),
                    serialized.tenant_id
                ))
                cipher = tenant_cipher
            
            data = cipher.decrypt(data)
        
        # Step 2: Verify hash
        state_hash = hashlib.sha256(data).hexdigest()
        if state_hash != serialized.state_hash:
            raise ValueError(
                f"Integrity check failed for session {serialized.session_id}: "
                f"hash mismatch"
            )
        
        # Step 3: Decompress
        decompressed = self._decompress(data, serialized.compression)
        
        # Step 4: Deserialize
        if serialized.format == SerializationFormat.JSON:
            return self._from_json(decompressed)
        elif serialized.format == SerializationFormat.PICKLE:
            return pickle.loads(decompressed)
        elif serialized.format == SerializationFormat.MESSAGEPACK:
            return self._from_msgpack(decompressed)
        else:
            raise ValueError(f"Unsupported format: {serialized.format}")
    
    def _to_json(self, state: SessionState) -> bytes:
        """Serialize to JSON bytes."""
        # Use Pydantic's json() for proper serialization
        return state.model_dump_json().encode('utf-8')
    
    def _from_json(self, data: bytes) -> SessionState:
        """Deserialize from JSON bytes."""
        return SessionState.model_validate_json(data.decode('utf-8'))
    
    def _to_msgpack(self, state: SessionState) -> bytes:
        """Serialize to MessagePack bytes."""
        import msgpack
        return msgpack.packb(state.model_dump(), use_bin_type=True)
    
    def _from_msgpack(self, data: bytes) -> SessionState:
        """Deserialize from MessagePack bytes."""
        import msgpack
        return SessionState.model_validate(msgpack.unpackb(data, raw=False))
    
    def _compress(self, data: bytes) -> bytes:
        """Compress data using configured algorithm."""
        if self.compression == CompressionAlgorithm.GZIP:
            return gzip.compress(data, compresslevel=self.compression_level)
        elif self.compression == CompressionAlgorithm.LZMA:
            return lzma.compress(data, preset=self.compression_level)
        elif self.compression == CompressionAlgorithm.NONE:
            return data
        else:
            raise ValueError(f"Unsupported compression: {self.compression}")
    
    def _decompress(self, data: bytes, algorithm: CompressionAlgorithm) -> bytes:
        """Decompress data using specified algorithm."""
        if algorithm == CompressionAlgorithm.GZIP:
            return gzip.decompress(data)
        elif algorithm == CompressionAlgorithm.LZMA:
            return lzma.decompress(data)
        elif algorithm == CompressionAlgorithm.NONE:
            return data
        else:
            raise ValueError(f"Unsupported compression: {algorithm}")
    
    def create_snapshot(
        self,
        state: SessionState,
        trigger: str,
        tenant_key: Optional[bytes] = None
    ) -> Tuple[SessionSnapshot, SerializedSession]:
        """Create a snapshot with serialized state."""
        serialized = self.serialize(state, tenant_key)
        
        snapshot = SessionSnapshot(
            session_id=state.session_id,
            version=state.version,
            trigger=trigger,
            state_hash=serialized.state_hash,
            compressed_size_bytes=serialized.compressed_size
        )
        
        return snapshot, serialized
