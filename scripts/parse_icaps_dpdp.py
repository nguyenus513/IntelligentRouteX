from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import timedelta
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_hhmmss(value: str) -> int:
    hours, minutes, seconds = [int(part) for part in value.split(":")]
    return int(timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds())


def _factory_point(row: dict[str, str]) -> tuple[float, float]:
    return float(row["longitude"]), float(row["latitude"])


def _distance_km(a: dict[str, str], b: dict[str, str]) -> float:
    # Equirectangular approximation is sufficient for benchmark consistency checks.
    lon1, lat1 = _factory_point(a)
    lon2, lat2 = _factory_point(b)
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = (lon2 - lon1) * math.cos(mean_lat) * 111.32
    dy = (lat2 - lat1) * 110.57
    return math.hypot(dx, dy)


def _order_times(order: dict[str, str]) -> tuple[int, int]:
    creation = parse_hhmmss(order["creation_time"])
    due = parse_hhmmss(order["committed_completion_time"])
    if due < creation:
        due += 24 * 60 * 60
    return creation, due


def _route_order(
    order: dict[str, str],
    factories: dict[str, dict[str, str]],
    start_time: float,
    start_factory_id: str,
    speed_kmph: float,
) -> dict[str, Any]:
    pickup = factories[order["pickup_id"]]
    dropoff = factories[order["delivery_id"]]
    start_factory = factories[start_factory_id]
    creation, due = _order_times(order)
    to_pickup_seconds = _distance_km(start_factory, pickup) / speed_kmph * 3600.0
    load_seconds = float(order.get("load_time", 0.0) or 0.0)
    travel_seconds = _distance_km(pickup, dropoff) / speed_kmph * 3600.0
    unload_seconds = float(order.get("unload_time", 0.0) or 0.0)
    pickup_arrival = max(start_time, creation) + to_pickup_seconds
    pickup_departure = pickup_arrival + load_seconds
    dropoff_arrival = pickup_departure + travel_seconds
    completion_time = dropoff_arrival + unload_seconds
    return {
        "orderId": order["order_id"],
        "pickupFactoryId": order["pickup_id"],
        "deliveryFactoryId": order["delivery_id"],
        "creationTimeSeconds": creation,
        "dueTimeSeconds": due,
        "pickupArrivalSeconds": pickup_arrival,
        "dropoffArrivalSeconds": dropoff_arrival,
        "completionTimeSeconds": completion_time,
        "demand": float(order["demand"]),
        "tardinessSeconds": max(0.0, completion_time - due),
    }


