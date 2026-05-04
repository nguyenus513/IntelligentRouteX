from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from external_benchmark_support import check_solution
from run_phase71_food_dispatch_metrics import compute_instance_metrics
from run_phase79_end_to_end_production_benchmark import validate_locked_prefix


@dataclass(frozen=True)
class UnifiedObjectiveWeights:
    vehicleCountWeight: float = 1_000_000.0
    distanceWeight: float = 1.0
    latenessWeight: float = 100_000.0
    tailWeight: float = 10.0
    churnWeight: float = 1_000.0
    balanceWeight: float = 100.0
    riskWeight: float = 10_000.0
    slackWeight: float = 10.0


class UnifiedNaturalObjective:
    def __init__(self, weights: UnifiedObjectiveWeights | None = None) -> None:
        self.weights = weights or UnifiedObjectiveWeights()

    def evaluate(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
        checked = check_solution(instance, solution)
        lock = validate_locked_prefix(solution, instance.get("activeRoutes", []), instance.get("drivers", []))
        hard_violations: List[str] = list(checked.get("violations", []))
        if not lock.get("valid", True):
            hard_violations.append("active-route-lock-violation")
        if hard_violations:
            return {"feasible": False, "hardViolations": hard_violations, "objective": float("inf"), "components": checked, "lockMetrics": lock}
        food = compute_instance_metrics(instance, solution)
        low_slack_penalty = max(0.0, 10.0 - float(food.get("orderToDeliveryP95", 0.0) or 0.0))
        objective = (
            self.weights.vehicleCountWeight * float(checked.get("vehicleCount", 0) or 0)
            + self.weights.distanceWeight * float(checked.get("totalDistance", 0.0) or 0.0)
            + self.weights.latenessWeight * float(food.get("lateOrderRate", 0.0) or 0.0)
            + self.weights.tailWeight * float(food.get("orderToDeliveryP95", 0.0) or 0.0)
            + self.weights.churnWeight * float(lock.get("routeChurnScore", 0.0) or 0.0)
            + self.weights.balanceWeight * float(food.get("driverLoadBalance", 0.0) or 0.0)
            + self.weights.riskWeight * float(food.get("riskWeightedLateRate", 0.0) or 0.0)
            + self.weights.slackWeight * low_slack_penalty
        )
        return {"feasible": True, "hardViolations": [], "objective": objective, "components": checked, "foodMetrics": food, "lockMetrics": lock}

    def improves(self, instance: Dict[str, Any], current: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        candidate_eval = self.evaluate(instance, candidate)
        if not candidate_eval.get("feasible"):
            return False
        current_eval = self.evaluate(instance, current)
        return float(candidate_eval["objective"]) < float(current_eval["objective"])
