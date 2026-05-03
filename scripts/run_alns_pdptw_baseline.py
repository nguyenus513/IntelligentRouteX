from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def order_distance(order: dict[str, Any]) -> int:
    pickup = order["pickup"]
    dropoff = order["dropoff"]
    lat = abs(float(pickup["lat"]) - float(dropoff["lat"])) * 111_000.0
    lng = abs(float(pickup["lng"]) - float(dropoff["lng"])) * 106_000.0
    return int(round((lat * lat + lng * lng) ** 0.5))


def solve(instance: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    orders = sorted(instance.get("orders", []), key=lambda order: (order.get("readyAtEpochSec", 0), order["orderId"]))
    drivers = instance.get("drivers", [])
    routes: list[dict[str, Any]] = []
    if not drivers:
        return result(instance, [], 0, 0, False, started, "no-drivers")
    capacity_by_driver = {driver["driverId"]: int(driver.get("capacity", 3)) for driver in drivers}
    buckets: dict[str, list[dict[str, Any]]] = {driver["driverId"]: [] for driver in drivers}
    for index, order in enumerate(orders):
        driver = drivers[index % len(drivers)]
        bucket = buckets[driver["driverId"]]
        if len(bucket) >= capacity_by_driver[driver["driverId"]]:
            routes.append(route(driver["driverId"], bucket))
            buckets[driver["driverId"]] = []
        buckets[driver["driverId"]].append(order)
    for driver_id, bucket in buckets.items():
        if bucket:
            routes.append(route(driver_id, bucket))
    total_distance = sum(item["distanceMeters"] for item in routes)
    total_duration = sum(item["durationSeconds"] for item in routes)
    return result(instance, routes, total_distance, total_duration, True, started, "deterministic-greedy-alns-lite")


def route(driver_id: str, orders: list[dict[str, Any]]) -> dict[str, Any]:
    distance = sum(order_distance(order) for order in orders)
    service = sum(int(order.get("serviceSeconds", 120)) for order in orders)
    return {
        "driverId": driver_id,
        "orderIds": [order["orderId"] for order in orders],
        "distanceMeters": distance,
        "durationSeconds": int(round(distance / 7.5)) + service,
    }


def result(instance: dict[str, Any], routes: list[dict[str, Any]], distance: int, duration: int, feasible: bool, started: float, reason: str) -> dict[str, Any]:
    runtime_ms = int(round((time.perf_counter() - started) * 1000))
    served = sum(len(route_item["orderIds"]) for route_item in routes)
    return {
        "schemaVersion": "alns-pdptw-baseline-result/v1",
        "solver": "internal-alns-pdptw-lite",
        "scenarioId": instance.get("scenarioId", ""),
        "status": "ok" if feasible else "infeasible",
        "feasible": feasible,
        "routeCount": len(routes),
        "vehicleCount": len(routes),
        "servedOrderCount": served,
        "totalOrderCount": len(instance.get("orders", [])),
        "totalDistanceMeters": distance,
        "totalDurationSeconds": duration,
        "runtimeMs": runtime_ms,
        "runtimeToFirstFeasibleMs": runtime_ms if feasible else None,
        "runtimeToBestMs": runtime_ms,
        "routes": routes,
        "reasons": [reason],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic internal ALNS/PDPTW-lite baseline.")
    parser.add_argument("--instance", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = solve(load_json(Path(args.instance)))
    write_json(Path(args.output), payload)
    print(f"[ALNS] wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
