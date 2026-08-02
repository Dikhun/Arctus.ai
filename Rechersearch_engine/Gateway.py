# arctus_research_engine/gateway.py
"""Ingress and egress adapter for the framework event bus."""

from datetime import datetime
from typing import Any, Dict

from arctus_research_engine.interfaces import IEventBus, ITelemetry
from arctus_research_engine.models import EventType, ResearchEvent, ResearchFragment
from arctus_research_engine.orchestrator import ResearchOrchestrator


class EventGateway:
    """Maps raw framework messages to domain events and delegates to orchestrator.
    Stateless: one gateway instance handles events for any correlation ID.
    """

    def __init__(
        self,
        event_bus: IEventBus,
        orchestrator: ResearchOrchestrator,
        telemetry: ITelemetry,
    ):
        self._event_bus = event_bus
        self._orchestrator = orchestrator
        self._telemetry = telemetry

    async def start(self) -> None:
        """Subscribe to all relevant topics. Called by framework lifecycle manager."""
        await self._event_bus.consume("research.requests", self._on_request)
        await self._event_bus.consume("research.fragments", self._on_fragment)
        await self._telemetry.log("info", "EventGateway started")

    async def stop(self) -> None:
        await self._telemetry.log("info", "EventGateway stopping")
        # Framework handles actual consumer unsubscribes and connection teardown.

    async def _on_request(self, payload: Dict[str, Any], delivery_tag: str) -> None:
        event = self._deserialize_event(payload)
        try:
            await self._orchestrator.run(event)
            await self._event_bus.ack(delivery_tag)
        except Exception:
            # Framework retry / dead-letter policy governs requeue semantics
            await self._event_bus.nack(delivery_tag, requeue=True)
            raise

    async def _on_fragment(self, payload: Dict[str, Any], delivery_tag: str) -> None:
        fragment = ResearchFragment(**payload)
        try:
            await self._orchestrator.handle_fragment(fragment)
            await self._event_bus.ack(delivery_tag)
        except Exception:
            await self._event_bus.nack(delivery_tag, requeue=True)
            raise

    def _deserialize_event(self, payload: Dict[str, Any]) -> ResearchEvent:
        return ResearchEvent(
            correlation_id=payload["correlation_id"],
            event_type=payload.get("event_type", EventType.RESEARCH_REQUEST.value),
            payload=payload.get("payload", payload),
            origin_timestamp=datetime.fromisoformat(payload.get("origin_timestamp", datetime.utcnow().isoformat())),
            processing_counter=payload.get("processing_counter", 0),
            sender_agent_id=payload.get("sender_agent_id"),
          )
