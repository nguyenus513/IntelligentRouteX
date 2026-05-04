from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from phase67_synthetic_instance_loader import load_benchmark_instance


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "final" / "synthetic_food_full_real_20260504_131148"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase71_food_dispatch_metrics_v1"
DEFAULT_DOC = REPO_ROOT / "docs" / "benchmark" / "food_dispatch_metrics.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}


def node_by_id(instance: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(node.get("id")): node for node in instance.get("nodes", [])}


def travel(instance: Dict[str, Any], left: str, right: str) -> float:
    indexes = matrix_index(instance)
    matrix = instance.get("durationMatrix") or instance.get("distanceMatrix")
    return float(matrix[indexes[str(left)]][indexes[str(right)]])


def percentile(values: List[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))]


def route_schedule(instance: Dict[str, Any], route: List[str]) -> Dict[str, float]:
    nodes = node_by_id(instance)
    arrival: Dict[str, float] = {}
    elapsed = 0.0
    for previous, current in zip(route, route[1:]):
        elapsed += travel(instance, str(previous), str(current))
        node = nodes[str(current)]
        ready = float(node.get("readyTime", 0.0))
        if elapsed < ready:
            elapsed = ready
        arrival[str(current)] = elapsed
        elapsed += float(node.get("serviceTime", 0.0))
    return arrival


def compute_instance_metrics(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    arrivals: Dict[str, float] = {}
    route_pair_counts = []
    route_durations = []
    for route in solution.get("routes", []):
        schedule = route_schedule(instance, [str(stop) for stop in route])
        arrivals.update(schedule)
        if len(route) > 2:
            route_durations.append(max(schedule.values()) - min(schedule.values()) if schedule else 0.0)
            route_pair_counts.append(max(0, (len(route) - 2) // 2))
    delivery_times = []
    pickup_delays = []
    dropoff_delays = []
    late_flags = []
    risk_late = []
    for request in instance.get("requests", []):
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        if pickup not in arrivals or dropoff not in arrivals:
            continue
        pickup_node = node_by_id(instance)[pickup]
        dropoff_node = node_by_id(instance)[dropoff]
        pickup_delay = max(0.0, arrivals[pickup] - float(pickup_node.get("readyTime", 0.0)))
        dropoff_delay = max(0.0, arrivals[dropoff] - float(dropoff_node.get("readyTime", 0.0)))
        late = arrivals[dropoff] > float(dropoff_node.get("dueTime", 0.0))
        risk = float(request.get("cancellationRisk", 0.0) or 0.0)
        delivery_times.append(arrivals[dropoff] - arrivals[pickup])
        pickup_delays.append(pickup_delay)
        dropoff_delays.append(dropoff_delay)
        late_flags.append(1.0 if late else 0.0)
        risk_late.append(risk if late else 0.0)
    return {
        "orderToDeliveryMean": sum(delivery_times) / len(delivery_times) if delivery_times else None,
        "orderToDeliveryP95": percentile(delivery_times, 0.95),
        "orderToDeliveryP99": percentile(delivery_times, 0.99),
        "pickupDelayMean": sum(pickup_delays) / len(pickup_delays) if pickup_delays else None,
        "dropoffDelayMean": sum(dropoff_delays) / len(dropoff_delays) if dropoff_delays else None,
        "lateOrderRate": sum(late_flags) / len(late_flags) if late_flags else None,
        "driverUtilization": len([count for count in route_pair_counts if count > 0]) / max(1, int(instance.get("vehicleCount", 1))),
        "driverLoadBalance": (max(route_pair_counts) - min(route_pair_counts)) if route_pair_counts else None,
        "batchingRatio": sum(route_pair_counts) / max(1, len(route_pair_counts)) if route_pair_counts else 0.0,
        "routeDurationMean": sum(route_durations) / len(route_durations) if route_durations else None,
        "riskWeightedLateRate": sum(risk_late) / max(1, len(risk_late)),
    }


def compute_metrics(input_dir: Path) -> Dict[str, Any]:
    summary = read_json(input_dir / "challenger_phase56f" / "phase56b_stable_promoted_summary.json")
    rows = []
    for row in summary.get("results", []):
        instance_name = str(row.get("instance"))
        instance = load_benchmark_instance("synthetic-food", instance_name)
        solution = read_json(input_dir / "challenger_phase56f" / instance_name / "final_solution.json")
        metrics = compute_instance_metrics(instance, solution)
        rows.append({"instance": instance_name, **metrics})
    aggregate = aggregate_metrics(rows)
    return {"schemaVersion": "phase71-food-dispatch-metrics/v1", "inputDir": str(input_dir), "rows": rows, "aggregate": aggregate, "gate": food_gate(aggregate)}


def aggregate_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = ["orderToDeliveryMean", "orderToDeliveryP95", "orderToDeliveryP99", "pickupDelayMean", "dropoffDelayMean", "lateOrderRate", "driverUtilization", "driverLoadBalance", "batchingRatio", "routeDurationMean", "riskWeightedLateRate"]
    aggregate = {}
    for field in fields:
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        aggregate[field] = sum(values) / len(values) if values else None
    return aggregate


def food_gate(aggregate: Dict[str, Any]) -> str:
    if aggregate.get("lateOrderRate") is not None and aggregate.get("lateOrderRate", 1.0) > 0.0:
        return "PARTIAL"
    if aggregate.get("orderToDeliveryP95") is not None and aggregate.get("orderToDeliveryP95", 0.0) > 90.0:
        return "PARTIAL"
    return "PASS"


def write_outputs(metrics: Dict[str, Any], output_dir: Path, doc_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase71_food_dispatch_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    text = markdown(metrics)
    (output_dir / "phase71_food_dispatch_metrics.md").write_text(text, encoding="utf-8")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(text, encoding="utf-8")


def markdown(metrics: Dict[str, Any]) -> str:
    lines = ["# Phase 71 Food Dispatch Metrics", "", f"Gate: **{metrics['gate']}**", "", "| Instance | O2D Mean | O2D P95 | Late Rate | Batching | Load Balance |", "|---|---:|---:|---:|---:|---:|"]
    for row in metrics.get("rows", []):
        lines.append(f"| {row['instance']} | {row.get('orderToDeliveryMean')} | {row.get('orderToDeliveryP95')} | {row.get('lateOrderRate')} | {row.get('batchingRatio')} | {row.get('driverLoadBalance')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute synthetic food dispatch metrics from Phase 63 artifacts.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    args = parser.parse_args()
    metrics = compute_metrics(Path(args.input_dir))
    write_outputs(metrics, Path(args.output_dir), Path(args.doc))
    print(f"[PHASE71 FOOD DISPATCH METRICS] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
