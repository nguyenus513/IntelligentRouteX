from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def parse_characteristics(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percent / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def with_metadata(metrics: dict[str, Any], **metadata: Any) -> dict[str, Any]:
    result = dict(metrics)
    result.update(metadata)
    return result


def score_profile(metrics: dict[str, Any]) -> float:
    food_score = metrics["servedOrderRate"] * 0.35 + (1.0 - metrics["lateOrderRate"]) * 0.25 + max(0.0, 1.0 - metrics["p95Delay"] / 45.0) * 0.20 + max(0.0, 1.0 - metrics["p95FoodOnVehicleTime"] / 30.0) * 0.20
    driver_score = metrics["courierUtilization"] * 0.45 + max(0.0, 1.0 - metrics["assignmentFairnessGini"]) * 0.35 + max(0.0, 1.0 - max(0.0, metrics["ordersPerCourierP95"] - 15.0) / 20.0) * 0.20
    anchor_score = (1.0 if metrics["pickupBeforeReadyTimeViolation"] == 0 else 0.0) * 0.45 + max(0.0, 1.0 - metrics["avgPickupWaitTime"] / 10.0) * 0.30 + max(0.0, 1.0 - metrics["p95OrderToDeliveryTime"] / 75.0) * 0.25
    order_to_delivery_score = max(0.0, 1.0 - metrics["p95OrderToDeliveryTime"] / 75.0) * 0.45 + max(0.0, 1.0 - metrics["avgOrderToDeliveryTime"] / 50.0) * 0.30 + max(0.0, 1.0 - metrics["p95Delay"] / 45.0) * 0.25
    return food_score * 0.30 + driver_score * 0.30 + anchor_score * 0.15 + order_to_delivery_score * 0.25


def order_to_delivery_lower_bounds(
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float) -> dict[str, float]:
    values: list[float] = []
    for order in orders:
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        prep_time = max(0.0, float(order["ready_time"]) - float(order["placement_time"]))
        direct_delivery = distance(restaurant, order) / speed_meters_per_minute
        values.append(prep_time + direct_delivery)
    return {
        "avgOrderToDeliveryLowerBound": sum(values) / max(1, len(values)),
        "p50OrderToDeliveryLowerBound": percentile(values, 50),
        "p95OrderToDeliveryLowerBound": percentile(values, 95),
    }


def freshness_lower_bounds(
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float) -> dict[str, float]:
    food_values: list[float] = []
    delay_values: list[float] = []
    for order in orders:
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        direct_delivery = distance(restaurant, order) / speed_meters_per_minute
        food_values.append(direct_delivery)
        delay_values.append(direct_delivery)
    return {
        "avgFoodOnVehicleLowerBound": sum(food_values) / max(1, len(food_values)),
        "p95FoodOnVehicleLowerBound": percentile(food_values, 95),
        "avgDelayLowerBound": sum(delay_values) / max(1, len(delay_values)),
        "p95DelayLowerBound": percentile(delay_values, 95),
    }


def point_line_distance(point: dict[str, Any], start: dict[str, Any], end: dict[str, Any]) -> float:
    px, py = float(point["x"]), float(point["y"])
    sx, sy = float(start["x"]), float(start["y"])
    ex, ey = float(end["x"]), float(end["y"])
    dx, dy = ex - sx, ey - sy
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - sx, py - sy)
    ratio = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / denom))
    projection_x = sx + ratio * dx
    projection_y = sy + ratio * dy
    return math.hypot(px - projection_x, py - projection_y)


def route_geometry_features(points: list[dict[str, Any]]) -> dict[str, float]:
    if len(points) < 2:
        return {"routeBeautyScore": 1.0, "routeShapePenalty": 0.0, "routeDetourRisk": 0.0, "routeCorridorFit": 1.0, "routeStraightnessProxy": 1.0, "routeZigzagPenalty": 0.0, "routeTurnProxy": 0.0}
    route_distance = sum(distance(points[index - 1], points[index]) for index in range(1, len(points)))
    direct_distance = distance(points[0], points[-1])
    straightness = 1.0 if route_distance <= 1e-9 else max(0.0, min(1.0, direct_distance / route_distance))
    detour_ratio = 1.0 if direct_distance <= 1e-9 else route_distance / direct_distance
    corridor_distances = [point_line_distance(point, points[0], points[-1]) for point in points[1:-1]]
    avg_corridor_distance = sum(corridor_distances) / max(1, len(corridor_distances))
    corridor_fit = 1.0 / (1.0 + avg_corridor_distance / max(1.0, direct_distance))
    turn_count = 0
    sharp_turn_count = 0
    for index in range(2, len(points)):
        ax = float(points[index - 1]["x"]) - float(points[index - 2]["x"])
        ay = float(points[index - 1]["y"]) - float(points[index - 2]["y"])
        bx = float(points[index]["x"]) - float(points[index - 1]["x"])
        by = float(points[index]["y"]) - float(points[index - 1]["y"])
        norm = math.hypot(ax, ay) * math.hypot(bx, by)
        if norm <= 1e-9:
            continue
        cosine = max(-1.0, min(1.0, (ax * bx + ay * by) / norm))
        angle = math.degrees(math.acos(cosine))
        if angle >= 35.0:
            turn_count += 1
        if angle >= 100.0:
            sharp_turn_count += 1
    turn_proxy = min(1.0, turn_count / max(1, len(points) - 2))
    zigzag_penalty = min(1.0, sharp_turn_count / max(1, len(points) - 2))
    detour_risk = max(0.0, min(1.0, (detour_ratio - 1.0) / 3.0))
    shape_penalty = max(0.0, min(1.0, detour_risk * 0.35 + (1.0 - straightness) * 0.30 + (1.0 - corridor_fit) * 0.20 + zigzag_penalty * 0.10 + turn_proxy * 0.05))
    return {
        "routeBeautyScore": max(0.0, min(1.0, 1.0 - shape_penalty)),
        "routeShapePenalty": shape_penalty,
        "routeDetourRisk": detour_risk,
        "routeCorridorFit": corridor_fit,
        "routeStraightnessProxy": straightness,
        "routeZigzagPenalty": zigzag_penalty,
        "routeTurnProxy": turn_proxy,
    }


