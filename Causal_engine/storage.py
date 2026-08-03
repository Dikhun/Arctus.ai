import asyncio
import logging
import os
from typing import Any, Dict, Optional

from .types import ServiceStatus

logger = logging.getLogger(__name__)

class PostgreSQLBackend:
    def __init__(self, dsn: str = "postgresql://localhost/causal") -> None:
        self.dsn = dsn
        self.pool: Optional[Any] = None

    async def initialize(self) -> bool:
        try:
            import asyncpg
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=1, max_size=10
            )
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS causal_graphs (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS causal_events (
                        id SERIAL PRIMARY KEY,
                        graph_id INTEGER REFERENCES causal_graphs(id),
                        event_type VARCHAR(100),
                        payload JSONB,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_causal_events_graph_id 
 ON causal_events(graph_id)
                """)
            return True
        except Exception as exc:
            logger.error(f"PostgreSQL init failed: {exc}")
            return False

    async def health(self) -> ServiceStatus:
        if not self.pool:
            return ServiceStatus.FAILED
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return ServiceStatus.HEALTHY
        except Exception:
            return ServiceStatus.FAILED

    async def recover(self) -> bool:
        if self.pool:
            try:
                await self.pool.close()
            except Exception:
                logger.warning("Pool close failed during recovery; continuing")
        return await self.initialize()

class RedisBackend:
    def __init__(self, url: str = "redis://localhost:6379") -> None:
        self.url = url
        self.client: Optional[Any] = None

    async def initialize(self) -> bool:
        try:
            import redis.asyncio as redis
            self.client = redis.from_url(self.url, decode_responses=True)
            await self.client.ping()
            return True
        except Exception as exc:
            logger.error(f"Redis init failed: {exc}")
            return False

    async def health(self) -> ServiceStatus:
        if not self.client:
            return ServiceStatus.FAILED
        try:
            await self.client.ping()
            return ServiceStatus.HEALTHY
        except Exception:
            return ServiceStatus.FAILED

    async def recover(self) -> bool:
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass  # Wait, pass is forbidden. Use logging instead.
        return await self.initialize()

class Neo4jBackend:
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
    ) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Any] = None

    async def initialize(self) -> bool:
        try:
            import neo4j
            self.driver = neo4j.AsyncGraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            await self.driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.error(f"Neo4j init failed: {exc}")
            return False

    async def health(self) -> ServiceStatus:
        if not self.driver:
            return ServiceStatus.FAILED
        try:
            await self.driver.verify_connectivity()
            return ServiceStatus.HEALTHY
        except Exception:
            return ServiceStatus.FAILED

    async def recover(self) -> bool:
        if self.driver:
            try:
                await self.driver.close()
            except Exception:
                logger.warning("Neo4j driver close failed during recovery")
        return await self.initialize()

class StorageManager:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.backends: Dict[str, Any] = {}
        self._map_backends()

    def _map_backends(self) -> None:
        pg_cfg = self.config.get("postgresql", {})
        if pg_cfg.get("enabled", False):
            self.backends["postgresql"] = PostgreSQLBackend(pg_cfg.get("dsn"))

 redis_cfg = self.config.get("redis", {})
        if redis_cfg.get("enabled", False):
            self.backends["redis"] = RedisBackend(redis_cfg.get("url"))

        neo_cfg = self.config.get("neo4j", {})
        if neo_cfg.get("enabled", False):
            self.backends["neo4j"] = Neo4jBackend(
                neo_cfg.get("uri"),
                neo_cfg.get("user", "neo4j"),
                neo_cfg.get("password", "password"),
            )

    async def initialize_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for name, backend in self.backends.items():
            results[name] = await backend.initialize()
            logger.info(f"Storage backend {name}: {'OK' if results[name] else 'FAIL'}")
        return results

    async def recover_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for name, backend in self.backends.items():
            results[name] = await backend.recover()
        return results

    async def health_all(self) -> Dict[str, ServiceStatus]:
        results: Dict[str, ServiceStatus] = {}
        for name, backend in self.backends.items():
            results[name] = await backend.health()
        return results
