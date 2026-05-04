from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Set

from external_benchmark_support import check_solution, route_distance
from optimizer.phase85_pair_utils import extract_request_pairs, remove_pair_from_route, request_id, solution_signature
from optimizer.phase87_insertion_index import InsertionIndex


@dataclass(frozen=True)
class CoverageDiff:
    requiredRequestIds: List[str]
    coveredRequestIds: List[str]
    missingRequestIds: List[str]
    duplicateRequestIds: List[str]
    partialPickupDropoffIds: List[str]
    affectedRequestIds: List[str]
    unaffectedRequestIds: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def coverage_diff(instance: Dict[str, Any], solution: Dict[str, Any], affected_request_ids: Set[str] | None = None) -> CoverageDiff:
    affected_request_ids = affected_request_ids or set()
    required = {request_id(request) for request in instance.get("requests", [])}
    route_hits: Dict[str, int] = {key: 0 for key in required}
    partial: Set[str] = set()
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    for request in instance.get("requests", []):
        rid = request_id(request)
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        for route in routes:
            has_pickup = pickup in route
            has_dropoff = dropoff in route
            if has_pickup and has_dropoff:
                route_hits[rid] += 1
            elif has_pickup or has_dropoff:
                partial.add(rid)
    covered = {rid for rid, count in route_hits.items() if count > 0}
    duplicate = {rid for rid, count in route_hits.items() if count > 1}
    missing = required - covered
    return CoverageDiff(sorted(required), sorted(covered), sorted(missing), sorted(duplicate), sorted(partial), sorted(affected_request_ids), sorted(required - affected_request_ids))


class ResidualCoverageRepair:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.lastTelemetry: Dict[str, Any] = {"residualCoverageRepairAttempts": 0, "residualCoverageRepairSuccess": False}

    def repair(self, instance: Dict[str, Any], candidate: Dict[str, Any], missing_request_ids: List[str], max_routes: int) -> Dict[str, Any] | None:
        self.lastTelemetry = {"residualCoverageRepairAttempts": 0, "residualCoverageRepairSuccess": False}
        if not missing_request_ids:
            self.lastTelemetry["residualCoverageRepairSuccess"] = True
            return candidate
        routes = [[str(stop) for stop in route] for route in candidate.get("routes", []) if len(route) > 2]
        if len(routes) > max_routes:
            return None
        requests = {request_id(request): request for request in instance.get("requests", [])}
        for rid in missing_request_ids:
            self.lastTelemetry["residualCoverageRepairAttempts"] += 1
            request = requests.get(str(rid))
            if request is None:
                return None
            best = None
            best_key = None
            for route_index, route in enumerate(routes):
                for option in self.index.enumerate_options(instance, route, request, top_k=6):
                    attempt = [list(item) for item in routes]
                    attempt[route_index] = option["route"]
                    checked = check_solution(instance, {"routes": attempt})
                    key = (0 if checked.get("feasible") else 1, option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": attempt}))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = attempt
            if best is None:
                return None
            routes = best
        repaired = {"routes": routes}
        self.lastTelemetry["residualCoverageRepairSuccess"] = not coverage_diff(instance, repaired).missingRequestIds
        return repaired if self.lastTelemetry["residualCoverageRepairSuccess"] else None


def remove_duplicate_pairs(instance: Dict[str, Any], solution: Dict[str, Any], duplicate_request_ids: List[str]) -> Dict[str, Any]:
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    requests = {request_id(request): request for request in instance.get("requests", [])}
    for rid in duplicate_request_ids:
        request = requests.get(str(rid))
        if request is None:
            continue
        occurrences = []
        for index, route in enumerate(routes):
            if str(request.get("pickupNodeId")) in route and str(request.get("dropoffNodeId")) in route:
                stripped = remove_pair_from_route(route, request)
                delta = route_distance(instance, route) - route_distance(instance, stripped)
                occurrences.append((delta, index, stripped))
        for _, index, stripped in sorted(occurrences, reverse=True)[:-1]:
            routes[index] = stripped
    return {"routes": [route for route in routes if len(route) > 2]}

