from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCENARIO_OFFSETS = {
    "normal-clear": (10.7750, 106.7000),
    "lunch-spike": (10.7800, 106.7050),
    "dinner-spike": (10.7700, 106.6950),
    "driver-scarcity": (10.7650, 106.6900),
}
SIZE_COUNTS = {
    "S": (8, 4),
    "M": (20, 8),
    "L": (50, 20),
    "XL": (100, 35),
}


def distance_meters(left: dict[str, float], right: dict[str, float]) -> int:
    lat_scale = 111_000.0
    lng_scale = 111_000.0 * math.cos(math.radians((left["lat"] + right["lat"]) / 2.0))
    return int(round(math.hypot((left["lat"] - right["lat"]) * lat_scale, (left["lng"] - right["lng"]) * lng_scale)))


def point(base_lat: float, base_lng: float, index: int, lane: int) -> dict[str, float]:
    return {
        "lat": round(base_lat + lane * 0.0015 + (index % 5) * 0.0008, 7),
        "lng": round(base_lng + lane * 0.0012 + (index // 5) * 0.0009, 7),
    }


def build_instance(scenario_pack: str, size: str, trace_id: str, include_matrix: bool = True) -> dict[str, Any]:
    order_count, driver_count = SIZE_COUNTS[size]
    base_lat, base_lng = SCENARIO_OFFSETS.get(scenario_pack, SCENARIO_OFFSETS["normal-clear"])
    now = int(datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc).timestamp())
    orders = []
    for index in range(order_count):
        orders.append({
            "orderId": f"order-{index + 1:03d}",
            "pickup": point(base_lat, base_lng, index % 6, 0),
            "dropoff": point(base_lat, base_lng, index, 2),
            "readyAtEpochSec": now + (index % 4) * 120,
            "promisedEtaMinutes": 30 + (index % 3) * 5,
            "serviceSeconds": 120,
            "demand": 1,
        })
    drivers = []
    for index in range(driver_count):
        drivers.append({
            "driverId": f"driver-{index + 1:03d}",
            "start": point(base_lat, base_lng, index, -1),
            "capacity": 3,
            "shiftEndEpochSec": now + 4 * 3600,
        })
    nodes = [driver["start"] for driver in drivers] + [order["pickup"] for order in orders] + [order["dropoff"] for order in orders]
    matrix = [[0 for _ in nodes] for _ in nodes]
    duration = [[0 for _ in nodes] for _ in nodes]
    if include_matrix:
        for left_index, left in enumerate(nodes):
            for right_index, right in enumerate(nodes):
                meters = 0 if left_index == right_index else distance_meters(left, right)
                matrix[left_index][right_index] = meters
                duration[left_index][right_index] = int(round(meters / 7.5))
    return {
        "schemaVersion": "dispatch-academic-instance/v1",
        "scenarioId": f"{scenario_pack}-{size}",
        "traceId": trace_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "orders": orders,
        "drivers": drivers,
        "distanceMatrixMeters": matrix if include_matrix else [],
        "durationMatrixSeconds": duration if include_matrix else [],
        "metadata": {
            "workloadSize": size,
            "scenarioPack": scenario_pack,
            "deterministic": True,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a deterministic Dispatch academic benchmark instance.")
    parser.add_argument("--scenario-pack", default="normal-clear")
    parser.add_argument("--size", default="S", choices=sorted(SIZE_COUNTS))
    parser.add_argument("--trace-id", default="academic-export-trace")
    parser.add_argument("--no-matrix", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    instance = build_instance(args.scenario_pack, args.size, args.trace_id, include_matrix=not args.no_matrix)
    write_json(Path(args.output), instance)
    print(f"[EXPORT] wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
