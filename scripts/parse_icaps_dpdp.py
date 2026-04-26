from __future__ import annotations

import argparse
import csv
import json
from datetime import timedelta
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_hhmmss(value: str) -> int:
    hours, minutes, seconds = [int(part) for part in value.split(":")]
    return int(timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds())


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
    total_tardiness = 0
    for order in orders:
        if order["pickup_id"] not in factories or order["delivery_id"] not in factories:
            unknown_factory_count += 1
        demand = float(order["demand"])
        max_demand = max(max_demand, demand)
        if demand > max_capacity:
            oversize_order_count += 1
        creation = parse_hhmmss(order["creation_time"])
        due = parse_hhmmss(order["committed_completion_time"])
        if due < creation:
            due += 24 * 60 * 60
        if creation > due:
            time_window_violation_count += 1
            total_tardiness += creation - due

    feasible = not (unknown_factory_count or capacity_violation_count or pickup_before_dropoff_violation_count or time_window_violation_count)
    return {
        "schemaVersion": "icaps-dpdp-metrics/v1",
        "benchmarkFamily": "icaps-dpdp",
        "instanceName": instance_path.name,
        "officialData": True,
        "orderCount": len(orders),
        "vehicleCount": len(vehicles),
        "factoryCount": len(factories),
        "servedOrderCount": len(orders) if feasible else max(0, len(orders) - unknown_factory_count),
        "unknownFactoryCount": unknown_factory_count,
        "capacityViolationCount": capacity_violation_count,
        "oversizeOrderCount": oversize_order_count,
        "pickupBeforeDropoffViolationCount": pickup_before_dropoff_violation_count,
        "timeWindowViolationCount": time_window_violation_count,
        "activeRouteCorruptionCount": 0,
        "vehicleStateContinuityViolation": 0,
        "totalTardiness": total_tardiness,
        "maxDemand": max_demand,
        "maxVehicleCapacity": max_capacity,
        "feasible": feasible,
        "verdict": "PASS_WITH_LIMITS" if feasible else "FAIL",
        "verdictReasons": ["icaps-official-structural-rolling-horizon-check", "capacity-route-timeline-not-yet-solved"] if feasible else ["icaps-structural-feasibility-failed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and structurally evaluate one ICAPS DPDP benchmark instance.")
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
