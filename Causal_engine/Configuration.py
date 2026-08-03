import json
import os
from typing import Any, Dict

from .types import SystemInfo

class ConfigurationManager:
    def __init__(self, config_path: str = "causal_config.json") -> None:
        self.config_path = config_path

    async def generate(self, info: SystemInfo) -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "engine": {
                "name": "causal-engine",
                "version": "1.0.0",
                "workers": info.cpu_count or 4,
                "async_mode": True,
                "host": os.getenv("CAUSAL_ENGINE_HOST", "0.0.0.0"),
                "port": int(os.getenv("CAUSAL_ENGINE_PORT", "8080")),
            },
            "storage": {
                "postgresql": {
                    "enabled": info.postgresql,
                    "dsn": os.getenv("POSTGRES_DSN", "postgresql://user:pass@localhost/causal"),
                },
                "redis": {
                    "enabled": info.redis,
                    "url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                },
                "neo4j": {
                    "enabled": info.neo4j,
                    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
 "user": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                },
                "mysql": {
                    "enabled": info.mysql,
                    "dsn": os.getenv("MYSQL_DSN", "mysql://user:pass@localhost/causal"),
                },
            },
            "cloud": {
                "provider": self._detect_cloud_provider(info),
                "region": os.getenv("AWS_REGION") or os.getenv("AZURE_REGION") or "unknown",
            },
            "telemetry": {
                "host": "0.0.0.0",
                "port": 9090,
                "endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            },
            "secret_manager": {
                "provider": os.getenv("SECRET_MANAGER_PROVIDER", "none"),
                "vault_addr": os.getenv("VAULT_ADDR", ""),
            },
            "capabilities": {
                "causal_inference": True,
                "graph_reasoning": True,
                "counterfactual_generation": True,
            },
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return config

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _detect_cloud_provider(self, info: SystemInfo) -> str:
        if info.aws:
            return "aws"
        if info.azure:
            return "azure"
        if info.gcp:
            return "gcp"
        if info.tencent:
            return "tencent"
        if info.oracle:
            return "oracle"
        if info.alibaba:
            return "alibaba"
        if info.kubernetes:
            return "kubernetes"
        return "local"
