from __future__ import annotations

import argparse
import json
from pathlib import Path

from external_benchmark_support import best_known, normalize_instance, read_lines


def parse_li_lim(path: Path) -> dict:
    lines = read_lines(path)
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
    if not nodes:
        raise ValueError(f"Li & Lim instance has no node rows: {path}")
    requests = []
    for node in nodes:
        if node["type"] == "PICKUP":
            requests.append({
                "requestId": f"request-{node['id']}-{node['pairNodeId']}",
                "pickupNodeId": node["id"],
                "dropoffNodeId": node["pairNodeId"],
                "demand": node["demand"],
            })
    if not requests:
        raise ValueError(f"Li & Lim instance has no pickup/dropoff requests: {path}")
    return normalize_instance("li-lim", "PDPTW", instance_name, vehicle_count, capacity, nodes, requests, best_known(lines))


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
