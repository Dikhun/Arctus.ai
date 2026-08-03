import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

class PureAsyncioTelemetryServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9090) -> None:
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.health_checks: List[Callable[[], Any]] = []
        self.metrics: Dict[str, Any] = {}

    def update_metrics(self, data: Dict[str, Any]) -> None:
        self.metrics.update(data)

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        addr = self.server.sockets[0].getsockname() if self.server.sockets else (self.host, self.port)
        logger.info(f"Telemetry server active on {addr}")

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await reader.read(65535)
            text = request.decode("utf-8", errors="ignore")
            path = self._parse_path(text)
            body = ""
            status = "404 Not Found"
            if path == "/health":
                body = await self._build_health()
                status = "200 OK"
            elif path == "/metrics":
                body = json.dumps(self.metrics)
                status = "200 OK"
            elif path == "/ready":
                body = json.dumps({"ready": True})
                status = "200 OK"
            response = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
                f"{body}"
            )
            writer.write(response.encode())
            await writer.drain()
        except Exception as exc:
            logger.error(f"Telemetry handler error: {exc}")
        finally:
            writer.close()
            await writer.wait_closed()

    def _parse_path(self, text: str) -> str:
        lines = text.splitlines()
        if lines:
            parts = lines[0].split(" ")
            if len(parts) > 1:
                return parts[1]
        return "/"

    async def _build_health(self) -> str:
        results: Dict[str, str] = {}
        overall = True
        for check in self.health_checks:
            try:
                ok = await check()
                results[check.__name__] = "healthy" if ok else "failed"
                if not ok:
                    overall = False
            except Exception:
                results[check.__name__] = "error"
                overall = False
        return json.dumps(
            {
                "healthy": overall,
                "checks": results,
                "timestamp": time.time(),
            }
        )

class AioHttpTelemetryServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9090) -> None:
        self.host = host
        self.port = port
        self.app: Any = None
        self.runner: Any = None
        self.metrics: Dict[str, Any] = {}
        self.health_checks: List[Callable[[], Any]] = []

    def update_metrics(self, data: Dict[str, Any]) -> None:
        self.metrics.update(data)

    async def start(self) -> None:
        import aiohttp.web as aw self.app = aw.Application()
        self.app.router.add_get("/health", self._health_handler)
        self.app.router.add_get("/metrics", self._metrics_handler)
        self.app.router.add_get("/ready", self._ready_handler)
        self.runner = aw.AppRunner(self.app)
        await self.runner.setup()
        site = aw.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"AIOHTTP telemetry on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    async def _health_handler(self, request: Any) -> Any:
        import aiohttp.web as aw
        results: Dict[str, str] = {}
        overall = True
        for check in self.health_checks:
            try:
                ok = await check()
                results[check.__name__] = "healthy" if ok else "failed"
                if not ok:
                    overall = False
            except Exception:
                results[check.__name__] = "error"
                overall = False
        return aw.json_response(
            {"healthy": overall, "checks": results, "timestamp": time.time()}
        )

    async def _metrics_handler(self, request: Any) -> Any:
        import aiohttp.web as aw
        return aw.json_response(self.metrics)

    async def _ready_handler(self, request: Any) -> Any:
        import aiohttp.web as aw
        return aw.json_response({"ready": True})
