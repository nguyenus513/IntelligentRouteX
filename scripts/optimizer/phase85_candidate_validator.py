from __future__ import annotations

from typing import Any, Dict

from external_benchmark_support import check_solution
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from run_phase79_end_to_end_production_benchmark import validate_locked_prefix


class CandidateValidator:
    def __init__(self) -> None:
        self.objective = UnifiedNaturalObjective()

    def validate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], candidate: Dict[str, Any], require_improvement: bool = True) -> Dict[str, Any]:
        checked = check_solution(instance, candidate)
        if not checked.get("feasible"):
            return {"valid": False, "reason": "hard-violation", "details": checked.get("violations", [])}
        lock = validate_locked_prefix(candidate, instance.get("activeRoutes", []), instance.get("drivers", []))
        if not lock.get("valid"):
            return {"valid": False, "reason": "lock-violation", "details": lock.get("errors", [])}
        if require_improvement and not self.objective.improves(instance, incumbent, candidate):
            return {"valid": False, "reason": "objective-not-improved", "details": []}
        return {"valid": True, "reason": "accepted", "details": [], "check": checked, "lock": lock}
