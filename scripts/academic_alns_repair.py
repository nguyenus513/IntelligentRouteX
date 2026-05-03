from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from external_benchmark_support import check_solution, route_distance
from optimizer_resource_core import OperatorScoreboard


def _solution(routes: List[List[str]], solver: str = "academic-alns-repair") -> Dict[str, Any]:
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": routes}


def _is_better(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    if not after.get("feasible"):
        return False
    before_vehicles = int(before.get("vehicleCount", 10**9))
    after_vehicles = int(after.get("vehicleCount", 10**9))
    if after_vehicles < before_vehicles:
        return True
    if after_vehicles > before_vehicles:
        return False
    return float(after.get("totalDistance", 1e18)) + 1e-9 < float(before.get("totalDistance", 1e18))


@dataclass(frozen=True)
class ALNSRepairConfig:
    max_runtime_ms: int = 1_500
    max_iterations: int = 80
    max_removed_pairs: int = 14
    receiver_route_shortlist: int = 24
    beam_width: int = 10
    distance_repair_attempts: int = 120


@dataclass(frozen=True)
class ALNSMove:
    operator: str
    source_route_index: int
    removed_pair_count: int
    before_vehicle_count: int
    after_vehicle_count: int
    before_distance: float
    after_distance: float
    feasible: bool
    accepted: bool
    reject_reason: str | None = None


@dataclass(frozen=True)
class ALNSRepairTrace:
    iterations: int = 0
    accepted_moves: int = 0
    rejected_moves: int = 0
    timed_out: bool = False
    moves: List[ALNSMove] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        reject_reasons: Dict[str, int] = {}
        for move in self.moves:
            if move.reject_reason:
                reject_reasons[move.reject_reason] = reject_reasons.get(move.reject_reason, 0) + 1
        return {
            "iterations": self.iterations,
            "acceptedMoves": self.accepted_moves,
            "rejectedMoves": self.rejected_moves,
            "timedOut": self.timed_out,
            "topRejectReasons": reject_reasons,
            "moves": [move.__dict__ for move in self.moves],
        }


@dataclass(frozen=True)
class ALNSRepairResult:
    solution: Dict[str, Any]
    before_metrics: Dict[str, Any]
    after_metrics: Dict[str, Any]
    trace: ALNSRepairTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beforeVehicleCount": self.before_metrics.get("vehicleCount"),
            "afterVehicleCount": self.after_metrics.get("vehicleCount"),
            "beforeDistance": self.before_metrics.get("totalDistance"),
            "afterDistance": self.after_metrics.get("totalDistance"),
            "operatorScoreboard": OperatorScoreboard.from_moves(self.trace.moves).summary(),
            **self.trace.to_dict(),
        }


