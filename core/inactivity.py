from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class InactivityTracker:
    minutes: int = 30

    def __post_init__(self) -> None:
        self._last_activity = time.time()

    def touch(self) -> None:
        self._last_activity = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self._last_activity) > (self.minutes * 60)

    def reset(self, minutes: int | None = None) -> None:
        if minutes is not None:
            self.minutes = minutes
        self.touch()
