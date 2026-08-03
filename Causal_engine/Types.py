import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Listclass CloudProvider(enum.Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    TENCENT = "tencent"
    ORACLE = "oracle"
    ALIBABA = "alibaba"
    LOCAL = "local"
    BARE_METAL = "bare_metal"

class ServiceStatus(enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"

@dataclass
class SystemInfo:
    os_name: str = ""
    os_version: str = ""
    python_version: str = ""
    cpu_arch: str = ""
    cpu_count: int = 0
    total_memory_mb: int = 0
    gpu_available: bool = False
    gpu_devices: List[Dict[str, Any]] = field(default_factory=list)
    cuda_version: str = ""
    docker: bool = False
    kubernetes: bool = False
    aws: bool = False
    azure: bool = False
    gcp: bool = False
    tencent: bool = False
    oracle: bool = False
    alibaba: bool = False
    redis: bool = False
    postgresql: bool = False
    mysql: bool = False
    tencentdb: bool = False
    chromadb: bool = False
    neo4j: bool = False
    knowledge_graph: bool = False
    digital_twin_engine: bool = False
    simulation_engine: bool = False
    research_engine: bool = False
    event_bus: bool = False
    persistent_memory: bool = False
    plugin_registry: bool = False
    secret_manager: bool = False
    telemetry: bool = False
    agent_mesh: bool = False

@dataclass
class CapabilityMeta:
    name: str
    version: str
    endpoint: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HealthReport:
    status: ServiceStatus
    checks: Dict[str, str]
    timestamp: float
