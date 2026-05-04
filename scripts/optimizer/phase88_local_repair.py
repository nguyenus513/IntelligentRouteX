from __future__ import annotations

from typing import Any, Dict

from external_benchmark_support import check_solution
from run_phase56b_stable_promoted_runner import canonicalize_solution


class BoundedLocalRepair:
    def repair(self, instance: Dict[str, Any], candidate: Dict[str, Any], maxRepairChecks: int = 4) -> Dict[str, Any]:
        normalized = canonicalize_solution(instance, candidate)
        if check_solution(instance, normalized).get("feasible"):
            return {"solution": normalized, "attempts": 0, "success": True}
        # Waiting is implicit in the checker, so the only safe generic repair here
        # is canonical normalization. Stronger repairs remain bounded future work.
        return {"solution": normalized, "attempts": min(1, maxRepairChecks), "success": False}
