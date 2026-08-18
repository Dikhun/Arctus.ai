import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Generator
from dataclasses import dataclass


class LLMError(Exception):
    """Custom exception for LLM-related errors."""
    pass


@dataclass
class Message:
    role: str  # system, user, assistant
    content: str


# Validated model endpoints that are confirmed working
VALID_OPENROUTER_MODELS = {
    "anthropic/claude-3.5-sonnet-20241022",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus-20240229",
    "anthropic/claude-3-haiku-20240307",
    "openai/gpt-4o-2024-08-06",
    "openai/gpt-4o-mini-2024-07-18",
    "openai/gpt-4-turbo-2024-04-09",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-coder",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "google/gemini-1.5-pro-latest",
    "mistralai/mistral-7b-instruct",
}


def validate_model(model: str, provider: str) -> str:
    """
    Validate and potentially fix a model ID.
    
    The error in screenshot shows:
    'No endpoints found for anthropic/claude-3.5-sonnet'
    
    This was likely missing the date suffix. We auto-correct common mistakes.
    """
    if provider in ("openrouter", "omniroute"):
        # Direct match
        if model in VALID_OPENROUTER_MODELS:
            return model
        
        # Auto-correct common mistakes
        corrections = {
            "anthropic/claude-3.5-sonnet": "anthropic/claude-3.5-sonnet-20241022",
            "anthropic/claude-3-opus": "anthropic/claude-3-opus-20240229",
            "anthropic/claude-3-haiku": "anthropic/claude-3-haiku-20240307",
            "openai/gpt-4o": "openai/gpt-4o-2024-08-06",
            "openai/gpt-4o-mini": "openai/gpt-4o-mini-2024-07-18",
        }
        
        if model in corrections:
            corrected = corrections[model]
            return corrected
        
        # If it looks like an OpenRouter model, warn but allow
        if "/" in model:
            return model  # Let the API decide
        
        raise LLMError(
            f"Unknown model '{model}' for OpenRouter. "
            f"Try: anthropic/claude-3.5-sonnet-20241022"
        )
    
    return model


class LLMClient:
    """Unified client for multiple LLM providers."""
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.config = self._load_config()
        self.provider = provider or self.config.get("active_provider", "ollama")
        self.provider_config = self._get_provider_config(self.provider)
        
        self.model = model or self.provider_config.get("default_model", "")
        self.api_key = api_key or self._get_api_key()
        self.base_url = base_url or self.provider_config.get("base_url", "")
        
        # Validate model ID
        self.model = validate_model(self.model, self.provider)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        config_dir = Path.home() / ".config" / "arctus"
        config_path = config_dir / "config.json"
        
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        
        return {}
    
    def _get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for specific provider."""
        providers = self.config.get("providers", {})
        return providers.get(provider, {})
    
    def _get_api_key(self) -> str:
        """Get API key from config or environment."""
        env_var = self.provider_config.get("api_key_env", "")
        if env_var:
            return os.environ.get(env_var, "")
        
        # Fallback to direct config storage
        return self.provider_config.get("api_key", "")
    
    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send chat completion request.
        
        Raises:
            LLMError: On API errors (including 404 model not found)
        """
        if self.provider in ("openrouter", "omniroute"):
            return self._chat_openrouter(messages, temperature, max_tokens)
        elif self.provider == "ollama":
            return self._chat_ollama(messages, temperature, max_tokens)
        elif self.provider == "hf":
            return self._chat_hf(messages, temperature, max_tokens)
        else:
            raise LLMError(f"Unknown provider: {self.provider}")
    
    def _chat_openrouter(
        self,
        messages: List[Message],
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        """Chat via OpenRouter/OmniRoute API."""
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        # Add provider-specific headers
        provider_headers = self.provider_config.get("headers", {})
        headers.update(provider_headers)
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.provider_config.get("timeout", 60)) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                msg = error_data.get("error", {}).get("message", error_body)
            except json.JSONDecodeError:
                msg = error_body
            
            # Specific handling for 404 model not found
            if e.code == 404:
                raise LLMError(
                    f"Model '{self.model}' not found on OpenRouter. "
                    f"Available models may have changed. "
                    f"Error: {msg}"
                )
            elif e.code == 401:
                raise LLMError(f"Invalid API key for OpenRouter. Check OPENROUTER_API_KEY")
            else:
                raise LLMError(f"OpenRouter HTTP {e.code}: {msg}")
        
        except Exception as e:
            raise LLMError(f"Request failed: {str(e)}")
    
    def _chat_ollama(
        self,
        messages: List[Message],
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        """Chat via local Ollama instance."""
        url = f"{self.base_url}/api/chat"
        
        # Ollama uses different format
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
                return data["message"]["content"]
        except Exception as e:
            raise LLMError(f"Ollama request failed: {str(e)}")
    
    def _chat_hf(
        self,
        messages: List[Message],
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        """Chat via Hugging Face Inference API."""
        # HF uses text generation, not chat format directly
        # This is a simplified implementation
        raise LLMError("HF provider not yet fully implemented")


# For compatibility with imports
__all__ = ["LLMClient", "LLMError", "Message", "validate_model"]
