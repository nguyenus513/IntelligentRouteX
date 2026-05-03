from __future__ import annotations

import math
from collections import Counter
from typing import Any, Sequence

from external_benchmark_support import route_distance
from run_academic_max_quality import route_feasible


def depot_id(instance: dict[str, Any]) -> str:
    return str(instance.get("depotNodeId", "0"))


def customers(instance: dict[str, Any]) -> list[str]:
    depot = depot_id(instance)
    return [str(node["id"]) for node in instance.get("nodes", []) if str(node.get("id")) != depot]


def node_by_id(instance: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in instance.get("nodes", [])}


def polar_angle(instance: dict[str, Any], customer: str) -> float:
    nodes = node_by_id(instance)
    depot = nodes[depot_id(instance)]
    node = nodes[customer]
    return math.atan2(float(node.get("y", 0.0)) - float(depot.get("y", 0.0)), float(node.get("x", 0.0)) - float(depot.get("x", 0.0)))


def route_pool_stitch_tour(instance: dict[str, Any], route_pool: Sequence[dict[str, Any]]) -> list[str]:
    depot = depot_id(instance)
    seen: set[str] = set()
    tour: list[str] = []
    for route in sorted(route_pool, key=lambda item: (-len(item.get("customerSet", [])), float(item.get("distance", 1e18)))):
        for stop in route.get("sequence", []):
            customer = str(stop)
            if customer != depot and customer not in seen:
                seen.add(customer)
                tour.append(customer)
    for customer in customers(instance):
        if customer not in seen:
            tour.append(customer)
    return tour


def nearest_due_neighbor_tour(instance: dict[str, Any]) -> list[str]:
    nodes = node_by_id(instance)
    remaining = set(customers(instance))
    current = depot_id(instance)
    tour: list[str] = []
    while remaining:
        selected = min(
            remaining,
            key=lambda customer: (
                route_distance(instance, [current, customer]),
                float(nodes[customer].get("dueTime", 1e18)),
                float(nodes[customer].get("readyTime", 0.0)),
            ),
        )
        remaining.remove(selected)
        tour.append(selected)
        current = selected
    return tour


def giant_tours(instance: dict[str, Any], route_pool: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = node_by_id(instance)
    base = customers(instance)
    tours = [
        {"strategy": "due-time-sorted", "tour": sorted(base, key=lambda customer: (float(nodes[customer].get("dueTime", 1e18)), float(nodes[customer].get("readyTime", 0.0))))},
        {"strategy": "ready-time-sorted", "tour": sorted(base, key=lambda customer: (float(nodes[customer].get("readyTime", 0.0)), float(nodes[customer].get("dueTime", 1e18))))},
        {"strategy": "polar-angle-sweep", "tour": sorted(base, key=lambda customer: (polar_angle(instance, customer), float(nodes[customer].get("dueTime", 1e18))))},
        {"strategy": "nearest-due-neighbor", "tour": nearest_due_neighbor_tour(instance)},
        {"strategy": "route-pool-stitch", "tour": route_pool_stitch_tour(instance, route_pool)},
    ]
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in tours:
        key = tuple(item["tour"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def append_feasible(instance: dict[str, Any], route: list[str], customer: str) -> bool:
    depot = depot_id(instance)
    return route_feasible(instance, route[:-1] + [customer, depot])


def greedy_split(instance: dict[str, Any], tour: Sequence[str]) -> tuple[list[list[str]], dict[str, Any]]:
    depot = depot_id(instance)
    routes: list[list[str]] = []
    current = [depot, depot]
    reject_reasons: Counter[str] = Counter()
    split_points = 0
    for customer in tour:
        candidate = current[:-1] + [str(customer), depot]
        if route_feasible(instance, candidate):
            current = candidate
            continue
        if len(current) > 2:
            routes.append(current)
            split_points += 1
        single = [depot, str(customer), depot]
        if route_feasible(instance, single):
            current = single
        else:
            reject_reasons["single-customer-infeasible"] += 1
            current = [depot, depot]
    if len(current) > 2:
        routes.append(current)
    return routes, {"splitPoints": split_points, "splitRejectReasons": dict(reject_reasons)}


def boundary_repair(instance: dict[str, Any], routes: Sequence[list[str]], max_passes: int = 2) -> tuple[list[list[str]], dict[str, int]]:
    repaired = [route[:] for route in routes]
    attempts = successes = 0
    for _ in range(max_passes):
        improved = False
        for index in range(len(repaired) - 1):
            left = repaired[index]
            right = repaired[index + 1]
            if len(right) > 3:
                attempts += 1
                moved = right[1]
                candidate_left = left[:-1] + [moved, left[-1]]
                candidate_right = [right[0]] + right[2:]
                if route_feasible(instance, candidate_left) and route_feasible(instance, candidate_right):
                    repaired[index] = candidate_left
                    repaired[index + 1] = candidate_right
                    successes += 1
                    improved = True
                    continue
            if len(left) > 3:
                attempts += 1
                moved = left[-2]
                candidate_left = left[:-2] + [left[-1]]
                candidate_right = [right[0], moved] + right[1:]
                if route_feasible(instance, candidate_left) and route_feasible(instance, candidate_right):
                    repaired[index] = candidate_left
                    repaired[index + 1] = candidate_right
                    successes += 1
                    improved = True
        repaired = [route for route in repaired if len(route) > 2]
        if not improved:
            break
    return repaired, {"boundaryRepairAttempts": attempts, "boundaryRepairSuccesses": successes}


def split_candidates(instance: dict[str, Any], route_pool: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in giant_tours(instance, route_pool):
        routes, split_trace = greedy_split(instance, item["tour"])
        repaired, repair_trace = boundary_repair(instance, routes)
        if all(route_feasible(instance, route) for route in repaired):
            candidates.append({
                "strategy": item["strategy"],
                "routes": repaired,
                "vehicleCount": len(repaired),
                "totalDistance": sum(route_distance(instance, route) for route in repaired),
                **split_trace,
                **repair_trace,
            })
    return sorted(candidates, key=lambda row: (int(row["vehicleCount"]), float(row["totalDistance"])))
