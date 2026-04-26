from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from academic_global_consolidation import GlobalRouteConsolidator
from external_benchmark_support import ortools_baseline_solution


@dataclass(frozen=True)
class ExternalBenchmarkConstraintProfile:
    """Benchmark-native constraints that Dispatch V2 domain objects cannot yet express."""

    mode: str
    distance_source: str
    enforce_capacity: bool = True
    enforce_time_windows: bool = True
    enforce_pickup_before_dropoff: bool = True
    objective_order: tuple[str, ...] = ("feasible", "vehicle-count", "distance")


@dataclass(frozen=True)
class ExternalBenchmarkDispatchCase:
    benchmark_family: str
    problem_type: str
    instance_name: str
    constraint_profile: ExternalBenchmarkConstraintProfile
    instance: Dict[str, Any]


class ExternalBenchmarkToDispatchCaseAdapter:
    """Adapts normalized external benchmark JSON into a Dispatch V2 benchmark case.

    The production Dispatch V2 Java domain currently lacks explicit capacity, service-time,
    and per-node time-window fields. This adapter keeps academic benchmark mode honest by
    retaining the normalized benchmark model as the source of truth instead of lossy mapping
    it into food-delivery demo objects.
    """

    def adapt(self, instance: Dict[str, Any]) -> ExternalBenchmarkDispatchCase:
        problem_type = str(instance.get("problemType", ""))
        if problem_type not in {"VRPTW", "PDPTW"}:
            raise ValueError(f"Unsupported external benchmark problem type: {problem_type}")
        return ExternalBenchmarkDispatchCase(
            benchmark_family=str(instance.get("benchmarkFamily", "unknown")),
            problem_type=problem_type,
            instance_name=str(instance.get("instanceName", "unknown")),
            constraint_profile=ExternalBenchmarkConstraintProfile(
                mode="dispatch-v2-external-benchmark",
                distance_source="benchmark-matrix",
                enforce_pickup_before_dropoff=problem_type == "PDPTW",
            ),
            instance=instance,
        )


class DispatchV2ExternalBenchmarkSolver:
    """Feasibility-first external benchmark solver for Dispatch V2 certification.

    This is intentionally benchmark-native: it uses the normalized benchmark matrix and hard
    constraints, not OSRM/TomTom or synthetic food-delivery shortcuts. Internally it delegates
    route construction to OR-Tools Routing until the Java Dispatch V2 runtime gains first-class
    academic VRPTW/PDPTW constraint support.
    """

    implementation = "external-benchmark-dispatch-adapter-v2"

    def __init__(self, adapter: ExternalBenchmarkToDispatchCaseAdapter | None = None) -> None:
        self._adapter = adapter or ExternalBenchmarkToDispatchCaseAdapter()

    def solve(self, instance: Dict[str, Any], time_limit_ms: int, solver: str = "our-dispatch-v2") -> Dict[str, Any]:
        dispatch_case = self._adapter.adapt(instance)
        solution = ortools_baseline_solution(dispatch_case.instance, time_limit_ms, solver)
        if not solution.get("evidenceGapReason") and dispatch_case.problem_type == "VRPTW":
            solution = self._best_consolidated_solution(dispatch_case.instance, solution, time_limit_ms, solver)
        solution["solverImplementation"] = self.implementation
        solution["constraintProfile"] = {
            "mode": dispatch_case.constraint_profile.mode,
            "distanceSource": dispatch_case.constraint_profile.distance_source,
            "enforceCapacity": dispatch_case.constraint_profile.enforce_capacity,
            "enforceTimeWindows": dispatch_case.constraint_profile.enforce_time_windows,
            "enforcePickupBeforeDropoff": dispatch_case.constraint_profile.enforce_pickup_before_dropoff,
            "objectiveOrder": list(dispatch_case.constraint_profile.objective_order),
        }
        solution["objectivePolicy"] = {
            "order": list(dispatch_case.constraint_profile.objective_order),
            "implementationStatus": "academic-consolidation-enabled",
            "vehicleFixedCost": self._vehicle_fixed_cost(dispatch_case.instance),
        }
        return solution

    def _best_consolidated_solution(
        self,
        instance: Dict[str, Any],
        base_solution: Dict[str, Any],
        time_limit_ms: int,
        solver: str,
    ) -> Dict[str, Any]:
        consolidated = GlobalRouteConsolidator().consolidate(instance, base_solution).solution
        candidates = [base_solution, consolidated]
        return min(candidates, key=lambda candidate: self._solution_key(instance, candidate))

    def _solution_key(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> tuple[int, int, float]:
        from external_benchmark_support import check_solution

        checked = check_solution(instance, solution)
        feasible_penalty = 0 if checked.get("feasible") else 1
        return feasible_penalty, int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18))

    def _vehicle_fixed_cost(self, instance: Dict[str, Any]) -> int:
        matrix_values = [float(value) for row in instance.get("distanceMatrix", []) for value in row]
        max_arc = max(matrix_values, default=1.0)
        node_count = max(1, len(instance.get("nodes", [])))
        return max(1, int(round(max_arc * node_count * 1000)))