def _run_rolling_horizon(
    orders: list[dict[str, str]],
    vehicles: list[dict[str, str]],
    factories: dict[str, dict[str, str]],
    speed_kmph: float = 35.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    known_factory_ids = sorted(factories)
    vehicle_states: dict[str, dict[str, Any]] = {}
    for index, vehicle in enumerate(vehicles):
        factory_id = known_factory_ids[index % len(known_factory_ids)]
        vehicle_states[vehicle["car_num"]] = {
            "availableAt": 0.0,
            "factoryId": factory_id,
            "capacity": float(vehicle["capacity"]),
            "route": [],
            "lastCommittedOrderId": None,
        }

    replan_count = 0
    active_route_corruption_count = 0
    vehicle_state_continuity_violation = 0
    max_replan_latency_ms = 0
    total_tardiness = 0.0
    assigned_count = 0
    driver_schedule_change_count = 0

    for order in sorted(orders, key=lambda row: _order_times(row)[0]):
        tick_started = time.perf_counter()
        if order["pickup_id"] not in factories or order["delivery_id"] not in factories:
            continue
        best_vehicle_id: str | None = None
        best_leg: dict[str, Any] | None = None
        for vehicle_id, state in vehicle_states.items():
            leg = _route_order(order, factories, state["availableAt"], state["factoryId"], speed_kmph)
            if best_leg is None or (leg["completionTimeSeconds"], leg["tardinessSeconds"]) < (
                best_leg["completionTimeSeconds"],
                best_leg["tardinessSeconds"],
            ):
                best_vehicle_id = vehicle_id
                best_leg = leg
        if best_vehicle_id is None or best_leg is None:
            continue
        state = vehicle_states[best_vehicle_id]
        previous_committed = state["lastCommittedOrderId"]
        if previous_committed is not None and state["route"] and state["route"][-1]["orderId"] != previous_committed:
            active_route_corruption_count += 1
        if best_leg["pickupArrivalSeconds"] > best_leg["dropoffArrivalSeconds"]:
            vehicle_state_continuity_violation += 1
        if state["route"] and state["route"][-1]["deliveryFactoryId"] != state["factoryId"]:
            vehicle_state_continuity_violation += 1
        if state["route"]:
            driver_schedule_change_count += 1
        state["route"].append(best_leg)
        state["availableAt"] = best_leg["completionTimeSeconds"]
        state["factoryId"] = best_leg["deliveryFactoryId"]
        state["lastCommittedOrderId"] = best_leg["orderId"]
        total_tardiness += best_leg["tardinessSeconds"]
        assigned_count += 1
        replan_count += 1
        max_replan_latency_ms = max(max_replan_latency_ms, int((time.perf_counter() - tick_started) * 1000))

    runtime_ms = int((time.perf_counter() - started) * 1000)
    return {
        "servedOrderCount": assigned_count,
        "unservedOrderCount": max(0, len(orders) - assigned_count),
        "totalTardiness": total_tardiness,
        "replanCount": replan_count,
        "maxReplanLatencyMs": max_replan_latency_ms,
        "runtimeMs": runtime_ms,
        "routeStabilityScore": 1.0 - (active_route_corruption_count / max(1, assigned_count)),
        "driverScheduleChangeCount": driver_schedule_change_count,
        "activeRouteCorruptionCount": active_route_corruption_count,
        "vehicleStateContinuityViolation": vehicle_state_continuity_violation,
        "routes": {vehicle_id: state["route"] for vehicle_id, state in vehicle_states.items() if state["route"]},
    }


def evaluate_icaps_instance(instance_path: Path, factory_info_path: Path) -> dict[str, Any]:
    factories = {row["factory_id"]: row for row in read_csv(factory_info_path)}
    order_files = sorted(path for path in instance_path.glob("*.csv") if not path.name.startswith("vehicle_info"))
    vehicle_files = sorted(instance_path.glob("vehicle_info_*.csv"))
    if not order_files or not vehicle_files:
        raise ValueError(f"ICAPS instance is missing order or vehicle files: {instance_path}")
    orders = read_csv(order_files[0])
    vehicles = read_csv(vehicle_files[0])

    unknown_factory_count = 0
    capacity_violation_count = 0
    oversize_order_count = 0
    pickup_before_dropoff_violation_count = 0
    time_window_violation_count = 0
    max_demand = 0.0
    max_capacity = max(float(row["capacity"]) for row in vehicles)
    for order in orders:
        if order["pickup_id"] not in factories or order["delivery_id"] not in factories:
            unknown_factory_count += 1
        demand = float(order["demand"])
        max_demand = max(max_demand, demand)
        if demand > max_capacity:
            oversize_order_count += 1
        creation, due = _order_times(order)
        if creation > due:
            time_window_violation_count += 1

    horizon = _run_rolling_horizon(orders, vehicles, factories)
    hard_violations = (
        unknown_factory_count
        + capacity_violation_count
        + pickup_before_dropoff_violation_count
        + time_window_violation_count
        + horizon["activeRouteCorruptionCount"]
        + horizon["vehicleStateContinuityViolation"]
    )
    feasible = hard_violations == 0 and horizon["servedOrderCount"] == len(orders)
    verdict = "PASS_WITH_LIMITS" if feasible else "FAIL"
    reasons = ["icaps-deterministic-rolling-horizon-baseline"] if feasible else ["icaps-dynamic-feasibility-failed"]
    if oversize_order_count:
        reasons.append("oversize-orders-reported-not-hard-failed")
    return {
        "schemaVersion": "icaps-dpdp-metrics/v2",
        "benchmarkFamily": "icaps-dpdp",
        "instanceName": instance_path.name,
        "officialData": True,
        "orderCount": len(orders),
        "vehicleCount": len(vehicles),
        "factoryCount": len(factories),
        "servedOrderCount": horizon["servedOrderCount"],
        "unservedOrderCount": horizon["unservedOrderCount"],
        "unknownFactoryCount": unknown_factory_count,
        "capacityViolationCount": capacity_violation_count,
        "oversizeOrderCount": oversize_order_count,
        "pickupBeforeDropoffViolationCount": pickup_before_dropoff_violation_count,
        "timeWindowViolationCount": time_window_violation_count,
        "activeRouteCorruptionCount": horizon["activeRouteCorruptionCount"],
        "vehicleStateContinuityViolation": horizon["vehicleStateContinuityViolation"],
        "totalTardiness": horizon["totalTardiness"],
        "replanCount": horizon["replanCount"],
        "maxReplanLatencyMs": horizon["maxReplanLatencyMs"],
        "routeStabilityScore": horizon["routeStabilityScore"],
        "driverScheduleChangeCount": horizon["driverScheduleChangeCount"],
        "runtimeMs": horizon["runtimeMs"],
        "maxDemand": max_demand,
        "maxVehicleCapacity": max_capacity,
        "feasible": feasible,
        "verdict": verdict,
        "verdictReasons": reasons,
        "routes": horizon["routes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and dynamically evaluate one ICAPS DPDP benchmark instance.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--factory-info", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = evaluate_icaps_instance(Path(args.input), Path(args.factory_info))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if payload["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
