from __future__ import annotations

import argparse
import gzip
import heapq
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "dimacs-road"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "route-beauty-community"


def read_coordinates(path: Path, limit: int) -> Dict[int, Tuple[float, float]]:
    coordinates: Dict[int, Tuple[float, float]] = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line or line[0] != "v":
                continue
            _, node_id, lon, lat = line.split()[:4]
            numeric_id = int(node_id)
            if numeric_id <= limit:
                coordinates[numeric_id] = (float(lon) / 1_000_000, float(lat) / 1_000_000)
            if len(coordinates) >= limit:
                break
    return coordinates


def read_graph(path: Path, node_limit: int) -> Dict[int, List[Tuple[int, float]]]:
    graph: Dict[int, List[Tuple[int, float]]] = {node: [] for node in range(1, node_limit + 1)}
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line or line[0] != "a":
                continue
            _, source, target, weight = line.split()[:4]
            left = int(source)
            right = int(target)
            if left <= node_limit and right <= node_limit:
                graph.setdefault(left, []).append((right, float(weight)))
    return graph


def shortest_path(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int) -> Tuple[float, List[int]] | None:
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
            candidate = distance + weight
            if candidate < distances.get(next_node, math.inf):
                distances[next_node] = candidate
                previous[next_node] = node
                heapq.heappush(queue, (candidate, next_node))
    return None


def euclidean_path_distance(path: Sequence[int], coordinates: Dict[int, Tuple[float, float]]) -> float:
    total = 0.0
    for left, right in zip(path, path[1:]):
        if left not in coordinates or right not in coordinates:
            continue
        left_lon, left_lat = coordinates[left]
        right_lon, right_lat = coordinates[right]
        total += math.hypot(right_lon - left_lon, right_lat - left_lat)
    return total


