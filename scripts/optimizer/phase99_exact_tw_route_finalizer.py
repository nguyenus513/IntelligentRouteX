from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Set, Tuple

from external_benchmark_support import check_solution, route_distance
from optimizer.phase85_pair_utils import extract_request_pairs, request_id, solution_signature
from optimizer.phase97_time_window_repair import evaluate_route_schedule


@dataclass(frozen=True)
class FinalizerTelemetry:
    attempted: bool
    improved: bool
    pairCount: int
    statesExpanded: int
    beamWidth: int
    maxStates: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExactTWRouteFinalizer:
    def __init__(self) -> None:
        self.lastTelemetry: Dict[str, Any] = FinalizerTelemetry(False, False, 0, 0, 0, 0, "not-run").to_dict()

    def finalize_route(
        self,
        instance: Dict[str, Any],
        route: List[str],
        max_states: int = 512,
        beam_width: int = 32,
        max_runtime_ms: int = 500,
    ) -> List[str] | None:
        started = time.perf_counter()
        depot = str(instance.get("depotNodeId", "0"))
        original = [str(stop) for stop in route]
        pairs = extract_request_pairs(instance, {"routes": [original]})
        pair_count = len(pairs)
        self.lastTelemetry = FinalizerTelemetry(True, False, pair_count, 0, beam_width, max_states, "started").to_dict()
        if pair_count == 0:
            self.lastTelemetry["reason"] = "no-pairs"
            return None
        if pair_count > 8:
            self.lastTelemetry["reason"] = "too-many-pairs"
            return None
        original_key = self._route_key(instance, original)
        requests = {str(pair["requestId"]): pair["request"] for pair in pairs}
        pickup_by_id = {rid: str(request.get("pickupNodeId")) for rid, request in requests.items()}
        dropoff_by_id = {rid: str(request.get("dropoffNodeId")) for rid, request in requests.items()}
        all_ids = tuple(sorted(requests))
        states: List[Tuple[Tuple[Any, ...], List[str], frozenset[str], frozenset[str]]] = [(self._partial_key(instance, [depot]), [depot], frozenset(), frozenset())]
        expanded = 0
        best_route = None
        best_key = original_key
        while states and expanded < max_states:
            next_states: List[Tuple[Tuple[Any, ...], List[str], frozenset[str], frozenset[str]]] = []
            for _, partial, picked, dropped in states:
                if (time.perf_counter() - started) * 1000.0 > max_runtime_ms:
                    self.lastTelemetry.update({"statesExpanded": expanded, "reason": "deadline"})
                    return self._finish(instance, original, best_route, best_key, original_key)
                if len(dropped) == pair_count:
                    completed = partial + [depot]
                    key = self._route_key(instance, completed)
                    if key < best_key:
                        best_key = key
                        best_route = completed
                    continue
                for rid in all_ids:
                    if rid not in picked:
                        candidate = partial + [pickup_by_id[rid]]
                        next_states.append((self._partial_key(instance, candidate), candidate, frozenset(set(picked) | {rid}), dropped))
                    elif rid not in dropped:
                        candidate = partial + [dropoff_by_id[rid]]
                        next_states.append((self._partial_key(instance, candidate), candidate, picked, frozenset(set(dropped) | {rid})))
                    expanded += 1
                    if expanded >= max_states:
                        break
                if expanded >= max_states:
                    break
            if not next_states:
                break
            states = sorted(next_states, key=lambda state: state[0])[: max(1, beam_width)]
        self.lastTelemetry["statesExpanded"] = expanded
        return self._finish(instance, original, best_route, best_key, original_key)

    def finalize_solution_routes(
        self,
        instance: Dict[str, Any],
        solution: Dict[str, Any],
        route_indices: List[int] | None = None,
        max_states: int = 512,
        beam_width: int = 32,
        max_runtime_ms: int = 500,
    ) -> Dict[str, Any] | None:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        indices = route_indices if route_indices is not None else list(range(len(routes)))
        best = {"routes": [list(route) for route in routes]}
        improved = False
        states = 0
        for route_index in indices:
            if route_index < 0 or route_index >= len(routes):
                continue
            finalized = self.finalize_route(instance, routes[route_index], max_states=max_states, beam_width=beam_width, max_runtime_ms=max_runtime_ms)
            states += int(self.lastTelemetry.get("statesExpanded", 0) or 0)
            if finalized is not None:
                candidate_routes = [list(route) for route in best["routes"]]
                candidate_routes[route_index] = finalized
                candidate = {"routes": candidate_routes}
                if self._solution_key(instance, candidate) < self._solution_key(instance, best):
                    best = candidate
                    routes = candidate_routes
                    improved = True
        self.lastTelemetry.update({"attempted": True, "improved": improved, "statesExpanded": states, "reason": "solution-improved" if improved else "no-solution-improvement"})
        return best if improved else None

    def _finish(self, instance: Dict[str, Any], original: List[str], best_route: List[str] | None, best_key: Tuple[Any, ...], original_key: Tuple[Any, ...]) -> List[str] | None:
        if best_route is not None and best_key < original_key and self._same_request_set(instance, original, best_route):
            self.lastTelemetry.update({"improved": True, "reason": "improved"})
            return best_route
        self.lastTelemetry.update({"improved": False, "reason": "no-improvement"})
        return None

    def _same_request_set(self, instance: Dict[str, Any], left: List[str], right: List[str]) -> bool:
        left_ids = {str(pair["requestId"]) for pair in extract_request_pairs(instance, {"routes": [left]})}
        right_ids = {str(pair["requestId"]) for pair in extract_request_pairs(instance, {"routes": [right]})}
        return left_ids == right_ids

    def _route_key(self, instance: Dict[str, Any], route: List[str]) -> Tuple[Any, ...]:
        checked = check_solution(instance, {"routes": [route]})
        schedule = evaluate_route_schedule(instance, route)
        return (
            int(checked.get("capacityViolationCount", 0) or 0) + int(checked.get("pickupBeforeDropoffViolationCount", 0) or 0) * 1000,
            int(schedule.timeWindowViolationCount),
            float(schedule.totalLateness),
            float(schedule.maxLateness),
            route_distance(instance, route),
            tuple(route),
        )

    def _solution_key(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Tuple[Any, ...]:
        checked = check_solution(instance, solution)
        schedules = [evaluate_route_schedule(instance, [str(stop) for stop in route]) for route in solution.get("routes", [])]
        return (
            int(checked.get("capacityViolationCount", 0) or 0) + int(checked.get("pickupBeforeDropoffViolationCount", 0) or 0) * 1000,
            sum(int(schedule.timeWindowViolationCount) for schedule in schedules),
            sum(float(schedule.totalLateness) for schedule in schedules),
            max([float(schedule.maxLateness) for schedule in schedules] or [0.0]),
            sum(route_distance(instance, [str(stop) for stop in route]) for route in solution.get("routes", [])),
            solution_signature(solution),
        )

    def _partial_key(self, instance: Dict[str, Any], partial: List[str]) -> Tuple[Any, ...]:
        schedule = evaluate_route_schedule(instance, partial)
        current = partial[-1] if partial else str(instance.get("depotNodeId", "0"))
        return (
            int(schedule.timeWindowViolationCount),
            float(schedule.totalLateness),
            float(schedule.maxLateness),
            -float(schedule.slackProxy),
            route_distance(instance, partial) if len(partial) > 1 else 0.0,
            current,
            tuple(partial),
        )
