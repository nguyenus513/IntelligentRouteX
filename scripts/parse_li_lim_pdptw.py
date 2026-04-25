from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from external_benchmark_support import best_known, normalize_instance, read_lines

OFFICIAL_BEST_KNOWN: Dict[str, Dict[str, Any]] = {
    "LC101": {"vehicleCount": 10, "objective": 828.94, "source": "Li & Lim/SINTEF PDPTW 100 customers BKS"},
    "LR101": {"vehicleCount": 19, "objective": 1650.80, "source": "Li & Lim/SINTEF PDPTW 100 customers BKS"},
    "LRC101": {"vehicleCount": 14, "objective": 1708.80, "source": "Li & Lim/SINTEF PDPTW 100 customers BKS"},
}


def _best_known(instance_name: str, lines: Iterable[str]) -> Dict[str, Any]:
    parsed = best_known(lines)
    if "objective" in parsed:
        return parsed
    return OFFICIAL_BEST_KNOWN.get(instance_name.upper(), {"source": "missing"})


def _parse_fixture(lines: List[str], path: Path) -> dict:
    instance_name = lines[0]
    capacity = 0
    vehicle_count = 0
    node_header = -1
    for index, line in enumerate(lines):
        if line.startswith("NUMBER") and index + 1 < len(lines):
            parts = lines[index + 1].split()
            vehicle_count = int(parts[0])
            capacity = int(parts[1])
        if line.startswith("ID X Y"):
            node_header = index
            break
    if node_header < 0:
        raise ValueError(f"Li & Lim node header not found: {path}")
    if vehicle_count <= 0 or capacity <= 0:
        raise ValueError(f"Li & Lim vehicle metadata not found: {path}")
    nodes = []
    for line in lines[node_header + 1:]:
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        nodes.append({
            "id": parts[0],
            "x": float(parts[1]),
            "y": float(parts[2]),
            "demand": int(float(parts[3])),
            "readyTime": float(parts[4]),
            "dueTime": float(parts[5]),
            "serviceTime": float(parts[6]),
            "pairNodeId": None if parts[7] == "-" else parts[7],
            "type": parts[8],
        })
    return _normalize(instance_name, vehicle_count, capacity, nodes, lines, path)


def _parse_official(lines: List[str], path: Path) -> dict:
    instance_name = path.stem.upper()
    header = lines[0].split()
    if len(header) < 2:
        raise ValueError(f"Li & Lim official vehicle metadata not found: {path}")
    vehicle_count = int(float(header[0]))
    capacity = int(float(header[1]))
    nodes = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        node_id = parts[0]
        demand = int(float(parts[3]))
        pickup_pair = parts[7]
        dropoff_pair = parts[8]
        node_type = "DEPOT"
        pair_node_id = None
        if node_id != "0" and demand > 0:
            node_type = "PICKUP"
            pair_node_id = dropoff_pair
        elif node_id != "0" and demand < 0:
            node_type = "DROPOFF"
            pair_node_id = pickup_pair
        nodes.append({
            "id": node_id,
            "x": float(parts[1]),
            "y": float(parts[2]),
            "demand": demand,
            "readyTime": float(parts[4]),
            "dueTime": float(parts[5]),
            "serviceTime": float(parts[6]),
            "pairNodeId": pair_node_id,
            "type": node_type,
        })
    return _normalize(instance_name, vehicle_count, capacity, nodes, lines, path)


def _normalize(instance_name: str, vehicle_count: int, capacity: int, nodes: List[Dict[str, Any]], lines: Iterable[str], path: Path) -> dict:
    if not nodes:
        raise ValueError(f"Li & Lim instance has no node rows: {path}")
    node_ids = {str(node["id"]) for node in nodes}
    requests = []
    for node in nodes:
        if node["type"] == "PICKUP":
            dropoff = str(node.get("pairNodeId"))
            if dropoff not in node_ids:
                raise ValueError(f"Li & Lim pickup {node['id']} points to missing dropoff {dropoff}: {path}")
            requests.append({
                "requestId": f"request-{node['id']}-{dropoff}",
                "pickupNodeId": node["id"],
                "dropoffNodeId": dropoff,
                "demand": node["demand"],
            })
    if not requests:
        raise ValueError(f"Li & Lim instance has no pickup/dropoff requests: {path}")
    return normalize_instance(
        "li-lim",
        "PDPTW",
        instance_name,
        vehicle_count,
        capacity,
        nodes,
        requests,
        _best_known(instance_name, lines),
        source_path=str(path),
    )


def parse_li_lim(path: Path) -> dict:
    lines = read_lines(path)
    if any(line.startswith("ID X Y") for line in lines):
        return _parse_fixture(lines, path)
    return _parse_official(lines, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a Li & Lim PDPTW instance into normalized JSON.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = parse_li_lim(Path(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
