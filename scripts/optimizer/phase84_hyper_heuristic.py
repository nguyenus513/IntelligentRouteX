from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class OperatorStats:
    attempts: int = 0
    feasibleCandidates: int = 0
    acceptedCandidates: int = 0
    totalReward: float = 0.0
    totalRuntimeMs: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdaptiveHyperHeuristic:
    def __init__(self, exploration: float = 0.25) -> None:
        self.exploration = exploration
        self.stats: Dict[str, OperatorStats] = {}

    def select(self, operators: List[str], features: Dict[str, Any]) -> str | None:
        if not operators:
            return None
        total_attempts = sum(self.stats.get(name, OperatorStats()).attempts for name in operators) + 1
        scored = []
        for name in operators:
            stats = self.stats.get(name, OperatorStats())
            if stats.attempts == 0:
                score = float("inf")
            else:
                mean_reward = stats.totalReward / max(1, stats.attempts)
                runtime = max(1.0, stats.totalRuntimeMs / max(1, stats.attempts))
                compatibility = self._feature_compatibility(name, features)
                score = (mean_reward / runtime) * compatibility + self.exploration * math.sqrt(math.log(total_attempts) / stats.attempts)
            scored.append((score, name))
        return sorted(scored, key=lambda item: (-item[0], item[1]))[0][1]

    def record(self, operator: str, reward: float, runtime_ms: int, feasible: bool, accepted: bool) -> None:
        stats = self.stats.setdefault(operator, OperatorStats())
        stats.attempts += 1
        stats.totalReward += float(reward)
        stats.totalRuntimeMs += max(0, int(runtime_ms))
        stats.feasibleCandidates += 1 if feasible else 0
        stats.acceptedCandidates += 1 if accepted else 0

    def _feature_compatibility(self, operator: str, features: Dict[str, Any]) -> float:
        lowered = operator.lower()
        score = 1.0
        if "traffic" in lowered:
            score += max(0.0, float(features.get("trafficMultiplier", 1.0) or 1.0) - 1.0)
        if "slack" in lowered:
            score += float(features.get("timeWindowTightness", 0.0) or 0.0)
        if "lock" in lowered:
            score += float(features.get("lockedPrefixPressure", 0.0) or 0.0)
        if "cluster" in lowered:
            score += float(features.get("clusterScore", 0.0) or 0.0)
        return score

    def telemetry(self) -> Dict[str, Any]:
        return {name: self.stats[name].to_dict() for name in sorted(self.stats)}
