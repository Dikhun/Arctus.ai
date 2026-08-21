#!/usr/bin/env python3
"""
Arctus AI — config.py
User configuration management with validation.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION PATHS
# ═══════════════════════════════════════════════════════════════════════════

def get_config_path() -> Path:
    """Return the user configuration file path."""
    # Check environment override
    env_path = os.environ.get("ARCTUS_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    
    # Standard XDG config location
    config_dir = Path.home() / ".config" / "arctus"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def get_data_dir() -> Path:
    """Return the user data directory."""
    data_dir = Path.home() / ".local" / "share" / "arctus"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_cache_dir() -> Path:
    """Return the cache directory."""
    cache_dir = Path.home() / ".cache" / "arctus"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CLASS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    """User configuration with validation."""
    
    default_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "anthropic/claude-3.5-sonnet-20241022"
    hf_token: Optional[str] = None
    runpod_api_key: Optional[str] = None
    runpod_endpoint: Optional[str] = None
    tier: str = "auto"
    providers: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load configuration from file."""
        config_path = path or get_config_path()
        
        if not config_path.exists():
            # Return defaults
            return cls()
        
        with open(config_path) as f:
            data = json.load(f)
        
        # Filter to known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        
        return cls(**filtered)
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Save configuration to file."""
        config_path = path or get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, "w") as f:
            json.dump(asdict(self), f, indent=2)
        
        return config_path
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for a specific provider."""
        return self.providers.get(provider, {})
    
    def set_provider_config(self, provider: str, config: Dict[str, Any]) -> None:
        """Set configuration for a specific provider."""
        self.providers[provider] = config
    
    def get_api_key(self, env_var: str) -> Optional[str]:
        """Get API key from environment or config."""
        # Check environment first
        key = os.environ.get(env_var)
        if key:
            return key
        
        # Check config fields
        field_map = {
            "OPENROUTER_API_KEY": "openrouter_api_key",
            "HF_TOKEN": "hf_token",
            "RUNPOD_API_KEY": "runpod_api_key",
        }
        field_name = field_map.get(env_var)
        if field_name:
            return getattr(self, field_name, None)
        
        return None


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def validate_config(cfg: Config) -> list[str]:
    """Validate configuration and return list of issues."""
    issues = []
    
    # Check default provider
    valid_providers = {"ollama", "openrouter", "huggingface", "runpod", "hf"}
    if cfg.default_provider not in valid_providers:
        issues.append(f"Unknown default_provider: {cfg.default_provider}")
    
    # Check Ollama host format
    if cfg.ollama_host and not cfg.ollama_host.startswith(("http://", "https://")):
        issues.append(f"Invalid ollama_host: {cfg.ollama_host}")
    
    # Check API keys if provider requires them
    if cfg.default_provider == "openrouter" and not cfg.openrouter_api_key:
        # Not an error if set in env
        if not os.environ.get("OPENROUTER_API_KEY"):
            issues.append("OpenRouter API key not configured")
    
    return issues


# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "get_config_path",
    "get_data_dir",
    "get_cache_dir",
    "Config",
    "validate_config",
]