import asyncio
import json
import logging
import os
import platform
import socket
import sys
from typing import Optional

from .types import SystemInfo

logger = logging.getLogger(__name__)

class EnvironmentDiscovery:
    def __init__(self) -> None:
        self.info = SystemInfo()

    async def discover_all(self) -> SystemInfo:
        await asyncio.gather(
            self.detect_os(),
            self.detect_python(),
            self.detect_cpu(),
            self.detect_memory(),
            self.detect_gpu(),
            self.detect_cuda(),
            self.detect_docker(),
            self.detect_kubernetes(),
            self.detect_aws(),
            self.detect_azure(),
            self.detect_gcp(),
            self.detect_tencent(),
            self.detect_oracle(),
            self.detect_alibaba(),
            self.detect_redis(),
            self.detect_postgresql(),
            self.detect_mysql(),
            self.detect_tencentdb(),
            self.detect_chromadb(),
            self.detect_neo4j(),
            self.detect_knowledge_graph(),
            self.detect_digital_twin_engine(),
            self.detect_simulation_engine(),
            self.detect_research_engine(),
            self.detect_event_bus(),
            self.detect_persistent_memory(),
            self.detect_plugin_registry(),
            self.detect_secret_manager(),
            self.detect_telemetry(),
            self.detect_agent_mesh(),
        )
        return self.info

    async def detect_os(self) -> None:
        self.info.os_name = platform.system()
        self.info.os_version = platform.release()

    async def detect_python(self) -> None:
        v = sys.version_info
        self.info.python_version = f"{v.major}.{v.minor}.{v.micro}"

    async def detect_cpu(self) -> None:
        self.info.cpu_arch = platform.machine()
        self.info.cpu_count = os.cpu_count() or 0

    async def detect_memory(self) -> None:
        try:
            import psutil
            mem = psutil.virtual_memory()
            self.info.total_memory_mb = int(mem.total / (1024 * 1024))
        except Exception:
            self.info.total_memory_mb = 0

    async def detect_gpu(self) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=json,noheader",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                data = json.loads(stdout.decode())
                self.info.gpu_available = True
                self.info.gpu_devices = data if isinstance(data, list) else [data]
            else:
                self.info.gpu_available = False
        except FileNotFoundError:
            self.info.gpu_available = False
        except Exception as exc:
            logger.warning(f"GPU detection error: {exc}")
            self.info.gpu_available = False

    async def detect_cuda(self) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().splitlines():
                if "CUDA Version" in line:
                    self.info.cuda_version = line.split("CUDA Version:")[-1].strip()
                    return
            self.info.cuda_version = ""
        except FileNotFoundError:
            self.info.cuda_version = ""
        except Exception as exc:
            logger.warning(f"CUDA detection error: {exc}")
            self.info.cuda_version = ""

    async def detect_docker(self) -> None:
        self.info.docker = await self._command_exists("docker", "version")

    async def detect_kubernetes(self) -> None:
        self.info.kubernetes = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount")

    async def detect_aws(self) -> None:
        self.info.aws = any(
            [
                os.getenv("AWS_ACCESS_KEY_ID"),
                os.getenv("AWS_LAMBDA_FUNCTION_NAME"),
                os.getenv("ECS_CONTAINER_METADATA_URI"),
            ]
        )

    async def detect_azure(self) -> None:
        self.info.azure = os.getenv("AZURE_SUBSCRIPTION_ID") is not None

    async def detect_gcp(self) -> None:
        self.info.gcp = any(
            [
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
                os.getenv("K_SERVICE"),
                os.getenv("GCP_PROJECT"),
            ]
        )

    async def detect_tencent(self) -> None:
        self.info.tencent = os.getenv("TENCENTCLOUD_SECRETID") is not None

    async def detect_oracle(self) -> None:
        self.info.oracle = os.getenv("OCI_CLI_AUTH") is not None

    async def detect_alibaba(self) -> None:
        self.info.alibaba = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID") is not None

    async def detect_redis(self) -> None:
        self.info.redis = await self._tcp_reachable("localhost", 6379)

    async def detect_postgresql(self) -> None:
        self.info.postgresql = await self._tcp_reachable("localhost", 5432)

    async def detect_mysql(self) -> None:
        self.info.mysql = await self._tcp_reachable("localhost", 3306)

    async def detect_tencentdb(self) -> None:
        host = os.getenv("TENCENTDB_HOST", "")
        port = int(os.getenv("TENCENTDB_PORT", "3306"))
        if host:
            self.info.tencentdb = await self._tcp_reachable(host, port)
        else:
            self.info.tencentdb = False

    async def detect_chromadb(self) -> None:
        try:
            import importlib
            importlib.import_module("chromadb")
            self.info.chromadb = True
        except ImportError:
            self.info.chromadb = False

    async def detect_neo4j(self) -> None:
        self.info.neo4j = await self._tcp_reachable("localhost", 7687)

    async def detect_knowledge_graph(self) -> None:
        self.info.knowledge_graph = os.getenv("KNOWLEDGE_GRAPH_ENDPOINT") is not None

    async def detect_digital_twin_engine(self) -> None:
        self.info.digital_twin_engine = os.getenv("DIGITAL_TWIN_ENDPOINT") is not None

    async def detect_simulation_engine(self) -> None:
        self.info.simulation_engine = os.getenv("SIMULATION_ENGINE_ENDPOINT") is not None

    async def detect_research_engine(self) -> None:
        self.info.research_engine = os.getenv("RESEARCH_ENGINE_ENDPOINT") is not None

    async def detect_event_bus(self) -> None:
        bus_port = int(os.getenv("EVENT_BUS_PORT", "9092"))
        self.info.event_bus = await self._tcp_reachable(
            os.getenv("EVENT_BUS_HOST", "localhost"), bus_port
        )

    async def detect_persistent_memory(self) -> None:
        if self.info.os_name == "Linux":
            self.info.persistent_memory = os.path.exists("/dev/pmem0") or os.path.exists(
                "/dev/dax0.0"
            )
        else:
            self.info.persistent_memory = False

    async def detect_plugin_registry(self) -> None:
        self.info.plugin_registry = os.getenv("PLUGIN_REGISTRY_URL") is not None

    async def detect_secret_manager(self) -> None:
        self.info.secret_manager = any(
            [
                os.getenv("VAULT_ADDR"),
                os.getenv("SECRET_MANAGER_URL"),
                os.getenv("AWS_SECRETS_MANAGER_REGION"),
            ]
        )

    async def detect_telemetry(self) -> None:
        self.info.telemetry = any(
            [
                os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
                os.getenv("PROMETHEUS_PUSHGATEWAY"),
                os.getenv("JAEGER_ENDPOINT"),
            ]
        )

    async def detect_agent_mesh(self) -> None:
        self.info.agent_mesh = os.getenv("AGENT_MESH_ENDPOINT") is not None

    async def _command_exists(self, command: str, arg: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                command, arg,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return (await proc.wait()) == 0
        except FileNotFoundError:
            return False

    async def _tcp_reachable(self, host: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False
