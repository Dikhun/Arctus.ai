import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict

# ============================================================================
# PATH UTILITIES (duplicated here to avoid import issues)
# ============================================================================

def get_config_dir() -> Path:
    """Return user's arctus config directory."""
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    
    config_dir = base / "arctus"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Return path to config.json."""
    return get_config_dir() / "config.json"


# ============================================================================
# PRESET DEFINITIONS
# ============================================================================

@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    headers: Dict[str, str]
    timeout: int = 60
    tier: str = "fast"  # fast, strong, free
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "default_model": self.default_model,
            "headers": self.headers,
            "timeout": self.timeout,
            "tier": self.tier,
        }


# CORRECTED OpenRouter model endpoints (these work as of 2024)
# The error "No endpoints found for anthropic/claude-3.5-sonnet" was because
# the model ID was missing the date suffix or was incorrect.
OPENROUTER_PRESET = ProviderConfig(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    default_model="anthropic/claude-3.5-sonnet-20241022",  # FIXED: added date suffix
    headers={
        "HTTP-Referer": "https://arctus.ai",
        "X-Title": "Arctus AI Orchestrator",
    },
    timeout=120,
    tier="strong",
)

# OmniRoute uses OpenRouter infrastructure but with routing optimizations
OMNIROUTE_PRESET = ProviderConfig(
    name="omniroute",
    base_url="https://openrouter.ai/api/v1",  # OmniRoute proxies to OpenRouter
    api_key_env="OMNIROUTE_API_KEY",  # Can also use OPENROUTER_API_KEY
    default_model="anthropic/claude-3.5-sonnet-20241022",
    headers={
        "HTTP-Referer": "https://arctus.ai",
        "X-Title": "Arctus AI - OmniRoute",
        "X-OmniRoute-Priority": "balanced",  # balanced, speed, quality
    },
    timeout=90,
    tier="strong",
)

OLLAMA_PRESET = ProviderConfig(
    name="ollama",
    base_url="http://localhost:11434",
    api_key_env="",  # Ollama typically needs no key locally
    default_model="llama3.1",
    headers={"Content-Type": "application/json"},
    timeout=300,  # Local inference can be slow
    tier="fast",
)

HF_PRESET = ProviderConfig(
    name="hf",
    base_url="https://api-inference.huggingface.co",
    api_key_env="HF_TOKEN",
    default_model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    headers={},
    timeout=60,
    tier="free",
)

# Registry of all presets
PRESETS: Dict[str, ProviderConfig] = {
    "openrouter": OPENROUTER_PRESET,
    "omniroute": OMNIROUTE_PRESET,
    "ollama": OLLAMA_PRESET,
    "hf": HF_PRESET,
}


# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

def setup_provider(provider: str, api_key: Optional[str] = None, **kwargs) -> Path:
    """
    Configure a provider preset and write to config file.
    
    Args:
        provider: One of 'ollama', 'openrouter', 'omniroute', 'hf'
        api_key: API key (or read from environment)
        **kwargs: Additional configuration overrides
    
    Returns:
        Path to written config file
    """
    provider = provider.lower().strip()
    
    if provider not in PRESETS:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Available: {', '.join(PRESETS.keys())}"
        )
    
    preset = PRESETS[provider]
    config_path = get_config_path()
    
    # Build configuration
    config = {
        "version": "1.0.0",
        "active_provider": provider,
        "providers": {},
    }
    
    # Load existing config if present
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                existing = json.load(f)
                config.update(existing)
        except json.JSONDecodeError:
            pass  # Start fresh if corrupted
    
    # Get API key
    key = api_key or os.environ.get(preset.api_key_env, "")
    
    # Build provider entry
    provider_config = preset.to_dict()
    provider_config["api_key"] = key  # Store in config (or use env)
    
    # Apply any overrides
    for k, v in kwargs.items():
        if k in provider_config:
            provider_config[k] = v
    
    config["providers"][provider] = provider_config
    
    # Write config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    # Also write .env file for easy sourcing
    env_path = get_config_dir() / ".env"
    env_lines = []
    if env_path.exists():
        env_lines = env_path.read_text().splitlines()
    
    # Update or add the API key line
    env_var = preset.api_key_env
    new_line = f"{env_var}={key}"
    
    updated = False
    for i, line in enumerate(env_lines):
        if line.startswith(f"{env_var}="):
            env_lines[i] = new_line
            updated = True
            break
    
    if not updated:
        env_lines.append(new_line)
    
    # Add Ollama-specific env vars
    if provider == "ollama":
        env_lines.append('OLLAMA_HOST="http://localhost:11434"')
    
    with open(env_path, "w") as f:
        f.write("\n".join(env_lines) + "\n")
    
    print(f"Setup complete: applied '{provider}' preset.")
    print(f"Config: {config_path}")
    print(f"Env file: {env_path}")
    
    if provider == "openrouter" and not key:
        print("\nWARNING: No OPENROUTER_API_KEY found.")
        print("Set it with: export OPENROUTER_API_KEY=sk-or-v1-...")
    
    return config_path


def check_status() -> Dict[str, Any]:
    """
    Check health of all configured providers.
    
    Returns:
        Dictionary with status for each provider
    """
    results = {}
    config_path = get_config_path()
    
    if not config_path.exists():
        print("No configuration found. Run: arctus setup <provider>")
        return results
    
    with open(config_path) as f:
        config = json.load(f)
    
    providers = config.get("providers", {})
    
    # Check Ollama
    if "ollama" in providers:
        results["ollama"] = _check_ollama()
    
    # Check OpenRouter
    if "openrouter" in providers:
        results["openrouter"] = _check_openrouter(providers["openrouter"])
    
    # Check OmniRoute
    if "omniroute" in providers:
        results["omniroute"] = _check_omniroute(providers["omniroute"])
    
    # Check HF
    if "hf" in providers:
        results["hf"] = _check_hf(providers["hf"])
    
    # Print summary
    print("\n" + "=" * 40)
    print("Provider Status Summary")
    print("=" * 40)
    for name, status in results.items():
        icon = "✓" if status.get("ok") else "✗"
        msg = status.get("message", "unknown")
        print(f"  {icon} {name}: {msg}")
    
    return results


def _check_ollama() -> Dict[str, Any]:
    """Check Ollama health."""
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Accept": "application/json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return {
                "ok": True,
                "message": f"Running with {len(models)} models",
                "models": models,
            }
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "message": f"Cannot connect: {e.reason}",
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Error: {str(e)}",
        }


def _check_openrouter(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check OpenRouter health with test request."""
    key = config.get("api_key", "")
    if not key:
        return {"ok": False, "message": "No API key configured"}
    
    try:
        # Test with a minimal request to models endpoint
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return {"ok": True, "message": "API key valid"}
            else:
                return {"ok": False, "message": f"HTTP {resp.status}"}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"ok": False, "message": "Invalid API key"}
        return {"ok": False, "message": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def _check_omniroute(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check OmniRoute health."""
    # OmniRoute uses same backend as OpenRouter
    result = _check_openrouter(config)
    result["message"] = f"OmniRoute (via OpenRouter): {result['message']}"
    return result


def _check_hf(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check Hugging Face Inference API health."""
    token = config.get("api_key", "")
    if not token:
        return {"ok": False, "message": "No HF_TOKEN configured"}
    
    try:
        req = urllib.request.Request(
            "https://api-inference.huggingface.co/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "message": "HF API reachable"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def get_active_provider() -> Optional[str]:
    """Return the currently active provider name."""
    config_path = get_config_path()
    if not config_path.exists():
        return None
    
    try:
        with open(config_path) as f:
            config = json.load(f)
        return config.get("active_provider")
    except Exception:
        return None


def list_available_models(provider: str) -> List[str]:
    """List available models for a provider."""
    provider = provider.lower()
    
    if provider == "ollama":
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
    
    elif provider in ("openrouter", "omniroute"):
        # Static list of known working models
        return [
            "anthropic/claude-3.5-sonnet-20241022",
            "anthropic/claude-3-opus-20240229",
            "anthropic/claude-3-haiku-20240307",
            "openai/gpt-4o-2024-08-06",
            "openai/gpt-4o-mini-2024-07-18",
            "deepseek/deepseek-chat",
            "meta-llama/llama-3.1-70b-instruct",
            "meta-llama/llama-3.1-8b-instruct",
        ]
    
    elif provider == "hf":
        return [
            "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "microsoft/Phi-3-mini-4k-instruct",
        ]
    
    return []
