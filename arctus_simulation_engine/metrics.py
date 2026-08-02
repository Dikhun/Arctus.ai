"""Simulation metrics collection and statistical analysis."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Sequence

@dataclass
class Metric:
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class TimeSeries:
    values: deque = field(default_factory=lambda: deque(maxlen=10000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=10000))

    def append(self, value: float, timestamp: Optional[float] = None) -> None:
        self.values.append(value)
        self.timestamps.append(timestamp or time.time())

    @property
    def latest(self) -> float:
        return self.values[-1] if self.values else 0.0

    def windowed_average(self, window_seconds: float) -> float:
        if not self.values:
            return 0.0
        now = time.time()
        total = 0.0
        count = 0
        for v, ts in zip(reversed(self.values), reversed(self.timestamps)):
            if now - ts <= window_seconds:
                total += v
                count += 1
            else:
                break
        return total / count if count > 0 else 0.0

class MetricsCollector:
    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = defaultdict(list)
        self._series: Dict[str, TimeSeries] = defaultdict(TimeSeries)
        self._gauges: Dict[str, float] = {}
        self._counters: Dict[str, float] = defaultdict(float)

    def record(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        metric = Metric(name=name, value=value, tags=tags or {})
        self._metrics[name].append(metric)
        self._series[name].append(value)

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value
        self.record(name, value, tags={"type": "gauge"})

    def counter(self, name: str, delta: float = 1.0) -> None:
        self._counters[name] += delta
        self.record(name, self._counters[name], tags={"type": "counter"})

    def compute_statistics(self, name: str) -> Dict[str, float]:
        series = list(self._series[name].values)
        if not series:
            return {"count": 0.0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": float(len(series)),
            "mean": mean(series),
            "std": stdev(series) if len(series) > 1 else 0.0,
            "min": min(series),
            "max": max(series),
            "median": median(series)
        }

    def windowed_average(self, name: str, window_seconds: float) -> float:
        return self._series[name].windowed_average(window_seconds)

    def compare(self, name_a: str, name_b: str) -> Dict[str, float]:
        stats_a = self.compute_statistics(name_a)
        stats_b = self.compute_statistics(name_b)
        return {
            "mean_delta": stats_a.get("mean", 0.0) - stats_b.get("mean", 0.0),
            "std_delta": stats_a.get("std", 0.0) - stats_b.get("std", 0.0),
            "correlation_estimate": self._correlation(name_a, name_b)
        }

    def _correlation(self, a: str, b: str) -> float:
        vals_a = list(self._series[a].values)[-1000:]
        vals_b = list(self._series[b].values)[-1000:]
        n = min(len(vals_a), len(vals_b))
        if n < 2:
            return 0.0
        vals_a = vals_a[-n:]
        vals_b = vals_b[-n:]
        mean_a = sum(vals_a) / n
        mean_b = sum(vals_b) / n
        num = sum((x - mean_a) * (y - mean_b) for x, y in zip(vals_a, vals_b))
        den = math.sqrt(sum((x - mean_a) ** 2 for x in vals_a) * sum((y - mean_b) ** 2 for y in vals_b))
        return num / den if den != 0 else 0.0

    def export(self, names: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        keys = names or list(self._metrics.keys())
        return {
            name: {
                "statistics": self.compute_statistics(name),
                "latest": self._series[name].latest if name in self._series else None,
                "gauges": {k: v for k, v in self._gauges.items() if k == name},
                "counters": {k: v for k, v in self._counters.items() if k == name}
            }
            for name in keys
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "total_series": len(self._series),
            "total_metrics": sum(len(v) for v in self._metrics.values()),
            "all_statistics": {k: self.compute_statistics(k) for k in self._metrics}
      }
