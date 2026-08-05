#!/usr/bin/env python3
"""
Arctus AI Orchestration Framework — Multi-Tenant Isolation Engine
=================================================================
Zero-trust multi-tenant isolation with RBAC, ABAC, encryption,
audit logging, and deployment compatibility.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# Optional crypto
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger("arctus.tenant")
logger.setLevel(logging.DEBUG)

# ============================================================================
# ENUMERATIONS
# ============================================================================

class IsolationLevel(Enum):
    """Levels of tenant isolation."""
    SHARED = auto()      # Shared infrastructure, logical separation
    DEDICATED = auto()   # Dedicated resources within shared infra
    ISOLATED = auto()    # Fully isolated infrastructure

class ResourceType(Enum):
    """Tenant-scoped resource types."""
    TENANT = auto()
    WORKSPACE = auto()
    PROJECT = auto()
    VM = auto()
    FILESYSTEM = auto()
    MEMORY = auto()
    BROWSER = auto()
    CONTAINER = auto()
    SECRET = auto()
    ENVIRONMENT = auto()
    API = auto()

# ============================================================================
# IDENTITY & ACCESS
# ============================================================================

@dataclass(frozen=True, slots=True)
class TenantId:
    """Strongly typed tenant identifier."""
    value: str
    
    def __str__(self):
        return self.value

@dataclass(frozen=True, slots=True)
class Principal:
    """Security principal (user or service)."""
    id: str
    type: str  # user, service, agent
    tenant_id: TenantId
    workspace_id: Optional[str] = None
    roles: Tuple[str, ...] = field(default_factory=tuple)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def has_role(self, role: str) -> bool:
        return role in self.roles

@dataclass
class Permission:
    """Permission definition."""
    resource_type: ResourceType
    action: str  # create, read, update, delete, execute
    resource_id: Optional[str] = None
    
    def __str__(self):
        if self.resource_id:
            return f"{self.resource_type.name}:{self.action}:{self.resource_id}"
        return f"{self.resource_type.name}:{self.action}"

# ============================================================================
# RBAC
# ============================================================================

class Role:
    """Role with assigned permissions."""
    
    def __init__(self, name: str, permissions: List[Permission]):
        self.name = name
        self.permissions = permissions
    
    def allows(self, permission: Permission) -> bool:
        """Check if role allows permission."""
        for p in self.permissions:
            if p.resource_type == permission.resource_type and p.action == permission.action:
                if p.resource_id is None or p.resource_id == permission.resource_id:
                    return True
        return False

class RBACManager:
    """Role-Based Access Control manager."""
    
    def __init__(self):
        self.roles: Dict[str, Role] = {}
        self.user_roles: Dict[str, Set[str]] = defaultdict(set)
        
        # Default roles
        self._create_default_roles()
    
    def _create_default_roles(self):
        """Create default system roles."""
        self.roles["admin"] = Role("admin", [
            Permission(r, "create") for r in ResourceType
        ] + [
            Permission(r, "read") for r in ResourceType
        ] + [
            Permission(r, "update") for r in ResourceType
        ] + [
            Permission(r, "delete") for r in ResourceType
        ] + [
            Permission(r, "execute") for r in [ResourceType.VM, ResourceType.BROWSER, ResourceType.API]
        ])
        
        self.roles["developer"] = Role("developer", [
            Permission(ResourceType.WORKSPACE, "create"),
            Permission(ResourceType.WORKSPACE, "read"),
            Permission(ResourceType.PROJECT, "create"),
            Permission(ResourceType.PROJECT, "read"),
            Permission(ResourceType.PROJECT, "update"),
            Permission(ResourceType.FILESYSTEM, "create"),
            Permission(ResourceType.FILESYSTEM, "read"),
            Permission(ResourceType.FILESYSTEM, "update"),
            Permission(ResourceType.FILESYSTEM, "delete"),
            Permission(ResourceType.MEMORY, "read"),
            Permission(ResourceType.MEMORY, "write"),
            Permission(ResourceType.BROWSER, "execute"),
            Permission(ResourceType.API, "execute"),
        ])
        
        self.roles["viewer"] = Role("viewer", [
            Permission(ResourceType.WORKSPACE, "read"),
            Permission(ResourceType.PROJECT, "read"),
            Permission(ResourceType.FILESYSTEM, "read"),
        ])
        
        self.roles["operator"] = Role("operator", [
            Permission(ResourceType.VM, "create"),
            Permission(ResourceType.VM, "read"),
            Permission(ResourceType.VM, "update"),
            Permission(ResourceType.VM, "delete"),
            Permission(ResourceType.VM, "execute"),
            Permission(ResourceType.CONTAINER, "create"),
            Permission(ResourceType.CONTAINER, "read"),
            Permission(ResourceType.CONTAINER, "execute"),
        ])
    
    def create_role(self, name: str, permissions: List[Permission]) -> Role:
        """Create custom role."""
        role = Role(name, permissions)
        self.roles[name] = role
        return role
    
    def assign_role(self, principal_id: str, role_name: str):
        """Assign role to principal."""
        if role_name in self.roles:
            self.user_roles[principal_id].add(role_name)
    
    def check_permission(self, principal: Principal, permission: Permission) -> bool:
        """Check if principal has permission."""
        for role_name in principal.roles:
            role = self.roles.get(role_name)
            if role and role.allows(permission):
                return True
        
        # Also check dynamically assigned roles
        for role_name in self.user_roles.get(principal.id, set()):
            role = self.roles.get(role_name)
            if role and role.allows(permission):
                return True
        
        return False

# ============================================================================
# ABAC
# ============================================================================

class ABACPolicy:
    """Attribute-Based Access Control policy."""
    
    def __init__(
        self,
        name: str,
        subject_conditions: Dict[str, Callable[[Any], bool]],
        resource_conditions: Dict[str, Callable[[Any], bool]],
        environment_conditions: Dict[str, Callable[[Any], bool]],
        effect: str = "permit",  # permit or deny
    ):
        self.name = name
        self.subject_conditions = subject_conditions
        self.resource_conditions = resource_conditions
        self.environment_conditions = environment_conditions
        self.effect = effect
    
    def evaluate(
        self,
        subject: Principal,
        resource: Dict[str, Any],
        environment: Dict[str, Any],
    ) -> Optional[str]:
        """Evaluate policy against request context."""
        # Check subject conditions
        for attr, check in self.subject_conditions.items():
            value = getattr(subject, attr, None) or subject.attributes.get(attr)
            if value is None or not check(value):
                return None  # Not applicable
        
        # Check resource conditions
        for attr, check in self.resource_conditions.items():
            value = resource.get(attr)
            if value is None or not check(value):
                return None
        
        # Check environment conditions
        for attr, check in self.environment_conditions.items():
            value = environment.get(attr)
            if value is None or not check(value):
                return None
        
        return self.effect

class ABACManager:
    """Attribute-Based Access Control manager."""
    
    def __init__(self):
        self.policies: List[ABACPolicy] = []
    
    def add_policy(self, policy: ABACPolicy):
        """Add ABAC policy."""
        self.policies.append(policy)
    
    def evaluate(
        self,
        subject: Principal,
        resource: Dict[str, Any],
        environment: Dict[str, Any],
    ) -> bool:
        """Evaluate all policies."""
        decisions = []
        
        for policy in self.policies:
            result = policy.evaluate(subject, resource, environment)
            if result:
                decisions.append(result)
        
        # Deny overrides if any deny
        if "deny" in decisions:
            return False
        if "permit" in decisions:
            return True
        
        return False  # Default deny

# ============================================================================
# ENCRYPTION
# ============================================================================

class TenantEncryption:
    """Per-tenant encryption with key isolation."""
    
    def __init__(self, master_key: Optional[bytes] = None):
        self.master_key = master_key or os.urandom(32)
        self._tenant_keys: Dict[str, bytes] = {}
        self._key_versions: Dict[str, int] = defaultdict(int)
    
    def _derive_key(self, tenant_id: str, version: int = 1) -> bytes:
        """Derive tenant-specific key."""
        cache_key = f"{tenant_id}:v{version}"
        if cache_key not in self._tenant_keys:
            # HMAC-based key derivation
            material = hmac.new(
                self.master_key,
                f"{tenant_id}:{version}".encode(),
                hashlib.sha256,
            ).digest()
            self._tenant_keys[cache_key] = material[:32]
        return self._tenant_keys[cache_key]
    
    def encrypt(self, tenant_id: str, plaintext: bytes) -> Dict[str, Any]:
        """Encrypt data for tenant."""
        if not CRYPTO_AVAILABLE:
            # Simple XOR obfuscation fallback
            key = self._derive_key(tenant_id)
            obfuscated = bytes(a ^ b for a, b in zip(plaintext, key * (len(plaintext) // 32 + 1)))
            return {
                "ciphertext": base64.b64encode(obfuscated).decode(),
                "version": 1,
                "algorithm": "xor-fallback",
            }
        
        version = self._key_versions[tenant_id] + 1
        key = self._derive_key(tenant_id, version)
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        return {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "version": version,
            "algorithm": "AES256-GCM",
        }
    
    def decrypt(self, tenant_id: str, encrypted_data: Dict[str, Any]) -> bytes:
        """Decrypt tenant data."""
        ciphertext = base64.b64decode(encrypted_data["ciphertext"])
        version = encrypted_data.get("version", 1)
        
        if encrypted_data.get("algorithm") == "xor-fallback":
            key = self._derive_key(tenant_id, version)
            return bytes(a ^ b for a, b in zip(ciphertext, key * (len(ciphertext) // 32 + 1)))
        
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography required for AES decryption")
        
        key = self._derive_key(tenant_id, version)
        nonce = base64.b64decode(encrypted_data["nonce"])
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    
    def rotate_key(self, tenant_id: str):
        """Rotate encryption key for tenant."""
        self._key_versions[tenant_id] += 1
        # Clear old key from cache to force regeneration
        old_version = self._key_versions[tenant_id] - 1
        self._tenant_keys.pop(f"{tenant_id}:v{old_version}", None)

# ============================================================================
# AUDIT LOGGING
# ============================================================================

@dataclass(slots=True)
class AuditEvent:
    """Security audit event."""
    event_id: str
    timestamp: datetime
    tenant_id: str
    principal_id: str
    action: str
    resource_type: ResourceType
    resource_id: str
    allowed: bool
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

class AuditLogger:
    """Comprehensive audit logging."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = Path(storage_path or tempfile.gettempdir()) / "arctus" / "audit"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._buffer: List[AuditEvent] = []
        self._flush_size = 100
        self._lock = asyncio.Lock()
    
    async def log(self, event: AuditEvent):
        """Log audit event."""
        async with self._lock:
            self._buffer.append(event)
            
            if len(self._buffer) >= self._flush_size:
                await self._flush()
    
    async def _flush(self):
        """Flush buffer to storage."""
        if not self._buffer:
            return
        
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = self.storage_path / f"{date_str}.jsonl"
        
        lines = []
        for event in self._buffer:
            lines.append(json.dumps({
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "tenant_id": event.tenant_id,
                "principal_id": event.principal_id,
                "action": event.action,
                "resource_type": event.resource_type.name,
                "resource_id": event.resource_id,
                "allowed": event.allowed,
                "reason": event.reason,
                "metadata": event.metadata,
            }))
        
        def _write():
            with open(file_path, "a") as f:
                for line in lines:
                    f.write(line + "\n")
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write)
        
        self._buffer.clear()
    
    async def query(
        self,
        tenant_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Query audit log."""
        # Simple in-memory query for demo
        results = []
        for event in self._buffer:
            if tenant_id and event.tenant_id != tenant_id:
                continue
            if principal_id and event.principal_id != principal_id:
                continue
            if action and event.action != action:
                continue
            results.append(event)
        return results

# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """Token bucket rate limiter per tenant."""
    
    def __init__(self):
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._default_rate = 100  # requests per minute
        self._default_burst = 20
    
    def configure(self, tenant_id: str, rate: int, burst: int):
        """Configure rate limit for tenant."""
        self._buckets[tenant_id] = {
            "rate": rate,
            "burst": burst,
            "tokens": burst,
            "last_update": time.time(),
        }
    
    def allow(self, tenant_id: str) -> bool:
        """Check if request is allowed."""
        bucket = self._buckets.get(tenant_id)
        if not bucket:
            # Use defaults
            bucket = {
                "rate": self._default_rate,
                "burst": self._default_burst,
                "tokens": self._default_burst,
                "last_update": time.time(),
            }
            self._buckets[tenant_id] = bucket
        
        now = time.time()
        elapsed = now - bucket["last_update"]
        bucket["last_update"] = now
        
        # Add tokens
        bucket["tokens"] = min(
            bucket["burst"],
            bucket["tokens"] + elapsed * (bucket["rate"] / 60.0),
        )
        
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        return False

# ============================================================================
# TENANT CONTEXT
# ============================================================================

class TenantContext:
    """Execution context with tenant isolation."""
    
    def __init__(
        self,
        tenant_id: TenantId,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        isolation_level: IsolationLevel = IsolationLevel.SHARED,
    ):
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.isolation_level = isolation_level
        self.created_at = datetime.utcnow()
        self._resources: Dict[ResourceType, Set[str]] = defaultdict(set)
        self._secrets: Dict[str, str] = {}
        self._env: Dict[str, str] = {}
    
    def register_resource(self, resource_type: ResourceType, resource_id: str):
        """Register resource in context."""
        self._resources[resource_type].add(resource_id)
    
    def set_secret(self, key: str, value: str):
        """Set tenant-scoped secret."""
        self._secrets[key] = value
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get tenant-scoped secret."""
        return self._secrets.get(key)
    
    def set_env(self, key: str, value: str):
        """Set tenant-scoped environment variable."""
        self._env[key] = value
    
    def get_env(self, key: str) -> Optional[str]:
        """Get tenant-scoped environment variable."""
        return self._env.get(key)

# ============================================================================
# MAIN ISOLATION ENGINE
# ============================================================================

class MultiTenantIsolationEngine:
    """
    Multi-tenant isolation engine with zero-trust security.
    
    Features:
    - Complete tenant isolation across all resources
    - RBAC and ABAC authorization
    - Encryption with per-tenant keys
    - Comprehensive audit logging
    - Rate limiting and quotas
    - Cross-tenant protection
    """
    
    def __init__(self):
        self.tenants: Dict[str, TenantContext] = {}
        self.rbac = RBACManager()
        self.abac = ABACManager()
        self.encryption = TenantEncryption()
        self.audit = AuditLogger()
        self.rate_limiter = RateLimiter()
        self._lock = asyncio.Lock()
        
        # Tenant quotas
        self._quotas: Dict[str, Dict[str, Any]] = {}
        
        # Cross-tenant protection
        self._cross_tenant_allowed: Set[Tuple[str, str]] = set()
    
    async def create_tenant(
        self,
        tenant_id: str,
        isolation_level: IsolationLevel = IsolationLevel.SHARED,
        admin_principal: Optional[str] = None,
    ) -> TenantContext:
     
