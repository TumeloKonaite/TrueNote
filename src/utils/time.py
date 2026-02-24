from __future__ import annotations

import time
from dataclasses import dataclass


def now_unix_s() -> float:
    return time.time()


@dataclass(slots=True)
class Timer:
    start_s: float

    @classmethod
    def start(cls) -> "Timer":
        return cls(start_s=now_unix_s())

    def elapsed_s(self) -> float:
        return max(0.0, now_unix_s() - self.start_s)
