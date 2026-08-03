import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from .types import CapabilityMeta

logger = logging.getLogger(__name__)

class FrameworkRegistry:
    def __init__(
        self,
        endpoint: str = "http://localhost:8080/arctus/registry",
    ) -> None:
        self.endpoint = endpoint
        self.capabilities: List[CapabilityMeta] = []

    async def register_engine(self, metadata: Dict[str, Any]) -> bool:
        payload = {
            "engine": "causal-engine",
            "version": "1.0.0",
            "metadata": metadata,
        }
        return await self._post("/engine", payload)

    def add_capability(self, cap: CapabilityMeta) -> None:
        self.capabilities.append(cap)

    async def publish_capabilities(self) -> bool:
        payload = [c.__dict__ for c in self.capabilities]
        return await self._post("/capabilities", payload)

    async def _post(self, path: str, payload: Dict[str, Any]) -> bool:
        url = f"{self.endpoint}{path}"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
 if resp.status in (200, 201, 202):
                        logger.info(f"Registry POST {path} succeeded")
                        return True
                    body = await resp.text()
                    logger.error(f"Registry POST {path} failed: {resp.status} {body}")
                    return False
        except Exception as exc:
            logger.warning(f"Registry unreachable ({url}): {exc}")
            return False

    def expose_capability_metadata(self) -> Dict[str, Any]:
        return {
            "engine": "causal-engine",
            "version": "1.0.0",
            "capabilities": [c.__dict__ for c in self.capabilities],
            "apis": {
                "health": "/health",
                "metrics": "/metrics",
                "ready": "/ready",
            },
                }
