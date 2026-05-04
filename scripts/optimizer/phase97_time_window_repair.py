from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Set, Tuple

from external_benchmark_support import check_solution, route_distance
from optimizer.phase85_pair_utils import extract_request_pairs, insert_pair_positions, remove_pair_from_route, request_id, solution_signature
from optimizer.phase96_coverage_repair import coverage_diff


@dataclass(frozen=True)
class RouteSchedule:
    arrivalTimes: List[float]
    waitingTime: float
    dueTimeLateness: List[float]
    firstViolationNode: str | None
    totalLateness: float
    maxLateness: float
    slackProxy: float
    timeWindowViolationCount: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_route_schedule(instance: Dict[str, Any], route: List[str]) -> RouteSchedule:
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    stops = [str(stop) for stop in route]
    elapsed = 0.0
    waiting = 0.0
    arrivals: List[float] = [0.0] if stops else []
    lateness_values: List[float] = [0.0] if stops else []
    first_violation = None
    total_lateness = 0.0
    max_lateness = 0.0
    min_slack = float("inf")
    violations = 0
    for previous, current in zip(stops, stops[1:]):
        elapsed += route_distance(instance, [previous, current])
        node = nodes.get(current, {})
        ready = float(node.get("readyTime", 0.0) or 0.0)
        due = float(node.get("dueTime", 1e18) or 1e18)
        if elapsed < ready:
            waiting += ready - elapsed
            elapsed = ready
        lateness = max(0.0, elapsed - due)
        slack = due - elapsed
        arrivals.append(elapsed)
        lateness_values.append(lateness)
        if lateness > 1e-9:
            violations += 1
            total_lateness += lateness
            max_lateness = max(max_lateness, lateness)
            if first_violation is None:
                first_violation = current
        min_slack = min(min_slack, slack)
        elapsed += float(node.get("serviceTime", 0.0) or 0.0)
    if min_slack == float("inf"):
        min_slack = 0.0
    return RouteSchedule(arrivals, waiting, lateness_values, first_violation, total_lateness, max_lateness, min_slack, violations)


