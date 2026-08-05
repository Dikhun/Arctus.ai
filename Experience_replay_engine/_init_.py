Arctus experience Replay Engine
Preview
Code
# =============================================================================
# Arctus AI Operating System — Experience Replay Engine
# =============================================================================
# Module: experience_replay/
# Role:  Capture, store, analyze, and replay all execution experiences to enable
#        continuous learning, failure prevention, and capability improvement.
# =============================================================================

# =============================================================================
# FILE: experience_replay/__init__.py
# =============================================================================

"""
Arctus Experience Replay Engine

Transforms every execution into reusable experience that continuously improves
future planning, reasoning, execution, and learning.
"""

__version__ = "1.0.0"
__author__ = "Arctus AI Systems"

from .engine import ExperienceReplayEngine
from .recorder import ExperienceRecorder
from .storage import ExperienceStorage
from .replay import ReplayExecutor
from .retrieval import ExperienceRetrieval
from .ranking import ExperienceRanker
from .indexing import ExperienceIndexer
from .embeddings import EmbeddingGenerator
from .similarity import SimilaritySearch
from .compression import ExperienceCompressor
from .deduplication import DeduplicationEngine
from .summarizer import ExperienceSummarizer
from .feedback import FeedbackIntegrator
from .reward import RewardCalculator
from .reinforcement import RLIntegration
from .forgetting import ForgettingPolicy
from .retention import RetentionPolicy
from .analytics import ExperienceAnalytics
from .visualization import ReplayVisualizer
from .api import ReplayAPI
from .config import ReplayConfig

__all__ = [
    "ExperienceReplayEngine",
    "ExperienceRecorder",
    "ExperienceStorage",
    "ReplayExecutor",
    "ExperienceRetrieval",
    "ExperienceRanker",
    "ExperienceIndexer",
    "EmbeddingGenerator",
    "SimilaritySearch",
    "ExperienceCompressor",
    "DeduplicationEngine",
    "ExperienceSummarizer",
    "FeedbackIntegrator",
    "RewardCalculator",
    "RLIntegration",
    "ForgettingPolicy",
    "RetentionPolicy",
    "ExperienceAnalytics",
    "ReplayVisualizer",
    "ReplayAPI",
    "ReplayConfig",
]


# =============================================================================
# FILE: experience_replay/config.py
# =============================================================================

"""
Configuration for the Experience Replay Engine.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class StorageConfig:
    """Database and storage configuration."""
    backend: str = "sqlite"  # sqlite, postgresql, mongodb, redis
    connection_string: Optional[str] = None
    database_path: str = "./data/experience_replay.db"
    index_path: str = "./data/experience_index"
    embedding_cache_path: str = "./data/embeddings"
    max_experience_size_mb: int = 10
    compression_threshold_days: int = 30
    deduplication_enabled: bool = True
    batch_size: int = 100


@dataclass
class EmbeddingConfig:
    """Semantic embedding configuration."""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_dimension: int = 384
    normalize_embeddings: bool = True
    batch_size: int = 32
    device: str = "cpu"
    cache_embeddings: bool = True


@dataclass
class ReplayConfig:
    """Main configuration for the Experience Replay Engine."""
    
    # Storage
    storage: StorageConfig = field(default_factory=StorageConfig)
    
    # Embeddings
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    
    # Replay settings
    max_replay_steps: int = 10000
    replay_timeout_seconds: int = 300
    deterministic_mode: bool = True
    branch_from_any_point: bool = True
    
    # Learning
    learning_rate: float = 0.001
    discount_factor: float = 0.95
    priority_alpha: float = 0.6  # Priority exponent for PER
    priority_beta: float = 0.4  # Importance sampling exponent
    
    # Retention
    max_experiences: int = 1000000
    retention_window_days: int = 365
    forget_threshold: float = 0.1  # Minimum importance to retain
    
    # Compression
    compression_enabled: bool = True
    compression_ratio: float = 0.5
    summarize_after_steps: int = 100
    
    # Analytics
    analytics_enabled: bool = True
    metrics_collection_interval: int = 60
    
    # Feedback
    feedback_weight_user: float = 1.0
    feedback_weight_verification: float = 0.8
    feedback_weight_simulation: float = 0.6
    
    # Classification thresholds
    success_threshold: float = 0.8
    partial_success_threshold: float = 0.5
    failure_threshold: float = 0.3
    
    # Integration
    kernel_endpoint: Optional[str] = None
    knowledge_graph_endpoint: Optional[str] = None
    capability_graph_endpoint: Optional[str] = None
    
    def __post_init__(self):
        """Ensure paths exist."""
        Path(self.storage.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.storage.index_path).mkdir(parents=True, exist_ok=True)
        Path(self.storage.embedding_cache_path).mkdir(parents=True, exist_ok=True)

