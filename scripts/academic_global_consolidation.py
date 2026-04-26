from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

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


class GlobalRouteConsolidator:
    def __init__(self, operators: List[ConsolidationOperator] | None = None, max_nodes: int = 50) -> None:
        self._operators = operators or [RouteEliminationOperator()]
        self._max_nodes = max_nodes

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