def solution_time_window_stats(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    schedules = [evaluate_route_schedule(instance, [str(stop) for stop in route]) for route in solution.get("routes", [])]
    first = next((schedule.firstViolationNode for schedule in schedules if schedule.firstViolationNode is not None), None)
    return {
        "timeWindowViolationCount": sum(schedule.timeWindowViolationCount for schedule in schedules),
        "totalLateness": sum(schedule.totalLateness for schedule in schedules),
        "maxLateness": max([schedule.maxLateness for schedule in schedules] or [0.0]),
        "firstViolationNode": first,
    }


class TimeWindowRepair:
    def __init__(self) -> None:
        self.lastTelemetry: Dict[str, Any] = self._empty_telemetry()

    def _empty_telemetry(self) -> Dict[str, Any]:
        return {
            "timeWindowRepairAttempts": 0,
            "timeWindowRepairSuccess": False,
            "timeWindowViolationCountBefore": 0,
            "timeWindowViolationCountAfter": 0,
            "totalLatenessBefore": 0.0,
            "totalLatenessAfter": 0.0,
            "firstViolationNode": None,
            "repairStrategyUsed": None,
            "candidateChecksUsed": 0,
        }

    def repair(
        self,
        instance: Dict[str, Any],
        solution: Dict[str, Any],
        affected_request_ids: Set[str],
        max_routes: int,
        max_candidate_checks: int = 96,
        max_runtime_ms: int = 750,
        max_moved_pairs: int = 3,
    ) -> Dict[str, Any] | None:
        started = time.perf_counter()
        before = solution_time_window_stats(instance, solution)
        self.lastTelemetry = self._empty_telemetry()
        self.lastTelemetry.update({
            "timeWindowRepairAttempts": 1,
            "timeWindowViolationCountBefore": int(before["timeWindowViolationCount"]),
            "timeWindowViolationCountAfter": int(before["timeWindowViolationCount"]),
            "totalLatenessBefore": float(before["totalLateness"]),
            "totalLatenessAfter": float(before["totalLateness"]),
            "firstViolationNode": before.get("firstViolationNode"),
        })
        if int(before["timeWindowViolationCount"]) == 0:
            self.lastTelemetry["timeWindowRepairSuccess"] = True
            return solution
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        affected_indices = self._affected_route_indices(instance, routes, affected_request_ids)
        best = {"routes": [list(route) for route in routes]}
        best_key = self._score(instance, best)
        strategies = [
            ("precedence-preserving-reorder", self._precedence_reorder_candidates),
            ("pair-relocate-within-route", self._within_route_relocate_candidates),
            ("cross-affected-route-pair-relocate", self._cross_route_relocate_candidates),
            ("schedule-regret-rebuild", self._schedule_regret_rebuild_candidates),
            ("exact-tw-route-finalizer", self._exact_tw_finalizer_candidates),
            ("mini-destroy-regret-repair", self._mini_destroy_regret_candidates),
        ]
        checks = 0
        for strategy_name, generator in strategies:
            for candidate in generator(instance, routes, affected_indices, affected_request_ids, max_moved_pairs):
                if (time.perf_counter() - started) * 1000.0 > max_runtime_ms or checks >= max_candidate_checks:
                    self.lastTelemetry["candidateChecksUsed"] = checks
                    return self._finish(instance, solution, best, best_key, strategy_name)
                checks += 1
                if not self._shape_ok(instance, candidate, affected_request_ids, max_routes):
                    continue
                key = self._score(instance, candidate)
                if key < best_key:
                    best_key = key
                    best = candidate
                    self.lastTelemetry["repairStrategyUsed"] = strategy_name
                    if check_solution(instance, best).get("feasible"):
                        self.lastTelemetry["candidateChecksUsed"] = checks
                        return self._finish(instance, solution, best, best_key, strategy_name)
        self.lastTelemetry["candidateChecksUsed"] = checks
        return self._finish(instance, solution, best, best_key, self.lastTelemetry.get("repairStrategyUsed"))

    def _finish(self, instance: Dict[str, Any], original: Dict[str, Any], best: Dict[str, Any], best_key: Tuple[float, int, str], strategy: str | None) -> Dict[str, Any] | None:
        after = solution_time_window_stats(instance, best)
        original_stats = solution_time_window_stats(instance, original)
        improved = (
            int(after["timeWindowViolationCount"]) < int(original_stats["timeWindowViolationCount"])
            or float(after["totalLateness"]) < float(original_stats["totalLateness"]) - 1e-9
        )
        self.lastTelemetry.update({
            "timeWindowViolationCountAfter": int(after["timeWindowViolationCount"]),
            "totalLatenessAfter": float(after["totalLateness"]),
            "timeWindowRepairSuccess": improved,
            "repairStrategyUsed": strategy if improved else None,
        })
        return best if improved else None

    def _score(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Tuple[float, int, str]:
        checked = check_solution(instance, solution)
        stats = solution_time_window_stats(instance, solution)
        route_count = len([route for route in solution.get("routes", []) if len(route) > 2])
        return (
            float(stats["totalLateness"]),
            int(stats["timeWindowViolationCount"]) + int(checked.get("capacityViolationCount", 0) or 0) * 1000 + int(checked.get("pickupBeforeDropoffViolationCount", 0) or 0) * 1000,
            f"{route_count}:{solution_signature(solution)}",
        )

    def _shape_ok(self, instance: Dict[str, Any], solution: Dict[str, Any], affected_request_ids: Set[str], max_routes: int) -> bool:
        active = len([route for route in solution.get("routes", []) if len(route) > 2])
        diff = coverage_diff(instance, solution, affected_request_ids)
        return active <= max_routes and not diff.missingRequestIds and not diff.duplicateRequestIds and not diff.partialPickupDropoffIds

    def _affected_route_indices(self, instance: Dict[str, Any], routes: List[List[str]], affected_request_ids: Set[str]) -> List[int]:
        requests = {request_id(request): request for request in instance.get("requests", [])}
        indices: Set[int] = set()
        for rid in affected_request_ids:
            request = requests.get(str(rid))
            if request is None:
                continue
            pickup = str(request.get("pickupNodeId"))
            dropoff = str(request.get("dropoffNodeId"))
            for index, route in enumerate(routes):
                if pickup in route or dropoff in route:
                    indices.add(index)
        return sorted(indices)

    def _route_pairs(self, instance: Dict[str, Any], route: List[str], affected_request_ids: Set[str] | None = None) -> List[Dict[str, Any]]:
        pair_rows = []
        allowed = affected_request_ids or {request_id(request) for request in instance.get("requests", [])}
        for pair in extract_request_pairs(instance, {"routes": [route]}):
            rid = str(pair["requestId"])
            if rid in allowed:
                pair_rows.append(pair)
        return pair_rows

    def _precedence_reorder_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        depot = str(instance.get("depotNodeId", "0"))
        candidates = []
        for route_index in affected_indices:
            pairs = self._route_pairs(instance, routes[route_index])
            if len(pairs) < 2:
                continue
            ordered = sorted(pairs, key=lambda pair: (min(float(nodes[str(pair["pickup"])].get("dueTime", 1e18)), float(nodes[str(pair["dropoff"])].get("dueTime", 1e18))), float(nodes[str(pair["pickup"])].get("readyTime", 0.0)), str(pair["requestId"])))
            new_route = [depot]
            for pair in ordered:
                new_route.extend([str(pair["pickup"]), str(pair["dropoff"])])
            new_route.append(depot)
            attempt = [list(route) for route in routes]
            attempt[route_index] = new_route
            candidates.append({"routes": [route for route in attempt if len(route) > 2]})
        return candidates

    def _within_route_relocate_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        candidates = []
        for route_index in affected_indices:
            route = routes[route_index]
            pairs = self._lateness_pairs(instance, route, affected_request_ids)[:max_moved_pairs]
            for pair in pairs:
                base = remove_pair_from_route(route, pair["request"])
                for _, _, candidate_route in insert_pair_positions(base, pair["request"]):
                    attempt = [list(item) for item in routes]
                    attempt[route_index] = candidate_route
                    candidates.append({"routes": [item for item in attempt if len(item) > 2]})
                    if len(candidates) >= 48:
                        return candidates
        return candidates

    def _cross_route_relocate_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        candidates = []
        for source_index in affected_indices:
            pairs = self._lateness_pairs(instance, routes[source_index], affected_request_ids)[:max_moved_pairs]
            for pair in pairs:
                source_base = remove_pair_from_route(routes[source_index], pair["request"])
                for target_index in affected_indices:
                    if target_index == source_index:
                        continue
                    for _, _, target_route in insert_pair_positions(routes[target_index], pair["request"]):
                        attempt = [list(item) for item in routes]
                        attempt[source_index] = source_base
                        attempt[target_index] = target_route
                        candidates.append({"routes": [item for item in attempt if len(item) > 2]})
                        if len(candidates) >= 48:
                            return candidates
        return candidates


    def _schedule_regret_rebuild_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        if not affected_indices:
            return []
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        requests = [request for request in instance.get("requests", []) if request_id(request) in affected_request_ids]
        if not requests:
            return []
        ordered = sorted(
            requests,
            key=lambda request: (
                min(float(nodes[str(request.get("pickupNodeId"))].get("dueTime", 1e18)), float(nodes[str(request.get("dropoffNodeId"))].get("dueTime", 1e18))),
                float(nodes[str(request.get("pickupNodeId"))].get("readyTime", 0.0)),
                request_id(request),
            ),
        )
        depot = str(instance.get("depotNodeId", "0"))
        rebuilt = [[depot, depot] for _ in affected_indices]
        unaffected = [list(route) for index, route in enumerate(routes) if index not in set(affected_indices)]
        for request in ordered:
            best_routes = None
            best_key = None
            for route_index, route in enumerate(rebuilt):
                for _, _, candidate_route in insert_pair_positions(route, request):
                    attempt_rebuilt = [list(item) for item in rebuilt]
                    attempt_rebuilt[route_index] = candidate_route
                    attempt_solution = {"routes": [route for route in unaffected + attempt_rebuilt if len(route) > 2]}
                    if coverage_diff(instance, attempt_solution, affected_request_ids).partialPickupDropoffIds:
                        continue
                    checked = check_solution(instance, attempt_solution)
                    stats = solution_time_window_stats(instance, attempt_solution)
                    key = (
                        int(checked.get("capacityViolationCount", 0) or 0) + int(checked.get("pickupBeforeDropoffViolationCount", 0) or 0) * 1000,
                        int(stats["timeWindowViolationCount"]),
                        float(stats["totalLateness"]),
                        route_distance(instance, candidate_route),
                        solution_signature(attempt_solution),
                    )
                    if best_key is None or key < best_key:
                        best_key = key
                        best_routes = attempt_rebuilt
            if best_routes is None:
                return []
            rebuilt = best_routes
        return [{"routes": [route for route in unaffected + rebuilt if len(route) > 2]}]


    def _exact_tw_finalizer_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        from optimizer.phase99_exact_tw_route_finalizer import ExactTWRouteFinalizer
        finalizer = ExactTWRouteFinalizer()
        candidate = finalizer.finalize_solution_routes(instance, {"routes": routes}, affected_indices, max_states=512, beam_width=32, max_runtime_ms=500)
        return [candidate] if candidate is not None else []

    def _mini_destroy_regret_candidates(self, instance: Dict[str, Any], routes: List[List[str]], affected_indices: List[int], affected_request_ids: Set[str], max_moved_pairs: int) -> List[Dict[str, Any]]:
        pairs = []
        for route_index in affected_indices:
            for pair in self._lateness_pairs(instance, routes[route_index], affected_request_ids):
                pairs.append((route_index, pair))
        pairs = pairs[:max_moved_pairs]
        if not pairs:
            return []
        base_routes = [list(route) for route in routes]
        removed = []
        for route_index, pair in pairs:
            base_routes[route_index] = remove_pair_from_route(base_routes[route_index], pair["request"])
            removed.append(pair["request"])
        for request in removed:
            best = None
            best_key = None
            for route_index in affected_indices:
                for _, _, candidate_route in insert_pair_positions(base_routes[route_index], request):
                    attempt = [list(route) for route in base_routes]
                    attempt[route_index] = candidate_route
                    key = self._score(instance, {"routes": [route for route in attempt if len(route) > 2]})
                    if best_key is None or key < best_key:
                        best_key = key
                        best = attempt
            if best is None:
                return []
            base_routes = best
        return [{"routes": [route for route in base_routes if len(route) > 2]}]

    def _lateness_pairs(self, instance: Dict[str, Any], route: List[str], affected_request_ids: Set[str]) -> List[Dict[str, Any]]:
        schedule = evaluate_route_schedule(instance, route)
        node_lateness = {str(stop): schedule.dueTimeLateness[index] for index, stop in enumerate(route) if index < len(schedule.dueTimeLateness)}
        pairs = self._route_pairs(instance, route, affected_request_ids)
        return sorted(pairs, key=lambda pair: (-(node_lateness.get(str(pair["pickup"]), 0.0) + node_lateness.get(str(pair["dropoff"]), 0.0)), str(pair["requestId"])))

