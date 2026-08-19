#!/usr/bin/env python3
"""
Arctus AI — llm.py
Unified LLM client with provider adapters for:
    • Ollama (local / remote)
    • OpenRouter (unified gateway)
    • OmniRoute (local gateway)
    • RunPod (serverless endpoints)
    • HuggingFace Inference API
    • Generic OpenAI-compatible endpoints

Design: async-first with sync wrappers, automatic retries,
        streaming support where available, unified error taxonomy.
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Iterator,
    Optional,
    Union,
    cast,
)
from enum import Enum
from contextlib import asynccontextmanager

# ── Optional dependencies with graceful degradation ─────────────────────────
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

# ── Internal imports ────────────────────────────────────────────────────────
from .presets import (
    ProviderPreset,
    ModelPreset,
    resolve_preset,
    get_api_key,
    PROVIDER_REGISTRY,
)

logger = logging.getLogger("arctus.llm")


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPTION HIERARCHY
# ═══════════════════════════════════════════════════════════════════════════

class LLMError(Exception):
    """Base for all LLM client errors."""
    pass


class LLMConfigError(LLMError):
    """Misconfiguration (missing API key, bad base URL, etc.)."""
    pass


class LLMRequestError(LLMError):
    """HTTP-level failure (timeout, connection reset, 5xx)."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class LLMResponseError(LLMError):
    """Malformed or unexpected response payload."""
    pass


class LLMRateLimitError(LLMRequestError):
    """429 or explicit rate-limit signal."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None  # For tool/assistant differentiation
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    finish_reason: Optional[str] = None
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class StreamChunk:
    content: str
    finish_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# BASE ADAPTER (Abstract)
# ═══════════════════════════════════════════════════════════════════════════

class BaseLLMClient(ABC):
    """
    Abstract interface all provider adapters implement.
    """
    
    def __init__(
        self,
        provider_preset: ProviderPreset,
        model_preset: ModelPreset,
        api_key: Optional[str] = None,
    ):
        self.preset = provider_preset
        self.model = model_preset
        self.api_key = api_key or get_api_key(provider_preset)
        self._validate_config()
    
    def _validate_config(self) -> None:
        if self.preset.api_key_env and not self.api_key:
            # Some providers (Ollama) don't require keys; warn only
            if self.preset.name not in ("ollama",):
                raise LLMConfigError(
                    f"API key required for {self.preset.name}. "
                    f"Set env var: {self.preset.api_key_env}"
                )
    
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Union[LLMResponse, AsyncIterator[StreamChunk]]:
        """Send chat completion request. Returns response or async stream."""
        raise NotImplementedError
    
    @abstractmethod
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """Request text embeddings."""
        raise NotImplementedError
    
    def _build_headers(self) -> dict[str, str]:
        """Common headers; subclasses extend."""
        headers = {
            "Content-Type": "application/json",
            **self.preset.headers,
        }
        if self.api_key:
            if self.preset.name == "huggingface":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def _merge_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Inject preset extra_body parameters."""
        merged = {**self.preset.extra_body, **body}
        return merged
    
    @staticmethod
    def _parse_usage(raw: dict[str, Any]) -> dict[str, int]:
        """Extract token usage with safe defaults."""
        usage = raw.get("usage") or {}
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }


# ═══════════════════════════════════════════════════════════════════════════
# HTTPX-BASED ADAPTER (OpenAI-compatible shape)
# ═══════════════════════════════════════════════════════════════════════════

