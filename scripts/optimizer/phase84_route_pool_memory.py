from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Set

from external_benchmark_support import route_distance


def _request_set(instance: Dict[str, Any], route: List[str]) -> List[str]:
    route_set = set(str(stop) for stop in route)
    orders = []
    for request in instance.get("requests", []):
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        if pickup in route_set and dropoff in route_set:
            orders.append(str(request.get("orderId", f"{pickup}->{dropoff}")))
    return sorted(orders)


def _signature(route: List[str]) -> str:
    return hashlib.sha256(json.dumps([str(stop) for stop in route], separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RouteColumn:
    requestSet: List[str]
    route: List[str]
    distance: float
    sourceOperator: str
    signature: str
    provenance: str = "internal"
    allowedForClaim: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RoutePoolMemory:
    def __init__(self, max_per_request_set: int = 5) -> None:
        self.max_per_request_set = max_per_request_set
        self.columns: Dict[str, RouteColumn] = {}

    def add_route(self, instance: Dict[str, Any], route: Iterable[str], source_operator: str, provenance: str = "internal") -> bool:
        if provenance != "internal":
            return False
        normalized = [str(stop) for stop in route]
        column = RouteColumn(
            requestSet=_request_set(instance, normalized),
            route=normalized,
            distance=route_distance(instance, normalized),
            sourceOperator=source_operator,
            signature=_signature(normalized),
        )
        if not column.requestSet:
            return False
        key = "|".join(column.requestSet)
        existing = [item for item in self.columns.values() if "|".join(item.requestSet) == key]
        if len(existing) >= self.max_per_request_set and all(item.distance <= column.distance for item in existing):
            return False
        self.columns[column.signature] = column
        return True

    def add_solution(self, instance: Dict[str, Any], solution: Dict[str, Any], source_operator: str) -> int:
        return sum(1 for route in solution.get("routes", []) if self.add_route(instance, route, source_operator))

    def request_coverage(self) -> Set[str]:
        covered: Set[str] = set()
        for column in self.columns.values():
            covered.update(column.requestSet)
        return covered

    def stats(self) -> Dict[str, Any]:
        return {"columnCount": len(self.columns), "coveredRequestCount": len(self.request_coverage()), "provenance": "internal-only"}

    def to_rows(self) -> List[Dict[str, Any]]:
        return [self.columns[key].to_dict() for key in sorted(self.columns)]
