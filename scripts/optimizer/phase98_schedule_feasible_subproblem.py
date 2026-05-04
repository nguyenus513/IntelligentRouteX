from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from external_benchmark_support import check_solution, route_distance
from optimizer.phase85_pair_utils import insert_pair_positions, request_id, solution_signature
from optimizer.phase95_slot_aware_subproblem import SlotAwareSubproblemConfig, SlotAwareSubproblemBuilder
from optimizer.phase96_coverage_repair import coverage_diff
from optimizer.phase97_time_window_repair import evaluate_route_schedule, solution_time_window_stats
from optimizer.phase99_exact_tw_route_finalizer import ExactTWRouteFinalizer


@dataclass(frozen=True)
class RouteScheduleScore:
    hardViolationCount: int
    timeWindowViolationCount: int
    totalLateness: float
    maxLateness: float
    distance: float
    capacityViolationCount: int
    pickupBeforeDropoffViolationCount: int

    def to_tuple(self) -> Tuple[int, int, float, float, float]:
        return (
            self.hardViolationCount,
            self.timeWindowViolationCount,
            self.totalLateness,
            self.maxLateness,
            self.distance,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_solution(instance: Dict[str, Any], solution: Dict[str, Any]) -> RouteScheduleScore:
    checked = check_solution(instance, solution)
    stats = solution_time_window_stats(instance, solution)
    capacity = int(checked.get("capacityViolationCount", 0) or 0)
    precedence = int(checked.get("pickupBeforeDropoffViolationCount", 0) or 0)
    vehicle = int(checked.get("vehicleLimitViolationCount", 0) or 0)
    coverage = coverage_diff(instance, solution)
    coverage_hard = len(coverage.missingRequestIds) + len(coverage.duplicateRequestIds) + len(coverage.partialPickupDropoffIds)
    return RouteScheduleScore(
        capacity + precedence + vehicle + coverage_hard,
        int(stats.get("timeWindowViolationCount", 0) or 0),
        float(stats.get("totalLateness", 0.0) or 0.0),
        float(stats.get("maxLateness", 0.0) or 0.0),
        sum(route_distance(instance, [str(stop) for stop in route]) for route in solution.get("routes", [])),
        capacity,
        precedence,
    )


class ScheduleFeasibleSubproblemBuilder:
    def __init__(self) -> None:
        self.fallback = SlotAwareSubproblemBuilder()
        self.lastTelemetry: Dict[str, Any] = self._empty_telemetry()

    def _empty_telemetry(self) -> Dict[str, Any]:
        return {
            "scheduleBuilderAttempts": 0,
            "scheduleBuilderSuccess": False,
            "scheduleBuilderStrategy": None,
            "subproblemTWBefore": 0,
            "subproblemTWAfter": 0,
            "subproblemLatenessBefore": 0.0,
            "subproblemLatenessAfter": 0.0,
            "scheduleBuiltCandidateUsed": False,
        }

    def build_incumbent(self, subproblem: Dict[str, Any], config: SlotAwareSubproblemConfig, fallback_incumbent: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        self.lastTelemetry = self._empty_telemetry()
        fallback = fallback_incumbent or self.fallback.build_incumbent(subproblem, config)
        if fallback is None:
            return None
        fallback_score = score_solution(subproblem, fallback)
        self.lastTelemetry.update({
            "scheduleBuilderAttempts": 1,
            "subproblemTWBefore": fallback_score.timeWindowViolationCount,
            "subproblemTWAfter": fallback_score.timeWindowViolationCount,
            "subproblemLatenessBefore": fallback_score.totalLateness,
            "subproblemLatenessAfter": fallback_score.totalLateness,
        })
        best = fallback
        best_key = (fallback_score.to_tuple(), solution_signature(fallback))
        for strategy, ordered in self._ordered_request_sets(subproblem):
            candidate = self._build_by_insertion(subproblem, config, ordered)
            if candidate is None:
                continue
            candidate = self._finalize_routes(subproblem, candidate) or candidate
            if not self._coverage_ok(subproblem, candidate) or self._active_route_count(candidate) > config.maxSubproblemRoutes:
                continue
            key = (score_solution(subproblem, candidate).to_tuple(), solution_signature(candidate))
            if key < best_key:
                best = candidate
                best_key = key
                self.lastTelemetry["scheduleBuilderStrategy"] = strategy
        best = self._finalize_routes(subproblem, best) or best
        best_score = score_solution(subproblem, best)
        improved = best_key < (fallback_score.to_tuple(), solution_signature(fallback))
        self.lastTelemetry.update({
            "scheduleBuilderSuccess": improved,
            "subproblemTWAfter": best_score.timeWindowViolationCount,
            "subproblemLatenessAfter": best_score.totalLateness,
            "scheduleBuiltCandidateUsed": improved,
        })
        return best

    def _finalize_routes(self, subproblem: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any] | None:
        finalizer = ExactTWRouteFinalizer()
        return finalizer.finalize_solution_routes(subproblem, solution, max_states=512, beam_width=32, max_runtime_ms=500)

    def choose_candidate(self, subproblem: Dict[str, Any], optimizer_solution: Dict[str, Any], schedule_incumbent: Dict[str, Any]) -> Dict[str, Any]:
        optimizer_key = (score_solution(subproblem, optimizer_solution).to_tuple(), solution_signature(optimizer_solution))
        schedule_key = (score_solution(subproblem, schedule_incumbent).to_tuple(), solution_signature(schedule_incumbent))
        if schedule_key < optimizer_key:
            self.lastTelemetry["scheduleBuiltCandidateUsed"] = True
            return schedule_incumbent
        return optimizer_solution

    def best_pair_insertion(self, subproblem: Dict[str, Any], route: List[str], request: Dict[str, Any]) -> List[str] | None:
        best_route = None
        best_key = None
        for _, _, candidate_route in insert_pair_positions([str(stop) for stop in route], request):
            candidate_solution = {"routes": [candidate_route]}
            score = score_solution(subproblem, candidate_solution)
            key = (score.to_tuple(), solution_signature(candidate_solution))
            if best_key is None or key < best_key:
                best_key = key
                best_route = candidate_route
        return best_route

    def _build_by_insertion(self, subproblem: Dict[str, Any], config: SlotAwareSubproblemConfig, ordered_requests: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        depot = str(subproblem.get("depotNodeId", "0"))
        routes = [[depot, depot] for _ in range(max(1, config.maxSubproblemRoutes))]
        for request in ordered_requests:
            best = None
            best_key = None
            for route_index, route in enumerate(routes):
                for _, _, candidate_route in insert_pair_positions(route, request):
                    attempt = [list(item) for item in routes]
                    attempt[route_index] = candidate_route
                    solution = {"routes": [item for item in attempt if len(item) > 2]}
                    score = score_solution(subproblem, solution)
                    key = (score.to_tuple(), solution_signature(solution))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = attempt
            if best is None:
                return None
            routes = best
        return {"routes": [route for route in routes if len(route) > 2]}

    def _ordered_request_sets(self, subproblem: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
        requests = list(subproblem.get("requests", []))
        nodes = {str(node.get("id")): node for node in subproblem.get("nodes", [])}

        def due_key(request: Dict[str, Any]) -> Tuple[float, float, str]:
            pickup = nodes[str(request.get("pickupNodeId"))]
            dropoff = nodes[str(request.get("dropoffNodeId"))]
            return (min(float(pickup.get("dueTime", 1e18)), float(dropoff.get("dueTime", 1e18))), float(pickup.get("readyTime", 0.0)), request_id(request))

        def slack_key(request: Dict[str, Any]) -> Tuple[float, float, str]:
            pickup = nodes[str(request.get("pickupNodeId"))]
            dropoff = nodes[str(request.get("dropoffNodeId"))]
            pickup_slack = float(pickup.get("dueTime", 1e18)) - float(pickup.get("readyTime", 0.0))
            dropoff_slack = float(dropoff.get("dueTime", 1e18)) - float(dropoff.get("readyTime", 0.0))
            return (min(pickup_slack, dropoff_slack), min(float(pickup.get("dueTime", 1e18)), float(dropoff.get("dueTime", 1e18))), request_id(request))

        def spatial_time_key(request: Dict[str, Any]) -> Tuple[float, float, str]:
            pickup = nodes[str(request.get("pickupNodeId"))]
            due = due_key(request)[0]
            cluster = float(pickup.get("x", 0.0) or 0.0) ** 2 + float(pickup.get("y", 0.0) or 0.0) ** 2
            return (due, cluster, request_id(request))

        return [
            ("earliest-due-first", sorted(requests, key=due_key)),
            ("min-slack-first", sorted(requests, key=slack_key)),
            ("spatial-time-clustered", sorted(requests, key=spatial_time_key)),
            ("reverse-earliest-due", sorted(requests, key=due_key, reverse=True)),
        ]

    def _coverage_ok(self, subproblem: Dict[str, Any], solution: Dict[str, Any]) -> bool:
        diff = coverage_diff(subproblem, solution)
        return not diff.missingRequestIds and not diff.duplicateRequestIds and not diff.partialPickupDropoffIds

    def _active_route_count(self, solution: Dict[str, Any]) -> int:
        return len([route for route in solution.get("routes", []) if len(route) > 2])
