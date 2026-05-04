from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Tuple


def request_id(request: Dict[str, Any]) -> str:
    return str(request.get("orderId", f"{request.get('pickupNodeId')}->{request.get('dropoffNodeId')}"))


def extract_request_pairs(instance: Dict[str, Any], solution: Dict[str, Any]) -> List[Dict[str, Any]]:
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    pairs = []
    for request in instance.get("requests", []):
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        for route_index, route in enumerate(routes):
            if pickup in route and dropoff in route:
                pairs.append({"request": request, "requestId": request_id(request), "pickup": pickup, "dropoff": dropoff, "routeIndex": route_index, "pickupIndex": route.index(pickup), "dropoffIndex": route.index(dropoff)})
                break
    return sorted(pairs, key=lambda item: (item["routeIndex"], item["pickupIndex"], item["dropoffIndex"], item["requestId"]))


def remove_pair_from_route(route: Iterable[str], request: Dict[str, Any]) -> List[str]:
    pickup = str(request.get("pickupNodeId"))
    dropoff = str(request.get("dropoffNodeId"))
    return [str(stop) for stop in route if str(stop) not in {pickup, dropoff}]


def insert_pair_positions(route: List[str], request: Dict[str, Any]) -> List[Tuple[int, int, List[str]]]:
    pickup = str(request.get("pickupNodeId"))
    dropoff = str(request.get("dropoffNodeId"))
    positions: List[Tuple[int, int, List[str]]] = []
    base = [str(stop) for stop in route]
    if len(base) < 2:
        return positions
    for pickup_pos in range(1, len(base)):
        with_pickup = base[:pickup_pos] + [pickup] + base[pickup_pos:]
        for dropoff_pos in range(pickup_pos + 1, len(with_pickup)):
            candidate = with_pickup[:dropoff_pos] + [dropoff] + with_pickup[dropoff_pos:]
            positions.append((pickup_pos, dropoff_pos, candidate))
    return positions


def route_signature(route: Iterable[str]) -> str:
    return hashlib.sha256(json.dumps([str(stop) for stop in route], separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def solution_signature(solution: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(solution.get("routes", []), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