def turn_angle_degrees(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    vector_ab = (b[0] - a[0], b[1] - a[1])
    vector_bc = (c[0] - b[0], c[1] - b[1])
    norm_ab = math.hypot(*vector_ab)
    norm_bc = math.hypot(*vector_bc)
    if norm_ab == 0.0 or norm_bc == 0.0:
        return 0.0
    cosine = max(-1.0, min(1.0, (vector_ab[0] * vector_bc[0] + vector_ab[1] * vector_bc[1]) / (norm_ab * norm_bc)))
    return math.degrees(math.acos(cosine))


def route_shape_metrics(path: Sequence[int], coordinates: Dict[int, Tuple[float, float]], network_distance: float) -> Dict[str, float | int | bool]:
    if len(path) < 2 or path[0] not in coordinates or path[-1] not in coordinates:
        return {"routePolylinePresent": False, "turnCount": 0, "sharpTurnCount": 0, "straightnessScore": 0.0, "networkDetourRatio": 0.0}
    start = coordinates[path[0]]
    end = coordinates[path[-1]]
    direct = math.hypot(end[0] - start[0], end[1] - start[1])
    euclidean_distance = euclidean_path_distance(path, coordinates)
    turn_count = 0
    sharp_turn_count = 0
    for left, middle, right in zip(path, path[1:], path[2:]):
        if left not in coordinates or middle not in coordinates or right not in coordinates:
            continue
        angle = turn_angle_degrees(coordinates[left], coordinates[middle], coordinates[right])
        if angle >= 30.0:
            turn_count += 1
        if angle >= 90.0:
            sharp_turn_count += 1
    straightness = 1.0 if euclidean_distance <= 0.0 else direct / euclidean_distance
    network_detour = 1.0 if direct <= 0.0 else euclidean_distance / direct
    return {
        "routePolylinePresent": True,
        "polylinePointCount": len(path),
        "turnCount": turn_count,
        "sharpTurnCount": sharp_turn_count,
        "straightnessScore": straightness,
        "networkDetourRatio": network_detour,
        "networkDistance": network_distance,
    }


def benchmark_pairs(nodes: Sequence[int], count: int) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int]] = []
    stride = max(7, len(nodes) // max(1, count))
    for index in range(count):
        source = nodes[(index * stride) % len(nodes)]
        target = nodes[(index * stride + stride * 5 + 17) % len(nodes)]
        if source != target:
            pairs.append((source, target))
    return pairs


def verdict(rows: Sequence[Dict[str, object]]) -> Tuple[str, List[str]]:
    if not rows:
        return "EVIDENCE_GAP", ["no-routable-pairs"]
    missing_polyline = sum(1 for row in rows if not row["routePolylinePresent"])
    bad_routes = sum(1 for row in rows if float(row["straightnessScore"]) < 0.30 or float(row["networkDetourRatio"]) > 4.0)
    if missing_polyline:
        return "FAIL", ["missing-route-polyline"]
    if bad_routes:
        return "PASS_WITH_LIMITS", ["high-detour-or-low-straightness-routes"]
    return "PASS", ["community-road-route-shape-clean"]


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def markdown(result: Dict[str, object]) -> str:
    lines = ["# Route Beauty Community Benchmark", "", f"FINAL_VERDICT = {result['finalVerdict']}", ""]
    lines.append("| Pair | Points | Straightness | Detour | Turns | Sharp Turns | Verdict |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in result["routes"]:
        route_verdict = "PASS" if row["routePolylinePresent"] and row["straightnessScore"] >= 0.30 and row["networkDetourRatio"] <= 4.0 else "PASS_WITH_LIMITS"
        pair_label = f"{row.get('region', '')}:{row['source']}->{row['target']}"
        lines.append(f"| {pair_label} | {row['polylinePointCount']} | {row['straightnessScore']:.3f} | {row['networkDetourRatio']:.3f} | {row['turnCount']} | {row['sharpTurnCount']} | {route_verdict} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run public DIMACS route-shape/route-beauty benchmark.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--node-limit", type=int, default=20_000)
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--regions", default="NY", help="Comma-separated DIMACS regions to evaluate.")
    args = parser.parse_args(argv)
    data_root = Path(args.data_root)
    regions = [part.strip().upper() for part in args.regions.split(",") if part.strip()]
    missing = [region for region in regions if not (data_root / f"USA-road-d.{region}.gr.gz").exists() or not (data_root / f"USA-road-d.{region}.co.gz").exists()]
    if missing:
        result = {"schemaVersion": "route-beauty-community/v1", "finalVerdict": "EVIDENCE_GAP", "verdictReasons": ["dimacs-road-data-missing"]}
        result["missingRegions"] = missing
        output_root = Path(args.output_root)
        write_json(output_root / "route_beauty_results.json", result)
        (output_root / "route_beauty_report.md").write_text(markdown({"finalVerdict": "EVIDENCE_GAP", "routes": []}), encoding="utf-8")
        print(f"[ROUTE BEAUTY JSON] {output_root / 'route_beauty_results.json'}")
        return 2
    rows: List[Dict[str, object]] = []
    for region in regions:
        graph_path = data_root / f"USA-road-d.{region}.gr.gz"
        coord_path = data_root / f"USA-road-d.{region}.co.gz"
        coordinates = read_coordinates(coord_path, args.node_limit)
        graph = read_graph(graph_path, args.node_limit)
        nodes = sorted(node for node in graph if graph[node] and node in coordinates)
        for source, target in benchmark_pairs(nodes, args.pairs):
            path_result = shortest_path(graph, source, target)
            if path_result is None:
                continue
            network_distance, path = path_result
            metrics = route_shape_metrics(path, coordinates, network_distance)
            rows.append({"region": region, "source": source, "target": target, **metrics})
    final_verdict, reasons = verdict(rows)
    result = {
        "schemaVersion": "route-beauty-community/v1",
        "benchmarkFamily": "dimacs-road",
        "regions": regions,
        "regionCount": len(regions),
        "dataSource": "DIMACS 9th Implementation Challenge USA-road-d",
        "nodeLimit": args.node_limit,
        "requestedPairs": args.pairs,
        "evaluatedPairs": len(rows),
        "finalVerdict": final_verdict,
        "verdictReasons": reasons,
        "avgStraightnessScore": sum(float(row["straightnessScore"]) for row in rows) / len(rows) if rows else 0.0,
        "avgNetworkDetourRatio": sum(float(row["networkDetourRatio"]) for row in rows) / len(rows) if rows else 0.0,
        "avgTurnCount": sum(int(row["turnCount"]) for row in rows) / len(rows) if rows else 0.0,
        "routes": rows,
    }
    output_root = Path(args.output_root)
    write_json(output_root / "route_beauty_results.json", result)
    (output_root / "route_beauty_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[ROUTE BEAUTY JSON] {output_root / 'route_beauty_results.json'}")
    print(f"[ROUTE BEAUTY REPORT] {output_root / 'route_beauty_report.md'}")
    return 1 if final_verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
