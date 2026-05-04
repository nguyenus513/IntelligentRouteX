from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any


@dataclass
class DeterministicRandom:
    seed: int

    @classmethod
    def from_signature(cls, signature: str) -> "DeterministicRandom":
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
        return cls(int(digest, 16))

    def value(self, salt: Any = "") -> float:
        rng = random.Random(self.seed ^ int(hashlib.sha256(str(salt).encode("utf-8")).hexdigest()[:16], 16))
        return rng.random()


def accepts(currentObjective: float, candidateObjective: float, bestObjective: float, temperature: float, deterministicRandom: DeterministicRandom, iteration: int = 0) -> bool:
    if candidateObjective < currentObjective:
        return True
    if candidateObjective <= bestObjective:
        return True
    if temperature <= 0:
        return False
    delta = max(0.0, candidateObjective - currentObjective)
    probability = math.exp(-delta / max(1e-9, temperature))
    return deterministicRandom.value(iteration) < probability


def decayed_temperature(initial: float, iteration: int, decay: float = 0.92) -> float:
    return max(1e-9, float(initial) * (float(decay) ** max(0, int(iteration))))
