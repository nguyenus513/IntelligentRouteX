from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from run_route_beauty_benchmark import (
    DEFAULT_DATA_ROOT,
    REPO_ROOT,
    benchmark_pairs,
    read_coordinates,
    read_graph,
    route_shape_metrics,
    shortest_path,
)


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "route-condition-community"
PROFILES = {
    "clear": {"traffic": 0.0, "weather": 0.0},
    "rain": {"traffic": 0.15, "weather": 0.35},
    "traffic-shock": {"traffic": 0.55, "weather": 0.05},
    "storm-peak": {"traffic": 0.65, "weather": 0.55},
}


def edge_factor(source: int, target: int, profile: Dict[str, float]) -> float:
    bucket = ((source * 1103515245 + target * 12345) & 0x7FFFFFFF) / 0x7FFFFFFF
    traffic_penalty = 1.0 + profile["traffic"] * (0.5 + bucket)
    weather_penalty = 1.0 + profile["weather"] * (0.25 + (1.0 - bucket) * 0.5)
    return traffic_penalty * weather_penalty


def weighted_path(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int, profile: Dict[str, float]) -> Tuple[float, List[int]] | None:
    queue: List[Tuple[float, int]] = [(0.0, source)]
    distances = {source: 0.0}
    previous: Dict[int, int] = {}
    while queue:
        distance, node = heapq.heappop(queue)
        if node == target:
            path = [target]
            while path[-1] != source:
                path.append(previous[path[-1]])
            path.reverse()
            return distance, path
        if distance > distances.get(node, math.inf):
            continue
        for next_node, weight in graph.get(node, []):
            candidate = distance + weight * edge_factor(node, next_node, profile)
            if candidate < distances.get(next_node, math.inf):
                distances[next_node] = candidate
                previous[next_node] = node
                heapq.heappush(queue, (candidate, next_node))
    return None


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def markdown(result: Dict[str, object]) -> str:
    lines = ["# Route Condition Community Benchmark", "", f"FINAL_VERDICT = {result['finalVerdict']}", ""]
    lines.append("| Profile | Region | Pair | Distance Ratio | Condition Cost Ratio | Straightness | Turns | Verdict |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | --- |")
    for row in result.get("routes", []):
        lines.append(
            f"| {row['profile']} | {row['region']} | {row['source']}->{row['target']} | {row['distanceRatio']:.3f} | {row['conditionCostRatio']:.3f} | {row['straightnessScore']:.3f} | {row['turnCount']} | {row['routeVerdict']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run road-route quality benchmark under transparent traffic/weather profiles.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--regions", default="NY")
    parser.add_argument("--profiles", default="clear,rain,traffic-shock,storm-peak")
    parser.add_argument("--node-limit", type=int, default=50_000)
    parser.add_argument("--pairs", type=int, default=20)
    args = parser.parse_args(argv)
    data_root = Path(args.data_root)
    regions = [part.strip().upper() for part in args.regions.split(",") if part.strip()]
    profiles = [part.strip() for part in args.profiles.split(",") if part.strip()]
    missing = [region for region in regions if not (data_root / f"USA-road-d.{region}.gr.gz").exists() or not (data_root / f"USA-road-d.{region}.co.gz").exists()]
    if missing:
        result = {"schemaVersion": "route-condition-community/v1", "finalVerdict": "EVIDENCE_GAP", "verdictReasons": ["dimacs-road-data-missing"], "missingRegions": missing, "routes": []}
        output_root = Path(args.output_root)
        write_json(output_root / "route_condition_results.json", result)
        (output_root / "route_condition_report.md").write_text(markdown(result), encoding="utf-8")
        return 2
    rows: List[Dict[str, object]] = []
    for region in regions:
        graph = read_graph(data_root / f"USA-road-d.{region}.gr.gz", args.node_limit)
        coordinates = read_coordinates(data_root / f"USA-road-d.{region}.co.gz", args.node_limit)
        nodes = sorted(node for node in graph if graph[node] and node in coordinates)
        for source, target in benchmark_pairs(nodes, args.pairs):
            base = shortest_path(graph, source, target)
            if base is None:
                continue
            base_distance, _ = base
            for profile_name in profiles:
                profile = PROFILES[profile_name]
                conditioned = weighted_path(graph, source, target, profile)
                if conditioned is None:
                    continue
                condition_cost, path = conditioned
                metrics = route_shape_metrics(path, coordinates, base_distance)
                distance_ratio = float(metrics["networkDistance"]) / max(1.0, base_distance)
                condition_cost_ratio = condition_cost / max(1.0, base_distance)
                route_verdict = "PASS" if distance_ratio <= 1.35 and condition_cost_ratio <= 2.25 and float(metrics["straightnessScore"]) >= 0.25 else "PASS_WITH_LIMITS"
                rows.append({
                    "region": region,
                    "profile": profile_name,
                    "source": source,
                    "target": target,
                    "distanceRatio": distance_ratio,
                    "conditionCostRatio": condition_cost_ratio,
                    "routeVerdict": route_verdict,
                    **metrics,
                })
    bad = sum(1 for row in rows if row["routeVerdict"] != "PASS")
    final = "EVIDENCE_GAP" if not rows else ("PASS_WITH_LIMITS" if bad else "PASS")
    result = {
        "schemaVersion": "route-condition-community/v1",
        "benchmarkFamily": "dimacs-road-condition-stress",
        "regions": regions,
        "profiles": profiles,
        "evaluatedRoutes": len(rows),
        "badConditionRouteCount": bad,
        "finalVerdict": final,
        "verdictReasons": ["condition-route-limits"] if bad else ["condition-route-quality-clean"],
        "avgDistanceRatio": sum(float(row["distanceRatio"]) for row in rows) / len(rows) if rows else 0.0,
        "avgConditionCostRatio": sum(float(row["conditionCostRatio"]) for row in rows) / len(rows) if rows else 0.0,
        "avgStraightnessScore": sum(float(row["straightnessScore"]) for row in rows) / len(rows) if rows else 0.0,
        "routes": rows,
    }
    output_root = Path(args.output_root)
    write_json(output_root / "route_condition_results.json", result)
    (output_root / "route_condition_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[ROUTE CONDITION JSON] {output_root / 'route_condition_results.json'}")
    print(f"[ROUTE CONDITION REPORT] {output_root / 'route_condition_report.md'}")
    return 1 if final == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