class HTTPXAdapter(BaseLLMClient):
    """
    Generic OpenAI-compatible adapter using httpx.
    Covers: OpenRouter, OmniRoute, OpenAI, RunPod (when OpenAI-compatible),
            Ollama (OpenAI compatibility mode /api/v1).
    """
    
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if httpx is None:
            raise LLMConfigError("httpx is required for HTTPXAdapter. "
                                 "Install: pip install httpx")
        self.client = httpx.AsyncClient(
            base_url=self.preset.base_url,
            timeout=httpx.Timeout(self.preset.request_timeout),
            headers=self._build_headers(),
        )
    
    async def chat(
        self,
        messages: list[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Union[LLMResponse, AsyncIterator[StreamChunk]]:
        
        payload: dict[str, Any] = {
            "model": self.model.model_id,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in messages
            ],
            "temperature": temperature if temperature is not None else self.model.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.model.max_tokens,
        }
        
        if tools and self.preset.supports_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        payload = self._merge_body(payload)
        url = "/chat/completions"
        
        # Retry loop
        last_error: Optional[Exception] = None
        for attempt in range(self.preset.max_retries + 1):
            try:
                if stream:
                    return self._chat_stream(payload, url)
                return await self._chat_sync(payload, url)
            except LLMRateLimitError:
                wait = self.preset.retry_backoff * (2 ** attempt)
                logger.warning("Rate limited; retrying in %.1fs (attempt %d/%d)",
                             wait, attempt + 1, self.preset.max_retries)
                await asyncio.sleep(wait)
            except (LLMRequestError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < self.preset.max_retries:
                    wait = self.preset.retry_backoff * (2 ** attempt)
                    await asyncio.sleep(wait)
        
        raise LLMRequestError(f"Failed after {self.preset.max_retries} retries: {last_error}")
    
    async def _chat_sync(self, payload: dict[str, Any], url: str) -> LLMResponse:
        resp = await self.client.post(url, json=payload)
        await self._check_http_error(resp)
        data = resp.json()
        return self._parse_chat_response(data)
    
    async def _chat_stream(
        self,
        payload: dict[str, Any],
        url: str,
    ) -> AsyncIterator[StreamChunk]:
        payload["stream"] = True
        async with self.client.stream("POST", url, json=payload) as resp:
            await self._check_http_error(resp)
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = parsed.get("choices", [{}])[0].get("delta", {})
                finish = parsed.get("choices", [{}])[0].get("finish_reason")
                yield StreamChunk(content=delta.get("content", ""), finish_reason=finish)
    
    def _parse_chat_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return LLMResponse(
            text=msg.get("content", ""),
            model=data.get("model", self.model.model_id),
            provider=self.preset.name,
            finish_reason=choice.get("finish_reason"),
            usage=self._parse_usage(data),
            raw=data,
        )
    
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model.model_id, "input": texts}
        resp = await self.client.post("/embeddings", json=payload)
        await self._check_http_error(resp)
        data = resp.json()
        return [item.get("embedding", []) for item in data.get("data", [])]
    
    async def _check_http_error(self, resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise LLMRateLimitError("Rate limited", status_code=429)
        if resp.status_code >= 500:
            raise LLMRequestError(f"Server error {resp.status_code}", status_code=resp.status_code)
        if resp.status_code >= 400:
            text = await resp.aread() if hasattr(resp, "aread") else resp.text
            raise LLMRequestError(f"Client error {resp.status_code}: {text[:500]}",
                                  status_code=resp.status_code)
    
    async def close(self) -> None:
        await self.client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# OLLAMA NATIVE ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class OllamaAdapter(BaseLLMClient):
    """
    Native Ollama /api/chat and /api/generate endpoints.
    Uses httpx; falls back to aiohttp if available.
    """
    
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if httpx is None:
            raise LLMConfigError("httpx required for OllamaAdapter")
        self.client = httpx.AsyncClient(
            base_url=self.preset.base_url,  # e.g. http://localhost:11434
            timeout=httpx.Timeout(self.preset.request_timeout),
        )
    
    async def chat(
        self,
        messages: list[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Union[LLMResponse, AsyncIterator[StreamChunk]]:
        
        ollama_messages = []
        for m in messages:
            ollama_messages.append({
                "role": m.role.value,
                "content": m.content,
            })
        
        payload = {
            "model": self.model.model_id,
            "messages": ollama_messages,
            "options": {
                "temperature": temperature if temperature is not None else self.model.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.model.max_tokens,
            },
            "stream": stream,
        }
        
        if tools and self.preset.supports_tools:
            payload["tools"] = tools
        
        for attempt in range(self.preset.max_retries + 1):
            try:
                if stream:
                    return self._stream_chat(payload)
                return await self._sync_chat(payload)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self.preset.max_retries:
                    wait = self.preset.retry_backoff * (2 ** attempt)
                    logger.warning("Ollama connection failed; retry in %.1fs: %s", wait, exc)
                    await asyncio.sleep(wait)
                else:
                    raise LLMRequestError(f"Cannot connect to Ollama at {self.preset.base_url}: {exc}")
    
    async def _sync_chat(self, payload: dict[str, Any]) -> LLMResponse:
        resp = await self.client.post("/api/chat", json=payload)
        self._raise_for_status(resp)
        data = resp.json()
        return LLMResponse(
            text=data.get("message", {}).get("content", ""),
            model=self.model.model_id,
            provider="ollama",
            finish_reason="stop" if data.get("done") else None,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
            },
            raw=data,
        )
    
    async def _stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[StreamChunk]:
        async with self.client.stream("POST", "/api/chat", json=payload) as resp:
            self._raise_for_status(resp)
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = data.get("message", {}).get("content", "")
                done = data.get("done", False)
                yield StreamChunk(content=content, finish_reason="stop" if done else None)
    
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model.model_id, "prompt": texts[0] if texts else ""}
        resp = await self.client.post("/api/embeddings", json=payload)
        self._raise_for_status(resp)
        data = resp.json()
        emb = data.get("embedding", [])
        return [emb] if emb else []
    
    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise LLMRequestError(f"Ollama error {resp.status_code}: {resp.text[:500]}",
                                  status_code=resp.status_code)
    
    async def close(self) -> None:
        await self.client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# HUGGINGFACE INFERENCE API ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class HuggingFaceAdapter(BaseLLMClient):
    """
    HuggingFace Inference API (serverless) and Inference Endpoints (dedicated).
    Supports text-generation and chat-completion tasks.
    """
    
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if httpx is None:
            raise LLMConfigError("httpx required for HuggingFaceAdapter")
        self.client = httpx.AsyncClient(
            base_url=self.preset.base_url,
            timeout=httpx.Timeout(self.preset.request_timeout),
            headers=self._build_headers(),
        )
    
    async def chat(
        self,
        messages: list[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
    ) -> LLMResponse:
        # HF Inference API uses a simple text input for many models;
        # newer models support chat-completion-like payloads.
        prompt = self._messages_to_prompt(messages)
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature if temperature is not None else self.model.temperature,
                "max_new_tokens": max_tokens if max_tokens is not None else self.model.max_tokens,
                "return_full_text": False,
            },
        }
        
        model_path = f"/models/{self.model.model_id}"
        resp = await self.client.post(model_path, json=payload)
        self._raise_for_status(resp)
        data = resp.json()
        
        # HF returns list of generation objects
        if isinstance(data, list) and len(data) > 0:
            generated = data[0].get("generated_text", "")
        elif isinstance(data, dict):
            generated = data.get("generated_text", "")
        else:
            generated = str(data)
        
        return LLMResponse(
            text=generated,
            model=self.model.model_id,
            provider="huggingface",
            raw=data if isinstance(data, dict) else {},
        )
    
    def _messages_to_prompt(self, messages: list[Message]) -> str:
        """Convert message list to a single prompt string for HF."""
        parts: list[str] = []
        for m in messages:
            if m.role == MessageRole.SYSTEM:
                parts.append(f"System: {m.content}")
            elif m.role == MessageRole.USER:
                parts.append(f"User: {m.content}")
            elif m.role == MessageRole.ASSISTANT:
                parts.append(f"Assistant: {m.content}")
        return "\n".join(parts)
    
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        # HF sentence-transformers inference
        payload = {"inputs": texts}
        resp = await self.client.post(
            f"/pipeline/feature-extraction/{self.model.model_id}",
            json=payload,
        )
        self._raise_for_status(resp)
        data = resp.json()
        if isinstance(data, list):
            return cast(list[list[float]], data)
        return []
    
    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise LLMRequestError(f"HF error {resp.status_code}: {resp.text[:500]}",
                                  status_code=resp.status_code)
    
    async def close(self) -> None:
        await self.client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# RUNPOD SERVERLESS ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class RunPodAdapter(BaseLLMClient):
    """
    RunPod serverless endpoint adapter.
    Supports both RunPod's native endpoint format and OpenAI-compatible wrappers.
    """
    
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if httpx is None:
            raise LLMConfigError("httpx required for RunPodAdapter")
        self.client = httpx.AsyncClient(
            base_url=self.preset.base_url,
            timeout=httpx.Timeout(self.preset.request_timeout),
            headers=self
