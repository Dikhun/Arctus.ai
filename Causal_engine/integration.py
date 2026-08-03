import asyncio
import logging
import os
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class EngineIntegrationClient:
    def __init__(self, name: str, endpoint_env: str, default_endpoint: str = "") -> None:
        self.name = name
        self.endpoint = os.getenv(endpoint_env, default_endpoint)

    async def is_reachable(self) -> bool:
        if not self.endpoint:
            return False
        try:
            parsed = urlparse(self.endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or 80
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def register_capability(self, capability: Dict[str, Any]) -> bool:
        logger.info(f"Registering capability with {self.name} at {self.endpoint}")
        if not await self.is_reachable():
            return False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.endpoint}/register",
                    json=capability,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    return resp.status in (200, 201)
        except Exception as exc:
            logger.warning(f"{self.name} registration failed: {exc}")
            return False

class IntegrationManager:
    def __init__(self) -> None:
        self.engines: Dict[str, EngineIntegrationClient] = {
            "digital_twin": EngineIntegrationClient(
                "DigitalTwinEngine", "DIGITAL_TWIN_ENDPOINT", "http://localhost:9001"
            ),
            "research": EngineIntegrationClient(
                "ResearchEngine", "RESEARCH_ENGINE_ENDPOINT", "http://localhost:9002"
            ),
            "simulation": EngineIntegrationClient(
                "SimulationEngine", "SIMULATION_ENGINE_ENDPOINT", "http://localhost:9003"
            ),
            "reasoning": EngineIntegrationClient(
                "ReasoningEngine", "REASONING_ENGINE_ENDPOINT", "http://localhost:9004"
            ),
            "meta_reasoning": EngineIntegrationClient(
                "MetaReasoningEngine", "META_REASONING_ENDPOINT", "http://localhost:9005"
            ),
            "experience_replay": EngineIntegrationClient(
                "ExperienceReplayEngine",
                "EXPERIENCE_REPLAY_ENDPOINT",
                "http://localhost:9006",
            ),
            "knowledge_graph": EngineIntegrationClient(
                "KnowledgeGraph", "KNOWLEDGE_GRAPH_ENDPOINT", "http://localhost:9007"
            ),
            "security": EngineIntegrationClient(
                "SecurityEngine", "SECURITY_ENGINE_ENDPOINT", "http://localhost:9008"
            ),
            "autonomous_improvement": EngineIntegrationClient(
                "AutonomousImprovementEngine",
                "AUTONOMOUS_IMPROVEMENT_ENDPOINT",
                "http://localhost:9009",
            ),
 }

    async def discover_and_connect(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for key, client in self.engines.items():
            reachable = await client.is_reachable()
            results[key] = reachable
            if reachable:
                logger.info(f"Integration available: {key}")
        return results

    async def publish_capabilities(self, capabilities: Dict[str, Any]) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for key, client in self.engines.items():
            if await client.is_reachable():
                results[key] = await client.register_capability(capabilities)
            else:
                results[key] = False
        return results
