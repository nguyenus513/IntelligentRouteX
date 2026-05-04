from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Deadline:
    end_perf_counter: float

    @classmethod
    def from_time_limit_ms(cls, ms: int) -> "Deadline":
        return cls(time.perf_counter() + max(0, int(ms)) / 1000.0)

    def remaining_ms(self) -> int:
        return max(0, int((self.end_perf_counter - time.perf_counter()) * 1000))

    def expired(self) -> bool:
        return self.remaining_ms() <= 0

    def child_budget(self, max_ms: int) -> "Deadline":
        return Deadline.from_time_limit_ms(min(max(0, int(max_ms)), self.remaining_ms()))

    def should_stop(self, reserve_ms: int = 0) -> bool:
        return self.remaining_ms() <= max(0, int(reserve_ms))

    def raise_if_expired(self) -> None:
        if self.expired():
            raise TimeoutError("phase90 deadline expired")
