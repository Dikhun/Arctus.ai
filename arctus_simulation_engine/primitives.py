from __future__ import annotationsimport enum
from dataclasses import dataclass

EntityId = strEventId = str
ScenarioId = str
CheckpointId = str


@dataclass(frozen=True, slots=True)
class SimulationTime:
    nanos: int = 0

    def __add__(self, other: Duration) -> SimulationTime:
        if not isinstance(other, Duration):
            return NotImplemented
        return SimulationTime(self.nanos + other.nanos)

    def __sub__(self, other: SimulationTime | Duration) -> SimulationTime | Duration:
        if isinstance(other, SimulationTime):
            return Duration(self.nanos - other.nanos)
        if isinstance(other, Duration):
            return SimulationTime(self.nanos - other.nanos)
        return NotImplemented

    def __lt__(self, other: SimulationTime) -> bool:
        return self.nanos < other.nanos

    def __le__(self, other: SimulationTime) -> bool:
        return self.nanos <= other.nanos

    def __gt__(self, other: SimulationTime) -> bool:
        return self.nanos > other.nanos

    def __ge__(self, other: SimulationTime) -> bool:
        return self.nanos >= other.nanos

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimulationTime):
            return NotImplemented
        return self.nanos == other.nanos

    def __hash__(self) -> int:
        return hash(self.nanos)

    @classmethod
    def from_seconds(cls, seconds: float) -> SimulationTime:
        return cls(int(seconds * 1_000_000_000))

    def to_seconds(self) -> float:
        return self.nanos / 1_000_000_000


@dataclass(frozen=True, slots=True)
class Duration:
    nanos: int = 0

    def __add__(self, other: Duration) -> Duration:
        return Duration(self.nanos + other.nanos)

    def __sub__(self, other: Duration) -> Duration:
        return Duration(self.nanos - other.nanos)

    def __mul__(self, scalar: float) -> Duration:
        return Duration(int(self.nanos * scalar))

    def __truediv__(self, scalar: float) -> Duration:
        return Duration(int(self.nanos / scalar))

    @classmethod
    def from_seconds(cls, seconds: float) -> Duration:
        return cls(int(seconds * 1_000_000_000))

    def to_seconds(self) -> float:
        return self.nanos / 1_000_000_000


class SimState(enum.StrEnum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"
    STOPPED = "stopped"
    ERROR = "error"


class EntityState(enum.StrEnum):
    SPAWNING = "spawning"
    ALIVE = "alive"
    SUSPENDED = "suspended"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
