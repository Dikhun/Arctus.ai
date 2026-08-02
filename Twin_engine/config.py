from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class TwinConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCTUS_", extra="ignore")

    project_root: Path = Field(default=Path("."), description="Root path to model")
    graph_backend: str = Field(default="memory", description="Graph backend: memory, neo4j, rdf")
    snapshot_dir: Path = Field(default=Path(".arctus/snapshots"))
    log_level: str = Field(default="INFO")
    sync_interval: float = Field(default=5.0, description="Seconds between sync polls")
    enable_prediction: bool = True
    enable_history: bool = True
    max_entities: int = 1_000_000
    event_queue_maxsize: int = 10_000

    restart_max_attempts: int = 5
    restart_base_delay: float = 1.0
    uv_path: str | None = None
  enable_auto_snapshot: bool = True
snapshot_interval: int = 300

graph_cache_size: int = 100_000

worker_threads: int = 4

shutdown_timeout: float = 30.0

health_check_interval: float = 5.0

enable_metrics: bool = True

enable_tracing: bool = False

enable_hot_reload: bool = True

max_parallel_tasks: int = 100

temp_dir: Path = Field(default=Path(".arctus/tmp"))

data_dir: Path = Field(default=Path(".arctus/data"))

logs_dir: Path = Field(default=Path(".arctus/logs"))
