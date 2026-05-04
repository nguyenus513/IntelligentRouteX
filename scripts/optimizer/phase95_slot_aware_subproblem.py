from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from external_benchmark_support import check_solution
from optimizer.phase85_pair_utils import extract_request_pairs, remove_pair_from_route, request_id, solution_signature
from optimizer.phase87_insertion_index import InsertionIndex


@dataclass(frozen=True)
class SlotAwareSubproblemConfig:
    mode: str
    availableRouteSlots: int
    maxSubproblemRoutes: int
    affectedRouteCount: int
    selectedRequestCount: int
    allowNewRoutes: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_slot_aware_config(mode: str, affected_route_count: int, selected_request_count: int) -> SlotAwareSubproblemConfig:
    affected_route_count = max(1, int(affected_route_count))
    if mode == "slot-compression" and affected_route_count > 1:
        max_routes = affected_route_count - 1
    else:
        mode = "same-slot-polish"
        max_routes = affected_route_count
    return SlotAwareSubproblemConfig(mode, affected_route_count, max_routes, affected_route_count, selected_request_count, False)


class SlotAwareSubproblemBuilder:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.lastTelemetry: Dict[str, Any] = {}

    def build_incumbent(self, subproblem: Dict[str, Any], config: SlotAwareSubproblemConfig) -> Dict[str, Any] | None:
        depot = str(subproblem.get("depotNodeId", "0"))
        requests = sorted(subproblem.get("requests", []), key=lambda request: (self._due_key(subproblem, request), request_id(request)))
        routes = [[depot, depot] for _ in range(max(1, config.maxSubproblemRoutes))]
        self.lastTelemetry = {"slotAwareConstructionBlocked": False, "incumbentSubproblemRouteCount": 0}
        for request in requests:
            best = None
            best_key = None
            for route_index, route in enumerate(routes):
                for option in self.index.enumerate_options(subproblem, route, request, top_k=4):
                    attempt = [list(item) for item in routes]
                    attempt[route_index] = option["route"]
                    checked = check_solution(subproblem, {"routes": [item for item in attempt if len(item) > 2]})
                    key = (0 if checked.get("feasible") else 1, option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": attempt}))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = attempt
            if best is None:
                self.lastTelemetry["slotAwareConstructionBlocked"] = True
                return None
            routes = best
        solution = {"routes": [route for route in routes if len(route) > 2]}
        self.lastTelemetry["incumbentSubproblemRouteCount"] = len(solution["routes"])
        return solution

    def compress_to_slots(self, subproblem: Dict[str, Any], solution: Dict[str, Any], max_routes: int) -> Dict[str, Any] | None:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
        self.lastTelemetry["slotCompressionAttempts"] = int(self.lastTelemetry.get("slotCompressionAttempts", 0) or 0) + 1
        if len(routes) <= max_routes:
            self.lastTelemetry["slotCompressionSuccess"] = True
            return {"routes": routes}
        pairs = extract_request_pairs(subproblem, {"routes": routes})
        while len(routes) > max_routes:
            route_infos = []
            for index, route in enumerate(routes):
                count = sum(1 for pair in pairs if pair["routeIndex"] == index)
                route_infos.append((count, len(route), index))
            remove_index = sorted(route_infos)[0][2]
            removed_route = routes.pop(remove_index)
            removed_pairs = [pair for pair in extract_request_pairs(subproblem, {"routes": [removed_route]})]
            for pair in removed_pairs:
                inserted = self._insert_pair(subproblem, routes, pair["request"])
                if inserted is None:
                    self.lastTelemetry["slotCompressionSuccess"] = False
                    return None
                routes = inserted
        candidate = {"routes": routes}
        if check_solution(subproblem, candidate).get("feasible"):
            self.lastTelemetry["slotCompressionSuccess"] = True
            return candidate
        self.lastTelemetry["slotCompressionSuccess"] = False
        return None

    def _insert_pair(self, subproblem: Dict[str, Any], routes: List[List[str]], request: Dict[str, Any]) -> List[List[str]] | None:
        best = None
        best_key = None
        for route_index, route in enumerate(routes):
            for option in self.index.enumerate_options(subproblem, route, request, top_k=6):
                attempt = [list(item) for item in routes]
                attempt[route_index] = option["route"]
                checked = check_solution(subproblem, {"routes": attempt})
                key = (0 if checked.get("feasible") else 1, option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": attempt}))
                if best_key is None or key < best_key:
                    best_key = key
                    best = attempt
        return best

    def _due_key(self, subproblem: Dict[str, Any], request: Dict[str, Any]) -> float:
        nodes = {str(node.get("id")): node for node in subproblem.get("nodes", [])}
        pickup = nodes.get(str(request.get("pickupNodeId")), {})
        dropoff = nodes.get(str(request.get("dropoffNodeId")), {})
        return min(float(pickup.get("dueTime", 0) or 0), float(dropoff.get("dueTime", 0) or 0))
