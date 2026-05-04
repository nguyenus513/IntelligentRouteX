from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

from external_benchmark_support import check_solution
from optimizer.phase84_unified_objective import UnifiedNaturalObjective


@dataclass(frozen=True)
class ExactDelta:
    vehicleDelta: float
    distanceDelta: float
    objectiveDeltaEstimate: float
    routeCountDelta: float
    tailMetricDelta: float = 0.0
    churnDelta: float = 0.0
    loadBalanceDelta: float = 0.0
    riskDelta: float = 0.0

    def has_quality_potential(self) -> bool:
        return self.vehicleDelta < 0 or self.distanceDelta < 0 or self.objectiveDeltaEstimate < 0 or (self.churnDelta < 0 and self.distanceDelta <= 0)

    def stable_key(self) -> tuple[float, float, float, float]:
        return (self.vehicleDelta, self.objectiveDeltaEstimate, self.distanceDelta, self.churnDelta)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExactDeltaScorer:
    def __init__(self) -> None:
        self.objective = UnifiedNaturalObjective()

    def score(self, instance: Dict[str, Any], incumbent: Dict[str, Any], candidate: Dict[str, Any]) -> ExactDelta:
        before = check_solution(instance, incumbent)
        after = check_solution(instance, candidate)
        before_objective = self.objective.evaluate(instance, incumbent).get("objective", float("inf"))
        after_objective = self.objective.evaluate(instance, candidate).get("objective", float("inf"))
        return ExactDelta(
            vehicleDelta=float(after.get("vehicleCount", 0) or 0) - float(before.get("vehicleCount", 0) or 0),
            distanceDelta=float(after.get("totalDistance", 0.0) or 0.0) - float(before.get("totalDistance", 0.0) or 0.0),
            objectiveDeltaEstimate=float(after_objective) - float(before_objective),
            routeCountDelta=float(len([route for route in candidate.get("routes", []) if len(route) > 2]) - len([route for route in incumbent.get("routes", []) if len(route) > 2])),
        )
