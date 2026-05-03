from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from academic_alns_repair import ALNSRepairConfig, BoundedALNSRepair
from external_benchmark_support import check_solution, route_distance


@dataclass(frozen=True)
class ConsolidationMove:
    operator: str
    route_index: int
    before_vehicle_count: int
    after_vehicle_count: int
    removed_stop_count: int
    inserted_stop_count: int
    feasible: bool
    accepted: bool
    reject_reason: str | None = None
    metadata: Dict[str, Any] | None = None


@dataclass(frozen=True)
class ConsolidationTrace:
    operator_attempts: int = 0
    accepted_moves: int = 0
    rejected_moves: int = 0
    moves: List[ConsolidationMove] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        reject_reasons: Dict[str, int] = {}
        for move in self.moves:
            if move.reject_reason:
                reject_reasons[move.reject_reason] = reject_reasons.get(move.reject_reason, 0) + 1
        return {
            "operatorAttempts": self.operator_attempts,
            "acceptedMoves": self.accepted_moves,
            "rejectedMoves": self.rejected_moves,
            "topRejectReasons": reject_reasons,
            "moves": [move.__dict__ for move in self.moves],
        }


@dataclass(frozen=True)
class ConsolidationResult:
    solution: Dict[str, Any]
    before_metrics: Dict[str, Any]
    after_metrics: Dict[str, Any]
    trace: ConsolidationTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beforeVehicleCount": self.before_metrics.get("vehicleCount"),
            "afterVehicleCount": self.after_metrics.get("vehicleCount"),
            "vehicleReduction": int(self.before_metrics.get("vehicleCount", 0)) - int(self.after_metrics.get("vehicleCount", 0)),
            "beforeDistance": self.before_metrics.get("totalDistance"),
            "afterDistance": self.after_metrics.get("totalDistance"),
            "beforeGap": self.before_metrics.get("objectiveGapPercent"),
            "afterGap": self.after_metrics.get("objectiveGapPercent"),
            "hardViolationCount": len(self.after_metrics.get("violations", [])),
            **self.trace.to_dict(),
        }


class ConsolidationOperator(Protocol):
    name: str

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        ...


def _active_routes(solution: Dict[str, Any]) -> List[List[str]]:
    return [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]


def _solution(routes: List[List[str]], solver: str) -> Dict[str, Any]:
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": routes}


