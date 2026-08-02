from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from arctus_simulation_engine.primitives import SimulationTime, Duration


@dataclass(slots=True)
class VirtualTime:
    _current: SimulationTime = field(default_factory=lambda: SimulationTime(0))
    _dilation: float = 1.0
    _listeners: list[Callable[[SimulationTime, SimulationTime], None]] = field(default_factory=list)

    @property
    def now(self) -> SimulationTime:
        return self._current

    def set(self, time: SimulationTime) -> None:
        if time < self._current:
            raise ValueError("Cannot rewind time without rollback capability")
        previous = self._current
        self._current = time
        self._notify(previous, self._current)

    def advance(self, duration: Duration) -> SimulationTime:
        previous = self._current
        scaled = int(duration.nanos * self._dilation)
        self._current = SimulationTime(self._current.nanos + scaled)
        self._notify(previous, self._current)
        return self._current

    def set_dilation(self, dilation: float) -> None:
        if dilation <= 0:
            raise ValueError("Dilation must be positive")
        self._dilation = dilation

    def dilation(self) -> float:
        return self._dilation

    def register_listener(self, listener: Callable[[SimulationTime, SimulationTime], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, previous: SimulationTime, current: SimulationTime) -> None:
        for listener in self._listeners:
            listener(previous, current)
