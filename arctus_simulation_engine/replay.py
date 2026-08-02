"""Deterministic replay engine for simulation events."""

from __future__ import annotations

import json
import pickle
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

@dataclass(frozen=True)
class RecordedEvent:
    timestamp: float
    step: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source_id: str = ""

class EventLog:
    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.events: List[RecordedEvent] = []
        self.metadata = metadata or {}
        self._by_step: Dict[int, List[RecordedEvent]] = {}

    def append(self, event: RecordedEvent) -> None:
        self.events.append(event)
        self._by_step.setdefault(event.step, []).append(event)

    def get_events_for_step(self, step: int) -> List[RecordedEvent]:
        return self._by_step.get(step, []).copy()

    def save(self, path: Path) -> None:
        data = {
            "metadata": self.metadata,
            "events": [asdict(e) for e in self.events]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "EventLog":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        log = cls(metadata=data.get("metadata", {}))
        for e in data["events"]:
            log.append(RecordedEvent(**e))
        return log

class ReplayEngine:
    def __init__(self, step_executor: Callable[[int, List[RecordedEvent], Dict[str, Any]], None]):
        self._executor = step_executor
        self._log: Optional[EventLog] = None
        self._current_step = 0
        self._state_context: Dict[str, Any] = {}
        self._random_state: Optional[Any] = None
        self._playback_speed = 1.0
        self._recording = False
        self._live_log = EventLog()

    def start_recording(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._live_log = EventLog(metadata=metadata)
        self._recording = True
        self._current_step = 0

    def record_event(self, step: int, event_type: str, payload: Dict[str, Any], source_id: str = "") -> None:
        if not self._recording:
            return
        event = RecordedEvent(
            timestamp=time.time(),
            step=step,
            event_type=event_type,
            payload=payload.copy(),
            source_id=source_id
        )
        self._live_log.append(event)

    def record_random_state(self) -> None:
        if not self._recording:
            return
        state = random.getstate()
        self.record_event(self._current_step, "RANDOM_STATE", {"state": pickle.dumps(state).hex()})

    def stop_recording(self) -> EventLog:
        self._recording = False
        return self._live_log

    def load_log(self, path: Path) -> None:
        self._log = EventLog.load(path)
        self._current_step = 0

    def set_log(self, log: EventLog) -> None:
        self._log = log
        self._current_step = 0

    def replay(self, from_step: int = 0, to_step: Optional[int] = None) -> int:
        if self._log is None:
            raise RuntimeError("No log loaded")
        self._current_step = from_step
        max_step = max((e.step for e in self._log.events), default=0)
        end_step = to_step if to_step is not None else max_step
        steps_processed = 0
        for step in range(from_step, end_step + 1):
            events = self._log.get_events_for_step(step)
            for ev in events:
                if ev.event_type == "RANDOM_STATE" and "state" in ev.payload:
                    rs = pickle.loads(bytes.fromhex(ev.payload["state"]))
                    random.setstate(rs)
            self._executor(step, events, self._state_context)
            steps_processed += 1
            self._current_step = step
        return steps_processed

    def seek(self, step: int) -> None:
        self._current_step = step

    def step_forward(self) -> bool:
        if self._log is None:
            return False
        future = [e.step for e in self._log.events if e.step > self._current_step]
        if not future:
            return False
        next_step = min(future)
        self.replay(from_step=next_step, to_step=next_step)
        return True

    def step_backward(self, state_loader: Callable[[int], Dict[str, Any]]) -> bool:
        target = self._current_step - 1
        if target < 0:
            return False
        self._state_context = state_loader(target)
        self._current_step = target
        return True

    def set_context(self, key: str, value: Any) -> None:
        self._state_context[key] = value

    def get_context(self, key: str) -> Any:
        return self._state_context.get(key)
