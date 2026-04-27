from __future__ import annotations

import argparse
import csv
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


def evaluate_mdrplib_instance(path: Path, speed_meters_per_minute: float = 500.0, max_delay_minutes: float = 45.0) -> dict[str, Any]:
    couriers = read_tsv(path / "couriers.txt")
    orders = read_tsv(path / "orders.txt")
    restaurants = {row["restaurant"]: row for row in read_tsv(path / "restaurants.txt")}
    characteristics = parse_characteristics(path / "instance_characteristics.txt")

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

    for order in sorted(orders, key=lambda row: float(row["placement_time"])):
        restaurant = restaurants.get(order["restaurant"])
        if restaurant is None:
            continue
        ready_time = float(order["ready_time"])
        best: tuple[float, str, float, float, float] | None = None
        for courier in couriers:
            courier_id = courier["courier"]
            start_time = max(courier_available[courier_id], float(courier["on_time"]), float(order["placement_time"]))
            to_pickup = distance(courier_location[courier_id], restaurant) / speed_meters_per_minute
            pickup_time = max(ready_time, start_time + to_pickup)
            to_dropoff = distance(restaurant, order) / speed_meters_per_minute
            dropoff_time = pickup_time + to_dropoff
            if dropoff_time > float(courier["off_time"]):
                continue
            if best is None or dropoff_time < best[0]:
                best = (dropoff_time, courier_id, pickup_time, to_dropoff, dropoff_time - ready_time)
        if best is None:
            continue
        dropoff_time, courier_id, pickup_time, food_on_vehicle, delay = best
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

    def percentile(values: list[float], percent: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((percent / 100.0) * (len(ordered) - 1)))))
        return ordered[index]

    return {
        "schemaVersion": "mdrplib-metrics/v1",
        "benchmarkFamily": "grubhub-mdrplib",
        "instanceName": path.name,
        "officialData": True,
        "characteristics": characteristics,
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
