from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCALE = 1000


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
    source_path: Optional[str] = None,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    distance_matrix = matrix(nodes)
    payload = {
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
    if source_path:
        payload["sourcePath"] = source_path
    if source_url:
        payload["sourceUrl"] = source_url
    return payload


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


def simple_baseline_solution(instance: Dict[str, Any], solver: str = "our-dispatch-v2") -> Dict[str, Any]:
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
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [route]}


def ortools_baseline_solution(
    instance: Dict[str, Any],
    time_limit_ms: int,
    solver: str = "ortools-baseline",
    vehicle_fixed_cost: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except Exception as exception:  # pragma: no cover - depends on optional local package.
        return {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": solver,
            "routes": [],
            "evidenceGapReason": f"ortools-python-unavailable: {exception}",
        }

    nodes = instance.get("nodes", [])
    depot_node_id = str(instance.get("depotNodeId", "0"))
    indexes = matrix_index(instance)
    depot_index = indexes[depot_node_id]
    vehicle_count = int(instance.get("vehicleCount", 1))
    capacity = int(instance.get("capacity", 0))
    manager = pywrapcp.RoutingIndexManager(len(nodes), vehicle_count, depot_index)
    routing = pywrapcp.RoutingModel(manager)
    distance_matrix = [[int(round(float(value) * SCALE)) for value in row] for row in instance["distanceMatrix"]]

    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    distance_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)
    if vehicle_fixed_cost is not None and vehicle_fixed_cost > 0:
        routing.SetFixedCostOfAllVehicles(vehicle_fixed_cost)

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        service = int(round(float(nodes[from_node].get("serviceTime", 0.0)) * SCALE))
        return distance_matrix[from_node][to_node] + service

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    horizon = max(int(round(float(node.get("dueTime", 0.0)) * SCALE)) for node in nodes) + 10_000 * SCALE
    routing.AddDimension(time_callback_index, horizon, horizon, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    for node_index, node in enumerate(nodes):
        index = manager.NodeToIndex(node_index)
        ready = int(round(float(node.get("readyTime", 0.0)) * SCALE))
        due = int(round(float(node.get("dueTime", horizon / SCALE)) * SCALE))
        time_dimension.CumulVar(index).SetRange(ready, due)
    for vehicle_id in range(vehicle_count):
        depot_node = nodes[depot_index]
        ready = int(round(float(depot_node.get("readyTime", 0.0)) * SCALE))
        due = int(round(float(depot_node.get("dueTime", horizon / SCALE)) * SCALE))
        time_dimension.CumulVar(routing.Start(vehicle_id)).SetRange(ready, due)
        time_dimension.CumulVar(routing.End(vehicle_id)).SetRange(ready, due)

    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        return int(round(float(nodes[from_node].get("demand", 0))))

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [capacity for _ in range(vehicle_count)],
        True,
        "Capacity",
    )

    for request in instance.get("requests", []):
        pickup_index = manager.NodeToIndex(indexes[str(request["pickupNodeId"])])
        delivery_index = manager.NodeToIndex(indexes[str(request["dropoffNodeId"])])
        routing.AddPickupAndDelivery(pickup_index, delivery_index)
        routing.solver().Add(routing.VehicleVar(pickup_index) == routing.VehicleVar(delivery_index))
        routing.solver().Add(time_dimension.CumulVar(pickup_index) <= time_dimension.CumulVar(delivery_index))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromMilliseconds(max(1, time_limit_ms))
    search_parameters.log_search = False
    assignment = routing.SolveWithParameters(search_parameters)
    if assignment is None:
        return {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": solver,
            "routes": [],
            "evidenceGapReason": "ortools-no-solution",
        }

    routes: List[List[str]] = []
    for vehicle_id in range(vehicle_count):
        route: List[str] = []
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            route.append(str(nodes[manager.IndexToNode(index)]["id"]))
            index = assignment.Value(routing.NextVar(index))
        route.append(str(nodes[manager.IndexToNode(index)]["id"]))
        if len(route) > 2:
            routes.append(route)
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": routes}


def check_solution(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    nodes = node_by_id(instance)
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    capacity = int(instance.get("capacity", 0))
    max_vehicles = int(instance.get("vehicleCount", 0))
    violations: List[str] = []
    served: set[str] = set()
    total_distance = 0.0
    capacity_violations = 0
    time_window_violations = 0
    pickup_dropoff_violations = 0
    vehicle_limit_violations = 0

    active_routes = [route for route in routes if len(route) > 2]
    if max_vehicles > 0 and len(active_routes) > max_vehicles:
        vehicle_limit_violations = len(active_routes) - max_vehicles
        violations.append("vehicle-count-violation")

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
        "violations": sorted(set(violations)),
        "vehicleCount": len(active_routes),
        "totalDistance": total_distance,
        "servedRequestCount": len(required) if instance.get("problemType") != "PDPTW" else len(instance.get("requests", [])) - pickup_dropoff_violations,
        "unservedRequestCount": len(missing),
        "capacityViolationCount": capacity_violations,
        "timeWindowViolationCount": time_window_violations,
        "pickupBeforeDropoffViolationCount": pickup_dropoff_violations,
        "vehicleLimitViolationCount": vehicle_limit_violations,
        "objectiveGapPercent": gap,
    }


def verdict(result: Dict[str, Any], gap_limit: float, runtime_ms: int, time_limit_ms: int) -> Tuple[str, List[str]]:
    # OR-Tools receives the time limit; Python parsing/reporting adds small OS-dependent overhead.
    timeout_slack_ms = max(5_000, int(time_limit_ms * 0.10))
    if runtime_ms > time_limit_ms + timeout_slack_ms:
        return "FAIL", ["runtime-timeout"]
    if not result.get("feasible"):
        return "FAIL", list(result.get("violations", ["infeasible"]))
    gap = result.get("objectiveGapPercent")
    if gap is None:
        return "PASS_WITH_LIMITS", ["best-known-objective-missing"]
    if float(gap) > gap_limit:
        return "PASS_WITH_LIMITS", ["objective-gap-above-pass-threshold"]
    return "PASS", ["external-benchmark-feasible-within-gap"]
