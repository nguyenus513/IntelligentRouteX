from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmarks" / "synthetic_food" / "generated_v1"


SCENARIOS = {
    "lunch_peak": {"orders": 24, "drivers": 8, "start": 11 * 60, "window": 35, "cluster": 0.45, "traffic": 1.0, "risk": 0.05},
    "dinner_peak": {"orders": 28, "drivers": 9, "start": 18 * 60, "window": 45, "cluster": 0.25, "traffic": 1.1, "risk": 0.06},
    "apartment_cluster": {"orders": 26, "drivers": 8, "start": 17 * 60, "window": 50, "cluster": 0.75, "traffic": 1.0, "risk": 0.04},
    "rain_peak": {"orders": 24, "drivers": 8, "start": 18 * 60, "window": 40, "cluster": 0.35, "traffic": 1.45, "risk": 0.08},
    "sparse_suburban": {"orders": 18, "drivers": 7, "start": 14 * 60, "window": 65, "cluster": 0.10, "traffic": 1.2, "risk": 0.03},
    "cancellation_risk": {"orders": 22, "drivers": 8, "start": 19 * 60, "window": 50, "cluster": 0.30, "traffic": 1.05, "risk": 0.22},
}


def distance(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    return math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))


def matrix(nodes: List[Dict[str, Any]], traffic: float) -> List[List[float]]:
    return [[distance(left, right) * traffic for right in nodes] for left in nodes]


def point(rng: random.Random, center: Tuple[float, float], spread: float) -> Tuple[float, float]:
    return (center[0] + rng.uniform(-spread, spread), center[1] + rng.uniform(-spread, spread))


def generate_scenario(name: str, seed: int) -> Dict[str, Any]:
    spec = SCENARIOS[name]
    rng = random.Random(f"{seed}:{name}")
    depot = {"id": "0", "x": 5.0, "y": 5.0, "demand": 0, "readyTime": spec["start"] - 30, "dueTime": spec["start"] + 240, "serviceTime": 0}
    nodes = [depot]
    requests = []
    orders = []
    apartment_center = (6.2, 5.8)
    restaurant_centers = [(4.2, 4.8), (4.8, 5.5), (5.5, 4.5), (3.8, 6.0)]
    for order_index in range(1, int(spec["orders"]) + 1):
        pickup_center = restaurant_centers[order_index % len(restaurant_centers)]
        pickup_x, pickup_y = point(rng, pickup_center, 0.5)
        clustered = rng.random() < float(spec["cluster"])
        dropoff_center = apartment_center if clustered else (rng.uniform(2.5, 7.5), rng.uniform(2.5, 7.5))
        dropoff_x, dropoff_y = point(rng, dropoff_center, 0.4 if clustered else 0.9)
        ready = int(spec["start"] + rng.randint(0, 45))
        pickup_id = str(order_index * 2 - 1)
        dropoff_id = str(order_index * 2)
        nodes.append({"id": pickup_id, "x": round(pickup_x, 3), "y": round(pickup_y, 3), "demand": 1, "readyTime": ready, "dueTime": ready + int(spec["window"]) + 20, "serviceTime": 2})
        nodes.append({"id": dropoff_id, "x": round(dropoff_x, 3), "y": round(dropoff_y, 3), "demand": -1, "readyTime": ready + 3, "dueTime": ready + int(spec["window"]) + 45, "serviceTime": 1})
        requests.append({"pickupNodeId": pickup_id, "dropoffNodeId": dropoff_id, "orderId": f"{name}-{order_index:03d}", "cancellationRisk": round(float(spec["risk"]) + rng.random() * 0.05, 3)})
        orders.append({"orderId": f"{name}-{order_index:03d}", "pickupNodeId": pickup_id, "dropoffNodeId": dropoff_id, "cancellationRisk": requests[-1]["cancellationRisk"]})
    duration_matrix = matrix(nodes, float(spec["traffic"]))
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "benchmarkFamily": "synthetic-food",
        "instanceName": name,
        "problemType": "PDPTW",
        "depotNodeId": "0",
        "vehicleCount": int(spec["drivers"]),
        "capacity": 4,
        "nodes": nodes,
        "requests": requests,
        "distanceMatrix": matrix(nodes, 1.0),
        "durationMatrix": duration_matrix,
        "orders": orders,
        "drivers": [{"driverId": f"driver-{index:02d}", "capacity": 4} for index in range(1, int(spec["drivers"]) + 1)],
        "activeRoutes": [],
        "constraints": {"pickupDelivery": True, "capacity": 4, "timeWindows": True},
        "expectedStress": scenario_stress(name),
        "metadata": {"scenario": name, "seed": seed, "trafficMultiplier": spec["traffic"], "assumptions": "Synthetic HCM-like food dispatch; no real customer data."},
    }


def scenario_stress(name: str) -> Dict[str, bool]:
    return {
        "peak": name in {"lunch_peak", "dinner_peak", "rain_peak"},
        "tightTimeWindows": name in {"lunch_peak", "rain_peak"},
        "clusteredDropoffs": name == "apartment_cluster",
        "longDistances": name == "sparse_suburban",
        "highCancellationRisk": name == "cancellation_risk",
        "rainTraffic": name == "rain_peak",
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def generate(output_dir: Path, seed: int) -> Dict[str, Any]:
    scenarios = []
    for name in SCENARIOS:
        instance = generate_scenario(name, seed)
        write_json(output_dir / f"{name}.json", instance)
        scenarios.append({"scenario": name, "path": str(output_dir / f"{name}.json"), "orders": len(instance["requests"]), "drivers": instance["vehicleCount"], "expectedStress": instance["expectedStress"]})
    manifest = {"schemaVersion": "phase64-synthetic-food-dataset/v1", "seed": seed, "scenarioCount": len(scenarios), "scenarios": scenarios}
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic production-like synthetic food dispatch PDPTW datasets.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed", type=int, default=64)
    args = parser.parse_args()
    generate(Path(args.output_dir), args.seed)
    print(f"[PHASE64 SYNTHETIC FOOD DATASET] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