def _is_better(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    if not after.get("feasible"):
        return False
    before_vehicles = int(before.get("vehicleCount", 0))
    after_vehicles = int(after.get("vehicleCount", 0))
    if after_vehicles < before_vehicles:
        return True
    if after_vehicles > before_vehicles:
        return False
    return float(after.get("totalDistance", 0.0)) + 1e-9 < float(before.get("totalDistance", 0.0))


@dataclass(frozen=True)
class PairInsertionOption:
    pair: tuple[str, str]
    route_index: int
    pickup_pos: int
    dropoff_pos: int
    delta_distance: float
    feasible: bool
    slack_after: float = 0.0


class PairInsertionIndex:
    def __init__(self, instance: Dict[str, Any], routes: List[List[str]], max_candidate_checks: int = 512, max_routes: int = 32, max_positions_per_route: int = 96) -> None:
        self._instance = instance
        self._routes = [route[:] for route in routes]
        self._max_candidate_checks = max_candidate_checks
        self._max_routes = max_routes
        self._max_positions_per_route = max_positions_per_route
        self._options_by_pair: Dict[tuple[str, str], List[PairInsertionOption]] = {}
        self.candidate_checks = 0
        self.cache_hits = 0

    @classmethod
    def build(cls, instance: Dict[str, Any], routes: List[List[str]], max_candidate_checks: int = 512, max_routes: int = 32, max_positions_per_route: int = 96) -> "PairInsertionIndex":
        return cls(instance, routes, max_candidate_checks=max_candidate_checks, max_routes=max_routes, max_positions_per_route=max_positions_per_route)

    def options_for_pair(self, pair: tuple[str, str], top_k: int = 32) -> List[PairInsertionOption]:
        if pair in self._options_by_pair:
            self.cache_hits += 1
            return self._options_by_pair[pair][:top_k]
        pickup, dropoff = pair
        options: List[PairInsertionOption] = []
        for route_index, route in self._ranked_routes(pair):
            route_checks = 0
            baseline_distance = route_distance(self._instance, route)
            for pickup_pos, dropoff_pos in self._ranked_position_pairs(route, pickup, dropoff):
                if self.candidate_checks >= self._max_candidate_checks or route_checks >= self._max_positions_per_route:
                    break
                candidate_route = route[:pickup_pos] + [pickup] + route[pickup_pos:dropoff_pos] + [dropoff] + route[dropoff_pos:]
                self.candidate_checks += 1
                route_checks += 1
                feasible, slack_after = _route_is_feasible(self._instance, candidate_route)
                if feasible:
                    options.append(PairInsertionOption(pair, route_index, pickup_pos, dropoff_pos, route_distance(self._instance, candidate_route) - baseline_distance, True, slack_after))
            if self.candidate_checks >= self._max_candidate_checks:
                break
        options.sort(key=lambda option: (option.delta_distance, -option.slack_after, len(self._routes[option.route_index])))
        self._options_by_pair[pair] = options
        return options[:top_k]

    def _ranked_position_pairs(self, route: List[str], pickup: str, dropoff: str) -> List[tuple[int, int]]:
        def arc_delta(left: str, inserted: str, right: str) -> float:
            return route_distance(self._instance, [left, inserted]) + route_distance(self._instance, [inserted, right]) - route_distance(self._instance, [left, right])

        candidates: List[tuple[float, int, int]] = []
        for pickup_pos in range(1, len(route)):
            pickup_delta = arc_delta(route[pickup_pos - 1], pickup, route[pickup_pos])
            for dropoff_pos in range(pickup_pos, len(route)):
                drop_left = pickup if dropoff_pos == pickup_pos else route[dropoff_pos - 1]
                drop_right = route[dropoff_pos]
                drop_delta = arc_delta(drop_left, dropoff, drop_right)
                candidates.append((pickup_delta + drop_delta, pickup_pos, dropoff_pos))
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return [(pickup_pos, dropoff_pos) for _, pickup_pos, dropoff_pos in candidates]

    def options_for_route(self, route_index: int, top_k: int = 64) -> List[PairInsertionOption]:
        options = [option for cached in self._options_by_pair.values() for option in cached if option.route_index == route_index]
        options.sort(key=lambda option: (option.delta_distance, -option.slack_after))
        return options[:top_k]

    def refresh_routes(self, changed_route_indexes: List[int]) -> None:
        changed = set(changed_route_indexes)
        self._options_by_pair = {
            pair: [option for option in options if option.route_index not in changed]
            for pair, options in self._options_by_pair.items()
        }

    def _ranked_routes(self, pair: tuple[str, str]) -> List[tuple[int, List[str]]]:
        nodes = {str(node["id"]): node for node in self._instance.get("nodes", [])}
        pickup_node = nodes.get(pair[0], {})
        dropoff_node = nodes.get(pair[1], {})

        def affinity(item: tuple[int, List[str]]) -> float:
            _, route = item
            active_stops = route[1:-1]
            if not active_stops:
                return 1e18
            return min(
                min(_euclidean(pickup_node, nodes.get(str(stop), {})), _euclidean(dropoff_node, nodes.get(str(stop), {})))
                for stop in active_stops
            )

        return sorted(enumerate(self._routes), key=lambda item: (affinity(item), len(item[1])))[:self._max_routes]


def _apply_pair_insertion(routes: List[List[str]], option: PairInsertionOption) -> List[List[str]]:
    candidate = [route[:] for route in routes]
    route = candidate[option.route_index]
    pickup, dropoff = option.pair
    candidate[option.route_index] = route[:option.pickup_pos] + [pickup] + route[option.pickup_pos:option.dropoff_pos] + [dropoff] + route[option.dropoff_pos:]
    return candidate


def _route_is_feasible(instance: Dict[str, Any], route: List[str]) -> tuple[bool, float]:
    depot = str(instance.get("depotNodeId", "0"))
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
    if not route or route[0] != depot or route[-1] != depot or any(stop not in nodes for stop in route):
        return False, -1e18
    capacity = int(instance.get("capacity", 0))
    load = 0
    elapsed = 0.0
    min_slack = 1e18
    for previous, current in zip(route, route[1:]):
        elapsed += route_distance(instance, [previous, current])
        node = nodes[current]
        ready = float(node.get("readyTime", 0.0))
        due = float(node.get("dueTime", 1e18))
        if elapsed < ready:
            elapsed = ready
        min_slack = min(min_slack, due - elapsed)
        if elapsed > due + 1e-9:
            return False, min_slack
        elapsed += float(node.get("serviceTime", 0.0))
        load += int(float(node.get("demand", 0)))
        if load > capacity or load < 0:
            return False, min_slack
    route_set = set(route)
    for request in instance.get("requests", []):
        pickup = str(request["pickupNodeId"])
        dropoff = str(request["dropoffNodeId"])
        if pickup in route_set or dropoff in route_set:
            if pickup not in route_set or dropoff not in route_set or route.index(pickup) >= route.index(dropoff):
                return False, min_slack
    return True, min_slack if min_slack != 1e18 else 0.0


def _euclidean(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    return ((float(left.get("x", 0.0)) - float(right.get("x", 0.0))) ** 2 + (float(left.get("y", 0.0)) - float(right.get("y", 0.0))) ** 2) ** 0.5


class RouteEliminationOperator:
    name = "route-elimination"

    def __init__(self, max_removed_stops: int = 6, max_attempts: int = 200) -> None:
        self._max_removed_stops = max_removed_stops
        self._max_attempts = max_attempts

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if instance.get("problemType") != "VRPTW" or len(routes) < 2:
            return routes, moves
        solver = "academic-global-consolidation"
        current_routes = [route[:] for route in routes]
        improved = True
        while improved:
            improved = False
            priorities = sorted(
                range(len(current_routes)),
                key=lambda index: (len(current_routes[index]), route_distance(instance, current_routes[index])),
            )
            for route_index in priorities:
                if len(moves) >= self._max_attempts:
                    return current_routes, moves
                before_solution = _solution(current_routes, solver)
                before_metrics = check_solution(instance, before_solution)
                candidate = [route[:] for index, route in enumerate(current_routes) if index != route_index]
                removed_stops = [stop for stop in current_routes[route_index][1:-1]]
                if len(removed_stops) > self._max_removed_stops:
                    moves.append(
                        ConsolidationMove(
                            operator=self.name,
                            route_index=route_index,
                            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
                            after_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
                            removed_stop_count=len(removed_stops),
                            inserted_stop_count=0,
                            feasible=True,
                            accepted=False,
                            reject_reason="route-too-large-for-v1",
                        )
                    )
                    continue
                feasible_inserted = 0
                reject_reason = None
                for stop in removed_stops:
                    insert_result = self._best_insert(instance, candidate, stop)
                    if insert_result is None:
                        reject_reason = "no-feasible-insertion"
                        break
                    target_route_index, position = insert_result
                    candidate[target_route_index].insert(position, stop)
                    feasible_inserted += 1
                after_metrics = check_solution(instance, _solution(candidate, solver)) if reject_reason is None else {"feasible": False}
                accepted = reject_reason is None and _is_better(before_metrics, after_metrics)
                moves.append(
                    ConsolidationMove(
                        operator=self.name,
                        route_index=route_index,
                        before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
                        after_vehicle_count=int(after_metrics.get("vehicleCount", len(candidate))),
                        removed_stop_count=len(removed_stops),
                        inserted_stop_count=feasible_inserted,
                        feasible=bool(after_metrics.get("feasible")),
                        accepted=accepted,
                        reject_reason=None if accepted else reject_reason or "not-better",
                    )
                )
                if accepted:
                    current_routes = candidate
                    improved = True
                    break
        return current_routes, moves

    def _best_insert(self, instance: Dict[str, Any], routes: List[List[str]], stop: str) -> tuple[int, int] | None:
        best: tuple[float, int, int] | None = None
        baseline_solution = _solution(routes, "academic-global-consolidation")
        baseline = check_solution(instance, baseline_solution)
        baseline_distance = float(baseline.get("totalDistance", 0.0))
        for route_index, route in enumerate(routes):
            for position in range(1, len(route)):
                candidate = [item[:] for item in routes]
                candidate[route_index].insert(position, stop)
                checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
                if not checked.get("feasible"):
                    continue
                distance_delta = float(checked.get("totalDistance", 0.0)) - baseline_distance
                score = distance_delta
                if best is None or score < best[0]:
                    best = (score, route_index, position)
        if best is None:
            return None
        return best[1], best[2]


class ContiguousBlockRouteEliminationOperator:
    name = "contiguous-block-route-elimination"

    def __init__(self, max_removed_stops: int = 4, max_attempts: int = 24) -> None:
        self._max_removed_stops = max_removed_stops
        self._max_attempts = max_attempts

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if len(routes) < 2:
            return routes, moves
        solver = "academic-global-consolidation"
        current_routes = [route[:] for route in routes]
        improved = True
        while improved:
            improved = False
            priorities = sorted(
                range(len(current_routes)),
                key=lambda index: (len(current_routes[index]), route_distance(instance, current_routes[index])),
            )
            for route_index in priorities:
                if len(moves) >= self._max_attempts:
                    return current_routes, moves
                before_metrics = check_solution(instance, _solution(current_routes, solver))
                removed_stops = [stop for stop in current_routes[route_index][1:-1]]
                if len(removed_stops) > self._max_removed_stops:
                    moves.append(self._move(route_index, before_metrics, before_metrics, len(removed_stops), 0, True, False, "route-too-large-for-block"))
                    continue
                candidate = self._best_block_insert(instance, current_routes, route_index, removed_stops)
                if candidate is None:
                    moves.append(self._move(route_index, before_metrics, {"vehicleCount": len(current_routes), "feasible": False}, len(removed_stops), 0, False, False, "no-feasible-block-insertion"))
                    continue
                after_metrics = check_solution(instance, _solution(candidate, solver))
                accepted = _is_better(before_metrics, after_metrics)
                moves.append(self._move(route_index, before_metrics, after_metrics, len(removed_stops), len(removed_stops), bool(after_metrics.get("feasible")), accepted, None if accepted else "not-better"))
                if accepted:
                    current_routes = candidate
                    improved = True
                    break
        return current_routes, moves

    def _best_block_insert(self, instance: Dict[str, Any], routes: List[List[str]], removed_route_index: int, block: List[str]) -> List[List[str]] | None:
        baseline_distance = float(check_solution(instance, _solution(routes, "academic-global-consolidation")).get("totalDistance", 0.0))
        best: tuple[float, List[List[str]]] | None = None
        remaining = [route[:] for index, route in enumerate(routes) if index != removed_route_index]
        for route_index, route in enumerate(remaining):
            for position in range(1, len(route)):
                candidate = [item[:] for item in remaining]
                candidate[route_index] = route[:position] + block + route[position:]
                checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
                if not checked.get("feasible"):
                    continue
                score = float(checked.get("totalDistance", 0.0)) - baseline_distance
                if best is None or score < best[0]:
                    best = (score, candidate)
        return None if best is None else best[1]

    def _move(self,
              route_index: int,
              before_metrics: Dict[str, Any],
              after_metrics: Dict[str, Any],
              removed_stop_count: int,
              inserted_stop_count: int,
              feasible: bool,
              accepted: bool,
              reject_reason: str | None) -> ConsolidationMove:
        return ConsolidationMove(
            operator=self.name,
            route_index=route_index,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(after_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=removed_stop_count,
            inserted_stop_count=inserted_stop_count,
            feasible=feasible,
            accepted=accepted,
            reject_reason=reject_reason,
        )


class PairAwareRouteEliminationOperator:
    name = "pair-aware-route-elimination"

    def __init__(self, max_removed_pairs: int = 12, max_attempts: int = 120, route_shortlist: int = 18, beam_width: int = 8, max_candidate_checks_per_pair: int = 512) -> None:
        self._max_removed_pairs = max_removed_pairs
        self._max_attempts = max_attempts
        self._route_shortlist = route_shortlist
        self._beam_width = beam_width
        self._max_candidate_checks_per_pair = max_candidate_checks_per_pair

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if instance.get("problemType") != "PDPTW" or len(routes) < 2:
            return routes, moves
        request_pairs = self._request_pairs(instance)
        solver = "academic-global-consolidation"
        current_routes = [route[:] for route in routes]
        improved = True
        while improved:
            improved = False
            priorities = [index for index in sorted(
                range(len(current_routes)),
                key=lambda index: (
                    len(self._pairs_in_route(current_routes[index], request_pairs)),
                    route_distance(instance, current_routes[index]),
                    len(current_routes[index]),
                ),
            ) if 0 < len(self._pairs_in_route(current_routes[index], request_pairs)) <= self._max_removed_pairs]
            if not priorities:
                before_metrics = check_solution(instance, _solution(current_routes, solver))
                moves.append(self._move(-1, before_metrics, before_metrics, 0, 0, bool(before_metrics.get("feasible")), False, "no-small-pair-route-for-v1"))
                return current_routes, moves
            for route_index in priorities:
                if len(moves) >= self._max_attempts:
                    return current_routes, moves
                before_metrics = check_solution(instance, _solution(current_routes, solver))
                route_pairs = self._pairs_in_route(current_routes[route_index], request_pairs)
                if not route_pairs:
                    moves.append(self._move(route_index, before_metrics, before_metrics, 0, 0, True, False, "no-complete-pair-in-route"))
                    continue
                if len(route_pairs) > self._max_removed_pairs:
                    moves.append(self._move(route_index, before_metrics, before_metrics, len(route_pairs) * 2, 0, True, False, "too-many-pairs-for-v1"))
                    continue
                candidate = self._best_pair_reinsertion(instance, current_routes, route_index, route_pairs)
                if candidate is None:
                    moves.append(self._move(route_index, before_metrics, {"vehicleCount": len(current_routes), "feasible": False}, len(route_pairs) * 2, 0, False, False, "no-feasible-pair-insertion"))
                    continue
                after_metrics = check_solution(instance, _solution(candidate, solver))
                accepted = _is_better(before_metrics, after_metrics)
                moves.append(self._move(route_index, before_metrics, after_metrics, len(route_pairs) * 2, len(route_pairs) * 2, bool(after_metrics.get("feasible")), accepted, None if accepted else "not-better"))
                if accepted:
                    current_routes = candidate
                    improved = True
                    break
        return current_routes, moves

    def _request_pairs(self, instance: Dict[str, Any]) -> List[tuple[str, str]]:
        return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]

    def _pairs_in_route(self, route: List[str], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [(pickup, dropoff) for pickup, dropoff in request_pairs if pickup in route_set and dropoff in route_set]

    def _best_pair_reinsertion(self,
                               instance: Dict[str, Any],
                               routes: List[List[str]],
                               removed_route_index: int,
                               route_pairs: List[tuple[str, str]]) -> List[List[str]] | None:
        remaining = [route[:] for index, route in enumerate(routes) if index != removed_route_index]
        best: tuple[tuple[int, float], List[List[str]]] | None = None
        route_pairs = self._hardest_pairs_first(instance, remaining, route_pairs)
        candidates = [(remaining, 0)]
        for pickup, dropoff in route_pairs:
            next_candidates: List[tuple[List[List[str]], int]] = []
            for candidate_routes, inserted_count in candidates:
                inserted = self._insert_pair_candidates(instance, candidate_routes, pickup, dropoff)
                next_candidates.extend((routes_candidate, inserted_count + 1) for routes_candidate in inserted)
            if not next_candidates:
                return None
            next_candidates.sort(key=lambda item: (len(item[0]), self._distance(instance, item[0])))
            candidates = next_candidates[:self._beam_width]
        for candidate_routes, _ in candidates:
            checked = check_solution(instance, _solution(candidate_routes, "academic-global-consolidation"))
            if not checked.get("feasible"):
                continue
            key = (int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18)))
            if best is None or key < best[0]:
                best = (key, candidate_routes)
        return None if best is None else best[1]

    def _hardest_pairs_first(self, instance: Dict[str, Any], routes: List[List[str]], route_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        scored: List[tuple[tuple[int, float, float], tuple[str, str]]] = []
        for pickup, dropoff in route_pairs:
            insertions = self._pair_insertion_costs(instance, routes, pickup, dropoff, limit=2)
            if not insertions:
                scored.append(((0, -1e18, -self._pair_direct_distance(instance, pickup, dropoff)), (pickup, dropoff)))
                continue
            regret = insertions[1] - insertions[0] if len(insertions) > 1 else insertions[0]
            scored.append(((len(insertions), -regret, -self._pair_direct_distance(instance, pickup, dropoff)), (pickup, dropoff)))
        scored.sort(key=lambda item: item[0])
        return [pair for _, pair in scored]

    def _pair_direct_distance(self, instance: Dict[str, Any], pickup: str, dropoff: str) -> float:
        try:
            indexes = {str(node["id"]): index for index, node in enumerate(instance.get("nodes", []))}
            return float(instance.get("distanceMatrix", [])[indexes[pickup]][indexes[dropoff]])
        except Exception:
            return 0.0

    def _pair_insertion_costs(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str, limit: int) -> List[float]:
        costs: List[float] = []
        baseline_distance = self._distance(instance, routes)
        checked_candidates = 0
        for route_index, route in self._ranked_receiver_routes(instance, routes, pickup, dropoff):
            for pickup_position in range(1, len(route)):
                for dropoff_position in range(pickup_position + 1, len(route) + 1):
                    if checked_candidates >= self._max_candidate_checks_per_pair:
                        costs.sort()
                        return costs[:limit]
                    candidate = [item[:] for item in routes]
                    candidate_route = route[:pickup_position] + [pickup] + route[pickup_position:dropoff_position] + [dropoff] + route[dropoff_position:]
                    candidate[route_index] = candidate_route
                    checked_candidates += 1
                    checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
                    if checked.get("feasible"):
                        costs.append(float(checked.get("totalDistance", 0.0)) - baseline_distance)
        costs.sort()
        return costs[:limit]

    def _insert_pair_candidates(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[List[List[str]]]:
        feasible: List[tuple[float, List[List[str]]]] = []
        baseline_distance = self._distance(instance, routes)
        checked_candidates = 0
        for route_index, route in self._ranked_receiver_routes(instance, routes, pickup, dropoff):
            for pickup_position in range(1, len(route)):
                for dropoff_position in range(pickup_position + 1, len(route) + 1):
                    if checked_candidates >= self._max_candidate_checks_per_pair:
                        feasible.sort(key=lambda item: item[0])
                        return [candidate for _, candidate in feasible[:self._beam_width]]
                    candidate = [item[:] for item in routes]
                    candidate_route = route[:pickup_position] + [pickup] + route[pickup_position:dropoff_position] + [dropoff] + route[dropoff_position:]
                    candidate[route_index] = candidate_route
                    checked_candidates += 1
                    checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
                    if checked.get("feasible"):
                        feasible.append((float(checked.get("totalDistance", 0.0)) - baseline_distance, candidate))
        feasible.sort(key=lambda item: item[0])
        return [candidate for _, candidate in feasible[:self._beam_width]]

    def _ranked_receiver_routes(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[tuple[int, List[str]]]:
        nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
        pickup_node = nodes.get(pickup, {})
        dropoff_node = nodes.get(dropoff, {})

        def distance_to_route(item: tuple[int, List[str]]) -> float:
            _, route = item
            active_stops = route[1:-1]
            if not active_stops:
                return 1e18
            return min(
                min(self._euclidean(pickup_node, nodes.get(str(stop), {})), self._euclidean(dropoff_node, nodes.get(str(stop), {})))
                for stop in active_stops
            )

        ranked = sorted(list(enumerate(routes)), key=lambda item: (distance_to_route(item), len(item[1])))
        return ranked[:self._route_shortlist]

    def _euclidean(self, left: Dict[str, Any], right: Dict[str, Any]) -> float:
        return ((float(left.get("x", 0.0)) - float(right.get("x", 0.0))) ** 2 + (float(left.get("y", 0.0)) - float(right.get("y", 0.0))) ** 2) ** 0.5

    def _distance(self, instance: Dict[str, Any], routes: List[List[str]]) -> float:
        return float(check_solution(instance, _solution(routes, "academic-global-consolidation")).get("totalDistance", 0.0))

    def _move(self,
              route_index: int,
              before_metrics: Dict[str, Any],
              after_metrics: Dict[str, Any],
              removed_stop_count: int,
              inserted_stop_count: int,
              feasible: bool,
              accepted: bool,
              reject_reason: str | None) -> ConsolidationMove:
        return ConsolidationMove(
            operator=self.name,
            route_index=route_index,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(after_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=removed_stop_count,
            inserted_stop_count=inserted_stop_count,
            feasible=feasible,
            accepted=accepted,
            reject_reason=reject_reason,
        )


class IntraRouteRelocateImprovementOperator:
    name = "intra-route-relocate-improvement"

    def __init__(self, max_routes: int = 80, max_route_stops: int = 80, max_attempts: int = 160) -> None:
        self._max_routes = max_routes
        self._max_route_stops = max_route_stops
        self._max_attempts = max_attempts

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        solver = "academic-global-consolidation"
        current_routes = [route[:] for route in routes]
        attempts = 0
        route_priorities = sorted(
            range(len(current_routes)),
            key=lambda index: route_distance(instance, current_routes[index]),
            reverse=True,
        )[:self._max_routes]
        for route_index in route_priorities:
            if attempts >= self._max_attempts:
                break
            route = current_routes[route_index]
            if len(route) <= 4 or len(route) > self._max_route_stops + 2:
                continue
            before_solution = _solution(current_routes, solver)
            before_metrics = check_solution(instance, before_solution)
            candidate_route = self._best_route_relocation(instance, route, before_metrics)
            attempts += 1
            if candidate_route is None:
                moves.append(self._move(route_index, before_metrics, before_metrics, 0, 0, True, False, "no-improving-relocation"))
                continue
            candidate_routes = [candidate[:] for candidate in current_routes]
            candidate_routes[route_index] = candidate_route
            after_metrics = check_solution(instance, _solution(candidate_routes, solver))
            accepted = _is_better(before_metrics, after_metrics)
            moves.append(self._move(route_index, before_metrics, after_metrics, 1, 1, bool(after_metrics.get("feasible")), accepted, None if accepted else "not-better"))
            if accepted:
                current_routes = candidate_routes
        return current_routes, moves

    def _best_route_relocation(self, instance: Dict[str, Any], route: List[str], before_metrics: Dict[str, Any]) -> List[str] | None:
        if instance.get("problemType") == "PDPTW":
            return self._best_pair_relocation(instance, route, before_metrics)
        return self._best_single_stop_relocation(instance, route, before_metrics)

    def _best_single_stop_relocation(self, instance: Dict[str, Any], route: List[str], before_metrics: Dict[str, Any]) -> List[str] | None:
        best_route: List[str] | None = None
        best_distance = float(before_metrics.get("totalDistance", 1e18))
        for source_index in range(1, len(route) - 1):
            stop = route[source_index]
            reduced = route[:source_index] + route[source_index + 1:]
            for insert_index in range(1, len(reduced)):
                if insert_index == source_index:
                    continue
                candidate = reduced[:insert_index] + [stop] + reduced[insert_index:]
                distance = route_distance(instance, candidate)
                if distance + 1e-9 >= best_distance:
                    continue
                checked = check_solution(instance, _solution([candidate], "academic-global-consolidation"))
                if checked.get("feasible"):
                    best_distance = distance
                    best_route = candidate
        return best_route

    def _best_pair_relocation(self, instance: Dict[str, Any], route: List[str], before_metrics: Dict[str, Any]) -> List[str] | None:
        best_route: List[str] | None = None
        best_distance = float(before_metrics.get("totalDistance", 1e18))
        for pickup, dropoff in self._request_pairs_in_route(instance, route):
            pickup_index = route.index(pickup)
            dropoff_index = route.index(dropoff)
            if pickup_index >= dropoff_index:
                continue
            reduced = [stop for index, stop in enumerate(route) if index not in {pickup_index, dropoff_index}]
            for pickup_insert in range(1, len(reduced)):
                with_pickup = reduced[:pickup_insert] + [pickup] + reduced[pickup_insert:]
                for dropoff_insert in range(pickup_insert + 1, len(with_pickup)):
                    candidate = with_pickup[:dropoff_insert] + [dropoff] + with_pickup[dropoff_insert:]
                    distance = route_distance(instance, candidate)
                    if distance + 1e-9 >= best_distance:
                        continue
                    checked = check_solution(instance, _solution([candidate], "academic-global-consolidation"))
                    if checked.get("feasible"):
                        best_distance = distance
                        best_route = candidate
        return best_route

    def _request_pairs_in_route(self, instance: Dict[str, Any], route: List[str]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [
            (str(request["pickupNodeId"]), str(request["dropoffNodeId"]))
            for request in instance.get("requests", [])
            if str(request["pickupNodeId"]) in route_set and str(request["dropoffNodeId"]) in route_set
        ]

    def _move(self,
              route_index: int,
              before_metrics: Dict[str, Any],
              after_metrics: Dict[str, Any],
              removed_stop_count: int,
              inserted_stop_count: int,
              feasible: bool,
              accepted: bool,
              reject_reason: str | None) -> ConsolidationMove:
        return ConsolidationMove(
            operator=self.name,
            route_index=route_index,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(after_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=removed_stop_count,
            inserted_stop_count=inserted_stop_count,
            feasible=feasible,
            accepted=accepted,
            reject_reason=reject_reason,
        )


class CrossRoutePairRelocateImprovementOperator:
    name = "cross-route-pair-relocate-improvement"

    def __init__(self, max_source_routes: int = 40, max_target_routes: int = 8, max_attempts: int = 80, max_candidate_checks_per_pair: int = 96) -> None:
        self._max_source_routes = max_source_routes
        self._max_target_routes = max_target_routes
        self._max_attempts = max_attempts
        self._max_candidate_checks_per_pair = max_candidate_checks_per_pair

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if instance.get("problemType") != "PDPTW" or len(routes) < 2:
            return routes, moves
        solver = "academic-global-consolidation"
        current_routes = [route[:] for route in routes]
        request_pairs = self._request_pairs(instance)
        source_priorities = sorted(
            range(len(current_routes)),
            key=lambda index: route_distance(instance, current_routes[index]),
            reverse=True,
        )[:self._max_source_routes]
        attempts = 0
        for source_index in source_priorities:
            if attempts >= self._max_attempts:
                break
            pairs = self._pairs_in_route(current_routes[source_index], request_pairs)
            for pickup, dropoff in pairs:
                if attempts >= self._max_attempts:
                    break
                before_metrics = check_solution(instance, _solution(current_routes, solver))
                candidate = self._best_pair_move(instance, current_routes, source_index, pickup, dropoff, before_metrics)
                attempts += 1
                if candidate is None:
                    moves.append(self._move(source_index, before_metrics, before_metrics, 2, 0, True, False, "no-improving-cross-route-pair-move"))
                    continue
                after_metrics = check_solution(instance, _solution(candidate, solver))
                accepted = _is_better(before_metrics, after_metrics)
                moves.append(self._move(source_index, before_metrics, after_metrics, 2, 2, bool(after_metrics.get("feasible")), accepted, None if accepted else "not-better"))
                if accepted:
                    current_routes = candidate
                    break
        return current_routes, moves

    def _best_pair_move(
        self,
        instance: Dict[str, Any],
        routes: List[List[str]],
        source_index: int,
        pickup: str,
        dropoff: str,
        before_metrics: Dict[str, Any],
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
        best_key = (int(before_metrics.get("vehicleCount", 10**9)), float(before_metrics.get("totalDistance", 1e18)))
        source_before_distance = route_distance(instance, source_route)
        source_after_distance = route_distance(instance, reduced_source) if len(reduced_source) > 2 else 0.0
        checked_candidates = 0
        for target_index in self._target_routes(instance, routes, source_index, pickup, dropoff):
            target_route = routes[target_index]
            target_before_distance = route_distance(instance, target_route)
            for pickup_insert in range(1, len(target_route)):
                with_pickup = target_route[:pickup_insert] + [pickup] + target_route[pickup_insert:]
                for dropoff_insert in range(pickup_insert + 1, len(with_pickup)):
                    if checked_candidates >= self._max_candidate_checks_per_pair:
                        return best_routes
                    moved_target = with_pickup[:dropoff_insert] + [dropoff] + with_pickup[dropoff_insert:]
                    moved_target_distance = route_distance(instance, moved_target)
                    candidate_vehicle_count = len(routes) - (1 if len(reduced_source) <= 2 else 0)
                    candidate_distance = (
                        float(before_metrics.get("totalDistance", 1e18))
                        - source_before_distance
                        - target_before_distance
                        + source_after_distance
                        + moved_target_distance
                    )
                    if (candidate_vehicle_count, candidate_distance) >= best_key:
                        continue
                    candidate_routes = []
                    for index, route in enumerate(routes):
                        if index == source_index:
                            if len(reduced_source) > 2:
                                candidate_routes.append(reduced_source)
                        elif index == target_index:
                            candidate_routes.append(moved_target)
                        else:
                            candidate_routes.append(route[:])
                    checked_candidates += 1
                    checked = check_solution(instance, _solution(candidate_routes, "academic-global-consolidation"))
                    if not checked.get("feasible"):
                        continue
                    candidate_key = (int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18)))
                    if candidate_key < best_key:
                        best_key = candidate_key
                        best_routes = candidate_routes
        return best_routes

    def _target_routes(self, instance: Dict[str, Any], routes: List[List[str]], source_index: int, pickup: str, dropoff: str) -> List[int]:
        nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
        pickup_node = nodes.get(pickup, {})
        dropoff_node = nodes.get(dropoff, {})

        def route_affinity(item: tuple[int, List[str]]) -> float:
            index, route = item
            if index == source_index:
                return 1e18
            active_stops = route[1:-1]
            if not active_stops:
                return 1e18
            return min(
                min(self._euclidean(pickup_node, nodes.get(str(stop), {})), self._euclidean(dropoff_node, nodes.get(str(stop), {})))
                for stop in active_stops
            )

        ranked = sorted(enumerate(routes), key=route_affinity)
        return [index for index, _ in ranked if index != source_index][:self._max_target_routes]

    def _request_pairs(self, instance: Dict[str, Any]) -> List[tuple[str, str]]:
        return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]

    def _pairs_in_route(self, route: List[str], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [(pickup, dropoff) for pickup, dropoff in request_pairs if pickup in route_set and dropoff in route_set]

    def _euclidean(self, left: Dict[str, Any], right: Dict[str, Any]) -> float:
        return ((float(left.get("x", 0.0)) - float(right.get("x", 0.0))) ** 2 + (float(left.get("y", 0.0)) - float(right.get("y", 0.0))) ** 2) ** 0.5

    def _move(self,
              route_index: int,
              before_metrics: Dict[str, Any],
              after_metrics: Dict[str, Any],
              removed_stop_count: int,
              inserted_stop_count: int,
              feasible: bool,
              accepted: bool,
              reject_reason: str | None) -> ConsolidationMove:
        return ConsolidationMove(
            operator=self.name,
            route_index=route_index,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(after_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=removed_stop_count,
            inserted_stop_count=inserted_stop_count,
            feasible=feasible,
            accepted=accepted,
            reject_reason=reject_reason,
        )


class PairEjectionChainOperator:
    name = "pair-ejection-chain"

    def __init__(
        self,
        max_removed_pairs: int = 8,
        max_runtime_ms: int = 1_500,
        max_states: int = 96,
        beam_width: int = 16,
        max_depth: int = 2,
        max_candidate_checks: int = 512,
    ) -> None:
        self._max_removed_pairs = max_removed_pairs
        self._max_runtime_ms = max_runtime_ms
        self._max_states = max_states
        self._beam_width = beam_width
        self._max_depth = max_depth
        self._max_candidate_checks = max_candidate_checks

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if instance.get("problemType") != "PDPTW" or len(routes) < 2:
            return routes, moves
        started = time.perf_counter()
        request_pairs = self._request_pairs(instance)
        current_routes = [route[:] for route in routes]
        before_metrics = check_solution(instance, _solution(current_routes, "academic-global-consolidation"))
        priorities = [index for index in sorted(
            range(len(current_routes)),
            key=lambda index: (len(self._pairs_in_route(current_routes[index], request_pairs)), route_distance(instance, current_routes[index])),
        ) if 0 < len(self._pairs_in_route(current_routes[index], request_pairs)) <= self._max_removed_pairs]
        states_expanded = 0
        candidate_checks = 0
        direct_insertions = 0
        ejection_insertions = 0
        depth_used = 0
        dead_end_pruned = 0
        best_uninserted_pair_option_count: int | None = None
        reject_reason = "no-small-pair-route-for-ejection"
        best_routes: List[List[str]] | None = None
        best_metrics = before_metrics
        for route_index in priorities:
            if self._elapsed_ms(started) >= self._max_runtime_ms or states_expanded >= self._max_states:
                reject_reason = "ejection-budget-exhausted"
                break
            partial_routes = [route[:] for index, route in enumerate(current_routes) if index != route_index]
            removed_pairs = self._hardest_pairs_first(instance, partial_routes, self._pairs_in_route(current_routes[route_index], request_pairs))
            candidate, stats = self._repair_pairs(instance, partial_routes, removed_pairs, started)
            states_expanded += int(stats.get("statesExpanded", 0))
            candidate_checks += int(stats.get("candidateChecks", 0))
            direct_insertions += int(stats.get("directInsertions", 0))
            ejection_insertions += int(stats.get("ejectionInsertions", 0))
            depth_used = max(depth_used, int(stats.get("ejectionDepthUsed", 0)))
            dead_end_pruned += int(stats.get("deadEndPruned", 0))
            option_count = stats.get("bestUninsertedPairOptionCount")
            if option_count is not None:
                best_uninserted_pair_option_count = int(option_count) if best_uninserted_pair_option_count is None else min(best_uninserted_pair_option_count, int(option_count))
            if candidate is None:
                reject_reason = str(stats.get("rejectReason", "ejection-repair-failed"))
                continue
            checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
            if _is_better(best_metrics, checked):
                best_routes = candidate
                best_metrics = checked
                break
        accepted = best_routes is not None and _is_better(before_metrics, best_metrics)
        metadata = {
            "ejectionDepthUsed": depth_used,
            "statesExpanded": states_expanded,
            "candidateChecks": candidate_checks,
            "directInsertions": direct_insertions,
            "ejectionInsertions": ejection_insertions,
            "deadEndPruned": dead_end_pruned,
            "bestUninsertedPairOptionCount": best_uninserted_pair_option_count,
            "rejectReason": None if accepted else reject_reason,
        }
        moves.append(ConsolidationMove(
            operator=self.name,
            route_index=-1,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(best_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=0,
            inserted_stop_count=0,
            feasible=bool(best_metrics.get("feasible")),
            accepted=accepted,
            reject_reason=None if accepted else reject_reason,
            metadata=metadata,
        ))
        return (best_routes if accepted and best_routes is not None else current_routes), moves

    def _repair_pairs(self, instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]], started: float) -> tuple[List[List[str]] | None, Dict[str, Any]]:
        states: List[tuple[List[List[str]], List[tuple[str, str]], int]] = [(routes, pairs[:], 0)]
        states_expanded = candidate_checks = direct_insertions = ejection_insertions = depth_used = dead_end_pruned = 0
        best_uninserted_pair_option_count: int | None = None
        best_complete: List[List[str]] | None = None
        while states and states_expanded < self._max_states and candidate_checks < self._max_candidate_checks and self._elapsed_ms(started) < self._max_runtime_ms:
            current_routes, pending, depth = states.pop(0)
            states_expanded += 1
            if not pending:
                checked = check_solution(instance, _solution(current_routes, "academic-global-consolidation"))
                if checked.get("feasible"):
                    if best_complete is None or (int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18))) < self._candidate_key(instance, best_complete):
                        best_complete = current_routes
                continue
            pair = pending[0]
            rest = pending[1:]
            remaining_checks = max(1, self._max_candidate_checks - candidate_checks)
            index = PairInsertionIndex.build(instance, current_routes, max_candidate_checks=remaining_checks, max_routes=16, max_positions_per_route=48)
            options = index.options_for_pair(pair, top_k=self._beam_width)
            candidate_checks += index.candidate_checks
            next_states: List[tuple[List[List[str]], List[tuple[str, str]], int]] = []
            for option in options[:self._beam_width]:
                direct_insertions += 1
                next_states.append((_apply_pair_insertion(current_routes, option), rest, depth))
            if depth < self._max_depth and candidate_checks < self._max_candidate_checks:
                ejected, ejection_checks = self._ejection_states(instance, current_routes, pair, rest, depth + 1, self._max_candidate_checks - candidate_checks, started)
                candidate_checks += ejection_checks
                ejection_insertions += len(ejected)
                depth_used = max(depth_used, depth + 1 if ejected else depth_used)
                next_states.extend(ejected[:self._beam_width])
            if not next_states:
                dead_end_pruned += 1
            if next_states:
                for candidate_routes, remaining, _ in next_states[: min(4, self._beam_width)]:
                    option_count = self._best_uninserted_option_count(instance, candidate_routes, remaining)
                    if option_count is not None:
                        best_uninserted_pair_option_count = option_count if best_uninserted_pair_option_count is None else min(best_uninserted_pair_option_count, option_count)
            states.extend(next_states)
            states.sort(key=lambda state: self._state_score(instance, state[0], state[1]))
            states = states[:self._beam_width]
        return best_complete, {
            "statesExpanded": states_expanded,
            "candidateChecks": candidate_checks,
            "directInsertions": direct_insertions,
            "ejectionInsertions": ejection_insertions,
            "ejectionDepthUsed": depth_used,
            "deadEndPruned": dead_end_pruned,
            "bestUninsertedPairOptionCount": best_uninserted_pair_option_count,
            "rejectReason": "ejection-budget-exhausted" if states_expanded >= self._max_states or candidate_checks >= self._max_candidate_checks else "ejection-no-feasible-repair",
        }

    def _hardest_pairs_first(self, instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        stats: Dict[tuple[str, str], tuple[int, int, float, float, float]] = {}
        for pair in pairs:
            index = PairInsertionIndex.build(instance, routes, max_candidate_checks=min(384, self._max_candidate_checks), max_routes=16, max_positions_per_route=24)
            options = index.options_for_pair(pair, top_k=16)
            feasible_routes = len({option.route_index for option in options})
            option_count = len(options)
            best = options[0].delta_distance if options else 1e9
            second = options[1].delta_distance if len(options) > 1 else best + 1e6
            regret = second - best
            slack = max((option.slack_after for option in options), default=-1e9)
            stats[pair] = (0 if option_count == 0 else 1, feasible_routes, -regret, slack, -self._pair_direct_distance(instance, pair))
        return sorted(pairs, key=lambda pair: stats[pair])

    def _state_score(self, instance: Dict[str, Any], routes: List[List[str]], pending: List[tuple[str, str]]) -> tuple[int, int, int, float, int]:
        blocked = 0
        min_options = 10**9
        for pair in pending[:3]:
            index = PairInsertionIndex.build(instance, routes, max_candidate_checks=24, max_routes=4, max_positions_per_route=6)
            option_count = len(index.options_for_pair(pair, top_k=4))
            if option_count == 0:
                blocked += 1
            min_options = min(min_options, option_count)
        if min_options == 10**9:
            min_options = 99
        return (blocked, -min_options, len(routes), self._distance(instance, routes), len(pending))

    def _best_uninserted_option_count(self, instance: Dict[str, Any], routes: List[List[str]], pending: List[tuple[str, str]]) -> int | None:
        if not pending:
            return None
        counts = []
        for pair in pending[:3]:
            index = PairInsertionIndex.build(instance, routes, max_candidate_checks=24, max_routes=4, max_positions_per_route=6)
            counts.append(len(index.options_for_pair(pair, top_k=4)))
        return min(counts) if counts else None

    def _ejection_states(self, instance: Dict[str, Any], routes: List[List[str]], pair: tuple[str, str], rest: List[tuple[str, str]], depth: int, max_candidate_checks: int, started: float) -> tuple[List[tuple[List[List[str]], List[tuple[str, str]], int]], int]:
        states: List[tuple[List[List[str]], List[tuple[str, str]], int]] = []
        candidate_checks = 0
        route_pairs = self._request_pairs(instance)
        for route_index, route in sorted(enumerate(routes), key=lambda item: route_distance(instance, item[1]), reverse=True)[:8]:
            for ejected_pair in self._pairs_in_route(route, route_pairs)[:4]:
                if candidate_checks >= max_candidate_checks or self._elapsed_ms(started) >= self._max_runtime_ms:
                    break
                reduced_route = [stop for stop in route if stop not in set(ejected_pair)]
                if not _route_is_feasible(instance, reduced_route)[0]:
                    continue
                reduced_routes = [candidate[:] for candidate in routes]
                reduced_routes[route_index] = reduced_route
                index = PairInsertionIndex.build(instance, reduced_routes, max_candidate_checks=min(96, max_candidate_checks - candidate_checks), max_routes=8, max_positions_per_route=24)
                for option in index.options_for_pair(pair, top_k=4):
                    candidate = _apply_pair_insertion(reduced_routes, option)
                    states.append((candidate, [ejected_pair] + rest, depth))
                candidate_checks += index.candidate_checks
            if candidate_checks >= max_candidate_checks or self._elapsed_ms(started) >= self._max_runtime_ms:
                break
        states.sort(key=lambda state: (len(state[0]), self._distance(instance, state[0]), len(state[1])))
        return states, candidate_checks

    def _request_pairs(self, instance: Dict[str, Any]) -> List[tuple[str, str]]:
        return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]

    def _pairs_in_route(self, route: List[str], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [(pickup, dropoff) for pickup, dropoff in request_pairs if pickup in route_set and dropoff in route_set]

    def _pair_direct_distance(self, instance: Dict[str, Any], pair: tuple[str, str]) -> float:
        return route_distance(instance, [pair[0], pair[1]])

    def _distance(self, instance: Dict[str, Any], routes: List[List[str]]) -> float:
        return sum(route_distance(instance, route) for route in routes)

    def _candidate_key(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[int, float]:
        checked = check_solution(instance, _solution(routes, "academic-global-consolidation"))
        return int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18))

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)


class MultiRouteDestroyRepairOperator:
    name = "multi-route-destroy-repair"

    def __init__(
        self,
        max_runtime_ms: int = 2_200,
        max_neighbor_routes: int = 3,
        max_removed_pairs: int = 18,
        beam_width: int = 24,
        max_states: int = 1_200,
        ejection_depth: int = 3,
        max_candidate_checks: int = 8_000,
    ) -> None:
        self._max_runtime_ms = max_runtime_ms
        self._max_neighbor_routes = max_neighbor_routes
        self._max_removed_pairs = max_removed_pairs
        self._beam_width = beam_width
        self._max_states = max_states
        self._ejection_depth = ejection_depth
        self._max_candidate_checks = max_candidate_checks
        self._repair = PairEjectionChainOperator(
            max_removed_pairs=max_removed_pairs,
            max_runtime_ms=max_runtime_ms,
            max_states=max_states,
            beam_width=beam_width,
            max_depth=ejection_depth,
            max_candidate_checks=max_candidate_checks,
        )

    def apply(self, instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[List[str]], List[ConsolidationMove]]:
        moves: List[ConsolidationMove] = []
        if instance.get("problemType") != "PDPTW" or len(routes) < 2:
            return routes, moves
        started = time.perf_counter()
        current_routes = [route[:] for route in routes]
        request_pairs = self._request_pairs(instance)
        before_metrics = check_solution(instance, _solution(current_routes, "academic-global-consolidation"))
        best_routes: List[List[str]] | None = None
        best_metrics = before_metrics
        metadata: Dict[str, Any] = {
            "weakRouteIndex": None,
            "destroyedRouteCount": 0,
            "removedPairCount": 0,
            "relatedPairCount": 0,
            "directStatesGenerated": 0,
            "ejectionStatesGenerated": 0,
            "statesExpanded": 0,
            "deadEndPruned": 0,
            "bestUninsertedPairOptionCount": None,
            "rejectReasons": {},
        }
        weak_routes = [index for index in sorted(
            range(len(current_routes)),
            key=lambda index: (len(self._pairs_in_route(current_routes[index], request_pairs)), route_distance(instance, current_routes[index])),
        ) if self._pairs_in_route(current_routes[index], request_pairs)]
        reject_reason = "no-destroy-candidate"
        for weak_route_index in weak_routes:
            if self._elapsed_ms(started) >= self._max_runtime_ms:
                reject_reason = "multi-route-budget-exhausted"
                break
            base_pairs = self._pairs_in_route(current_routes[weak_route_index], request_pairs)
            if not base_pairs or len(base_pairs) > self._max_removed_pairs:
                continue
            related = self._related_pairs(instance, current_routes, weak_route_index, base_pairs, request_pairs)
            removed_pairs = (base_pairs + related)[:self._max_removed_pairs]
            removed_set = {stop for pair in removed_pairs for stop in pair}
            partial_routes = []
            destroyed_indexes = set()
            for route_index, route in enumerate(current_routes):
                reduced_route = [stop for stop in route if stop not in removed_set]
                if route_index == weak_route_index or reduced_route != route:
                    destroyed_indexes.add(route_index)
                if len(reduced_route) > 2:
                    partial_routes.append(reduced_route)
            depot = str(instance.get("depotNodeId", "0"))
            target_route_count = max(1, len(current_routes) - 1)
            while len(partial_routes) < target_route_count:
                partial_routes.append([depot, depot])
            if len(partial_routes) >= len(current_routes):
                continue
            ordered_pairs = self._repair._hardest_pairs_first(instance, partial_routes, removed_pairs)
            candidate, stats = self._repair._repair_pairs(instance, partial_routes, ordered_pairs, started)
            metadata["weakRouteIndex"] = weak_route_index
            metadata["destroyedRouteCount"] = max(int(metadata["destroyedRouteCount"]), len(destroyed_indexes))
            metadata["removedPairCount"] = max(int(metadata["removedPairCount"]), len(removed_pairs))
            metadata["relatedPairCount"] = max(int(metadata["relatedPairCount"]), len(related))
            metadata["directStatesGenerated"] = int(metadata["directStatesGenerated"]) + int(stats.get("directInsertions", 0))
            metadata["ejectionStatesGenerated"] = int(metadata["ejectionStatesGenerated"]) + int(stats.get("ejectionInsertions", 0))
            metadata["statesExpanded"] = int(metadata["statesExpanded"]) + int(stats.get("statesExpanded", 0))
            metadata["deadEndPruned"] = int(metadata["deadEndPruned"]) + int(stats.get("deadEndPruned", 0))
            option_count = stats.get("bestUninsertedPairOptionCount")
            if option_count is not None:
                metadata["bestUninsertedPairOptionCount"] = int(option_count) if metadata["bestUninsertedPairOptionCount"] is None else min(int(metadata["bestUninsertedPairOptionCount"]), int(option_count))
            if candidate is None:
                reject_reason = str(stats.get("rejectReason", "multi-route-repair-failed"))
                reject_reasons = metadata["rejectReasons"]
                reject_reasons[reject_reason] = reject_reasons.get(reject_reason, 0) + 1
                continue
            checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
            if _is_better(best_metrics, checked):
                best_routes = candidate
                best_metrics = checked
                break
            reject_reason = "multi-route-not-better"
            reject_reasons = metadata["rejectReasons"]
            reject_reasons[reject_reason] = reject_reasons.get(reject_reason, 0) + 1
        accepted = best_routes is not None and _is_better(before_metrics, best_metrics)
        moves.append(ConsolidationMove(
            operator=self.name,
            route_index=int(metadata["weakRouteIndex"]) if metadata["weakRouteIndex"] is not None else -1,
            before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
            after_vehicle_count=int(best_metrics.get("vehicleCount", before_metrics.get("vehicleCount", 0))),
            removed_stop_count=int(metadata["removedPairCount"]) * 2,
            inserted_stop_count=int(metadata["removedPairCount"]) * 2 if accepted else 0,
            feasible=bool(best_metrics.get("feasible")),
            accepted=accepted,
            reject_reason=None if accepted else reject_reason,
            metadata=metadata,
        ))
        return (best_routes if accepted and best_routes is not None else current_routes), moves

    def _related_pairs(self, instance: Dict[str, Any], routes: List[List[str]], weak_route_index: int, base_pairs: List[tuple[str, str]], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        base_set = set(base_pairs)
        candidates: List[tuple[float, tuple[str, str]]] = []
        for route_index, route in enumerate(routes):
            if route_index == weak_route_index:
                continue
            route_pairs = self._pairs_in_route(route, request_pairs)
            if not route_pairs:
                continue
            for pair in route_pairs:
                if pair in base_set:
                    continue
                candidates.append((self._relatedness(instance, base_pairs, pair), pair))
        candidates.sort(key=lambda item: item[0])
        limit = max(0, self._max_removed_pairs - len(base_pairs))
        return [pair for _, pair in candidates[: max(limit, self._max_neighbor_routes)]] [:limit]

    def _relatedness(self, instance: Dict[str, Any], base_pairs: List[tuple[str, str]], pair: tuple[str, str]) -> float:
        nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
        pickup = nodes.get(pair[0], {})
        dropoff = nodes.get(pair[1], {})
        best = 1e18
        for base_pickup_id, base_dropoff_id in base_pairs:
            base_pickup = nodes.get(base_pickup_id, {})
            base_dropoff = nodes.get(base_dropoff_id, {})
            proximity = _euclidean(pickup, base_pickup) + _euclidean(dropoff, base_dropoff)
            ready_gap = abs(float(pickup.get("readyTime", 0.0)) - float(base_pickup.get("readyTime", 0.0)))
            due_gap = abs(float(dropoff.get("dueTime", 0.0)) - float(base_dropoff.get("dueTime", 0.0)))
            best = min(best, proximity + 0.01 * ready_gap + 0.01 * due_gap)
        return best

    def _request_pairs(self, instance: Dict[str, Any]) -> List[tuple[str, str]]:
        return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]

    def _pairs_in_route(self, route: List[str], request_pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
        route_set = set(route)
        return [(pickup, dropoff) for pickup, dropoff in request_pairs if pickup in route_set and dropoff in route_set]

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)


class GlobalRouteConsolidator:
    def __init__(self, operators: List[ConsolidationOperator] | None = None, max_nodes: int = 250, alns_repair_max_runtime_ms: int = 1_500) -> None:
        self._operators = operators or [IntraRouteRelocateImprovementOperator(), CrossRoutePairRelocateImprovementOperator(), PairAwareRouteEliminationOperator(), ContiguousBlockRouteEliminationOperator(max_removed_stops=4, max_attempts=24), RouteEliminationOperator(max_removed_stops=4, max_attempts=36)]
        self._max_nodes = max_nodes
        self._alns_repair_max_runtime_ms = alns_repair_max_runtime_ms

    def consolidate(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> ConsolidationResult:
        before_metrics = check_solution(instance, solution)
        if not before_metrics.get("feasible"):
            return ConsolidationResult(solution, before_metrics, before_metrics, ConsolidationTrace())
        if len(instance.get("nodes", [])) > self._max_nodes:
            trace = ConsolidationTrace(
                operator_attempts=1,
                accepted_moves=0,
                rejected_moves=1,
                moves=[
                    ConsolidationMove(
                        operator="route-elimination",
                        route_index=-1,
                        before_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
                        after_vehicle_count=int(before_metrics.get("vehicleCount", 0)),
                        removed_stop_count=0,
                        inserted_stop_count=0,
                        feasible=True,
                        accepted=False,
                        reject_reason="instance-too-large-for-v1",
                    )
                ],
            )
            skipped_solution = dict(solution)
            skipped_solution["globalConsolidation"] = ConsolidationResult(skipped_solution, before_metrics, before_metrics, trace).to_dict()
            return ConsolidationResult(skipped_solution, before_metrics, before_metrics, trace)
        routes = _active_routes(solution)
        all_moves: List[ConsolidationMove] = []
        for operator in self._operators:
            routes, moves = operator.apply(instance, routes)
            all_moves.extend(moves)
        consolidated_solution = dict(solution)
        consolidated_solution["routes"] = routes
        after_metrics = check_solution(instance, consolidated_solution)
        if after_metrics.get("feasible") and instance.get("problemType") == "PDPTW" and self._alns_repair_max_runtime_ms >= 50:
            alns_result = BoundedALNSRepair(ALNSRepairConfig(max_runtime_ms=self._alns_repair_max_runtime_ms)).repair(instance, consolidated_solution)
            if _is_better(after_metrics, alns_result.after_metrics):
                consolidated_solution = alns_result.solution
                routes = [[str(stop) for stop in route] for route in consolidated_solution.get("routes", []) if len(route) > 2]
                after_metrics = alns_result.after_metrics
        if not _is_better(before_metrics, after_metrics):
            consolidated_solution = solution
            after_metrics = before_metrics
        trace = ConsolidationTrace(
            operator_attempts=len(all_moves),
            accepted_moves=sum(1 for move in all_moves if move.accepted),
            rejected_moves=sum(1 for move in all_moves if not move.accepted),
            moves=all_moves,
        )
        consolidated_solution["globalConsolidation"] = ConsolidationResult(consolidated_solution, before_metrics, after_metrics, trace).to_dict()
        return ConsolidationResult(consolidated_solution, before_metrics, after_metrics, trace)


