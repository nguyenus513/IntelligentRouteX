from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "live-dispatch-snapshot/v1"

REQUIRED_TOP_LEVEL_FIELDS = (
    "schemaVersion",
    "snapshotId",
    "timestamp",
    "region",
    "orders",
    "drivers",
    "activeRoutes",
    "durationMatrix",
    "trafficContext",
    "restaurantDelay",
    "cancellationRisk",
)

REQUIRED_ORDER_FIELDS = (
    "orderId",
    "pickupNodeId",
    "dropoffNodeId",
    "restaurantId",
    "readyTime",
    "dueTime",
    "serviceTimePickup",
    "serviceTimeDropoff",
    "demand",
)

REQUIRED_DRIVER_FIELDS = (
    "driverId",
    "startNodeId",
    "capacity",
    "shiftStart",
    "shiftEnd",
)

REQUIRED_ACTIVE_ROUTE_FIELDS = (
    "driverId",
    "route",
    "lockedPrefixLength",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require_fields(value: dict[str, Any], required: tuple[str, ...], prefix: str, errors: list[str]) -> None:
    for field in required:
        if field not in value:
            errors.append(f"{prefix}: missing required field '{field}'")


def _validate_array(snapshot: dict[str, Any], field: str, errors: list[str]) -> None:
    if field in snapshot and not isinstance(snapshot[field], list):
        errors.append(f"{field}: must be an array")


def _validate_duration_matrix(matrix: Any, errors: list[str]) -> None:
    if not isinstance(matrix, list) or not matrix:
        errors.append("durationMatrix: must be a non-empty square numeric matrix")
        return

    size = len(matrix)
    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != size:
            errors.append(f"durationMatrix[{row_index}]: must have exactly {size} entries")
            continue
        for column_index, value in enumerate(row):
            if not _is_number(value) or value < 0:
                errors.append(f"durationMatrix[{row_index}][{column_index}]: must be a finite non-negative number")


def _validate_orders(orders: Any, errors: list[str]) -> None:
    if not isinstance(orders, list):
        return
    for index, order in enumerate(orders):
        prefix = f"orders[{index}]"
        if not isinstance(order, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        _require_fields(order, REQUIRED_ORDER_FIELDS, prefix, errors)
        ready_time = order.get("readyTime")
        due_time = order.get("dueTime")
        if _is_number(ready_time) and _is_number(due_time) and ready_time > due_time:
            errors.append(f"{prefix}: readyTime must be <= dueTime")
        for field in ("serviceTimePickup", "serviceTimeDropoff", "demand"):
            if field in order and (not _is_number(order[field]) or order[field] < 0):
                errors.append(f"{prefix}.{field}: must be a finite non-negative number")


def _validate_drivers(drivers: Any, errors: list[str]) -> None:
    if not isinstance(drivers, list):
        return
    for index, driver in enumerate(drivers):
        prefix = f"drivers[{index}]"
        if not isinstance(driver, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        _require_fields(driver, REQUIRED_DRIVER_FIELDS, prefix, errors)
        shift_start = driver.get("shiftStart")
        shift_end = driver.get("shiftEnd")
        if _is_number(shift_start) and _is_number(shift_end) and shift_start > shift_end:
            errors.append(f"{prefix}: shiftStart must be <= shiftEnd")
        if "capacity" in driver and (not _is_number(driver["capacity"]) or driver["capacity"] < 0):
            errors.append(f"{prefix}.capacity: must be a finite non-negative number")


def _validate_active_routes(active_routes: Any, errors: list[str]) -> None:
    if not isinstance(active_routes, list):
        return
    for index, active_route in enumerate(active_routes):
        prefix = f"activeRoutes[{index}]"
        if not isinstance(active_route, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        _require_fields(active_route, REQUIRED_ACTIVE_ROUTE_FIELDS, prefix, errors)
        if "route" in active_route and not isinstance(active_route["route"], list):
            errors.append(f"{prefix}.route: must be an array")
        if "lockedPrefixLength" in active_route:
            locked_prefix_length = active_route["lockedPrefixLength"]
            if not isinstance(locked_prefix_length, int) or locked_prefix_length < 0:
                errors.append(f"{prefix}.lockedPrefixLength: must be a non-negative integer")


def validate_snapshot(snapshot: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return {"valid": False, "errors": ["snapshot: must be a JSON object"]}

    _require_fields(snapshot, REQUIRED_TOP_LEVEL_FIELDS, "snapshot", errors)

    if snapshot.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion: must be '{SCHEMA_VERSION}'")

    for field in ("orders", "drivers", "activeRoutes"):
        _validate_array(snapshot, field, errors)

    if "durationMatrix" in snapshot:
        _validate_duration_matrix(snapshot["durationMatrix"], errors)

    for object_field in ("trafficContext", "restaurantDelay", "cancellationRisk"):
        if object_field in snapshot and not isinstance(snapshot[object_field], dict):
            errors.append(f"{object_field}: must be an object")

    _validate_orders(snapshot.get("orders"), errors)
    _validate_drivers(snapshot.get("drivers"), errors)
    _validate_active_routes(snapshot.get("activeRoutes"), errors)

    return {"valid": not errors, "errors": errors}


def load_snapshot(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 78 live dispatch snapshot schema.")
    parser.add_argument("--input", required=True, type=Path, help="Path to a live dispatch snapshot JSON file.")
    args = parser.parse_args(argv)

    try:
        snapshot = load_snapshot(args.input)
        result = validate_snapshot(snapshot)
    except json.JSONDecodeError as exc:
        result = {"valid": False, "errors": [f"invalid JSON: {exc}"]}
    except OSError as exc:
        result = {"valid": False, "errors": [f"cannot read input: {exc}"]}

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
