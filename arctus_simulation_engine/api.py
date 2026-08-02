"""RESTful API layer for simulation control and observability."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional

@dataclass
class APIResponse:
    status: int = 200
    body: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.body)

class RouteRegistry:
    def __init__(self):
        self._routes: Dict[str, Dict[str, Callable[..., APIResponse]]] = {}

    def add(self, method: str, path: str, handler: Callable[..., APIResponse]) -> None:
        self._routes.setdefault(method.upper(), {})[path] = handler

    def match(self, method: str, path: str) -> Optional[Callable[..., APIResponse]]:
        return self._routes.get(method.upper(), {}).get(path)

class SimulationAPI:
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self._registry = RouteRegistry()
        self._running = False
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._simulation_state: Dict[str, Any] = {"status": "idle", "scenario": None}
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._setup_routes()

    def register_handler(self, name: str, handler: Callable[..., Any]) -> None:
        self._handlers[name] = handler

    def _setup_routes(self) -> None:
        self._registry.add("GET", "/health", self.health_check)
        self._registry.add("GET", "/status", self.get_status)
        self._registry.add("POST", "/start", self.start_simulation)
        self._registry.add("POST", "/stop", self.stop_simulation)
        self._registry.add("POST", "/event", self.post_event)
        self._registry.add("GET", "/results", self.get_results)
        self._registry.add("GET", "/metrics", self.get_metrics)
        self._registry.add("POST", "/checkpoint", self.create_checkpoint)
        self._registry.add("GET", "/checkpoint/load", self.load_checkpoint)

    def health_check(self, **kwargs: Any) -> APIResponse:
        return APIResponse(body={"status": "healthy", "service": "artus.simulation.api"})

    def get_status(self, **kwargs: Any) -> APIResponse:
        return APIResponse(body=self._simulation_state.copy())

    def start_simulation(self, body: Optional[Dict[str, Any]] = None, **kwargs: Any) -> APIResponse:
        scenario = (body or {}).get("scenario", "default")
        self._simulation_state["status"] = "running"
        self._simulation_state["scenario"] = scenario
        self._simulation_state["started_at"] = time.time()
        self._simulation_state["run_id"] = str(uuid.uuid4())
        if "start_simulation" in self._handlers:
            self._handlers["start_simulation"](scenario)
        return APIResponse(body={"message": "Simulation started", "run_id": self._simulation_state["run_id"]})

    def stop_simulation(self, **kwargs: Any) -> APIResponse:
        self._simulation_state["status"] = "stopped"
        self._simulation_state["stopped_at"] = time.time()
        if "stop_simulation" in self._handlers:
            self._handlers["stop_simulation"]()
        return APIResponse(body={"message": "Simulation stopped"})

    def post_event(self, body: Optional[Dict[str, Any]] = None, **kwargs: Any) -> APIResponse:
        event = body or {}
        if "post_event" in self._handlers:
            self._handlers["post_event"](event)
        return APIResponse(body={"received": True, "event_type": event.get("type")})

    def get_results(self, **kwargs: Any) -> APIResponse:
        results: Dict[str, Any] = {}
        if "get_results" in self._handlers:
            results = self._handlers["get_results"]()
        return APIResponse(body={"results": results})

    def get_metrics(self, **kwargs: Any) -> APIResponse:
        metrics: Dict[str, Any] = {}
        if "get_metrics" in self._handlers:
            metrics = self._handlers["get_metrics"]()
        return APIResponse(body={"metrics": metrics})

    def create_checkpoint(self, body: Optional[Dict[str, Any]] = None, **kwargs: Any) -> APIResponse:
        cp_id = None
        if "create_checkpoint" in self._handlers:
            cp_id = self._handlers["create_checkpoint"](body)
        return APIResponse(body={"checkpoint_id": cp_id or str(uuid.uuid4())})

    def load_checkpoint(self, body: Optional[Dict[str, Any]] = None, **kwargs: Any) -> APIResponse:
        checkpoint_id = (body or {}).get("checkpoint_id", "")
        state = {}
        if "load_checkpoint" in self._handlers:
            state = self._handlers["load_checkpoint"](checkpoint_id)
        return APIResponse(body={"state": state})

    def _make_handler(self):
        registry = self._registry
        api_self = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def _handle(self, method: str):
                path = self.path.split("?")[0]
                handler = registry.match(method, path)
                body = None
                if method == "POST":
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length:
                        raw = self.rfile.read(content_length)
                        try:
                            body = json.loads(raw.decode("utf-8"))
                        except json.JSONDecodeError:
                            body = {}
                if handler:
                    try:
                        response = handler(body=body)
                    except Exception as e:
                        response = APIResponse(status=500, body={"error": str(e)})
                else:
                    response = APIResponse(status=404, body={"error": "Not found"})

                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.to_json().encode("utf-8"))

        return RequestHandler

    def start(self) -> None:
        if self._running:
            return
        handler = self._make_handler()
        self._server = HTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False

    def is_running(self) -> bool:
        return self._running
