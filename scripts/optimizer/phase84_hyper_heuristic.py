from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class OperatorStats:
    attempts: int = 0
    feasibleCandidates: int = 0
    checkerFeasibleCandidates: int = 0
    objectiveImprovingCandidates: int = 0
    acceptedCandidates: int = 0
    totalReward: float = 0.0
    totalRuntimeMs: int = 0
    bestDistanceDelta: float = 0.0
    bestVehicleDelta: float = 0.0

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
                runtime = max(1.0, stats.totalRuntimeMs / max(1, stats.attempts))
                checker_rate = stats.checkerFeasibleCandidates / max(1, stats.attempts)
                improving_rate = stats.objectiveImprovingCandidates / max(1, stats.attempts)
                accepted_rate = stats.acceptedCandidates / max(1, stats.attempts)
                delta_bonus = max(0.0, -stats.bestDistanceDelta) + 1000.0 * max(0.0, -stats.bestVehicleDelta)
                compatibility = self._feature_compatibility(name, features)
                exploitation = (accepted_rate * 10.0 + improving_rate * 5.0 + checker_rate + delta_bonus / 1000.0) / runtime
                score = exploitation * compatibility + self.exploration * math.sqrt(math.log(total_attempts) / stats.attempts)
            scored.append((score, name))
        return sorted(scored, key=lambda item: (-item[0], item[1]))[0][1]

    def record(self, operator: str, reward: float, runtime_ms: int, feasible: bool, accepted: bool, telemetry: Dict[str, Any] | None = None) -> None:
        stats = self.stats.setdefault(operator, OperatorStats())
        telemetry = telemetry or {}
        stats.attempts += 1
        stats.totalReward += float(reward)
        stats.totalRuntimeMs += max(0, int(runtime_ms))
        checker = int(telemetry.get("checkerFeasibleCandidates", telemetry.get("feasibleCandidates", 1 if feasible else 0)) or 0)
        improving = int(telemetry.get("objectiveImprovingCandidates", 1 if accepted else 0) or 0)
        accepted_count = int(telemetry.get("acceptedCandidates", 1 if accepted else 0) or 0)
        stats.feasibleCandidates += checker
        stats.checkerFeasibleCandidates += checker
        stats.objectiveImprovingCandidates += improving
        stats.acceptedCandidates += accepted_count
        if telemetry.get("bestDistanceDelta") is not None:
            stats.bestDistanceDelta = min(stats.bestDistanceDelta, float(telemetry.get("bestDistanceDelta") or 0.0))
        if telemetry.get("bestVehicleDelta") is not None:
            stats.bestVehicleDelta = min(stats.bestVehicleDelta, float(telemetry.get("bestVehicleDelta") or 0.0))

    def _feature_compatibility(self, operator: str, features: Dict[str, Any]) -> float:
        lowered = operator.lower()
        score = 1.0
        if "traffic" in lowered:
            score += max(0.0, float(features.get("trafficMultiplier", 1.0) or 1.0) - 1.0)
        if "slack" in lowered:
            score += float(features.get("timeWindowTightness", 0.0) or 0.0)
        if "lock" in lowered:
            score += float(features.get("lockedPrefixPressure", 0.0) or 0.0)
        if "cluster" in lowered or "pool" in lowered:
            score += float(features.get("clusterScore", 0.0) or 0.0)
        if "compression" in lowered:
            score += float(features.get("capacityPressure", 0.0) or 0.0)
        if "polish" in lowered or "chain" in lowered:
            score += 0.25 + float(features.get("timeWindowTightness", 0.0) or 0.0) * 0.25
        return score

    def telemetry(self) -> Dict[str, Any]:
        return {name: self.stats[name].to_dict() for name in sorted(self.stats)}
