from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def read_lines(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def euclidean(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def matrix(nodes: List[Dict[str, Any]]) -> List[List[float]]:
    return [[euclidean(left, right) for right in nodes] for left in nodes]


def best_known(lines: Iterable[str]) -> Dict[str, Any]:
    best: Dict[str, Any] = {"source": "fixture"}
    for line in lines:
        if line.startswith("# BEST_KNOWN_VEHICLES"):
            best["vehicleCount"] = int(line.split()[-1])
        if line.startswith("# BEST_KNOWN_DISTANCE"):
            best["objective"] = float(line.split()[-1])
    return best


def normalize_instance(
    benchmark_family: str,
    problem_type: str,
    instance_name: str,
    vehicle_count: int,
    capacity: int,
    nodes: List[Dict[str, Any]],
    requests: List[Dict[str, Any]],
    best: Dict[str, Any],
) -> Dict[str, Any]:
    distance_matrix = matrix(nodes)
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "benchmarkFamily": benchmark_family,
        "instanceName": instance_name,
        "problemType": problem_type,
        "vehicleCount": vehicle_count,
        "capacity": capacity,
        "depotNodeId": "0",
        "nodes": nodes,
        "requests": requests,
        "distanceMatrix": distance_matrix,
        "durationMatrix": distance_matrix,
        "bestKnown": best,
    }


def node_by_id(instance: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(node["id"]): node for node in instance.get("nodes", [])}


def matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node["id"]): index for index, node in enumerate(instance.get("nodes", []))}


def route_distance(instance: Dict[str, Any], route: List[str]) -> float:
    indexes = matrix_index(instance)
    distances = instance["distanceMatrix"]
    total = 0.0
    for left, right in zip(route, route[1:]):
        total += float(distances[indexes[str(left)]][indexes[str(right)]])
    return total


def simple_baseline_solution(instance: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    if instance.get("problemType") == "PDPTW":
        route = [depot]
        for request in instance.get("requests", []):
            route.append(str(request["pickupNodeId"]))
            route.append(str(request["dropoffNodeId"]))
        route.append(depot)
    else:
        customers = [str(node["id"]) for node in instance.get("nodes", []) if str(node["id"]) != depot]
        route = [depot] + customers + [depot]
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "our-dispatch-v2", "routes": [route]}


def check_solution(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    nodes = node_by_id(instance)
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    capacity = int(instance.get("capacity", 0))
    violations: List[str] = []
    served: set[str] = set()
    total_distance = 0.0
    capacity_violations = 0
    time_window_violations = 0
    pickup_dropoff_violations = 0

    for route in routes:
        unknown_stops = [stop for stop in route if stop not in nodes]
        if unknown_stops:
            violations.append("unknown-node-in-route")
            continue
        if not route or route[0] != depot or route[-1] != depot:
            violations.append("route-does-not-start-end-at-depot")
        load = 0
        elapsed = 0.0
        for previous, current in zip(route, route[1:]):
            elapsed += route_distance(instance, [previous, current])
            node = nodes[current]
            ready = float(node.get("readyTime", 0.0))
            due = float(node.get("dueTime", 1e18))
            if elapsed < ready:
                elapsed = ready
            if elapsed > due + 1e-9:
                time_window_violations += 1
            elapsed += float(node.get("serviceTime", 0.0))
            load += int(float(node.get("demand", 0)))
            if load > capacity or load < 0:
                capacity_violations += 1
            if current != depot:
                served.add(current)
        total_distance += route_distance(instance, route)

    for request in instance.get("requests", []):
        pickup = str(request["pickupNodeId"])
        dropoff = str(request["dropoffNodeId"])
        containing = [route for route in routes if pickup in route or dropoff in route]
        if len(containing) != 1 or pickup not in containing[0] or dropoff not in containing[0]:
            pickup_dropoff_violations += 1
            continue
        if containing[0].index(pickup) >= containing[0].index(dropoff):
            pickup_dropoff_violations += 1

    required = {str(node["id"]) for node in instance.get("nodes", []) if str(node["id"]) != depot}
    missing = required - served
    duplicate_count = sum(sum(1 for route in routes for stop in route if stop == node_id) > 1 for node_id in required)
    if missing:
        violations.append("missing-required-nodes")
    if duplicate_count:
        violations.append("duplicate-required-nodes")
    if capacity_violations:
        violations.append("capacity-violation")
    if time_window_violations:
        violations.append("time-window-violation")
    if pickup_dropoff_violations:
        violations.append("pickup-before-dropoff-violation")

    best = instance.get("bestKnown", {})
    best_objective = float(best.get("objective", 0.0) or 0.0)
    gap = None if best_objective <= 0.0 else ((total_distance - best_objective) / best_objective) * 100.0
    return {
        "feasible": not violations,
        "violations": violations,
        "vehicleCount": len([route for route in routes if len(route) > 2]),
        "totalDistance": total_distance,
        "servedRequestCount": len(required) if instance.get("problemType") != "PDPTW" else len(instance.get("requests", [])) - pickup_dropoff_violations,
        "unservedRequestCount": len(missing),
        "capacityViolationCount": capacity_violations,
        "timeWindowViolationCount": time_window_violations,
        "pickupBeforeDropoffViolationCount": pickup_dropoff_violations,
        "objectiveGapPercent": gap,
    }


def verdict(result: Dict[str, Any], gap_limit: float, runtime_ms: int, time_limit_ms: int) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if runtime_ms > time_limit_ms:
        return "FAIL", ["runtime-timeout"]
    if not result.get("feasible"):
        return "FAIL", list(result.get("violations", ["infeasible"]))
    gap = result.get("objectiveGapPercent")
    if gap is None:
        return "PASS_WITH_LIMITS", ["best-known-objective-missing"]
    if float(gap) > gap_limit:
        return "PASS_WITH_LIMITS", ["objective-gap-above-pass-threshold"]
    return "PASS", ["external-benchmark-feasible-within-gap"]
