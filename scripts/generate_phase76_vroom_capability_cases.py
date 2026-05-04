from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmarks" / "vroom_capability" / "generated_v1"


CASES = [
    "single_shipment",
    "two_shipments_same_driver_bundle",
    "capacity_blocks_bundle",
    "time_window_blocks_bundle",
    "waiting_required",
    "service_time_required",
    "driver_selection_nearest",
    "driver_skill_matching",
    "vehicle_shift_window",
    "driver_break",
    "open_route",
    "priority_unassigned",
    "custom_matrix_asymmetric",
    "pickup_delivery_precedence",
    "multi_driver_load_balance",
]


def dist(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    return math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))


def matrix(nodes: List[Dict[str, Any]], asymmetric: bool = False) -> List[List[float]]:
    output = []
    for i, left in enumerate(nodes):
        row = []
        for j, right in enumerate(nodes):
            value = dist(left, right)
            if asymmetric and i > j:
                value *= 1.8
            row.append(round(value, 3))
        output.append(row)
    return output


def node(node_id: str, x: float, y: float, demand: int = 0, ready: int = 0, due: int = 200, service: int = 0) -> Dict[str, Any]:
    return {"id": node_id, "x": x, "y": y, "demand": demand, "readyTime": ready, "dueTime": due, "serviceTime": service}


