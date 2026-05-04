from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class OperatorBudget:
    operator: str
    allocatedMs: int
    usedMs: int = 0
    candidateChecks: int = 0
    generatedCandidates: int = 0
    feasibleCandidateCount: int = 0
    acceptedCount: int = 0
    roi: float = 0.0
    earlyStopReason: str | None = None
    failReasons: Dict[str, int] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdaptiveBudgetController:
    def allocate(self, total_ms: int, features: Dict[str, Any], operators: List[str]) -> Dict[str, OperatorBudget]:
        if not operators:
            return {}
        weights: Dict[str, float] = {operator: 1.0 for operator in operators}
        tightness = float(features.get("timeWindowTightness", 0.0) or 0.0)
        capacity = float(features.get("capacityPressure", 0.0) or 0.0)
        cluster = float(features.get("clusterScore", 0.0) or 0.0)
        lock = float(features.get("lockedPrefixPressure", 0.0) or 0.0)
        traffic = float(features.get("trafficMultiplier", 1.0) or 1.0)
        confidence = float(features.get("trafficConfidence", 1.0) or 1.0)
        for name in operators:
            lowered = name.lower()
            if "slack" in lowered or "time" in lowered:
                weights[name] += tightness + max(0.0, traffic - 1.0)
            if "elimination" in lowered or "relocate" in lowered:
                weights[name] += capacity
            if "cluster" in lowered or "pool" in lowered:
                weights[name] += cluster
            if "lock" in lowered:
                weights[name] += lock * 2.0
            if "traffic" in lowered:
                weights[name] += max(0.0, traffic - 1.0) + max(0.0, 1.0 - confidence)
        total_weight = sum(weights.values()) or 1.0
        available = max(1, int(total_ms))
        return {name: OperatorBudget(name, max(1, int(available * weights[name] / total_weight))) for name in operators}

    def telemetry(self, budgets: Dict[str, OperatorBudget]) -> List[Dict[str, Any]]:
        return [budgets[name].to_dict() for name in sorted(budgets)]
