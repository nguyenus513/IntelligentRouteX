from __future__ import annotations

from typing import Any, Dict

from run_phase79_end_to_end_production_benchmark import validate_locked_prefix


class LockAwareOptimizer:
    def validate(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
        return validate_locked_prefix(solution, instance.get("activeRoutes", []), instance.get("drivers", []))

    def accepts(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> bool:
        return bool(self.validate(instance, solution).get("valid"))
