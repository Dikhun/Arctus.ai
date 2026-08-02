from __future__ import annotations

import random


class ExponentialBackoff:
    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_attempts: int = 5,
        jitter: bool = True,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        self.jitter = jitter
        self.attempts = 0

    def next_delay(self) -> float:
        if self.attempts >= self.max_attempts:
            raise RuntimeError("Maximum retry attempts exceeded")
        delay = min(self.base_delay * (2 ** self.attempts), self.max_delay)
        self.attempts += 1
        if self.jitter:
            delay *= random.uniform(0.8, 1.2)
        return delay

    def reset(self) -> None:
        self.attempts = 0