def request(index: int, ready: int = 0, due: int = 200, amount: int = 1, skills: List[int] | None = None, priority: int | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    pickup_id = str(index * 2 - 1)
    dropoff_id = str(index * 2)
    nodes = [node(pickup_id, 2 + index, 2, amount, ready, due, 1), node(dropoff_id, 2 + index, 4, -amount, ready, due + 20, 1)]
    payload: Dict[str, Any] = {"pickupNodeId": pickup_id, "dropoffNodeId": dropoff_id, "demand": amount}
    if skills:
        payload["skills"] = skills
    if priority is not None:
        payload["priority"] = priority
    return nodes, payload


def base_case(name: str, request_count: int = 2, vehicle_count: int = 2, capacity: int = 4, asymmetric: bool = False, expected: Dict[str, Any] | None = None) -> Dict[str, Any]:
    nodes = [node("0", 0, 0, 0, 0, 300, 0)]
    requests = []
    for index in range(1, request_count + 1):
        req_nodes, req = request(index)
        nodes.extend(req_nodes)
        requests.append(req)
    return normalized(name, nodes, requests, vehicle_count, capacity, asymmetric=asymmetric, expected=expected)


def normalized(name: str, nodes: List[Dict[str, Any]], requests: List[Dict[str, Any]], vehicle_count: int, capacity: int, *, asymmetric: bool = False, expected: Dict[str, Any] | None = None, vroom_vehicles: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    mat = matrix(nodes, asymmetric=asymmetric)
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "benchmarkFamily": "vroom-capability",
        "instanceName": name,
        "problemType": "PDPTW",
        "depotNodeId": "0",
        "vehicleCount": vehicle_count,
        "capacity": capacity,
        "nodes": nodes,
        "requests": requests,
        "distanceMatrix": mat,
        "durationMatrix": mat,
        "bestKnown": {},
        "capabilityExpected": expected or {},
        "vroomVehicles": vroom_vehicles or [],
    }


def build_case(name: str) -> Dict[str, Any]:
    if name == "single_shipment":
        return base_case(name, 1, 1, expected={"vroomExpected": "one-feasible-route"})
    if name == "two_shipments_same_driver_bundle":
        return base_case(name, 2, 1, capacity=4, expected={"vroomExpected": "bundle-two-shipments"})
    if name == "capacity_blocks_bundle":
        case = base_case(name, 2, 2, capacity=1, expected={"vroomExpected": "requires-more-than-one-route"})
        return case
    if name == "time_window_blocks_bundle":
        nodes = [node("0", 0, 0, 0, 0, 300)]
        req1_nodes, req1 = request(1, 0, 30)
        req2_nodes, req2 = request(2, 120, 150)
        nodes.extend(req1_nodes + req2_nodes)
        return normalized(name, nodes, [req1, req2], 2, 4, expected={"vroomExpected": "time-windows-block-single-bundle"})
    if name == "waiting_required":
        nodes = [node("0", 0, 0, 0, 0, 300), node("1", 1, 0, 1, 50, 100, 1), node("2", 2, 0, -1, 55, 130, 1)]
        return normalized(name, nodes, [{"pickupNodeId": "1", "dropoffNodeId": "2"}], 1, 2, expected={"vroomExpected": "waiting-required"})
    if name == "service_time_required":
        nodes = [node("0", 0, 0, 0, 0, 300), node("1", 1, 0, 1, 0, 100, 20), node("2", 2, 0, -1, 0, 130, 10)]
        return normalized(name, nodes, [{"pickupNodeId": "1", "dropoffNodeId": "2"}], 1, 2, expected={"vroomExpected": "service-affects-arrival"})
    if name == "driver_selection_nearest":
        case = base_case(name, 1, 2, expected={"vroomExpected": "nearest-driver-selected"})
        case["vroomVehicles"] = [{"id": 1, "start_index": 0, "end_index": 0, "capacity": [4]}, {"id": 2, "start_index": 1, "end_index": 0, "capacity": [4]}]
        return case
    if name == "driver_skill_matching":
        nodes, req = request(1, skills=[7])
        return normalized(name, [node("0", 0, 0, 0, 0, 300)] + nodes, [req], 2, 4, expected={"vroomExpected": "skill-matched-driver"}, vroom_vehicles=[{"id": 1, "start_index": 0, "end_index": 0, "capacity": [4], "skills": [7]}, {"id": 2, "start_index": 0, "end_index": 0, "capacity": [4], "skills": [1]}])
    if name == "vehicle_shift_window":
        case = base_case(name, 1, 2, expected={"vroomExpected": "respect-driver-shift"})
        case["vroomVehicles"] = [{"id": 1, "start_index": 0, "end_index": 0, "capacity": [4], "time_window": [0, 20]}, {"id": 2, "start_index": 0, "end_index": 0, "capacity": [4], "time_window": [0, 300]}]
        return case
    if name == "driver_break":
        case = base_case(name, 2, 1, expected={"vroomExpected": "break-respected"})
        case["vroomVehicles"] = [{"id": 1, "start_index": 0, "end_index": 0, "capacity": [4], "breaks": [{"id": 1, "time_windows": [[20, 60]], "service": 5}]}]
        return case
    if name == "open_route":
        case = base_case(name, 1, 1, expected={"vroomExpected": "open-route-supported"})
        case["vroomVehicles"] = [{"id": 1, "start_index": 0, "capacity": [4]}]
        return case
    if name == "priority_unassigned":
        case = base_case(name, 2, 1, capacity=1, expected={"vroomExpected": "priority-controls-unassigned"})
        case["requests"][0]["priority"] = 100
        case["requests"][1]["priority"] = 1
        return case
    if name == "custom_matrix_asymmetric":
        return base_case(name, 2, 1, asymmetric=True, expected={"vroomExpected": "asymmetric-matrix-respected"})
    if name == "pickup_delivery_precedence":
        return base_case(name, 2, 1, expected={"vroomExpected": "pickup-before-delivery"})
    if name == "multi_driver_load_balance":
        return base_case(name, 4, 2, expected={"vroomExpected": "multiple-drivers-used-if-beneficial"})
    raise ValueError(name)


def generate(output_dir: Path, seed: int = 76) -> Dict[str, Any]:
    del seed
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for name in CASES:
        case = build_case(name)
        path = output_dir / f"{name}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")
        cases.append({"case": name, "path": str(path), "expected": case.get("capabilityExpected", {})})
    manifest = {"schemaVersion": "phase76-vroom-capability-cases/v1", "caseCount": len(cases), "cases": cases}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate VROOM capability micro-test normalized PDPTW cases.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed", type=int, default=76)
    args = parser.parse_args()
    generate(Path(args.output_dir), args.seed)
    print(f"[PHASE76 VROOM CAPABILITY] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