class BoundedALNSRepair:
    def __init__(self, config: ALNSRepairConfig | None = None) -> None:
        self._config = config or ALNSRepairConfig()

    def repair(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> ALNSRepairResult:
        before_metrics = check_solution(instance, solution)
        if not before_metrics.get("feasible") or instance.get("problemType") != "PDPTW":
            return ALNSRepairResult(solution, before_metrics, before_metrics, ALNSRepairTrace())
        started = time.perf_counter()
        routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
        current_routes = [route[:] for route in routes]
        best_routes = [route[:] for route in routes]
        best_metrics = before_metrics
        request_pairs = self._request_pairs(instance)
        moves: List[ALNSMove] = []
        timed_out = False
        for iteration in range(self._config.max_iterations):
            if self._elapsed_ms(started) >= self._config.max_runtime_ms:
                timed_out = True
                break
            source_index = self._select_source_route(instance, current_routes, request_pairs, iteration)
            if source_index is None:
                moves.append(self._move("route-ejection", -1, 0, best_metrics, best_metrics, True, False, "no-source-route"))
                break
            removed_pairs = self._pairs_in_route(current_routes[source_index], request_pairs)
            if not removed_pairs or len(removed_pairs) > self._config.max_removed_pairs:
                moves.append(self._move("route-ejection", source_index, len(removed_pairs), best_metrics, best_metrics, True, False, "route-pair-count-out-of-budget"))
                continue
            candidate_routes = self._remove_route_and_repair(instance, current_routes, source_index, removed_pairs)
            if candidate_routes is None:
                moves.append(self._move("route-ejection-regret-repair", source_index, len(removed_pairs), best_metrics, best_metrics, False, False, "repair-infeasible"))
                continue
            candidate_metrics = check_solution(instance, _solution(candidate_routes))
            accepted = _is_better(best_metrics, candidate_metrics)
            moves.append(self._move("route-ejection-regret-repair", source_index, len(removed_pairs), best_metrics, candidate_metrics, bool(candidate_metrics.get("feasible")), accepted, None if accepted else "not-better"))
            if accepted:
                current_routes = [route[:] for route in candidate_routes]
                best_routes = [route[:] for route in candidate_routes]
                best_metrics = candidate_metrics
        if not timed_out and self._elapsed_ms(started) < self._config.max_runtime_ms:
            best_routes, best_metrics, distance_moves, distance_timed_out = self._improve_distance_same_vehicle(
                instance,
                best_routes,
                best_metrics,
                request_pairs,
                started,
            )
            moves.extend(distance_moves)
            timed_out = timed_out or distance_timed_out
        repaired_solution = dict(solution)
        repaired_solution["routes"] = best_routes
        trace = ALNSRepairTrace(
            iterations=len(moves),
            accepted_moves=sum(1 for move in moves if move.accepted),
            rejected_moves=sum(1 for move in moves if not move.accepted),
            timed_out=timed_out,
            moves=moves,
        )
        repaired_solution["alnsRepair"] = ALNSRepairResult(repaired_solution, before_metrics, best_metrics, trace).to_dict()
        return ALNSRepairResult(repaired_solution, before_metrics, best_metrics, trace)

    def _improve_distance_same_vehicle(
        self,
        instance: Dict[str, Any],
        routes: List[List[str]],
        best_metrics: Dict[str, Any],
        request_pairs: List[tuple[str, str]],
        started: float,
    ) -> tuple[List[List[str]], Dict[str, Any], List[ALNSMove], bool]:
        current_routes = [route[:] for route in routes]
        moves: List[ALNSMove] = []
        timed_out = False
        attempts = 0
        route_pairs = self._ranked_route_pairs(instance, current_routes)
        for left_index, right_index in route_pairs:
            if attempts >= self._config.distance_repair_attempts:
                break
            if self._elapsed_ms(started) >= self._config.max_runtime_ms:
                timed_out = True
                break
            attempts += 1
            candidate_routes = self._best_pair_swap_or_relocate(instance, current_routes, left_index, right_index, request_pairs, best_metrics)
            if candidate_routes is None:
                moves.append(self._move("distance-pair-swap-relocate", left_index, 1, best_metrics, best_metrics, True, False, "no-improving-distance-move"))
                continue
            candidate_metrics = check_solution(instance, _solution(candidate_routes))
            accepted = _is_better(best_metrics, candidate_metrics)
            moves.append(self._move("distance-pair-swap-relocate", left_index, 1, best_metrics, candidate_metrics, bool(candidate_metrics.get("feasible")), accepted, None if accepted else "not-better"))
            if accepted:
                current_routes = [route[:] for route in candidate_routes]
                best_metrics = candidate_metrics
                route_pairs = self._ranked_route_pairs(instance, current_routes)
        return current_routes, best_metrics, moves, timed_out

    def _best_pair_swap_or_relocate(
        self,
        instance: Dict[str, Any],
        routes: List[List[str]],
        left_index: int,
        right_index: int,
        request_pairs: List[tuple[str, str]],
        best_metrics: Dict[str, Any],
    ) -> List[List[str]] | None:
        best_routes: List[List[str]] | None = None
        best_key = (int(best_metrics.get("vehicleCount", 10**9)), float(best_metrics.get("totalDistance", 1e18)))
        left_pairs = self._pairs_in_route(routes[left_index], request_pairs)
        right_pairs = self._pairs_in_route(routes[right_index], request_pairs)
        for pickup, dropoff in left_pairs[: self._config.beam_width]:
            relocated = self._best_pair_relocate_between_routes(instance, routes, left_index, right_index, pickup, dropoff, best_key)
            if relocated is not None:
                key = self._candidate_key(instance, relocated)
                if key < best_key:
                    best_key = key
                    best_routes = relocated
        for left_pair in left_pairs[: self._config.beam_width]:
            for right_pair in right_pairs[: self._config.beam_width]:
                swapped = self._pair_swap_candidate(instance, routes, left_index, right_index, left_pair, right_pair, best_key)
                if swapped is not None:
                    key = self._candidate_key(instance, swapped)
                    if key < best_key:
                        best_key = key
                        best_routes = swapped
        return best_routes

    def _best_pair_relocate_between_routes(
        self,
        instance: Dict[str, Any],
        routes: List[List[str]],
        source_index: int,
        target_index: int,
        pickup: str,
        dropoff: str,
        best_key: tuple[int, float],
    ) -> List[List[str]] | None:
        source_route = routes[source_index]
        if pickup not in source_route or dropoff not in source_route:
            return None
        pickup_index = source_route.index(pickup)
        dropoff_index = source_route.index(dropoff)
        if pickup_index >= dropoff_index:
            return None
        reduced_source = [stop for index, stop in enumerate(source_route) if index not in {pickup_index, dropoff_index}]
        best_routes: List[List[str]] | None = None
        target_route = routes[target_index]
        for pickup_position in range(1, len(target_route)):
            with_pickup = target_route[:pickup_position] + [pickup] + target_route[pickup_position:]
            for dropoff_position in range(pickup_position + 1, len(with_pickup)):
                moved_target = with_pickup[:dropoff_position] + [dropoff] + with_pickup[dropoff_position:]
                candidate = [route[:] for route in routes]
                candidate[source_index] = reduced_source
                candidate[target_index] = moved_target
                if len(reduced_source) <= 2:
                    continue
                checked = check_solution(instance, _solution(candidate))
                if not checked.get("feasible"):
                    continue
                key = (int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18)))
                if key < best_key:
                    best_key = key
                    best_routes = candidate
        return best_routes

    def _pair_swap_candidate(
        self,
        instance: Dict[str, Any],
        routes: List[List[str]],
        left_index: int,
        right_index: int,
        left_pair: tuple[str, str],
        right_pair: tuple[str, str],
        best_key: tuple[int, float],
    ) -> List[List[str]] | None:
        left_removed = self._remove_pair(routes[left_index], left_pair)
        right_removed = self._remove_pair(routes[right_index], right_pair)
        if left_removed is None or right_removed is None:
            return None
        best_routes: List[List[str]] | None = None
        for left_candidate in self._insert_pair_into_route(instance, left_removed, right_pair):
            for right_candidate in self._insert_pair_into_route(instance, right_removed, left_pair):
                candidate = [route[:] for route in routes]
                candidate[left_index] = left_candidate
                candidate[right_index] = right_candidate
                checked = check_solution(instance, _solution(candidate))
                if not checked.get("feasible"):
                    continue
                key = (int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18)))
                if key < best_key:
                    best_key = key
                    best_routes = candidate
        return best_routes

    def _insert_pair_into_route(self, instance: Dict[str, Any], route: List[str], pair: tuple[str, str]) -> List[List[str]]:
        pickup, dropoff = pair
        candidates: List[tuple[float, List[str]]] = []
        for pickup_position in range(1, len(route)):
            with_pickup = route[:pickup_position] + [pickup] + route[pickup_position:]
            for dropoff_position in range(pickup_position + 1, len(with_pickup)):
                candidate = with_pickup[:dropoff_position] + [dropoff] + with_pickup[dropoff_position:]
                checked = check_solution(instance, _solution([candidate]))
                if checked.get("feasible"):
                    candidates.append((route_distance(instance, candidate), candidate))
        candidates.sort(key=lambda item: item[0])
        return [candidate for _, candidate in candidates[: self._config.beam_width]]

    def _remove_pair(self, route: List[str], pair: tuple[str, str]) -> List[str] | None:
        pickup, dropoff = pair
        if pickup not in route or dropoff not in route:
            return None
        pickup_index = route.index(pickup)
        dropoff_index = route.index(dropoff)
        if pickup_index >= dropoff_index:
            return None
        return [stop for index, stop in enumerate(route) if index not in {pickup_index, dropoff_index}]

    def _ranked_route_pairs(self, instance: Dict[str, Any], routes: List[List[str]]) -> List[tuple[int, int]]:
        route_order = sorted(range(len(routes)), key=lambda index: route_distance(instance, routes[index]), reverse=True)
        pairs: List[tuple[int, int]] = []
        for left_position, left_index in enumerate(route_order[: self._config.receiver_route_shortlist]):
            for right_index in route_order[left_position + 1: self._config.receiver_route_shortlist]:
                pairs.append((left_index, right_index))
        return pairs

    def _select_source_route(self, instance: Dict[str, Any], routes: List[List[str]], request_pairs: List[tuple[str, str]], iteration: int) -> int | None:
        eligible = [
            index for index, route in enumerate(routes)
            if 0 < len(self._pairs_in_route(route, request_pairs)) <= self._config.max_removed_pairs
        ]
        if not eligible:
            return None
        ranked = sorted(
            eligible,
            key=lambda index: (
                len(self._pairs_in_route(routes[index], request_pairs)),
                -route_distance(instance, routes[index]),
                len(routes[index]),
            ),
        )
        return ranked[iteration % min(len(ranked), max(1, self._config.receiver_route_shortlist))]

    def _remove_route_and_repair(self, instance: Dict[str, Any], routes: List[List[str]], source_index: int, removed_pairs: List[tuple[str, str]]) -> List[List[str]] | None:
        remaining = [route[:] for index, route in enumerate(routes) if index != source_index]
        candidates: List[List[List[str]]] = [remaining]
        for pickup, dropoff in self._hardest_pairs_first(instance, remaining, removed_pairs):
            next_candidates: List[List[List[str]]] = []
            for candidate_routes in candidates:
                next_candidates.extend(self._insert_pair_candidates(instance, candidate_routes, pickup, dropoff))
            if not next_candidates:
                return None
            next_candidates.sort(key=lambda candidate: self._candidate_key(instance, candidate))
            candidates = next_candidates[:self._config.beam_width]
        feasible = [candidate for candidate in candidates if check_solution(instance, _solution(candidate)).get("feasible")]
        if not feasible:
            return None
        feasible.sort(key=lambda candidate: self._candidate_key(instance, candidate))
        return feasible[0]

    def _insert_pair_candidates(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[List[List[str]]]:
        candidates: List[List[List[str]]] = []
        for route_index, route in self._ranked_receiver_routes(instance, routes, pickup, dropoff):
            for pickup_position in range(1, len(route)):
                for dropoff_position in range(pickup_position + 1, len(route) + 1):
                    candidate = [item[:] for item in routes]
                    candidate_route = route[:pickup_position] + [pickup] + route[pickup_position:dropoff_position] + [dropoff] + route[dropoff_position:]
                    candidate[route_index] = candidate_route
                    checked = check_solution(instance, _solution(candidate))
                    if checked.get("feasible"):
                        candidates.append(candidate)
        candidates.sort(key=lambda candidate: self._candidate_key(instance, candidate))
        return candidates[:self._config.beam_width]

    def _ranked_receiver_routes(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[tuple[int, List[str]]]:
        nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
        pickup_node = nodes.get(pickup, {})
        dropoff_node = nodes.get(dropoff, {})

        def affinity(item: tuple[int, List[str]]) -> float:
            _, route = item
            active_stops = route[1:-1]
            if not active_stops:
                return 1e18
            return min(
                min(self._euclidean(pickup_node, nodes.get(stop, {})), self._euclidean(dropoff_node, nodes.get(stop, {})))
                for stop in active_stops
            )

        return sorted(enumerate(routes), key=lambda item: (affinity(item), len(item[1])))[:self._config.receiver_route_shortlist]

    def _hardest_pairs_first(self, instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        scored: List[tuple[tuple[int, float, float], tuple[str, str]]] = []
        for pickup, dropoff in pairs:
            costs = self._pair_insertion_costs(instance, routes, pickup, dropoff)
            if not costs:
                scored.append(((0, -1e18, -self._pair_direct_distance(instance, pickup, dropoff)), (pickup, dropoff)))
                continue
            regret = costs[1] - costs[0] if len(costs) > 1 else costs[0]
            scored.append(((len(costs), -regret, -self._pair_direct_distance(instance, pickup, dropoff)), (pickup, dropoff)))
        scored.sort(key=lambda item: item[0])
        return [pair for _, pair in scored]

    def _pair_direct_distance(self, instance: Dict[str, Any], pickup: str, dropoff: str) -> float:
        try:
            indexes = {str(node["id"]): index for index, node in enumerate(instance.get("nodes", []))}
            return float(instance.get("distanceMatrix", [])[indexes[pickup]][indexes[dropoff]])
        except Exception:
            return 0.0

    def _pair_insertion_costs(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[float]:
        baseline_distance = float(check_solution(instance, _solution(routes)).get("totalDistance", 0.0))
        costs: List[float] = []
        for candidate in self._insert_pair_candidates(instance, routes, pickup, dropoff):
            costs.append(float(check_solution(instance, _solution(candidate)).get("totalDistance", 1e18)) - baseline_distance)
        costs.sort()
        return costs[:3]

    def _candidate_key(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[int, float]:
        checked = check_solution(instance, _solution(routes))
        return int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18))

    def _request_pairs(self, instance: Dict[str, Any]) -> List[tuple[str, str]]:
        return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]

    def _pairs_in_route(self, route: List[str], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [(pickup, dropoff) for pickup, dropoff in request_pairs if pickup in route_set and dropoff in route_set]

    def _move(self, operator: str, source_index: int, removed_pair_count: int, before: Dict[str, Any], after: Dict[str, Any], feasible: bool, accepted: bool, reject_reason: str | None) -> ALNSMove:
        return ALNSMove(
            operator=operator,
            source_route_index=source_index,
            removed_pair_count=removed_pair_count,
            before_vehicle_count=int(before.get("vehicleCount", 0)),
            after_vehicle_count=int(after.get("vehicleCount", before.get("vehicleCount", 0))),
            before_distance=float(before.get("totalDistance", 0.0)),
            after_distance=float(after.get("totalDistance", before.get("totalDistance", 0.0))),
            feasible=feasible,
            accepted=accepted,
            reject_reason=reject_reason,
        )

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _euclidean(self, left: Dict[str, Any], right: Dict[str, Any]) -> float:
        return ((float(left.get("x", 0.0)) - float(right.get("x", 0.0))) ** 2 + (float(left.get("y", 0.0)) - float(right.get("y", 0.0))) ** 2) ** 0.5