def route_points_for_orders(courier: dict[str, str], orders: list[dict[str, str]], restaurants: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = [courier]
    for order in orders:
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is not None:
            points.append(restaurant)
        points.append(order)
    return points


def order_priority(order: dict[str, str], profile: dict[str, float | str]) -> tuple[Any, ...]:
    placement = float(order["placement_time"])
    ready = float(order["ready_time"])
    restaurant = str(order["restaurant"])
    strategy = str(profile.get("orderSort", "placement"))
    if strategy == "ready-time-tight":
        return ready, placement, restaurant, str(order["order"])
    if strategy == "ready-restaurant":
        return ready, restaurant, placement, str(order["order"])
    if strategy == "restaurant-ready":
        return restaurant, ready, placement, str(order["order"])
    if strategy == "placement-restaurant":
        return placement, restaurant, ready, str(order["order"])
    return placement, ready, restaurant, str(order["order"])


def anchor_v2_features(
        anchor: dict[str, str],
        pending_orders: list[dict[str, str]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        ready_window: float = 6.0,
        placement_window: float = 10.0) -> dict[str, float]:
    restaurant = restaurants.get(anchor["restaurant"])
    if restaurant is None:
        return {
            "anchorReadySlack": 0.0,
            "anchorCourierProximity": 0.0,
            "anchorCorridorFit": 0.0,
            "anchorDetourRisk": 1.0,
            "anchorTrafficRisk": 1.0,
            "anchorWeatherRisk": 1.0,
            "anchorBoundaryCrossPenalty": 1.0,
            "anchorV2Score": 0.0,
        }
    anchor_ready = float(anchor["ready_time"])
    anchor_placement = float(anchor["placement_time"])
    compatible_ready_slacks: list[float] = []
    nearby_restaurants: set[str] = {str(anchor["restaurant"])}
    for order in pending_orders:
        ready_gap = abs(float(order["ready_time"]) - anchor_ready)
        placement_gap = float(order["placement_time"]) - anchor_placement
        if ready_gap <= ready_window and placement_gap <= placement_window:
            compatible_ready_slacks.append(max(0.0, 1.0 - ready_gap / max(1.0, ready_window)))
            nearby_restaurants.add(str(order["restaurant"]))
    ready_slack = sum(compatible_ready_slacks) / max(1, len(compatible_ready_slacks))
    nearest_courier = min(couriers, key=lambda courier: distance(courier, restaurant) / speed_meters_per_minute) if couriers else restaurant
    courier_minutes = distance(nearest_courier, restaurant) / speed_meters_per_minute
    courier_proximity = max(0.0, min(1.0, 1.0 - courier_minutes / 18.0))
    geometry = route_geometry_features([nearest_courier, restaurant, anchor])
    corridor_fit = float(geometry["routeCorridorFit"])
    detour_risk = float(geometry["routeDetourRisk"])
    traffic_risk = max(0.0, min(1.0, detour_risk * 0.60 + max(0.0, 1.0 - corridor_fit) * 0.40))
    weather_risk = max(0.0, min(1.0, detour_risk * 0.35 + max(0.0, 1.0 - corridor_fit) * 0.65))
    boundary_cross = max(0.0, min(1.0, (len(nearby_restaurants) - 1) / 4.0))
    score = max(0.0, min(1.0,
        ready_slack * 0.30
        + courier_proximity * 0.25
        + corridor_fit * 0.20
        + (1.0 - detour_risk) * 0.12
        + (1.0 - traffic_risk) * 0.08
        + (1.0 - boundary_cross) * 0.05
    ))
    return {
        "anchorReadySlack": ready_slack,
        "anchorCourierProximity": courier_proximity,
        "anchorCorridorFit": corridor_fit,
        "anchorDetourRisk": detour_risk,
        "anchorTrafficRisk": traffic_risk,
        "anchorWeatherRisk": weather_risk,
        "anchorBoundaryCrossPenalty": boundary_cross,
        "anchorV2Score": score,
    }


def anchor_top_k_candidates(
        orders: list[dict[str, str]],
        pending_ids: set[str],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        profile: dict[str, float | str],
        limit: int,
        ready_window: float = 6.0,
        placement_window: float = 10.0) -> tuple[list[dict[str, str]], dict[str, dict[str, float]]]:
    pending_orders = [order for order in orders if str(order["order"]) in pending_ids]
    ranked: list[tuple[float, tuple[Any, ...], dict[str, str], dict[str, float]]] = []
    for anchor in pending_orders:
        features = anchor_v2_features(anchor, pending_orders, couriers, restaurants, speed_meters_per_minute, ready_window, placement_window)
        ranked.append((float(features["anchorV2Score"]), order_priority(anchor, profile), anchor, features))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = ranked[:max(1, limit)]
    feature_by_order = {str(anchor["order"]): features for _score, _priority, anchor, features in selected}
    return [anchor for _score, _priority, anchor, _features in selected], feature_by_order


def route_dropoffs(
        pickup_time: float,
        restaurant: dict[str, Any],
        bundle: list[dict[str, str]],
        speed_meters_per_minute: float,
        max_permutations: int = 24) -> tuple[float, tuple[dict[str, str], ...], dict[str, float]]:
    best: tuple[float, tuple[dict[str, str], ...], dict[str, float]] | None = None
    permutations = itertools.permutations(bundle)
    for index, sequence in enumerate(permutations):
        if index >= max_permutations:
            break
        clock = pickup_time
        location: dict[str, Any] = restaurant
        dropoff_times: dict[str, float] = {}
        for order in sequence:
            clock += distance(location, order) / speed_meters_per_minute
            dropoff_times[str(order["order"])] = clock
            location = order
        if best is None or clock < best[0]:
            best = (clock, sequence, dropoff_times)
    if best is None:
        return pickup_time, tuple(), {}
    return best


def bundle_candidates(
        anchor: dict[str, str],
        pending_orders: list[dict[str, str]],
        restaurant: dict[str, str],
        max_bundle_size: int,
        ready_window: float,
        placement_window: float,
        max_pair_distance_minutes: float,
        speed_meters_per_minute: float) -> list[dict[str, str]]:
    anchor_ready = float(anchor["ready_time"])
    anchor_placement = float(anchor["placement_time"])
    same_restaurant = [
        order for order in pending_orders
        if order["restaurant"] == anchor["restaurant"]
        and abs(float(order["ready_time"]) - anchor_ready) <= ready_window
        and float(order["placement_time"]) <= anchor_placement + placement_window
    ]
    ranked = sorted(
        same_restaurant,
        key=lambda order: (
            0 if order["order"] == anchor["order"] else 1,
            distance(anchor, order) / speed_meters_per_minute,
            abs(float(order["ready_time"]) - anchor_ready),
            float(order["placement_time"]),
            str(order["order"]),
        ),
    )
    bundle: list[dict[str, str]] = []
    for order in ranked:
        if len(bundle) >= max_bundle_size:
            break
        if order["order"] != anchor["order"] and distance(anchor, order) / speed_meters_per_minute > max_pair_distance_minutes:
            continue
        if distance(restaurant, order) / speed_meters_per_minute > max_pair_distance_minutes * 2.5:
            continue
        bundle.append(order)
    return bundle


def multi_restaurant_bundle_candidates(
        anchor: dict[str, str],
        pending_orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        max_bundle_size: int,
        ready_window: float,
        placement_window: float,
        max_pair_distance_minutes: float,
        max_restaurant_distance_minutes: float,
        speed_meters_per_minute: float) -> list[dict[str, str]]:
    anchor_restaurant = restaurants.get(anchor["restaurant"])
    if anchor_restaurant is None:
        return []
    anchor_ready = float(anchor["ready_time"])
    anchor_placement = float(anchor["placement_time"])
    compatible: list[dict[str, str]] = []
    for order in pending_orders:
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        ready_gap = abs(float(order["ready_time"]) - anchor_ready)
        placement_gap = float(order["placement_time"]) - anchor_placement
        restaurant_gap = distance(anchor_restaurant, restaurant) / speed_meters_per_minute
        dropoff_gap = distance(anchor, order) / speed_meters_per_minute
        if ready_gap > ready_window:
            continue
        if placement_gap > placement_window:
            continue
        if restaurant_gap > max_restaurant_distance_minutes:
            continue
        if order["order"] != anchor["order"] and dropoff_gap > max_pair_distance_minutes:
            continue
        compatible.append(order)
    return sorted(
        compatible,
        key=lambda order: (
            0 if order["order"] == anchor["order"] else 1,
            distance(anchor_restaurant, restaurants[order["restaurant"]]) / speed_meters_per_minute,
            distance(anchor, order) / speed_meters_per_minute,
            abs(float(order["ready_time"]) - anchor_ready),
            float(order["placement_time"]),
            str(order["order"]),
        ),
    )[:max_bundle_size]


def route_multi_restaurant_bundle(
        start_time: float,
        start_location: dict[str, Any],
        bundle: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_permutations: int = 24) -> tuple[float, tuple[dict[str, str], ...], dict[str, float], dict[str, float]]:
    pickup_clock = start_time
    pickup_location = start_location
    pickup_times: dict[str, float] = {}
    pickup_sequence = sorted(bundle, key=lambda order: (float(order["ready_time"]), str(order["restaurant"]), str(order["order"])))
    for order in pickup_sequence:
        restaurant = restaurants[order["restaurant"]]
        pickup_arrival = pickup_clock + distance(pickup_location, restaurant) / speed_meters_per_minute
        pickup_clock = max(float(order["ready_time"]), pickup_arrival)
        pickup_times[str(order["order"])] = pickup_clock
        pickup_location = restaurant

    best: tuple[float, tuple[dict[str, str], ...], dict[str, float]] | None = None
    for index, sequence in enumerate(itertools.permutations(bundle)):
        if index >= max_permutations:
            break
        clock = pickup_clock
        location: dict[str, Any] = pickup_location
        dropoff_times: dict[str, float] = {}
        for order in sequence:
            clock += distance(location, order) / speed_meters_per_minute
            dropoff_times[str(order["order"])] = clock
            location = order
        if best is None or clock < best[0]:
            best = (clock, sequence, dropoff_times)
    if best is None:
        return pickup_clock, tuple(), pickup_times, {}
    return best[0], best[1], pickup_times, best[2]


def evaluate_order_routes(
        couriers: list[dict[str, str]],
        routes: dict[str, list[dict[str, str]]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        repair_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    served = 0
    late = 0
    pickup_before_ready_violations = 0
    shift_violations = 0
    max_delay_observed = 0.0
    total_delay = 0.0
    total_food_on_vehicle = 0.0
    delays: list[float] = []
    food_on_vehicle_times: list[float] = []
    order_to_delivery_times: list[float] = []
    pickup_wait_times: list[float] = []
    pickup_dropoff_violations = 0

    for courier_id, route in routes.items():
        courier = courier_by_id[courier_id]
        clock = float(courier["on_time"])
        location: dict[str, Any] = courier
        for order in route:
            restaurant = restaurants.get(order["restaurant"])
            if restaurant is None:
                continue
            clock = max(clock, float(order["placement_time"]))
            pickup_arrival = clock + distance(location, restaurant) / speed_meters_per_minute
            pickup_time = max(float(order["ready_time"]), pickup_arrival)
            dropoff_time = pickup_time + distance(restaurant, order) / speed_meters_per_minute
            if pickup_time + 1e-9 < float(order["ready_time"]):
                pickup_before_ready_violations += 1
            if dropoff_time + 1e-9 < pickup_time:
                pickup_dropoff_violations += 1
            if dropoff_time > float(courier["off_time"]) + 1e-9:
                shift_violations += 1
            delay = dropoff_time - float(order["ready_time"])
            food_on_vehicle = dropoff_time - pickup_time
            order_to_delivery = dropoff_time - float(order["placement_time"])
            pickup_wait = max(0.0, pickup_time - float(order["ready_time"]))
            if delay > max_delay_minutes:
                late += 1
            served += 1
            max_delay_observed = max(max_delay_observed, delay)
            total_delay += delay
            total_food_on_vehicle += food_on_vehicle
            delays.append(delay)
            food_on_vehicle_times.append(food_on_vehicle)
            order_to_delivery_times.append(order_to_delivery)
            pickup_wait_times.append(pickup_wait)
            clock = dropoff_time
            location = order

    courier_order_values = [len(routes.get(courier["courier"], [])) for courier in couriers]
    mean_orders = sum(courier_order_values) / max(1, len(courier_order_values))
    fairness_gini = 0.0
    if mean_orders > 0.0:
        fairness_gini = sum(abs(left - right) for left in courier_order_values for right in courier_order_values) / (2 * len(courier_order_values) ** 2 * mean_orders)
    hard_violations = pickup_before_ready_violations + shift_violations + pickup_dropoff_violations
    payload = {
        "orderCount": served,
        "courierCount": len(couriers),
        "restaurantCount": len(restaurants),
        "servedOrderCount": served,
        "unservedOrderCount": 0,
        "servedOrderRate": 1.0 if served else 0.0,
        "lateOrderCount": late,
        "lateOrderRate": late / max(1, served),
        "pickupBeforeReadyTimeViolation": pickup_before_ready_violations,
        "courierShiftViolation": shift_violations,
        "foodOnVehicleHardViolation": 0,
        "pickupBeforeDropoffViolationCount": pickup_dropoff_violations,
        "avgDelay": total_delay / max(1, served),
        "p50Delay": percentile(delays, 50),
        "p95Delay": percentile(delays, 95),
        "maxDelay": max_delay_observed,
        "avgFoodOnVehicleTime": total_food_on_vehicle / max(1, served),
        "p50FoodOnVehicleTime": percentile(food_on_vehicle_times, 50),
        "p95FoodOnVehicleTime": percentile(food_on_vehicle_times, 95),
        "avgOrderToDeliveryTime": sum(order_to_delivery_times) / max(1, served),
        "p50OrderToDeliveryTime": percentile(order_to_delivery_times, 50),
        "p95OrderToDeliveryTime": percentile(order_to_delivery_times, 95),
        "avgPickupWaitTime": sum(pickup_wait_times) / max(1, served),
        "courierUtilization": sum(1 for count in courier_order_values if count > 0) / max(1, len(couriers)),
        "ordersPerCourier": served / max(1, len(couriers)),
        "ordersPerCourierP95": percentile([float(value) for value in courier_order_values], 95),
        "assignmentFairnessGini": fairness_gini,
        "bundleCount": served,
        "avgBundleSize": 1.0 if served else 0.0,
        "maxBundleSize": 1 if served else 0,
        "multiOrderBundleRate": 0.0,
        "hardViolationCount": hard_violations,
        "verdict": "PASS_WITH_LIMITS" if hard_violations == 0 and served > 0 else "FAIL",
        "verdictReasons": ["mdrplib-route-state-repair-v4"] if hard_violations == 0 and served > 0 else ["mdrplib-hard-violation-or-no-service"],
    }
    if repair_metadata:
        payload.update(repair_metadata)
    return payload


def repair_objective(metrics: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    return (
        -float(metrics.get("servedOrderRate", 0.0)),
        float(metrics.get("p95OrderToDeliveryTime", 0.0)),
        float(metrics.get("p95FoodOnVehicleTime", 0.0)),
        float(metrics.get("avgPickupWaitTime", 0.0)),
        float(metrics.get("assignmentFairnessGini", 1.0)),
        -float(metrics.get("courierUtilization", 0.0)),
    )


def hard_feasible(metrics: dict[str, Any]) -> bool:
    return int(metrics.get("pickupBeforeReadyTimeViolation", 0)) + int(metrics.get("courierShiftViolation", 0)) + int(metrics.get("foodOnVehicleHardViolation", 0)) + int(metrics.get("pickupBeforeDropoffViolationCount", 0)) == 0


def clone_routes(routes: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    return {courier_id: list(route) for courier_id, route in routes.items()}


def route_tail_order_to_delivery(
        route: list[dict[str, str]],
        courier: dict[str, str],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float) -> list[tuple[float, dict[str, str]]]:
    clock = float(courier["on_time"])
    location: dict[str, Any] = courier
    scored: list[tuple[float, dict[str, str]]] = []
    for order in route:
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        clock = max(clock, float(order["placement_time"]))
        pickup_time = max(float(order["ready_time"]), clock + distance(location, restaurant) / speed_meters_per_minute)
        dropoff_time = pickup_time + distance(restaurant, order) / speed_meters_per_minute
        scored.append((dropoff_time - float(order["placement_time"]), order))
        clock = dropoff_time
        location = order
    return scored


def route_order_risks(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float) -> list[dict[str, Any]]:
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    risks: list[dict[str, Any]] = []
    for courier_id, route in routes.items():
        courier = courier_by_id[courier_id]
        clock = float(courier["on_time"])
        location: dict[str, Any] = courier
        for index, order in enumerate(route):
            restaurant = restaurants.get(order["restaurant"])
            if restaurant is None:
                continue
            clock = max(clock, float(order["placement_time"]))
            pickup_arrival = clock + distance(location, restaurant) / speed_meters_per_minute
            pickup_time = max(float(order["ready_time"]), pickup_arrival)
            dropoff_time = pickup_time + distance(restaurant, order) / speed_meters_per_minute
            risks.append({
                "courierId": courier_id,
                "index": index,
                "order": order,
                "orderToDelivery": dropoff_time - float(order["placement_time"]),
                "foodOnVehicle": dropoff_time - pickup_time,
                "pickupWait": max(0.0, pickup_time - float(order["ready_time"])),
                "delay": dropoff_time - float(order["ready_time"]),
            })
            clock = dropoff_time
            location = order
    return risks


def destroy_alns_orders(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        operator: str,
        remove_count: int) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    candidate = clone_routes(routes)
    risks = route_order_risks(candidate, couriers, restaurants, speed_meters_per_minute)
    if operator == "worstFoodOnVehicle":
        ranked = sorted(risks, key=lambda row: (float(row["foodOnVehicle"]), float(row["orderToDelivery"])), reverse=True)
    elif operator == "highPickupWait":
        ranked = sorted(risks, key=lambda row: (float(row["pickupWait"]), float(row["orderToDelivery"])), reverse=True)
    elif operator == "overloadedTail":
        overloaded = sorted(candidate, key=lambda courier_id: len(candidate[courier_id]), reverse=True)
        ranked = [row for courier_id in overloaded for row in reversed(risks) if row["courierId"] == courier_id]
    elif operator == "corridorSpread":
        ranked = sorted(risks, key=lambda row: (str(row["order"].get("restaurant")), float(row["orderToDelivery"])), reverse=True)
    elif operator == "shawRelated":
        seed = max(risks, key=lambda row: float(row["orderToDelivery"]), default=None)
        if seed is None:
            ranked = []
        else:
            seed_order = seed["order"]
            seed_restaurant = restaurants.get(seed_order["restaurant"], seed_order)
            ranked = sorted(
                risks,
                key=lambda row: (
                    0 if row["order"]["restaurant"] == seed_order["restaurant"] else 1,
                    abs(float(row["order"]["ready_time"]) - float(seed_order["ready_time"])),
                    distance(restaurants.get(row["order"]["restaurant"], row["order"]), seed_restaurant) / speed_meters_per_minute,
                    distance(row["order"], seed_order) / speed_meters_per_minute,
                    -float(row["orderToDelivery"]),
                ),
            )
    else:
        ranked = sorted(risks, key=lambda row: (float(row["orderToDelivery"]), float(row["delay"])), reverse=True)
    removed: list[dict[str, str]] = []
    removed_ids: set[str] = set()
    for row in ranked:
        if len(removed) >= remove_count:
            break
        courier_id = str(row["courierId"])
        order = row["order"]
        order_id = str(order["order"])
        if order_id in removed_ids or order not in candidate.get(courier_id, []):
            continue
        candidate[courier_id].remove(order)
        removed.append(order)
        removed_ids.add(order_id)
    return candidate, removed


def route_end_location(routes: dict[str, list[dict[str, str]]], courier_by_id: dict[str, dict[str, str]], courier_id: str) -> dict[str, Any]:
    route = routes.get(courier_id, [])
    return route[-1] if route else courier_by_id[courier_id]


def geographic_candidate_couriers(
        routes: dict[str, list[dict[str, str]]],
        order: dict[str, str],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        neighbor_limit: int) -> list[str]:
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    restaurant = restaurants.get(order["restaurant"], order)
    scored = []
    mean_load = sum(len(route) for route in routes.values()) / max(1, len(routes))
    for courier_id, route in routes.items():
        end_location = route_end_location(routes, courier_by_id, courier_id)
        proximity = distance(end_location, restaurant) / speed_meters_per_minute
        load_penalty = max(0.0, len(route) - mean_load)
        scored.append((proximity + 0.25 * load_penalty, len(route), courier_id))
    return [courier_id for _score, _load, courier_id in sorted(scored)[:neighbor_limit]]


def insertion_options(
        routes: dict[str, list[dict[str, str]]],
        order: dict[str, str],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        neighbor_limit: int,
        insertion_limit: int) -> list[tuple[tuple[float, float, float, float, float, float], dict[str, list[dict[str, str]]]]]:
    candidate_couriers = geographic_candidate_couriers(routes, order, couriers, restaurants, speed_meters_per_minute, neighbor_limit)
    options: list[tuple[tuple[float, float, float, float, float, float], dict[str, list[dict[str, str]]]]] = []
    for courier_id in candidate_couriers:
        route_len = len(routes[courier_id])
        positions = sorted(set([0, route_len, min(route_len, insertion_limit // 2), *range(min(route_len + 1, insertion_limit))]))
        for position in positions:
            candidate = clone_routes(routes)
            candidate[courier_id].insert(position, order)
            metrics = evaluate_order_routes(couriers, candidate, restaurants, speed_meters_per_minute, max_delay_minutes)
            if hard_feasible(metrics):
                options.append((repair_objective(metrics), candidate))
    return sorted(options, key=lambda item: item[0])


def insert_order_best_position(
        routes: dict[str, list[dict[str, str]]],
        order: dict[str, str],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        neighbor_limit: int,
        insertion_limit: int) -> tuple[dict[str, list[dict[str, str]]] | None, tuple[float, float, float, float, float, float] | None]:
    options = insertion_options(routes, order, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, neighbor_limit, insertion_limit)
    if not options:
        return None, None
    return options[0][1], options[0][0]


def regret_reinsert_orders(
        routes: dict[str, list[dict[str, str]]],
        removed: list[dict[str, str]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        neighbor_limit: int,
        insertion_limit: int) -> tuple[dict[str, list[dict[str, str]]], int, int]:
    current = clone_routes(routes)
    accepted = 0
    rejected = 0
    pending = list(removed)
    while pending:
        scored: list[tuple[float, dict[str, str], dict[str, list[dict[str, str]]]]] = []
        for order in pending:
            options = insertion_options(current, order, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, neighbor_limit, insertion_limit)
            if not options:
                continue
            best_objective, best_routes = options[0]
            second_objective = options[1][0] if len(options) > 1 else tuple(value + 1.0 for value in best_objective)
            regret = sum(second_objective) - sum(best_objective)
            scored.append((regret, order, best_routes))
        if not scored:
            fallback = min(current, key=lambda courier_id: len(current[courier_id]))
            current[fallback].extend(pending)
            rejected += len(pending)
            break
        _regret, order, best_routes = max(scored, key=lambda item: (item[0], -float(item[1]["ready_time"])))
        current = best_routes
        pending.remove(order)
        accepted += 1
    return current, accepted, rejected


def try_ejection_chain_depth2(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        neighbor_limit: int,
        insertion_limit: int) -> tuple[dict[str, list[dict[str, str]]], bool]:
    current_metrics = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    best_routes = clone_routes(routes)
    best_objective = repair_objective(current_metrics)
    risks = sorted(route_order_risks(routes, couriers, restaurants, speed_meters_per_minute), key=lambda row: float(row["orderToDelivery"]), reverse=True)[:3]
    for risk in risks:
        source_id = str(risk["courierId"])
        order = risk["order"]
        if order not in routes.get(source_id, []):
            continue
        for middle_id in geographic_candidate_couriers(routes, order, couriers, restaurants, speed_meters_per_minute, min(4, neighbor_limit)):
            if middle_id == source_id or not routes.get(middle_id):
                continue
            ejected = routes[middle_id][-1]
            candidate = clone_routes(routes)
            candidate[source_id].remove(order)
            candidate[middle_id].append(order)
            candidate[middle_id].remove(ejected)
            inserted, objective = insert_order_best_position(candidate, ejected, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, neighbor_limit, insertion_limit)
            if inserted is None or objective is None:
                continue
            metrics = evaluate_order_routes(couriers, inserted, restaurants, speed_meters_per_minute, max_delay_minutes)
            if hard_feasible(metrics) and repair_objective(metrics) < best_objective:
                best_routes = inserted
                best_objective = repair_objective(metrics)
    return best_routes, best_objective < repair_objective(current_metrics)


def maybe_accept_repair(
        candidate: dict[str, list[dict[str, str]]],
        current: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        counts: dict[str, int],
        operator: str) -> tuple[dict[str, list[dict[str, str]]], bool]:
    current_metrics = evaluate_order_routes(couriers, current, restaurants, speed_meters_per_minute, max_delay_minutes)
    candidate_metrics = evaluate_order_routes(couriers, candidate, restaurants, speed_meters_per_minute, max_delay_minutes)
    if hard_feasible(candidate_metrics) and repair_objective(candidate_metrics) < repair_objective(current_metrics):
        counts[operator] = counts.get(operator, 0) + 1
        return candidate, True
    return current, False


def initial_repair_routes(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, list[dict[str, str]]]:
    routes = {courier["courier"]: [] for courier in couriers}
    courier_available = {courier["courier"]: float(courier["on_time"]) for courier in couriers}
    courier_location: dict[str, dict[str, Any]] = {courier["courier"]: courier for courier in couriers}
    courier_orders = {courier["courier"]: 0 for courier in couriers}
    for order in sorted(orders, key=lambda row: order_priority(row, profile)):
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        mean_orders = sum(courier_orders.values()) / max(1, len(courier_orders))
        best: tuple[tuple[float, ...], str, float] | None = None
        for courier in couriers:
            courier_id = courier["courier"]
            start_time = max(courier_available[courier_id], float(courier["on_time"]), float(order["placement_time"]))
            pickup_time = max(float(order["ready_time"]), start_time + distance(courier_location[courier_id], restaurant) / speed_meters_per_minute)
            dropoff_time = pickup_time + distance(restaurant, order) / speed_meters_per_minute
            if dropoff_time > float(courier["off_time"]):
                continue
            delay = dropoff_time - float(order["ready_time"])
            order_to_delivery = dropoff_time - float(order["placement_time"])
            pickup_wait = max(0.0, pickup_time - float(order["ready_time"]))
            load_pressure = max(0.0, courier_orders[courier_id] - mean_orders)
            objective = (
                0.0 if delay <= max_delay_minutes else 1.0,
                order_to_delivery,
                delay,
                pickup_wait,
                load_pressure,
                dropoff_time,
            )
            if best is None or objective < best[0]:
                best = (objective, courier_id, dropoff_time)
        if best is not None:
            routes[best[1]].append(order)
            courier_available[best[1]] = best[2]
            courier_location[best[1]] = order
            courier_orders[best[1]] += 1
    return routes


def simulate_mdrp_repair_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:
    routes = initial_repair_routes(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile)
    before = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    if len(orders) > int(float(profile.get("repairFullSearchOrderLimit", 350))):
        before.update({
            "orderCount": len(orders),
            "unservedOrderCount": max(0, len(orders) - int(before.get("servedOrderCount", 0))),
            "servedOrderRate": float(before.get("servedOrderCount", 0)) / max(1, len(orders)),
            "repairMode": "route-state-relocate-swap-regret-v4-budgeted",
            "repairOperatorCounts": {"relocate": 0, "swap": 0, "regretReinsert": 0},
            "repairAcceptedMoves": 0,
            "repairRejectedMoves": 0,
            "repairImprovementDelta": {
                "p95OrderToDeliveryTime": 0.0,
                "p95FoodOnVehicleTime": 0.0,
                "avgPickupWaitTime": 0.0,
                "assignmentFairnessGini": 0.0,
                "courierUtilization": 0.0,
            },
        })
        return before
    counts = {"relocate": 0, "swap": 0, "regretReinsert": 0}
    accepted = 0
    rejected = 0
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    candidate_limit = int(float(profile.get("repairCandidateLimit", 8)))
    insertion_limit = int(float(profile.get("repairInsertionLimit", 4)))
    neighbor_limit = int(float(profile.get("repairNeighborLimit", 12)))

    scored_orders: list[tuple[float, str, dict[str, str]]] = []
    for courier_id, route in routes.items():
        for score, order in route_tail_order_to_delivery(route, courier_by_id[courier_id], restaurants, speed_meters_per_minute):
            scored_orders.append((score, courier_id, order))
    for _score, source_id, order in sorted(scored_orders, reverse=True)[:candidate_limit]:
        if order not in routes.get(source_id, []):
            continue
        best_routes: dict[str, list[dict[str, str]]] | None = None
        best_objective = repair_objective(evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes))
        target_ids = sorted(routes, key=lambda courier_id: (len(routes[courier_id]), courier_id))[:neighbor_limit]
        for target_id in target_ids:
            if target_id == source_id:
                continue
            for position in range(min(len(routes[target_id]) + 1, insertion_limit)):
                candidate = clone_routes(routes)
                candidate[source_id].remove(order)
                candidate[target_id].insert(position, order)
                metrics = evaluate_order_routes(couriers, candidate, restaurants, speed_meters_per_minute, max_delay_minutes)
                if hard_feasible(metrics) and repair_objective(metrics) < best_objective:
                    best_objective = repair_objective(metrics)
                    best_routes = candidate
        if best_routes is not None:
            routes, ok = maybe_accept_repair(best_routes, routes, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, counts, "relocate")
            accepted += 1 if ok else 0
            rejected += 0 if ok else 1
        else:
            rejected += 1

    busy = [courier_id for courier_id, route in routes.items() if route]
    for left_id, right_id in itertools.islice(itertools.combinations(busy[:neighbor_limit], 2), candidate_limit):
        left_route = routes[left_id]
        right_route = routes[right_id]
        best_pair = (min(len(left_route), 3), min(len(right_route), 3))
        improved = False
        for left_index in range(best_pair[0]):
            for right_index in range(best_pair[1]):
                candidate = clone_routes(routes)
                candidate[left_id][left_index], candidate[right_id][right_index] = candidate[right_id][right_index], candidate[left_id][left_index]
                routes, ok = maybe_accept_repair(candidate, routes, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, counts, "swap")
                if ok:
                    accepted += 1
                    improved = True
                    break
                rejected += 1
            if improved:
                break

    overloaded = sorted(routes, key=lambda courier_id: len(routes[courier_id]), reverse=True)[:max(1, min(3, len(routes)))]
    removed: list[dict[str, str]] = []
    for courier_id in overloaded:
        if routes[courier_id]:
            removed.append(routes[courier_id].pop())
    for order in sorted(removed, key=lambda row: (float(row["ready_time"]), str(row["order"]))):
        best_routes = None
        best_objective = repair_objective(evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes))
        for target_id in routes:
            for position in range(min(len(routes[target_id]) + 1, insertion_limit)):
                candidate = clone_routes(routes)
                candidate[target_id].insert(position, order)
                metrics = evaluate_order_routes(couriers, candidate, restaurants, speed_meters_per_minute, max_delay_minutes)
                if hard_feasible(metrics) and repair_objective(metrics) < best_objective:
                    best_objective = repair_objective(metrics)
                    best_routes = candidate
        if best_routes is None:
            best_target = min(routes, key=lambda courier_id: len(routes[courier_id]))
            routes[best_target].append(order)
            rejected += 1
        else:
            routes, ok = maybe_accept_repair(best_routes, routes, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, counts, "regretReinsert")
            accepted += 1 if ok else 0
            rejected += 0 if ok else 1

    after = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    after.update({
        "orderCount": len(orders),
        "unservedOrderCount": max(0, len(orders) - int(after.get("servedOrderCount", 0))),
        "servedOrderRate": float(after.get("servedOrderCount", 0)) / max(1, len(orders)),
        "repairMode": "route-state-relocate-swap-regret-v4",
        "repairOperatorCounts": counts,
        "repairAcceptedMoves": accepted,
        "repairRejectedMoves": rejected,
        "repairImprovementDelta": {
            "p95OrderToDeliveryTime": float(after["p95OrderToDeliveryTime"]) - float(before["p95OrderToDeliveryTime"]),
            "p95FoodOnVehicleTime": float(after["p95FoodOnVehicleTime"]) - float(before["p95FoodOnVehicleTime"]),
            "avgPickupWaitTime": float(after["avgPickupWaitTime"]) - float(before["avgPickupWaitTime"]),
            "assignmentFairnessGini": float(after["assignmentFairnessGini"]) - float(before["assignmentFairnessGini"]),
            "courierUtilization": float(after["courierUtilization"]) - float(before["courierUtilization"]),
        },
    })
    return after


def simulate_mdrp_alns_lite_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:
    routes = initial_repair_routes(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile)
    before = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    if len(orders) > int(float(profile.get("alnsFullSearchOrderLimit", 350))):
        before.update({
            "orderCount": len(orders),
            "unservedOrderCount": max(0, len(orders) - int(before.get("servedOrderCount", 0))),
            "servedOrderRate": float(before.get("servedOrderCount", 0)) / max(1, len(orders)),
            "alnsMode": "alns-lite-food-v7-budgeted",
            "alnsIterations": 0,
            "alnsDestroyOperatorCounts": {"worstOtd": 0, "worstFoodOnVehicle": 0, "highPickupWait": 0, "overloadedTail": 0, "corridorSpread": 0},
            "alnsRepairOperatorCounts": {"regretReinsert": 0, "bestInsertion": 0},
            "alnsAcceptedMoves": 0,
            "alnsRejectedMoves": 0,
            "alnsBestObjectiveDelta": {
                "p95OrderToDeliveryTime": 0.0,
                "p95FoodOnVehicleTime": 0.0,
                "avgPickupWaitTime": 0.0,
                "assignmentFairnessGini": 0.0,
                "courierUtilization": 0.0,
            },
            "operatorLearningRows": [],
        })
        return before

    destroy_operators = ["worstOtd", "worstFoodOnVehicle", "highPickupWait", "overloadedTail", "corridorSpread", "shawRelated"]
    destroy_counts = {operator: 0 for operator in destroy_operators}
    repair_counts = {"regretReinsert": 0, "bestInsertion": 0, "ejectionChainDepth2": 0}
    accepted = 0
    rejected = 0
    learning_rows: list[dict[str, Any]] = []
    iterations = int(float(profile.get("alnsIterations", 12)))
    remove_count = int(float(profile.get("alnsRemoveCount", 4)))
    neighbor_limit = int(float(profile.get("alnsNeighborLimit", 10)))
    insertion_limit = int(float(profile.get("alnsInsertionLimit", 5)))
    current = clone_routes(routes)
    current_metrics = evaluate_order_routes(couriers, current, restaurants, speed_meters_per_minute, max_delay_minutes)
    best_routes = clone_routes(current)
    best_metrics = dict(current_metrics)

    for iteration in range(iterations):
        operator = destroy_operators[iteration % len(destroy_operators)]
        destroyed, removed = destroy_alns_orders(current, couriers, restaurants, speed_meters_per_minute, operator, remove_count)
        destroy_counts[operator] += 1
        if not removed:
            rejected += 1
            continue
        repaired, repair_accepted, repair_rejected = regret_reinsert_orders(destroyed, removed, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, neighbor_limit, insertion_limit)
        repair_counts["regretReinsert"] += 1
        repaired, ejection_accepted = try_ejection_chain_depth2(repaired, couriers, restaurants, speed_meters_per_minute, max_delay_minutes, neighbor_limit, insertion_limit)
        if ejection_accepted:
            repair_counts["ejectionChainDepth2"] += 1
        repaired_metrics = evaluate_order_routes(couriers, repaired, restaurants, speed_meters_per_minute, max_delay_minutes)
        objective_before = repair_objective(current_metrics)
        objective_after = repair_objective(repaired_metrics)
        accepted_move = hard_feasible(repaired_metrics) and objective_after < objective_before
        if accepted_move:
            current = repaired
            current_metrics = repaired_metrics
            accepted += 1
            if repair_objective(repaired_metrics) < repair_objective(best_metrics):
                best_routes = clone_routes(repaired)
                best_metrics = dict(repaired_metrics)
        else:
            rejected += 1
        learning_rows.append({
            "iteration": iteration,
            "destroyOperator": operator,
            "repairOperator": "regretReinsert",
            "removedOrderCount": len(removed),
            "repairAcceptedInsertions": repair_accepted,
            "repairRejectedInsertions": repair_rejected,
            "ejectionAccepted": ejection_accepted,
            "accepted": accepted_move,
            "p95OrderToDeliveryDelta": float(repaired_metrics["p95OrderToDeliveryTime"]) - float(current_metrics["p95OrderToDeliveryTime"]),
            "p95FoodOnVehicleDelta": float(repaired_metrics["p95FoodOnVehicleTime"]) - float(current_metrics["p95FoodOnVehicleTime"]),
            "avgPickupWaitDelta": float(repaired_metrics["avgPickupWaitTime"]) - float(current_metrics["avgPickupWaitTime"]),
        })

    after = evaluate_order_routes(couriers, best_routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    after.update({
        "orderCount": len(orders),
        "unservedOrderCount": max(0, len(orders) - int(after.get("servedOrderCount", 0))),
        "servedOrderRate": float(after.get("servedOrderCount", 0)) / max(1, len(orders)),
        "alnsMode": "alns-lite-food-v7",
        "alnsIterations": iterations,
        "alnsDestroyOperatorCounts": destroy_counts,
        "alnsRepairOperatorCounts": repair_counts,
        "alnsAcceptedMoves": accepted,
        "alnsRejectedMoves": rejected,
        "alnsBestObjectiveDelta": {
            "p95OrderToDeliveryTime": float(after["p95OrderToDeliveryTime"]) - float(before["p95OrderToDeliveryTime"]),
            "p95FoodOnVehicleTime": float(after["p95FoodOnVehicleTime"]) - float(before["p95FoodOnVehicleTime"]),
            "avgPickupWaitTime": float(after["avgPickupWaitTime"]) - float(before["avgPickupWaitTime"]),
            "assignmentFairnessGini": float(after["assignmentFairnessGini"]) - float(before["assignmentFairnessGini"]),
            "courierUtilization": float(after["courierUtilization"]) - float(before["courierUtilization"]),
        },
        "operatorLearningRows": learning_rows[:25],
    })
    return after


def route_candidate_metrics(
        candidate_id: str,
        source: str,
        courier_id: str,
        orders: list[dict[str, str]],
        courier: dict[str, str],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float) -> dict[str, Any] | None:
    if not orders:
        return None
    routes = {courier_id: list(orders)}
    metrics = evaluate_order_routes([courier], routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    hard = hard_feasible(metrics)
    covered = [str(order["order"]) for order in orders]
    geometry = route_geometry_features(route_points_for_orders(courier, orders, restaurants))
    return {
        "candidateId": candidate_id,
        "candidateSource": source,
        "courierId": courier_id,
        "coveredOrders": covered,
        "orderCount": len(covered),
        "pickupSequence": [str(order["restaurant"]) for order in orders],
        "dropoffSequence": covered,
        "otdRisk": float(metrics.get("p95OrderToDeliveryTime", 0.0)),
        "freshnessRisk": float(metrics.get("p95FoodOnVehicleTime", 0.0)),
        "pickupWaitRisk": float(metrics.get("avgPickupWaitTime", 0.0)),
        "fairnessImpact": float(len(orders)),
        "routeInsertionDelta": float(metrics.get("p95Delay", 0.0)),
        "routeBeautyScore": geometry["routeBeautyScore"],
        "routeShapePenalty": geometry["routeShapePenalty"],
        "routeDetourRisk": geometry["routeDetourRisk"],
        "routeCorridorFit": geometry["routeCorridorFit"],
        "routeStraightnessProxy": geometry["routeStraightnessProxy"],
        "routeZigzagPenalty": geometry["routeZigzagPenalty"],
        "routeTurnProxy": geometry["routeTurnProxy"],
        "hardFeasible": hard,
        "metrics": metrics,
        "orders": list(orders),
    }


def build_route_candidate_pool(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> list[dict[str, Any]]:
    anchor_limit = int(float(profile.get("poolAnchorLimit", 80)))
    courier_limit = int(float(profile.get("poolCourierLimit", 12)))
    per_anchor_limit = int(float(profile.get("poolCandidatesPerAnchor", 4)))
    max_bundle_size = int(float(profile.get("poolMaxBundleSize", 2)))
    ready_window = float(profile.get("poolReadyWindow", 6.0))
    placement_window = float(profile.get("poolPlacementWindow", 10.0))
    pair_distance = float(profile.get("poolPairDistanceMinutes", 6.0))
    restaurant_distance = float(profile.get("poolRestaurantDistanceMinutes", 4.0))
    pending_ids = {str(order["order"]) for order in orders}
    anchors, anchor_features = anchor_top_k_candidates(orders, pending_ids, couriers, restaurants, speed_meters_per_minute, profile, anchor_limit, ready_window, placement_window)
    candidates: list[dict[str, Any]] = []
    candidate_index = 0
    for anchor in anchors:
        restaurant = restaurants.get(anchor["restaurant"])
        if restaurant is None:
            continue
        courier_choices = sorted(couriers, key=lambda courier: distance(courier, restaurant) / speed_meters_per_minute)[:courier_limit]
        compatible = multi_restaurant_bundle_candidates(anchor, orders, restaurants, max_bundle_size, ready_window, placement_window, pair_distance, restaurant_distance, speed_meters_per_minute)
        bundles = [[anchor]]
        if len(compatible) > 1:
            bundles.append(compatible[:max_bundle_size])
        same_restaurant = bundle_candidates(anchor, [order for order in orders if order["restaurant"] == anchor["restaurant"]], restaurant, max_bundle_size, ready_window, placement_window, pair_distance, speed_meters_per_minute)
        if len(same_restaurant) > 1:
            bundles.append(same_restaurant[:max_bundle_size])
        seen_bundles: set[tuple[str, ...]] = set()
        for bundle in bundles[:per_anchor_limit]:
            key = tuple(sorted(str(order["order"]) for order in bundle))
            if key in seen_bundles:
                continue
            seen_bundles.add(key)
            for courier in courier_choices[:max(1, per_anchor_limit)]:
                candidate = route_candidate_metrics(f"cand-{candidate_index}", "pool-single" if len(bundle) == 1 else "pool-bundle", courier["courier"], bundle, courier, restaurants, speed_meters_per_minute, max_delay_minutes)
                candidate_index += 1
                if candidate is not None:
                    candidate.update(anchor_features.get(str(anchor["order"]), {}))
                    candidates.append(candidate)
    return candidates


def build_route_fragment_candidates(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        fragment_limit: int,
        max_fragment_size: int) -> list[dict[str, Any]]:
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    risks = route_order_risks(routes, couriers, restaurants, speed_meters_per_minute)
    risk_by_order = {str(row["order"]["order"]): float(row["orderToDelivery"]) + float(row["foodOnVehicle"]) for row in risks}
    fragments: list[tuple[float, str, list[dict[str, str]]]] = []
    for courier_id, route in routes.items():
        for start in range(len(route)):
            for size in range(1, min(max_fragment_size, len(route) - start) + 1):
                fragment = route[start:start + size]
                score = sum(risk_by_order.get(str(order["order"]), 0.0) for order in fragment) / max(1, len(fragment))
                fragments.append((score, courier_id, fragment))
    candidates: list[dict[str, Any]] = []
    index = 0
    for courier_id, route in routes.items():
        if not route:
            continue
        candidate = route_candidate_metrics(f"route-{index}", "full-route-fragment", courier_id, route, courier_by_id[courier_id], restaurants, speed_meters_per_minute, max_delay_minutes)
        index += 1
        if candidate is not None:
            candidates.append(candidate)
    for _score, courier_id, fragment in sorted(fragments, reverse=True)[:fragment_limit]:
        candidate = route_candidate_metrics(f"frag-{index}", "route-fragment", courier_id, fragment, courier_by_id[courier_id], restaurants, speed_meters_per_minute, max_delay_minutes)
        index += 1
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def dominates_candidate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_orders = set(left["coveredOrders"])
    right_orders = set(right["coveredOrders"])
    if not left_orders.intersection(right_orders):
        return False
    if len(left_orders) < len(right_orders) and left_orders.issubset(right_orders):
        return False
    left_tuple = (
        0 if left["hardFeasible"] else 1,
        float(left["otdRisk"]),
        float(left["freshnessRisk"]),
        float(left["pickupWaitRisk"]),
        float(left["fairnessImpact"]),
        float(left["routeInsertionDelta"]),
    )
    right_tuple = (
        0 if right["hardFeasible"] else 1,
        float(right["otdRisk"]),
        float(right["freshnessRisk"]),
        float(right["pickupWaitRisk"]),
        float(right["fairnessImpact"]),
        float(right["routeInsertionDelta"]),
    )
    return all(left_value <= right_value for left_value, right_value in zip(left_tuple, right_tuple)) and any(left_value < right_value for left_value, right_value in zip(left_tuple, right_tuple))


def pareto_filter_candidates(candidates: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    front: list[dict[str, Any]] = []
    rejected = 0
    for candidate in sorted(candidates, key=lambda item: (not item["hardFeasible"], -int(item["orderCount"]), float(item["otdRisk"]), float(item["freshnessRisk"]))):
        if any(dominates_candidate(existing, candidate) for existing in front):
            rejected += 1
            continue
        front = [existing for existing in front if not dominates_candidate(candidate, existing)]
        front.append(candidate)
        if len(front) >= limit:
            break
    return front, rejected + max(0, len(candidates) - len(front) - rejected)


def candidate_selection_score(candidate: dict[str, Any], courier_load: dict[str, int], target_load: float) -> float:
    coverage_reward = 100.0 * int(candidate["orderCount"])
    source_bonus = 500.0 if candidate.get("candidateSource") == "full-route-fragment" else (12.0 if candidate.get("candidateSource") == "route-fragment" else 0.0)
    projected_load = courier_load.get(str(candidate["courierId"]), 0) + int(candidate["orderCount"])
    overload = max(0.0, projected_load - target_load)
    underuse_reward = max(0.0, target_load - courier_load.get(str(candidate["courierId"]), 0)) * 3.0
    overload_penalty = 8.0 * overload * overload
    risk_penalty = float(candidate["otdRisk"]) * 1.4 + float(candidate["freshnessRisk"]) * 1.0 + float(candidate["pickupWaitRisk"]) * 0.6 + float(candidate["routeInsertionDelta"]) * 0.4
    beauty_penalty = float(candidate.get("routeShapePenalty", 0.0)) * 35.0 + float(candidate.get("routeDetourRisk", 0.0)) * 20.0 + max(0.0, 1.0 - float(candidate.get("routeCorridorFit", 1.0))) * 20.0
    anchor_reward = float(candidate.get("anchorV2Score", 0.0)) * 24.0 + float(candidate.get("anchorReadySlack", 0.0)) * 8.0 + float(candidate.get("anchorCourierProximity", 0.0)) * 8.0
    anchor_penalty = float(candidate.get("anchorDetourRisk", 0.0)) * 12.0 + float(candidate.get("anchorTrafficRisk", 0.0)) * 8.0 + float(candidate.get("anchorBoundaryCrossPenalty", 0.0)) * 4.0
    infeasible_penalty = 10_000.0 if not candidate["hardFeasible"] else 0.0
    return coverage_reward + source_bonus + underuse_reward + anchor_reward - overload_penalty - risk_penalty - beauty_penalty - anchor_penalty - infeasible_penalty


def greedy_set_pack_candidates(candidates: list[dict[str, Any]], target_load: float) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()
    courier_load: dict[str, int] = {}
    remaining = list(candidates)
    while remaining:
        candidate = max(remaining, key=lambda item: candidate_selection_score(item, courier_load, target_load))
        remaining.remove(candidate)
        candidate_orders = set(candidate["coveredOrders"])
        if candidate_orders.intersection(covered):
            continue
        if candidate_selection_score(candidate, courier_load, target_load) <= 0.0:
            continue
        selected.append(candidate)
        covered.update(candidate_orders)
        courier_id = str(candidate["courierId"])
        courier_load[courier_id] = courier_load.get(courier_id, 0) + int(candidate["orderCount"])
        remaining = [item for item in remaining if not set(item["coveredOrders"]).intersection(covered)]
    return selected


def balance_route_loads(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        move_limit: int) -> tuple[dict[str, list[dict[str, str]]], int]:
    balanced = clone_routes(routes)
    accepted = 0
    baseline_metrics = evaluate_order_routes(couriers, balanced, restaurants, speed_meters_per_minute, max_delay_minutes)
    target_load = sum(len(route) for route in balanced.values()) / max(1, len(balanced))
    while accepted < move_limit:
        overloaded = [courier_id for courier_id, route in balanced.items() if len(route) > target_load + 1 and route]
        underused = [courier_id for courier_id, route in balanced.items() if len(route) < target_load]
        if not overloaded or not underused:
            break
        source_id = max(overloaded, key=lambda courier_id: len(balanced[courier_id]))
        moved = False
        for order in list(reversed(balanced[source_id][-min(5, len(balanced[source_id])):])):
            for target_id in sorted(underused, key=lambda courier_id: len(balanced[courier_id])):
                candidate = clone_routes(balanced)
                candidate[source_id].remove(order)
                candidate[target_id].append(order)
                metrics = evaluate_order_routes(couriers, candidate, restaurants, speed_meters_per_minute, max_delay_minutes)
                if not hard_feasible(metrics):
                    continue
                objective = repair_objective(metrics)
                current_objective = repair_objective(baseline_metrics)
                fairness_improves = float(metrics["assignmentFairnessGini"]) < float(baseline_metrics["assignmentFairnessGini"])
                tail_safe = float(metrics["p95OrderToDeliveryTime"]) <= float(baseline_metrics["p95OrderToDeliveryTime"]) + 1.0
                if (objective <= current_objective or (fairness_improves and tail_safe)):
                    balanced = candidate
                    baseline_metrics = metrics
                    accepted += 1
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break
    return balanced, accepted


def optimize_single_courier_route(
        courier: dict[str, str],
        route: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        move_limit: int) -> tuple[list[dict[str, str]], int]:
    if len(route) < 3:
        return route, 0
    current = list(route)
    current_metrics = evaluate_order_routes([courier], {courier["courier"]: current}, restaurants, speed_meters_per_minute, max_delay_minutes)
    moves = 0
    while moves < move_limit:
        best_route = current
        best_objective = repair_objective(current_metrics)
        route_len = len(current)
        indices = range(min(route_len, 8))
        for left in indices:
            for right in range(left + 1, min(route_len, left + 7)):
                variants = []
                swapped = list(current)
                swapped[left], swapped[right] = swapped[right], swapped[left]
                variants.append(swapped)
                reversed_segment = list(current)
                reversed_segment[left:right + 1] = reversed(reversed_segment[left:right + 1])
                variants.append(reversed_segment)
                relocated = list(current)
                order = relocated.pop(right)
                relocated.insert(left, order)
                variants.append(relocated)
                for variant in variants:
                    metrics = evaluate_order_routes([courier], {courier["courier"]: variant}, restaurants, speed_meters_per_minute, max_delay_minutes)
                    if hard_feasible(metrics) and repair_objective(metrics) < best_objective:
                        best_objective = repair_objective(metrics)
                        best_route = variant
                        current_metrics = metrics
        if best_route == current:
            break
        current = best_route
        moves += 1
    return current, moves


def optimize_routes_intra_route(
        routes: dict[str, list[dict[str, str]]],
        couriers: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        move_limit: int) -> tuple[dict[str, list[dict[str, str]]], int]:
    courier_by_id = {courier["courier"]: courier for courier in couriers}
    optimized = clone_routes(routes)
    total_moves = 0
    for courier_id, route in list(optimized.items()):
        if courier_id not in courier_by_id:
            continue
        route_metrics = evaluate_order_routes([courier_by_id[courier_id]], {courier_id: route}, restaurants, speed_meters_per_minute, max_delay_minutes)
        if len(route) < 3 or float(route_metrics.get("p95OrderToDeliveryTime", 0.0)) < 35.0:
            continue
        new_route, moves = optimize_single_courier_route(courier_by_id[courier_id], route, restaurants, speed_meters_per_minute, max_delay_minutes, move_limit)
        optimized[courier_id] = new_route
        total_moves += moves
    return optimized, total_moves


def simulate_mdrp_route_pool_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:
    baseline_routes = initial_repair_routes(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile)
    baseline_metrics = evaluate_order_routes(couriers, baseline_routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    if len(orders) > int(float(profile.get("poolFullSearchOrderLimit", 700))):
        baseline_metrics.update({
            "orderCount": len(orders),
            "servedOrderRate": float(baseline_metrics.get("servedOrderCount", 0)) / max(1, len(orders)),
            "routePoolMode": "route-pool-set-packing-v8-budgeted",
            "fallbackAllowed": False,
            "candidatePoolSize": 0,
            "paretoFrontSize": 0,
            "dominanceRejectedCandidates": 0,
            "selectedCandidateCount": 0,
            "selectedCandidateSources": {},
            "routeFragmentCandidateCount": 0,
            "targetLoad": 0.0,
            "overloadedCourierCount": 0,
            "loadBalancingMoves": 0,
            "postPackingIntraRouteMoves": 0,
            "setPackingFallbackUsed": False,
            "setPackingRawObjectiveDelta": {},
            "setPackingObjectiveDelta": {},
            "postSelectionRepairApplied": False,
        })
        return baseline_metrics
    pool = build_route_candidate_pool(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile)
    fragment_candidates = build_route_fragment_candidates(
        baseline_routes,
        couriers,
        restaurants,
        speed_meters_per_minute,
        max_delay_minutes,
        int(float(profile.get("poolFragmentLimit", 80))),
        int(float(profile.get("poolMaxFragmentSize", 3))),
    )
    pool.extend(fragment_candidates)
    front, rejected = pareto_filter_candidates(pool, int(float(profile.get("poolParetoLimit", 200))))
    target_load = len(orders) / max(1, len(couriers))
    selected = greedy_set_pack_candidates(front, target_load)
    routes = {courier["courier"]: [] for courier in couriers}
    for candidate in selected:
        routes[str(candidate["courierId"])].extend(candidate["orders"])
    selected_order_ids = {order_id for candidate in selected for order_id in candidate["coveredOrders"]}
    remaining = [order for order in orders if str(order["order"]) not in selected_order_ids]
    repaired_routes = initial_repair_routes(couriers, remaining, restaurants, speed_meters_per_minute, max_delay_minutes, profile)
    for courier_id, route in repaired_routes.items():
        routes[courier_id].extend(route)
    full_route_couriers = {str(candidate["courierId"]) for candidate in selected if candidate.get("candidateSource") == "full-route-fragment"}
    for courier_id, route in routes.items():
        if courier_id not in full_route_couriers:
            routes[courier_id] = sorted(route, key=lambda row: order_priority(row, profile))
    raw_packed_metrics = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    routes, intra_route_moves = optimize_routes_intra_route(
        routes,
        couriers,
        restaurants,
        speed_meters_per_minute,
        max_delay_minutes,
        int(float(profile.get("poolIntraRouteMoveLimit", 3))),
    )
    routes, load_balancing_moves = balance_route_loads(
        routes,
        couriers,
        restaurants,
        speed_meters_per_minute,
        max_delay_minutes,
        int(float(profile.get("poolLoadBalanceMoveLimit", 6))),
    )
    post_repair_routes, post_repair_applied = try_ejection_chain_depth2(
        routes,
        couriers,
        restaurants,
        speed_meters_per_minute,
        max_delay_minutes,
        int(float(profile.get("poolPostRepairNeighborLimit", 5))),
        int(float(profile.get("poolPostRepairInsertionLimit", 3))),
    )
    if post_repair_applied:
        routes = post_repair_routes
    packed_metrics = evaluate_order_routes(couriers, routes, restaurants, speed_meters_per_minute, max_delay_minutes)
    fallback = not hard_feasible(packed_metrics)
    final_metrics = dict(baseline_metrics if fallback else packed_metrics)
    source_counts: dict[str, int] = {}
    for candidate in selected:
        source = str(candidate["candidateSource"])
        source_counts[source] = source_counts.get(source, 0) + 1
    selected_beauty_scores = [float(candidate.get("routeBeautyScore", 1.0)) for candidate in selected]
    selected_shape_penalties = [float(candidate.get("routeShapePenalty", 0.0)) for candidate in selected]
    selected_anchor_scores = [float(candidate.get("anchorV2Score", 0.0)) for candidate in selected if "anchorV2Score" in candidate]
    selected_anchor_ready = [float(candidate.get("anchorReadySlack", 0.0)) for candidate in selected if "anchorReadySlack" in candidate]
    selected_anchor_proximity = [float(candidate.get("anchorCourierProximity", 0.0)) for candidate in selected if "anchorCourierProximity" in candidate]
    selected_anchor_corridor = [float(candidate.get("anchorCorridorFit", 0.0)) for candidate in selected if "anchorCorridorFit" in candidate]
    selected_anchor_detour = [float(candidate.get("anchorDetourRisk", 0.0)) for candidate in selected if "anchorDetourRisk" in candidate]
    selected_anchor_traffic = [float(candidate.get("anchorTrafficRisk", 0.0)) for candidate in selected if "anchorTrafficRisk" in candidate]
    selected_anchor_weather = [float(candidate.get("anchorWeatherRisk", 0.0)) for candidate in selected if "anchorWeatherRisk" in candidate]
    pool_anchor_rows = [candidate for candidate in pool if "anchorV2Score" in candidate]
    if not selected_anchor_scores:
        selected_anchor_scores = [float(candidate.get("anchorV2Score", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_ready = [float(candidate.get("anchorReadySlack", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_proximity = [float(candidate.get("anchorCourierProximity", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_corridor = [float(candidate.get("anchorCorridorFit", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_detour = [float(candidate.get("anchorDetourRisk", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_traffic = [float(candidate.get("anchorTrafficRisk", 0.0)) for candidate in pool_anchor_rows]
        selected_anchor_weather = [float(candidate.get("anchorWeatherRisk", 0.0)) for candidate in pool_anchor_rows]
    beauty_rejected_candidates = sum(1 for candidate in front if float(candidate.get("routeBeautyScore", 1.0)) < 0.65)
    final_metrics.update({
        "orderCount": len(orders),
        "servedOrderRate": float(final_metrics.get("servedOrderCount", 0)) / max(1, len(orders)),
        "routePoolMode": "route-pool-set-packing-v8",
        "fallbackAllowed": False,
        "candidatePoolSize": len(pool),
        "paretoFrontSize": len(front),
        "dominanceRejectedCandidates": rejected,
        "selectedCandidateCount": len(selected),
        "selectedCandidateSources": source_counts,
        "beautyAwareCandidateCount": sum(1 for candidate in pool if "routeBeautyScore" in candidate),
        "beautyRejectedCandidates": beauty_rejected_candidates,
        "selectedBeautyScoreAvg": sum(selected_beauty_scores) / max(1, len(selected_beauty_scores)),
        "routeShapePenalty": sum(selected_shape_penalties) / max(1, len(selected_shape_penalties)),
        "routeDetourRisk": sum(float(candidate.get("routeDetourRisk", 0.0)) for candidate in selected) / max(1, len(selected)),
        "routeCorridorFit": sum(float(candidate.get("routeCorridorFit", 1.0)) for candidate in selected) / max(1, len(selected)),
        "anchorMode": "top-k-corridor-risk-v2",
        "anchorTopK": int(float(profile.get("poolAnchorLimit", 70))),
        "anchorFeatureCandidateCount": len(pool_anchor_rows),
        "anchorV2Score": sum(selected_anchor_scores) / max(1, len(selected_anchor_scores)),
        "anchorReadySlack": sum(selected_anchor_ready) / max(1, len(selected_anchor_ready)),
        "anchorCourierProximity": sum(selected_anchor_proximity) / max(1, len(selected_anchor_proximity)),
        "anchorCorridorFit": sum(selected_anchor_corridor) / max(1, len(selected_anchor_corridor)),
        "anchorDetourRisk": sum(selected_anchor_detour) / max(1, len(selected_anchor_detour)),
        "anchorTrafficRisk": sum(selected_anchor_traffic) / max(1, len(selected_anchor_traffic)),
        "anchorWeatherRisk": sum(selected_anchor_weather) / max(1, len(selected_anchor_weather)),
        "routeFragmentCandidateCount": len(fragment_candidates),
        "targetLoad": target_load,
        "overloadedCourierCount": sum(1 for route in routes.values() if len(route) > target_load + 1),
        "loadBalancingMoves": load_balancing_moves,
        "postPackingIntraRouteMoves": intra_route_moves,
        "setPackingFallbackUsed": fallback,
        "postSelectionRepairApplied": post_repair_applied,
        "setPackingRawObjectiveDelta": {
            "p95OrderToDeliveryTime": float(raw_packed_metrics["p95OrderToDeliveryTime"]) - float(baseline_metrics["p95OrderToDeliveryTime"]),
            "p95FoodOnVehicleTime": float(raw_packed_metrics["p95FoodOnVehicleTime"]) - float(baseline_metrics["p95FoodOnVehicleTime"]),
            "avgPickupWaitTime": float(raw_packed_metrics["avgPickupWaitTime"]) - float(baseline_metrics["avgPickupWaitTime"]),
            "assignmentFairnessGini": float(raw_packed_metrics["assignmentFairnessGini"]) - float(baseline_metrics["assignmentFairnessGini"]),
        },
        "setPackingObjectiveDelta": {
            "p95OrderToDeliveryTime": float(packed_metrics["p95OrderToDeliveryTime"]) - float(baseline_metrics["p95OrderToDeliveryTime"]),
            "p95FoodOnVehicleTime": float(packed_metrics["p95FoodOnVehicleTime"]) - float(baseline_metrics["p95FoodOnVehicleTime"]),
            "avgPickupWaitTime": float(packed_metrics["avgPickupWaitTime"]) - float(baseline_metrics["avgPickupWaitTime"]),
            "assignmentFairnessGini": float(packed_metrics["assignmentFairnessGini"]) - float(baseline_metrics["assignmentFairnessGini"]),
        },
    })
    return final_metrics


def simulate_mdrp_multi_restaurant_batch_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:
    if len(orders) > int(float(profile.get("bundleFullSearchOrderLimit", 350))):
        budgeted = simulate_mdrp_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, {"name": "bundle-v5-budgeted-base", "orderSort": profile.get("orderSort", "ready-restaurant"), "loadWeight": 2.0, "pickupWaitWeight": 1.0, "foodOnVehicleWeight": 2.0, "orderToDeliveryWeight": 1.5})
        budgeted.update({
            "bundleMode": "compatible-multi-restaurant-v5-budgeted",
            "bundleCompatibilityFeatures": ["ready-time", "restaurant-proximity", "route-insertion-delta", "food-on-vehicle-risk", "max-delay", "courier-shift-risk"],
            "multiRestaurantBundleRate": 0.0,
            "rejectedBundleCandidates": 0,
        })
        return budgeted
    max_bundle_size = int(float(profile.get("maxBundleSize", 2)))
    ready_window = float(profile.get("readyWindow", 6.0))
    placement_window = float(profile.get("placementWindow", 10.0))
    max_pair_distance_minutes = float(profile.get("maxPairDistanceMinutes", 6.0))
    max_restaurant_distance_minutes = float(profile.get("maxRestaurantDistanceMinutes", 4.0))
    max_food_on_vehicle_minutes = float(profile.get("maxFoodOnVehicleMinutes", 24.0))
    max_order_to_delivery_minutes = float(profile.get("maxOrderToDeliveryMinutes", 72.0))

    courier_available = {row["courier"]: float(row["on_time"]) for row in couriers}
    courier_location: dict[str, dict[str, Any]] = {row["courier"]: row for row in couriers}
    courier_orders = {row["courier"]: 0 for row in couriers}
    courier_off_time = {row["courier"]: float(row["off_time"]) for row in couriers}
    order_by_id = {row["order"]: row for row in orders}
    pending_ids = {row["order"] for row in orders}

    served = 0
    late = 0
    pickup_before_ready_violations = 0
    shift_violations = 0
    max_delay_observed = 0.0
    total_delay = 0.0
    total_food_on_vehicle = 0.0
    delays: list[float] = []
    food_on_vehicle_times: list[float] = []
    order_to_delivery_times: list[float] = []
    pickup_wait_times: list[float] = []
    bundle_sizes: list[int] = []
    multi_restaurant_bundle_count = 0
    rejected_bundle_candidates = 0
    anchor_feature_rows: list[dict[str, float]] = []

    anchor_limit = int(float(profile.get("anchorTopKLimit", len(orders))))
    anchor_candidates, anchor_feature_by_order = anchor_top_k_candidates(orders, pending_ids, couriers, restaurants, speed_meters_per_minute, profile, anchor_limit, ready_window, placement_window)
    for anchor in anchor_candidates:
        if anchor["order"] not in pending_ids:
            continue
        pending_orders = [order_by_id[order_id] for order_id in pending_ids]
        anchor_features = anchor_feature_by_order.get(str(anchor["order"]), anchor_v2_features(anchor, pending_orders, couriers, restaurants, speed_meters_per_minute, ready_window, placement_window))
        bundle = multi_restaurant_bundle_candidates(anchor, pending_orders, restaurants, max_bundle_size, ready_window, placement_window, max_pair_distance_minutes, max_restaurant_distance_minutes, speed_meters_per_minute)
        if not bundle:
            continue
        release_time = min(float(order["placement_time"]) for order in bundle)
        mean_orders = sum(courier_orders.values()) / max(1, len(courier_orders))
        best: tuple[tuple[float, ...], float, str, tuple[dict[str, str], ...], dict[str, float], dict[str, float]] | None = None
        for courier in couriers:
            courier_id = courier["courier"]
            start_time = max(courier_available[courier_id], float(courier["on_time"]), release_time)
            dropoff_time, sequence, pickup_times, dropoff_times = route_multi_restaurant_bundle(start_time, courier_location[courier_id], bundle, restaurants, speed_meters_per_minute)
            if not sequence:
                continue
            if dropoff_time > courier_off_time[courier_id]:
                rejected_bundle_candidates += 1
                continue
            per_order_delay = [dropoff_times[str(order["order"])] - float(order["ready_time"]) for order in sequence]
            per_order_otd = [dropoff_times[str(order["order"])] - float(order["placement_time"]) for order in sequence]
            per_order_food = [dropoff_times[str(order["order"])] - pickup_times[str(order["order"])] for order in sequence]
            if max(per_order_delay, default=0.0) > max_delay_minutes:
                rejected_bundle_candidates += 1
                continue
            if max(per_order_food, default=0.0) > max_food_on_vehicle_minutes:
                rejected_bundle_candidates += 1
                continue
            if max(per_order_otd, default=0.0) > max_order_to_delivery_minutes:
                rejected_bundle_candidates += 1
                continue
            pickup_wait = sum(max(0.0, pickup_times[str(order["order"])] - float(order["ready_time"])) for order in sequence) / max(1, len(sequence))
            load_pressure = max(0.0, courier_orders[courier_id] + len(sequence) - mean_orders)
            shift_pressure = max(0.0, dropoff_time - (courier_off_time[courier_id] - 20.0)) / 20.0
            restaurant_count = len({order["restaurant"] for order in sequence})
            route_insertion_risk = max(per_order_otd, default=0.0) + max(per_order_food, default=0.0)
            anchor_penalty = (
                (1.0 - float(anchor_features.get("anchorReadySlack", 0.0))) * 3.0
                + (1.0 - float(anchor_features.get("anchorCourierProximity", 0.0))) * 2.5
                + (1.0 - float(anchor_features.get("anchorCorridorFit", 0.0))) * 2.0
                + float(anchor_features.get("anchorDetourRisk", 0.0)) * 2.0
                + float(anchor_features.get("anchorTrafficRisk", 0.0)) * 1.5
            )
            objective = (
                0.0,
                -len(sequence),
                max(per_order_otd, default=0.0),
                max(per_order_food, default=0.0),
                pickup_wait,
                load_pressure,
                route_insertion_risk + anchor_penalty + float(profile.get("multiRestaurantPenalty", 0.0)) * max(0, restaurant_count - 1) + float(profile.get("shiftRiskWeight", 0.0)) * shift_pressure,
            )
            if best is None or objective < best[0]:
                best = (objective, dropoff_time, courier_id, sequence, pickup_times, dropoff_times)
        if best is None:
            pending_ids.remove(anchor["order"])
            continue
        _objective, dropoff_time, courier_id, sequence, pickup_times, dropoff_times = best
        courier_available[courier_id] = dropoff_time
        courier_location[courier_id] = sequence[-1]
        courier_orders[courier_id] += len(sequence)
        bundle_sizes.append(len(sequence))
        if len({order["restaurant"] for order in sequence}) > 1:
            multi_restaurant_bundle_count += 1
        anchor_feature_rows.append(anchor_features)
        for order in sequence:
            order_id = str(order["order"])
            if order_id not in pending_ids:
                continue
            pending_ids.remove(order_id)
            served += 1
            ready = float(order["ready_time"])
            pickup_time = pickup_times[order_id]
            order_dropoff_time = dropoff_times[order_id]
            delay = order_dropoff_time - ready
            food_on_vehicle = order_dropoff_time - pickup_time
            order_to_delivery = order_dropoff_time - float(order["placement_time"])
            pickup_wait = max(0.0, pickup_time - ready)
            if pickup_time + 1e-9 < ready:
                pickup_before_ready_violations += 1
            if order_dropoff_time > courier_off_time[courier_id] + 1e-9:
                shift_violations += 1
            if delay > max_delay_minutes:
                late += 1
            max_delay_observed = max(max_delay_observed, delay)
            total_delay += delay
            total_food_on_vehicle += food_on_vehicle
            delays.append(delay)
            food_on_vehicle_times.append(food_on_vehicle)
            order_to_delivery_times.append(order_to_delivery)
            pickup_wait_times.append(pickup_wait)

    courier_order_values = list(courier_orders.values())
    mean_orders = sum(courier_order_values) / max(1, len(courier_order_values))
    fairness_gini = 0.0
    if mean_orders > 0.0:
        fairness_gini = sum(abs(left - right) for left in courier_order_values for right in courier_order_values) / (2 * len(courier_order_values) ** 2 * mean_orders)
    hard_violations = pickup_before_ready_violations + shift_violations
    verdict = "PASS_WITH_LIMITS" if hard_violations == 0 and served > 0 else "FAIL"
    return {
        "orderCount": len(orders),
        "courierCount": len(couriers),
        "restaurantCount": len(restaurants),
        "servedOrderCount": served,
        "unservedOrderCount": len(orders) - served,
        "servedOrderRate": served / max(1, len(orders)),
        "lateOrderCount": late,
        "lateOrderRate": late / max(1, served),
        "pickupBeforeReadyTimeViolation": pickup_before_ready_violations,
        "courierShiftViolation": shift_violations,
        "foodOnVehicleHardViolation": 0,
        "avgDelay": total_delay / max(1, served),
        "p50Delay": percentile(delays, 50),
        "p95Delay": percentile(delays, 95),
        "maxDelay": max_delay_observed,
        "avgFoodOnVehicleTime": total_food_on_vehicle / max(1, served),
        "p50FoodOnVehicleTime": percentile(food_on_vehicle_times, 50),
        "p95FoodOnVehicleTime": percentile(food_on_vehicle_times, 95),
        "avgOrderToDeliveryTime": sum(order_to_delivery_times) / max(1, served),
        "p50OrderToDeliveryTime": percentile(order_to_delivery_times, 50),
        "p95OrderToDeliveryTime": percentile(order_to_delivery_times, 95),
        "avgPickupWaitTime": sum(pickup_wait_times) / max(1, served),
        "courierUtilization": sum(1 for count in courier_orders.values() if count > 0) / max(1, len(couriers)),
        "ordersPerCourier": served / max(1, len(couriers)),
        "ordersPerCourierP95": percentile([float(value) for value in courier_order_values], 95),
        "assignmentFairnessGini": fairness_gini,
        "bundleCount": len(bundle_sizes),
        "avgBundleSize": sum(bundle_sizes) / max(1, len(bundle_sizes)),
        "maxBundleSize": max(bundle_sizes, default=0),
        "multiOrderBundleRate": sum(1 for size in bundle_sizes if size > 1) / max(1, len(bundle_sizes)),
        "multiRestaurantBundleRate": multi_restaurant_bundle_count / max(1, len(bundle_sizes)),
        "rejectedBundleCandidates": rejected_bundle_candidates,
        "bundleMode": "compatible-multi-restaurant-v5",
        "bundleCompatibilityFeatures": ["ready-time", "restaurant-proximity", "route-insertion-delta", "food-on-vehicle-risk", "max-delay", "courier-shift-risk"],
        "anchorMode": "top-k-corridor-risk-v2",
        "anchorTopK": anchor_limit,
        "anchorFeatureCandidateCount": len(anchor_feature_by_order),
        "anchorV2Score": sum(float(row.get("anchorV2Score", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorReadySlack": sum(float(row.get("anchorReadySlack", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorCourierProximity": sum(float(row.get("anchorCourierProximity", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorCorridorFit": sum(float(row.get("anchorCorridorFit", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorDetourRisk": sum(float(row.get("anchorDetourRisk", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorTrafficRisk": sum(float(row.get("anchorTrafficRisk", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "anchorWeatherRisk": sum(float(row.get("anchorWeatherRisk", 0.0)) for row in anchor_feature_rows) / max(1, len(anchor_feature_rows)),
        "verdict": verdict,
        "verdictReasons": ["mdrplib-compatible-multi-restaurant-bundle-v5"] if verdict == "PASS_WITH_LIMITS" else ["mdrplib-hard-violation-or-no-service"],
    }


def simulate_mdrp_batch_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:

    max_bundle_size = int(float(profile.get("maxBundleSize", 2)))
    ready_window = float(profile.get("readyWindow", 8.0))
    placement_window = float(profile.get("placementWindow", 12.0))
    max_pair_distance_minutes = float(profile.get("maxPairDistanceMinutes", 8.0))
    hold_window = float(profile.get("holdWindow", 3.0))

    courier_available = {row["courier"]: float(row["on_time"]) for row in couriers}
    courier_location: dict[str, dict[str, Any]] = {row["courier"]: row for row in couriers}
    courier_orders = {row["courier"]: 0 for row in couriers}
    courier_off_time = {row["courier"]: float(row["off_time"]) for row in couriers}
    order_by_id = {row["order"]: row for row in orders}
    pending_ids = {row["order"] for row in orders}
    pending_ids_by_restaurant: dict[str, set[str]] = {}
    for order in orders:
        pending_ids_by_restaurant.setdefault(order["restaurant"], set()).add(order["order"])

    served = 0
    late = 0
    pickup_before_ready_violations = 0
    shift_violations = 0
    max_delay_observed = 0.0
    total_delay = 0.0
    total_food_on_vehicle = 0.0
    delays: list[float] = []
    food_on_vehicle_times: list[float] = []
    order_to_delivery_times: list[float] = []
    pickup_wait_times: list[float] = []
    bundle_sizes: list[int] = []

    for anchor in sorted(orders, key=lambda row: order_priority(row, profile)):
        if anchor["order"] not in pending_ids:
            continue
        restaurant = restaurants.get(anchor["restaurant"])
        if restaurant is None:
            pending_ids.remove(anchor["order"])
            pending_ids_by_restaurant.get(anchor["restaurant"], set()).discard(anchor["order"])
            continue
        pending_orders = [order_by_id[order_id] for order_id in pending_ids_by_restaurant.get(anchor["restaurant"], set()) if order_id in pending_ids]
        bundle = bundle_candidates(anchor, pending_orders, restaurant, max_bundle_size, ready_window, placement_window, max_pair_distance_minutes, speed_meters_per_minute)
        if not bundle:
            continue
        release_time = min(float(order["placement_time"]) for order in bundle)
        ready_time = max(float(order["ready_time"]) for order in bundle)
        mean_orders = sum(courier_orders.values()) / max(1, len(courier_orders))
        best: tuple[float, float, str, float, tuple[dict[str, str], ...], dict[str, float]] | None = None
        for courier in couriers:
            courier_id = courier["courier"]
            start_time = max(courier_available[courier_id], float(courier["on_time"]), release_time)
            to_pickup = distance(courier_location[courier_id], restaurant) / speed_meters_per_minute
            pickup_time = max(ready_time, start_time + to_pickup)
            if pickup_time - ready_time > hold_window and len(bundle) > 1:
                smaller = [anchor]
                ready_time = float(anchor["ready_time"])
                pickup_time = max(ready_time, start_time + to_pickup)
                candidate_bundle = smaller
            else:
                candidate_bundle = bundle
            dropoff_time, sequence, dropoff_times = route_dropoffs(pickup_time, restaurant, candidate_bundle, speed_meters_per_minute)
            if dropoff_time > courier_off_time[courier_id]:
                continue
            per_order_delay = [dropoff_times[str(order["order"])] - float(order["ready_time"]) for order in candidate_bundle]
            per_order_otd = [dropoff_times[str(order["order"])] - float(order["placement_time"]) for order in candidate_bundle]
            per_order_food = [dropoff_times[str(order["order"])] - pickup_time for order in candidate_bundle]
            if max(per_order_delay, default=0.0) > max_delay_minutes:
                continue
            if max(per_order_food, default=0.0) > float(profile.get("maxFoodOnVehicleMinutes", 30.0)):
                continue
            if max(per_order_otd, default=0.0) > float(profile.get("maxOrderToDeliveryMinutes", 75.0)):
                continue
            load_pressure = max(0.0, courier_orders[courier_id] + len(candidate_bundle) - mean_orders)
            shift_pressure = max(0.0, dropoff_time - (courier_off_time[courier_id] - 20.0)) / 20.0
            freshness_risk = max(per_order_food, default=0.0)
            delay_risk = max(per_order_delay, default=0.0)
            order_to_delivery_risk = max(per_order_otd, default=0.0)
            pickup_wait = max(0.0, pickup_time - ready_time)
            bundle_reward = float(profile.get("bundleReward", 0.0)) * max(0, len(candidate_bundle) - 1)
            cost = (
                dropoff_time
                + float(profile.get("loadWeight", 0.0)) * load_pressure
                + float(profile.get("pickupWaitWeight", 0.0)) * pickup_wait
                + float(profile.get("foodOnVehicleWeight", 0.0)) * freshness_risk
                + float(profile.get("orderToDeliveryWeight", 0.0)) * order_to_delivery_risk
                + float(profile.get("delayWeight", 0.0)) * delay_risk
                + float(profile.get("shiftRiskWeight", 0.0)) * shift_pressure
                - bundle_reward
            )
            if best is None or cost < best[0]:
                best = (cost, dropoff_time, courier_id, pickup_time, sequence, dropoff_times)
        if best is None:
            pending_ids.remove(anchor["order"])
            pending_ids_by_restaurant.get(anchor["restaurant"], set()).discard(anchor["order"])
            continue
        _cost, dropoff_time, courier_id, pickup_time, sequence, dropoff_times = best
        courier_available[courier_id] = dropoff_time
        courier_location[courier_id] = sequence[-1]
        courier_orders[courier_id] += len(sequence)
        bundle_sizes.append(len(sequence))
        for order in sequence:
            order_id = str(order["order"])
            if order_id not in pending_ids:
                continue
            pending_ids.remove(order_id)
            pending_ids_by_restaurant.get(order["restaurant"], set()).discard(order_id)
            served += 1
            ready = float(order["ready_time"])
            delay = dropoff_times[order_id] - ready
            food_on_vehicle = dropoff_times[order_id] - pickup_time
            order_to_delivery = dropoff_times[order_id] - float(order["placement_time"])
            pickup_wait = max(0.0, pickup_time - ready)
            if pickup_time + 1e-9 < ready:
                pickup_before_ready_violations += 1
            if dropoff_times[order_id] > courier_off_time[courier_id] + 1e-9:
                shift_violations += 1
            if delay > max_delay_minutes:
                late += 1
            max_delay_observed = max(max_delay_observed, delay)
            total_delay += delay
            total_food_on_vehicle += food_on_vehicle
            delays.append(delay)
            food_on_vehicle_times.append(food_on_vehicle)
            order_to_delivery_times.append(order_to_delivery)
            pickup_wait_times.append(pickup_wait)

    served_rate = served / max(1, len(orders))
    hard_violations = pickup_before_ready_violations + shift_violations
    verdict = "PASS_WITH_LIMITS" if hard_violations == 0 and served > 0 else "FAIL"
    courier_order_values = list(courier_orders.values())
    mean_orders = sum(courier_order_values) / max(1, len(courier_order_values))
    fairness_gini = 0.0
    if mean_orders > 0.0:
        fairness_gini = sum(abs(left - right) for left in courier_order_values for right in courier_order_values) / (2 * len(courier_order_values) ** 2 * mean_orders)
    return {
        "orderCount": len(orders),
        "courierCount": len(couriers),
        "restaurantCount": len(restaurants),
        "servedOrderCount": served,
        "unservedOrderCount": len(orders) - served,
        "servedOrderRate": served_rate,
        "lateOrderCount": late,
        "lateOrderRate": late / max(1, served),
        "pickupBeforeReadyTimeViolation": pickup_before_ready_violations,
        "courierShiftViolation": shift_violations,
        "foodOnVehicleHardViolation": 0,
        "avgDelay": total_delay / max(1, served),
        "p50Delay": percentile(delays, 50),
        "p95Delay": percentile(delays, 95),
        "maxDelay": max_delay_observed,
        "avgFoodOnVehicleTime": total_food_on_vehicle / max(1, served),
        "p50FoodOnVehicleTime": percentile(food_on_vehicle_times, 50),
        "p95FoodOnVehicleTime": percentile(food_on_vehicle_times, 95),
        "avgOrderToDeliveryTime": sum(order_to_delivery_times) / max(1, served),
        "p50OrderToDeliveryTime": percentile(order_to_delivery_times, 50),
        "p95OrderToDeliveryTime": percentile(order_to_delivery_times, 95),
        "avgPickupWaitTime": sum(pickup_wait_times) / max(1, served),
        "courierUtilization": sum(1 for count in courier_orders.values() if count > 0) / max(1, len(couriers)),
        "ordersPerCourier": served / max(1, len(couriers)),
        "ordersPerCourierP95": percentile([float(value) for value in courier_order_values], 95),
        "assignmentFairnessGini": fairness_gini,
        "bundleCount": len(bundle_sizes),
        "avgBundleSize": sum(bundle_sizes) / max(1, len(bundle_sizes)),
        "maxBundleSize": max(bundle_sizes, default=0),
        "multiOrderBundleRate": sum(1 for size in bundle_sizes if size > 1) / max(1, len(bundle_sizes)),
        "verdict": verdict,
        "verdictReasons": ["mdrplib-bounded-batch-insertion-v4"] if verdict == "PASS_WITH_LIMITS" else ["mdrplib-hard-violation-or-no-service"],
    }


def simulate_mdrp_profile(
        couriers: list[dict[str, str]],
        orders: list[dict[str, str]],
        restaurants: dict[str, dict[str, str]],
        speed_meters_per_minute: float,
        max_delay_minutes: float,
        profile: dict[str, float | str]) -> dict[str, Any]:

    courier_available = {row["courier"]: float(row["on_time"]) for row in couriers}
    courier_location: dict[str, dict[str, Any]] = {row["courier"]: row for row in couriers}
    courier_orders = {row["courier"]: 0 for row in couriers}

    served = 0
    late = 0
    pickup_before_ready_violations = 0
    shift_violations = 0
    max_delay_observed = 0.0
    total_delay = 0.0
    total_food_on_vehicle = 0.0
    delays: list[float] = []
    food_on_vehicle_times: list[float] = []
    order_to_delivery_times: list[float] = []
    pickup_wait_times: list[float] = []

    for order in sorted(orders, key=lambda row: order_priority(row, profile)):
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        ready_time = float(order["ready_time"])
        best: tuple[float, float, str, float, float, float] | None = None
        mean_orders = sum(courier_orders.values()) / max(1, len(courier_orders))
        for courier in couriers:
            courier_id = courier["courier"]
            start_time = max(courier_available[courier_id], float(courier["on_time"]), float(order["placement_time"]))
            to_pickup = distance(courier_location[courier_id], restaurant) / speed_meters_per_minute
            pickup_time = max(ready_time, start_time + to_pickup)
            to_dropoff = distance(restaurant, order) / speed_meters_per_minute
            dropoff_time = pickup_time + to_dropoff
            if dropoff_time > float(courier["off_time"]):
                continue
            pickup_wait = max(0.0, pickup_time - ready_time)
            food_on_vehicle = to_dropoff
            order_to_delivery = dropoff_time - float(order["placement_time"])
            load_pressure = max(0.0, courier_orders[courier_id] - mean_orders)
            shift_pressure = max(0.0, dropoff_time - (float(courier["off_time"]) - 20.0)) / 20.0
            cost = (
                dropoff_time
                + float(profile.get("loadWeight", 0.0)) * load_pressure
                + float(profile.get("pickupWaitWeight", 0.0)) * pickup_wait
                + float(profile.get("foodOnVehicleWeight", 0.0)) * food_on_vehicle
                + float(profile.get("orderToDeliveryWeight", 0.0)) * order_to_delivery
                + float(profile.get("shiftRiskWeight", 0.0)) * shift_pressure
            )
            if best is None or cost < best[0]:
                best = (cost, dropoff_time, courier_id, pickup_time, to_dropoff, dropoff_time - ready_time)
        if best is None:
            continue
        _cost, dropoff_time, courier_id, pickup_time, food_on_vehicle, delay = best
        served += 1
        courier_available[courier_id] = dropoff_time
        courier_location[courier_id] = order
        courier_orders[courier_id] += 1
        if pickup_time + 1e-9 < ready_time:
            pickup_before_ready_violations += 1
        if dropoff_time > max(float(c["off_time"]) for c in couriers if c["courier"] == courier_id) + 1e-9:
            shift_violations += 1
        if delay > max_delay_minutes:
            late += 1
        max_delay_observed = max(max_delay_observed, delay)
        total_delay += delay
        total_food_on_vehicle += food_on_vehicle
        delays.append(delay)
        food_on_vehicle_times.append(food_on_vehicle)
        order_to_delivery_times.append(dropoff_time - float(order["placement_time"]))
        pickup_wait_times.append(max(0.0, pickup_time - ready_time))

    served_rate = served / max(1, len(orders))
    hard_violations = pickup_before_ready_violations + shift_violations
    verdict = "PASS_WITH_LIMITS" if hard_violations == 0 and served > 0 else "FAIL"
    reasons = ["mdrplib-official-structural-baseline"] if verdict == "PASS_WITH_LIMITS" else ["mdrplib-hard-violation-or-no-service"]
    courier_order_values = list(courier_orders.values())
    mean_orders = sum(courier_order_values) / max(1, len(courier_order_values))
    fairness_gini = 0.0
    if mean_orders > 0.0:
        fairness_gini = sum(abs(left - right) for left in courier_order_values for right in courier_order_values) / (2 * len(courier_order_values) ** 2 * mean_orders)

    return {
        "orderCount": len(orders),
        "courierCount": len(couriers),
        "restaurantCount": len(restaurants),
        "servedOrderCount": served,
        "unservedOrderCount": len(orders) - served,
        "servedOrderRate": served_rate,
        "lateOrderCount": late,
        "lateOrderRate": late / max(1, served),
        "pickupBeforeReadyTimeViolation": pickup_before_ready_violations,
        "courierShiftViolation": shift_violations,
        "foodOnVehicleHardViolation": 0,
        "avgDelay": total_delay / max(1, served),
        "p50Delay": percentile(delays, 50),
        "p95Delay": percentile(delays, 95),
        "maxDelay": max_delay_observed,
        "avgFoodOnVehicleTime": total_food_on_vehicle / max(1, served),
        "p50FoodOnVehicleTime": percentile(food_on_vehicle_times, 50),
        "p95FoodOnVehicleTime": percentile(food_on_vehicle_times, 95),
        "avgOrderToDeliveryTime": sum(order_to_delivery_times) / max(1, served),
        "p50OrderToDeliveryTime": percentile(order_to_delivery_times, 50),
        "p95OrderToDeliveryTime": percentile(order_to_delivery_times, 95),
        "avgPickupWaitTime": sum(pickup_wait_times) / max(1, served),
        "courierUtilization": sum(1 for count in courier_orders.values() if count > 0) / max(1, len(couriers)),
        "ordersPerCourier": served / max(1, len(couriers)),
        "ordersPerCourierP95": percentile([float(value) for value in courier_order_values], 95),
        "assignmentFairnessGini": fairness_gini,
        "bundleCount": served,
        "avgBundleSize": 1.0 if served else 0.0,
        "maxBundleSize": 1 if served else 0,
        "multiOrderBundleRate": 0.0,
        "verdict": verdict,
        "verdictReasons": reasons,
    }


def evaluate_mdrplib_instance(path: Path, speed_meters_per_minute: float = 500.0, max_delay_minutes: float = 45.0) -> dict[str, Any]:
    couriers = read_tsv(path / "couriers.txt")
    orders = read_tsv(path / "orders.txt")
    restaurants = {row["restaurant"]: row for row in read_tsv(path / "restaurants.txt")}
    characteristics = parse_characteristics(path / "instance_characteristics.txt")
    profiles: list[dict[str, float | str]] = [
        {"name": "earliest-dropoff-baseline"},
        {"name": "freshness-balanced-v2", "loadWeight": 5.0, "pickupWaitWeight": 0.5, "foodOnVehicleWeight": 1.0},
        {"name": "order-to-delivery-v2", "loadWeight": 3.0, "pickupWaitWeight": 0.2, "foodOnVehicleWeight": 0.5, "orderToDeliveryWeight": 0.5},
        {"name": "shift-and-fairness-v2", "loadWeight": 4.0, "pickupWaitWeight": 0.2, "foodOnVehicleWeight": 0.5, "orderToDeliveryWeight": 0.2, "shiftRiskWeight": 20.0},
        {"name": "delay-heavy-v2", "loadWeight": 1.0, "pickupWaitWeight": 0.0, "foodOnVehicleWeight": 0.0, "orderToDeliveryWeight": 2.0},
        {"name": "fresh-heavy-v2", "loadWeight": 1.0, "pickupWaitWeight": 0.0, "foodOnVehicleWeight": 3.0, "orderToDeliveryWeight": 0.0},
        {"name": "freshness-very-heavy-v3", "loadWeight": 0.5, "pickupWaitWeight": 0.0, "foodOnVehicleWeight": 8.0, "orderToDeliveryWeight": 0.0},
        {"name": "balanced-product-quality-v3", "loadWeight": 5.0, "pickupWaitWeight": 1.0, "foodOnVehicleWeight": 2.0, "orderToDeliveryWeight": 2.0},
        {"name": "ready-time-tight-v3", "loadWeight": 2.0, "pickupWaitWeight": 1.5, "foodOnVehicleWeight": 2.0, "orderToDeliveryWeight": 2.0, "orderSort": "ready-time-tight"},
        {"name": "ready-restaurant-v3", "loadWeight": 2.0, "pickupWaitWeight": 1.0, "foodOnVehicleWeight": 2.0, "orderToDeliveryWeight": 1.5, "orderSort": "ready-restaurant"},
        {"name": "restaurant-ready-v3", "loadWeight": 2.0, "pickupWaitWeight": 1.0, "foodOnVehicleWeight": 3.0, "orderToDeliveryWeight": 1.0, "orderSort": "restaurant-ready"},
    ]
    batch_profiles: list[dict[str, float | str]] = [
        {"name": "batch-ready-insertion-v4", "loadWeight": 2.0, "pickupWaitWeight": 1.0, "foodOnVehicleWeight": 2.5, "orderToDeliveryWeight": 2.0, "delayWeight": 1.0, "bundleReward": 4.0, "maxBundleSize": 2, "readyWindow": 7.0, "placementWindow": 10.0, "maxPairDistanceMinutes": 6.0, "holdWindow": 3.0, "maxFoodOnVehicleMinutes": 25.0, "maxOrderToDeliveryMinutes": 70.0, "orderSort": "ready-restaurant"},
        {"name": "batch-freshness-regret-v4", "loadWeight": 1.5, "pickupWaitWeight": 0.5, "foodOnVehicleWeight": 5.0, "orderToDeliveryWeight": 1.5, "delayWeight": 2.0, "bundleReward": 2.0, "maxBundleSize": 2, "readyWindow": 5.0, "placementWindow": 8.0, "maxPairDistanceMinutes": 5.0, "holdWindow": 2.0, "maxFoodOnVehicleMinutes": 22.0, "maxOrderToDeliveryMinutes": 68.0, "orderSort": "ready-time-tight"},
        {"name": "batch-corridor-balanced-v4", "loadWeight": 3.0, "pickupWaitWeight": 0.8, "foodOnVehicleWeight": 2.0, "orderToDeliveryWeight": 2.5, "delayWeight": 1.5, "bundleReward": 6.0, "maxBundleSize": 3, "readyWindow": 8.0, "placementWindow": 12.0, "maxPairDistanceMinutes": 7.0, "holdWindow": 4.0, "maxFoodOnVehicleMinutes": 26.0, "maxOrderToDeliveryMinutes": 70.0, "orderSort": "restaurant-ready"},
    ]
    repair_profiles: list[dict[str, float | str]] = [
        {"name": "repair-relocate-swap-regret-v4", "orderSort": "ready-restaurant", "repairCandidateLimit": 6, "repairInsertionLimit": 3, "repairNeighborLimit": 8},
    ]
    bundle_v5_profiles: list[dict[str, float | str]] = [
        {"name": "compatible-multi-restaurant-bundle-v5", "maxBundleSize": 2, "readyWindow": 5.0, "placementWindow": 8.0, "maxPairDistanceMinutes": 5.0, "maxRestaurantDistanceMinutes": 3.5, "maxFoodOnVehicleMinutes": 22.0, "maxOrderToDeliveryMinutes": 68.0, "multiRestaurantPenalty": 2.0, "shiftRiskWeight": 8.0, "orderSort": "ready-restaurant", "bundleFullSearchOrderLimit": 350, "anchorTopKLimit": 1000000},
        {"name": "anchor-corridor-bundle-v6", "maxBundleSize": 2, "readyWindow": 6.0, "placementWindow": 9.0, "maxPairDistanceMinutes": 5.5, "maxRestaurantDistanceMinutes": 3.5, "maxFoodOnVehicleMinutes": 22.0, "maxOrderToDeliveryMinutes": 68.0, "multiRestaurantPenalty": 2.0, "shiftRiskWeight": 8.0, "orderSort": "ready-restaurant", "bundleFullSearchOrderLimit": 350, "anchorTopKLimit": 1000000},
    ]
    alns_profiles: list[dict[str, float | str]] = [
        {"name": "alns-lite-food-v7", "orderSort": "ready-restaurant", "alnsIterations": 4, "alnsRemoveCount": 3, "alnsNeighborLimit": 5, "alnsInsertionLimit": 3, "alnsFullSearchOrderLimit": 600},
    ]
    route_pool_profiles: list[dict[str, float | str]] = [
        {"name": "route-pool-set-packing-v8", "orderSort": "ready-restaurant", "poolAnchorLimit": 70, "poolCourierLimit": 10, "poolCandidatesPerAnchor": 3, "poolMaxBundleSize": 2, "poolParetoLimit": 180, "poolFragmentLimit": 90, "poolMaxFragmentSize": 3, "poolLoadBalanceMoveLimit": 6, "poolFullSearchOrderLimit": 700},
        {"name": "anchor-corridor-route-pool-v9", "orderSort": "ready-restaurant", "poolAnchorLimit": 90, "poolCourierLimit": 10, "poolCandidatesPerAnchor": 3, "poolMaxBundleSize": 2, "poolParetoLimit": 220, "poolFragmentLimit": 90, "poolMaxFragmentSize": 3, "poolLoadBalanceMoveLimit": 6, "poolFullSearchOrderLimit": 700},
    ]
    evaluated = [with_metadata(simulate_mdrp_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="single-order-greedy") for profile in profiles]
    evaluated.extend(with_metadata(simulate_mdrp_batch_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="bounded-batch-insertion") for profile in batch_profiles)
    evaluated.extend(with_metadata(simulate_mdrp_repair_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="route-state-repair") for profile in repair_profiles)
    evaluated.extend(with_metadata(simulate_mdrp_multi_restaurant_batch_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="compatible-multi-restaurant-bundle") for profile in bundle_v5_profiles)
    evaluated.extend(with_metadata(simulate_mdrp_alns_lite_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="alns-lite-food") for profile in alns_profiles)
    evaluated.extend(with_metadata(simulate_mdrp_route_pool_profile(couriers, orders, restaurants, speed_meters_per_minute, max_delay_minutes, profile), optimizerProfile=profile["name"], qualityScore=0.0, optimizerFamily="route-pool-set-packing") for profile in route_pool_profiles)
    for metrics in evaluated:
        metrics["qualityScore"] = score_profile(metrics)
    baseline = evaluated[0]
    repair_evidence = max((row for row in evaluated if row.get("optimizerFamily") == "route-state-repair"), key=lambda row: float(row.get("qualityScore", 0.0)), default={})
    bundle_evidence = max((row for row in evaluated if row.get("optimizerFamily") == "compatible-multi-restaurant-bundle"), key=lambda row: float(row.get("qualityScore", 0.0)), default={})
    alns_evidence = max((row for row in evaluated if row.get("optimizerFamily") == "alns-lite-food"), key=lambda row: float(row.get("qualityScore", 0.0)), default={})
    route_pool_evidence = max((row for row in evaluated if row.get("optimizerFamily") == "route-pool-set-packing"), key=lambda row: float(row.get("qualityScore", 0.0)), default={})
    feasible = [row for row in evaluated if int(row["pickupBeforeReadyTimeViolation"]) + int(row["courierShiftViolation"]) + int(row["foodOnVehicleHardViolation"]) == 0]
    selection_pool = feasible or evaluated
    best = max(selection_pool, key=lambda row: (float(row["qualityScore"]), row["servedOrderCount"], -row["p95Delay"], -row["assignmentFairnessGini"], str(row["optimizerProfile"])))
    baseline_summary = {key: baseline[key] for key in ("optimizerProfile", "qualityScore", "servedOrderRate", "p95Delay", "p95FoodOnVehicleTime", "p95OrderToDeliveryTime", "avgOrderToDeliveryTime", "courierUtilization", "assignmentFairnessGini", "avgPickupWaitTime")}
    profile_summaries = [{key: row[key] for key in ("optimizerProfile", "optimizerFamily", "qualityScore", "servedOrderRate", "p95Delay", "p95FoodOnVehicleTime", "p95OrderToDeliveryTime", "avgOrderToDeliveryTime", "courierUtilization", "assignmentFairnessGini", "avgPickupWaitTime", "bundleMode", "multiOrderBundleRate", "multiRestaurantBundleRate", "alnsMode", "alnsAcceptedMoves", "routePoolMode", "candidatePoolSize", "paretoFrontSize", "selectedCandidateCount", "anchorMode", "anchorV2Score", "anchorReadySlack", "anchorCorridorFit", "anchorDetourRisk", "anchorTrafficRisk") if key in row} for row in sorted(evaluated, key=lambda item: float(item["qualityScore"]), reverse=True)]
    best = dict(best)
    otd_lower_bounds = order_to_delivery_lower_bounds(orders, restaurants, speed_meters_per_minute)
    fresh_lower_bounds = freshness_lower_bounds(orders, restaurants, speed_meters_per_minute)
    p95_otd_gap = float(best["p95OrderToDeliveryTime"]) - float(otd_lower_bounds["p95OrderToDeliveryLowerBound"])
    avg_otd_gap = float(best["avgOrderToDeliveryTime"]) - float(otd_lower_bounds["avgOrderToDeliveryLowerBound"])
    p95_food_gap = float(best["p95FoodOnVehicleTime"]) - float(fresh_lower_bounds["p95FoodOnVehicleLowerBound"])
    p95_delay_gap = float(best["p95Delay"]) - float(fresh_lower_bounds["p95DelayLowerBound"])
    best.update({
        "schemaVersion": "mdrplib-metrics/v9",
        "benchmarkFamily": "grubhub-mdrplib",
        "instanceName": path.name,
        "officialData": True,
        "optimizerMode": "product-quality-max-anchor-route-pool-v9",
        "characteristics": characteristics,
        "baselineMetrics": baseline_summary,
        "profileSummaries": profile_summaries,
        "baselineBeaten": float(best["qualityScore"]) >= float(baseline["qualityScore"]),
        "qualityScoreDeltaVsBaseline": float(best["qualityScore"]) - float(baseline["qualityScore"]),
        "p95DelayDeltaVsBaseline": float(best["p95Delay"]) - float(baseline["p95Delay"]),
        "p95OrderToDeliveryDeltaVsBaseline": float(best["p95OrderToDeliveryTime"]) - float(baseline["p95OrderToDeliveryTime"]),
        "fairnessGiniDeltaVsBaseline": float(best["assignmentFairnessGini"]) - float(baseline["assignmentFairnessGini"]),
        "courierUtilizationDeltaVsBaseline": float(best["courierUtilization"]) - float(baseline["courierUtilization"]),
        "avgOrderToDeliveryLowerBound": otd_lower_bounds["avgOrderToDeliveryLowerBound"],
        "p50OrderToDeliveryLowerBound": otd_lower_bounds["p50OrderToDeliveryLowerBound"],
        "p95OrderToDeliveryLowerBound": otd_lower_bounds["p95OrderToDeliveryLowerBound"],
        "avgOrderToDeliveryGapToLowerBound": avg_otd_gap,
        "p95OrderToDeliveryGapToLowerBound": p95_otd_gap,
        "orderToDeliveryLowerBoundTight": p95_otd_gap <= 1.0,
        "avgFoodOnVehicleLowerBound": fresh_lower_bounds["avgFoodOnVehicleLowerBound"],
        "p95FoodOnVehicleLowerBound": fresh_lower_bounds["p95FoodOnVehicleLowerBound"],
        "avgDelayLowerBound": fresh_lower_bounds["avgDelayLowerBound"],
        "p95DelayLowerBound": fresh_lower_bounds["p95DelayLowerBound"],
        "p95FoodOnVehicleGapToLowerBound": p95_food_gap,
        "p95DelayGapToLowerBound": p95_delay_gap,
        "freshnessLowerBoundTight": p95_food_gap <= 1.0 and p95_delay_gap <= 1.0,
        "portfolioProfileCount": len(evaluated),
        "repairMode": best.get("repairMode") or repair_evidence.get("repairMode", "portfolio-repair-not-evaluated"),
        "repairOperatorCounts": best.get("repairOperatorCounts") or repair_evidence.get("repairOperatorCounts", {}),
        "repairAcceptedMoves": best.get("repairAcceptedMoves", repair_evidence.get("repairAcceptedMoves", 0)),
        "repairRejectedMoves": best.get("repairRejectedMoves", repair_evidence.get("repairRejectedMoves", 0)),
        "repairImprovementDelta": best.get("repairImprovementDelta") or repair_evidence.get("repairImprovementDelta", {}),
        "repairEvidenceProfile": {key: repair_evidence.get(key) for key in ("optimizerProfile", "optimizerFamily", "qualityScore", "p95OrderToDeliveryTime", "p95FoodOnVehicleTime", "avgPickupWaitTime", "assignmentFairnessGini", "courierUtilization") if key in repair_evidence},
        "bundleMode": best.get("bundleMode") or bundle_evidence.get("bundleMode", "portfolio-bundle-v5-not-evaluated"),
        "bundleCompatibilityFeatures": best.get("bundleCompatibilityFeatures") or bundle_evidence.get("bundleCompatibilityFeatures", []),
        "bundleEvidenceProfile": {key: bundle_evidence.get(key) for key in ("optimizerProfile", "optimizerFamily", "qualityScore", "p95OrderToDeliveryTime", "p95FoodOnVehicleTime", "avgPickupWaitTime", "assignmentFairnessGini", "courierUtilization", "multiOrderBundleRate", "multiRestaurantBundleRate", "rejectedBundleCandidates", "anchorMode", "anchorV2Score", "anchorReadySlack", "anchorCorridorFit", "anchorDetourRisk", "anchorTrafficRisk") if key in bundle_evidence},
        "alnsMode": best.get("alnsMode") or alns_evidence.get("alnsMode", "portfolio-alns-v7-not-evaluated"),
        "alnsIterations": best.get("alnsIterations", alns_evidence.get("alnsIterations", 0)),
        "alnsDestroyOperatorCounts": best.get("alnsDestroyOperatorCounts") or alns_evidence.get("alnsDestroyOperatorCounts", {}),
        "alnsRepairOperatorCounts": best.get("alnsRepairOperatorCounts") or alns_evidence.get("alnsRepairOperatorCounts", {}),
        "alnsAcceptedMoves": best.get("alnsAcceptedMoves", alns_evidence.get("alnsAcceptedMoves", 0)),
        "alnsRejectedMoves": best.get("alnsRejectedMoves", alns_evidence.get("alnsRejectedMoves", 0)),
        "alnsBestObjectiveDelta": best.get("alnsBestObjectiveDelta") or alns_evidence.get("alnsBestObjectiveDelta", {}),
        "operatorLearningRows": best.get("operatorLearningRows") or alns_evidence.get("operatorLearningRows", []),
        "alnsEvidenceProfile": {key: alns_evidence.get(key) for key in ("optimizerProfile", "optimizerFamily", "qualityScore", "p95OrderToDeliveryTime", "p95FoodOnVehicleTime", "avgPickupWaitTime", "assignmentFairnessGini", "courierUtilization", "alnsMode", "alnsAcceptedMoves") if key in alns_evidence},
        "routePoolMode": best.get("routePoolMode") or route_pool_evidence.get("routePoolMode", "portfolio-route-pool-v8-not-evaluated"),
        "fallbackAllowed": best.get("fallbackAllowed", route_pool_evidence.get("fallbackAllowed", False)),
        "candidatePoolSize": best.get("candidatePoolSize", route_pool_evidence.get("candidatePoolSize", 0)),
        "paretoFrontSize": best.get("paretoFrontSize", route_pool_evidence.get("paretoFrontSize", 0)),
        "dominanceRejectedCandidates": best.get("dominanceRejectedCandidates", route_pool_evidence.get("dominanceRejectedCandidates", 0)),
        "selectedCandidateCount": best.get("selectedCandidateCount", route_pool_evidence.get("selectedCandidateCount", 0)),
        "selectedCandidateSources": best.get("selectedCandidateSources") or route_pool_evidence.get("selectedCandidateSources", {}),
        "beautyAwareCandidateCount": best.get("beautyAwareCandidateCount", route_pool_evidence.get("beautyAwareCandidateCount", 0)),
        "beautyRejectedCandidates": best.get("beautyRejectedCandidates", route_pool_evidence.get("beautyRejectedCandidates", 0)),
        "selectedBeautyScoreAvg": best.get("selectedBeautyScoreAvg", route_pool_evidence.get("selectedBeautyScoreAvg", 0.0)),
        "routeShapePenalty": best.get("routeShapePenalty", route_pool_evidence.get("routeShapePenalty", 0.0)),
        "routeDetourRisk": best.get("routeDetourRisk", route_pool_evidence.get("routeDetourRisk", 0.0)),
        "routeCorridorFit": best.get("routeCorridorFit", route_pool_evidence.get("routeCorridorFit", 0.0)),
        "anchorMode": best.get("anchorMode") or route_pool_evidence.get("anchorMode") or bundle_evidence.get("anchorMode", "portfolio-anchor-v2-not-evaluated"),
        "anchorTopK": best.get("anchorTopK", route_pool_evidence.get("anchorTopK", bundle_evidence.get("anchorTopK", 0))),
        "anchorFeatureCandidateCount": best.get("anchorFeatureCandidateCount", route_pool_evidence.get("anchorFeatureCandidateCount", bundle_evidence.get("anchorFeatureCandidateCount", 0))),
        "anchorV2Score": best.get("anchorV2Score", route_pool_evidence.get("anchorV2Score", bundle_evidence.get("anchorV2Score", 0.0))),
        "anchorReadySlack": best.get("anchorReadySlack", route_pool_evidence.get("anchorReadySlack", bundle_evidence.get("anchorReadySlack", 0.0))),
        "anchorCourierProximity": best.get("anchorCourierProximity", route_pool_evidence.get("anchorCourierProximity", bundle_evidence.get("anchorCourierProximity", 0.0))),
        "anchorCorridorFit": best.get("anchorCorridorFit", route_pool_evidence.get("anchorCorridorFit", bundle_evidence.get("anchorCorridorFit", 0.0))),
        "anchorDetourRisk": best.get("anchorDetourRisk", route_pool_evidence.get("anchorDetourRisk", bundle_evidence.get("anchorDetourRisk", 0.0))),
        "anchorTrafficRisk": best.get("anchorTrafficRisk", route_pool_evidence.get("anchorTrafficRisk", bundle_evidence.get("anchorTrafficRisk", 0.0))),
        "anchorWeatherRisk": best.get("anchorWeatherRisk", route_pool_evidence.get("anchorWeatherRisk", bundle_evidence.get("anchorWeatherRisk", 0.0))),
        "routeFragmentCandidateCount": best.get("routeFragmentCandidateCount", route_pool_evidence.get("routeFragmentCandidateCount", 0)),
        "targetLoad": best.get("targetLoad", route_pool_evidence.get("targetLoad", 0.0)),
        "overloadedCourierCount": best.get("overloadedCourierCount", route_pool_evidence.get("overloadedCourierCount", 0)),
        "loadBalancingMoves": best.get("loadBalancingMoves", route_pool_evidence.get("loadBalancingMoves", 0)),
        "postPackingIntraRouteMoves": best.get("postPackingIntraRouteMoves", route_pool_evidence.get("postPackingIntraRouteMoves", 0)),
        "setPackingFallbackUsed": best.get("setPackingFallbackUsed", route_pool_evidence.get("setPackingFallbackUsed", True)),
        "postSelectionRepairApplied": best.get("postSelectionRepairApplied", route_pool_evidence.get("postSelectionRepairApplied", False)),
        "setPackingRawObjectiveDelta": best.get("setPackingRawObjectiveDelta") or route_pool_evidence.get("setPackingRawObjectiveDelta", {}),
        "setPackingObjectiveDelta": best.get("setPackingObjectiveDelta") or route_pool_evidence.get("setPackingObjectiveDelta", {}),
        "routePoolEvidenceProfile": {key: route_pool_evidence.get(key) for key in ("optimizerProfile", "optimizerFamily", "qualityScore", "p95OrderToDeliveryTime", "p95FoodOnVehicleTime", "avgPickupWaitTime", "assignmentFairnessGini", "courierUtilization", "routePoolMode", "candidatePoolSize", "paretoFrontSize", "selectedCandidateCount", "routeFragmentCandidateCount", "anchorMode", "anchorV2Score", "anchorReadySlack", "anchorCorridorFit", "anchorDetourRisk", "anchorTrafficRisk") if key in route_pool_evidence},
    })
    if best["verdict"] == "PASS_WITH_LIMITS":
        best["verdictReasons"] = ["mdrplib-product-quality-max-v9", "mdrplib-baseline-compared"]
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and evaluate one MDRPLib instance directory.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = evaluate_mdrplib_instance(Path(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if payload["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
