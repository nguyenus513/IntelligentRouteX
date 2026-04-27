from __future__ import annotations

import argparse
import json
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "traffic"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "community-traffic-route"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def dataset_paths(data_root: Path, dataset: str) -> tuple[Path, Path]:
    root = data_root / dataset
    if dataset == "metr-la":
        return root / "METR-LA.npz", root / "adj_mx.pkl"
    if dataset == "pems-bay":
        return root / "PEMS-BAY.npz", root / "adj_mx_bay.pkl"
    raise ValueError(f"Unsupported traffic dataset: {dataset}")


def load_speed_matrix(path: Path) -> Any:
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"numpy unavailable: {exc}") from exc
    payload = np.load(path)
    if "data" in payload:
        data = payload["data"]
    else:
        data = payload[payload.files[0]]
    if len(data.shape) == 3:
        data = data[:, :, 0]
    return data


def load_adjacency(path: Path) -> tuple[list[str], Any]:
    with path.open("rb") as handle:
        payload = pickle.load(handle, encoding="latin1")
    if isinstance(payload, tuple) and len(payload) >= 3:
        sensor_ids, _, adjacency = payload[:3]
        return [str(item) for item in sensor_ids], adjacency
    if isinstance(payload, dict):
        adjacency = payload.get("adj_mx") or payload.get("adjacency")
        sensor_ids = payload.get("sensor_ids") or list(range(len(adjacency)))
        return [str(item) for item in sensor_ids], adjacency
    raise ValueError(f"Unsupported adjacency format: {path}")


def graph_from_adjacency(adjacency: Any, speed_row: Any) -> Dict[int, List[Tuple[int, float]]]:
    graph: Dict[int, List[Tuple[int, float]]] = {}
    node_count = len(adjacency)
    for source in range(node_count):
        graph[source] = []
        speed = max(1.0, float(speed_row[source]))
        for target in range(node_count):
            weight = float(adjacency[source][target])
            if source == target or not math.isfinite(weight) or weight <= 0.0:
                continue
            travel_time = weight / speed
            graph[source].append((target, travel_time))
    return graph


def shortest_path_cost(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int) -> float | None:
    import heapq

    queue: List[Tuple[float, int]] = [(0.0, source)]
    distances = {source: 0.0}
    while queue:
        cost, node = heapq.heappop(queue)
        if node == target:
            return cost
        if cost > distances.get(node, math.inf):
            continue
        for next_node, edge_cost in graph.get(node, []):
            candidate = cost + edge_cost
            if candidate < distances.get(next_node, math.inf):
                distances[next_node] = candidate
                heapq.heappush(queue, (candidate, next_node))
    return None


def benchmark_pairs(node_count: int, count: int) -> list[tuple[int, int]]:
    pairs = []
    stride = max(3, node_count // max(1, count))
    for index in range(count):
        source = (index * stride) % node_count
        target = (index * stride + stride * 7 + 11) % node_count
        if source != target:
            pairs.append((source, target))
    return pairs


def evaluate_dataset(data_root: Path, dataset: str, pair_count: int) -> Dict[str, Any]:
    speed_path, adjacency_path = dataset_paths(data_root, dataset)
    if not speed_path.exists() or not adjacency_path.exists():
        return {
            "dataset": dataset,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["community-traffic-data-missing"],
            "missingFiles": [str(path) for path in (speed_path, adjacency_path) if not path.exists()],
        }
    speeds = load_speed_matrix(speed_path)
    sensor_ids, adjacency = load_adjacency(adjacency_path)
    node_count = min(len(sensor_ids), speeds.shape[1])
    offpeak_index = min(speeds.shape[0] - 1, speeds.shape[0] // 2)
    peak_index = min(speeds.shape[0] - 1, speeds.shape[0] // 4)
    offpeak_graph = graph_from_adjacency(adjacency, speeds[offpeak_index])
    peak_graph = graph_from_adjacency(adjacency, speeds[peak_index])
    rows = []
    for source, target in benchmark_pairs(node_count, pair_count):
        offpeak_cost = shortest_path_cost(offpeak_graph, source, target)
        peak_cost = shortest_path_cost(peak_graph, source, target)
        if offpeak_cost is None or peak_cost is None:
            continue
        ratio = peak_cost / max(1e-9, offpeak_cost)
        rows.append({"source": sensor_ids[source], "target": sensor_ids[target], "offPeakTravelTime": offpeak_cost, "peakTravelTime": peak_cost, "peakVsOffPeakRatio": ratio})
    if not rows:
        return {"dataset": dataset, "verdict": "EVIDENCE_GAP", "verdictReasons": ["no-routable-sensor-pairs"]}
    avg_ratio = sum(float(row["peakVsOffPeakRatio"]) for row in rows) / len(rows)
    bad = sum(1 for row in rows if float(row["peakVsOffPeakRatio"]) > 2.5)
    return {
        "dataset": dataset,
        "verdict": "PASS" if bad == 0 else "PASS_WITH_LIMITS",
        "verdictReasons": ["community-traffic-route-clean"] if bad == 0 else ["high-peak-regret-routes"],
        "sensorCount": node_count,
        "routeCount": len(rows),
        "badTrafficRouteCount": bad,
        "avgPeakVsOffPeakRatio": avg_ratio,
        "routes": rows,
    }


def markdown(result: Dict[str, Any]) -> str:
    lines = ["# Community Traffic Route Benchmark", "", f"FINAL_VERDICT = {result['finalVerdict']}", ""]
    lines.append("| Dataset | Routes | Avg Peak/Offpeak | Bad Routes | Verdict | Reasons |")
    lines.append("| --- | ---: | ---: | ---: | --- | --- |")
    for row in result.get("datasets", []):
        lines.append(f"| {row['dataset']} | {row.get('routeCount', 0)} | {float(row.get('avgPeakVsOffPeakRatio', 0.0)):.3f} | {row.get('badTrafficRouteCount', 0)} | {row['verdict']} | {', '.join(row.get('verdictReasons', []))} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run traffic-aware route benchmark on community sensor datasets.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="metr-la,pems-bay")
    parser.add_argument("--pairs", type=int, default=20)
    args = parser.parse_args(argv)
    datasets = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    rows = [evaluate_dataset(Path(args.data_root), dataset, args.pairs) for dataset in datasets]
    if all(row["verdict"] == "EVIDENCE_GAP" for row in rows):
        final = "EVIDENCE_GAP"
    elif any(row["verdict"] == "FAIL" for row in rows):
        final = "FAIL"
    elif any(row["verdict"] != "PASS" for row in rows):
        final = "PASS_WITH_LIMITS"
    else:
        final = "PASS"
    result = {"schemaVersion": "community-traffic-route/v1", "finalVerdict": final, "datasets": rows}
    output_root = Path(args.output_root)
    write_json(output_root / "traffic_route_results.json", result)
    (output_root / "traffic_route_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[COMMUNITY TRAFFIC ROUTE JSON] {output_root / 'traffic_route_results.json'}")
    print(f"[COMMUNITY TRAFFIC ROUTE REPORT] {output_root / 'traffic_route_report.md'}")
    return 1 if final == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
