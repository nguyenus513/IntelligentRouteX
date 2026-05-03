from __future__ import annotations

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

    def __init__(self, max_removed_pairs: int = 12, max_attempts: int = 120, route_shortlist: int = 18, beam_width: int = 8) -> None:
        self._max_removed_pairs = max_removed_pairs
        self._max_attempts = max_attempts
        self._route_shortlist = route_shortlist
        self._beam_width = beam_width

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
        scored: List[tuple[tuple[int, float], tuple[str, str]]] = []
        for pickup, dropoff in route_pairs:
            insertions = self._pair_insertion_costs(instance, routes, pickup, dropoff, limit=2)
            if not insertions:
                scored.append(((10**9, 1e18), (pickup, dropoff)))
                continue
            regret = insertions[1] - insertions[0] if len(insertions) > 1 else insertions[0]
            scored.append(((-len(insertions), -regret), (pickup, dropoff)))
        scored.sort(key=lambda item: item[0])
        return [pair for _, pair in scored]

    def _pair_insertion_costs(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str, limit: int) -> List[float]:
        costs: List[float] = []
        baseline_distance = self._distance(instance, routes)
        for route_index, route in self._ranked_receiver_routes(instance, routes, pickup, dropoff):
            for pickup_position in range(1, len(route)):
                for dropoff_position in range(pickup_position + 1, len(route) + 1):
                    candidate = [item[:] for item in routes]
                    candidate_route = route[:pickup_position] + [pickup] + route[pickup_position:dropoff_position] + [dropoff] + route[dropoff_position:]
                    candidate[route_index] = candidate_route
                    checked = check_solution(instance, _solution(candidate, "academic-global-consolidation"))
                    if checked.get("feasible"):
                        costs.append(float(checked.get("totalDistance", 0.0)) - baseline_distance)
        costs.sort()
        return costs[:limit]

    def _insert_pair_candidates(self, instance: Dict[str, Any], routes: List[List[str]], pickup: str, dropoff: str) -> List[List[List[str]]]:
        feasible: List[tuple[float, List[List[str]]]] = []
        baseline_distance = self._distance(instance, routes)
        for route_index, route in self._ranked_receiver_routes(instance, routes, pickup, dropoff):
            for pickup_position in range(1, len(route)):
                for dropoff_position in range(pickup_position + 1, len(route) + 1):
                    candidate = [item[:] for item in routes]
                    candidate_route = route[:pickup_position] + [pickup] + route[pickup_position:dropoff_position] + [dropoff] + route[dropoff_position:]
                    candidate[route_index] = candidate_route
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


