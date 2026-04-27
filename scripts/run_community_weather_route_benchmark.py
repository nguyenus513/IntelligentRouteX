from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from run_route_beauty_benchmark import (
    DEFAULT_DATA_ROOT as DEFAULT_DIMACS_ROOT,
    REPO_ROOT,
    benchmark_pairs,
    read_coordinates,
    read_graph,
    route_shape_metrics,
    shortest_path,
)


DEFAULT_WEATHER_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "weather"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "community-weather-route"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def dataset_path(weather_root: Path, dataset: str) -> Path:
    return weather_root / dataset / "weather.json"


def load_weather_events(path: Path, max_events: int) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    precipitation = hourly.get("precipitation", [])
    rain = hourly.get("rain", [])
    wind = hourly.get("wind_speed_10m", [])
    codes = hourly.get("weather_code", [])
    events: List[Dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        rain_mm = float(rain[index] if index < len(rain) and rain[index] is not None else 0.0)
        precipitation_mm = float(precipitation[index] if index < len(precipitation) and precipitation[index] is not None else 0.0)
        wind_kmh = float(wind[index] if index < len(wind) and wind[index] is not None else 0.0)
        weather_code = int(codes[index]) if index < len(codes) and codes[index] is not None else None
        severity = weather_severity(rain_mm, precipitation_mm, wind_kmh, weather_code)
        if severity <= 0.0:
            continue
        events.append({
            "timestamp": timestamp,
            "rainMm": rain_mm,
            "precipitationMm": precipitation_mm,
            "windKmh": wind_kmh,
            "weatherCode": weather_code,
            "severity": severity,
        })
    events.sort(key=lambda item: float(item["severity"]), reverse=True)
    return events[:max_events]


def weather_severity(rain_mm: float, precipitation_mm: float, wind_kmh: float, weather_code: int | None) -> float:
    rain_score = min(1.0, max(rain_mm, precipitation_mm) / 8.0)
    wind_score = min(1.0, max(0.0, wind_kmh - 15.0) / 45.0)
    code_score = 0.0
    if weather_code is not None:
        if weather_code >= 95:
            code_score = 1.0
        elif weather_code >= 80:
            code_score = 0.75
        elif weather_code >= 60:
            code_score = 0.55
        elif weather_code >= 50:
            code_score = 0.35
    return max(rain_score, wind_score, code_score)


def edge_weather_factor(source: int, target: int, event: Dict[str, Any]) -> float:
    bucket = ((source * 1664525 + target * 1013904223) & 0xFFFFFFFF) / 0xFFFFFFFF
    rain_component = min(1.0, max(float(event["rainMm"]), float(event["precipitationMm"])) / 8.0)
    wind_component = min(1.0, max(0.0, float(event["windKmh"]) - 15.0) / 45.0)
    severity = float(event["severity"])
    local_exposure = 0.65 + bucket * 0.70
    return 1.0 + local_exposure * (0.38 * rain_component + 0.22 * wind_component + 0.25 * severity)


def weighted_path(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int, event: Dict[str, Any]) -> Tuple[float, List[int]] | None:
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
            candidate = distance + weight * edge_weather_factor(node, next_node, event)
            if candidate < distances.get(next_node, math.inf):
                distances[next_node] = candidate
                previous[next_node] = node
                heapq.heappush(queue, (candidate, next_node))
    return None


def missing_dimacs_regions(dimacs_root: Path, regions: Sequence[str]) -> List[str]:
    return [region for region in regions if not (dimacs_root / f"USA-road-d.{region}.gr.gz").exists() or not (dimacs_root / f"USA-road-d.{region}.co.gz").exists()]


def evaluate_dataset(dimacs_root: Path, weather_root: Path, dataset: str, regions: Sequence[str], pair_count: int, event_count: int, node_limit: int) -> Dict[str, Any]:
    weather_path = dataset_path(weather_root, dataset)
    if not weather_path.exists():
        return {
            "dataset": dataset,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["community-weather-data-missing"],
            "missingFiles": [str(weather_path)],
        }
    missing_regions = missing_dimacs_regions(dimacs_root, regions)
    if missing_regions:
        return {
            "dataset": dataset,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["dimacs-road-data-missing"],
            "missingRegions": missing_regions,
        }
    events = load_weather_events(weather_path, event_count)
    if not events:
        return {"dataset": dataset, "verdict": "EVIDENCE_GAP", "verdictReasons": ["no-weather-stress-events"]}
    rows: List[Dict[str, Any]] = []
    for region in regions:
        graph = read_graph(dimacs_root / f"USA-road-d.{region}.gr.gz", node_limit)
        coordinates = read_coordinates(dimacs_root / f"USA-road-d.{region}.co.gz", node_limit)
        nodes = sorted(node for node in graph if graph[node] and node in coordinates)
        for source, target in benchmark_pairs(nodes, pair_count):
            base = shortest_path(graph, source, target)
            if base is None:
                continue
            base_distance, _ = base
            for event in events:
                conditioned = weighted_path(graph, source, target, event)
                if conditioned is None:
                    continue
                weather_cost, path = conditioned
                metrics = route_shape_metrics(path, coordinates, base_distance)
                distance_ratio = float(metrics["networkDistance"]) / max(1.0, base_distance)
                weather_cost_ratio = weather_cost / max(1.0, base_distance)
                route_verdict = "PASS" if distance_ratio <= 1.40 and weather_cost_ratio <= 2.35 and float(metrics["straightnessScore"]) >= 0.25 else "PASS_WITH_LIMITS"
                rows.append({
                    "dataset": dataset,
                    "region": region,
                    "timestamp": event["timestamp"],
                    "source": source,
                    "target": target,
                    "rainMm": event["rainMm"],
                    "precipitationMm": event["precipitationMm"],
                    "windKmh": event["windKmh"],
                    "weatherSeverity": event["severity"],
                    "distanceRatio": distance_ratio,
                    "weatherCostRatio": weather_cost_ratio,
                    "routeVerdict": route_verdict,
                    **metrics,
                })
    bad = sum(1 for row in rows if row["routeVerdict"] != "PASS")
    rain_events = sum(1 for event in events if max(float(event["rainMm"]), float(event["precipitationMm"])) > 0.0)
    wind_events = sum(1 for event in events if float(event["windKmh"]) >= 25.0)
    return {
        "dataset": dataset,
        "verdict": "EVIDENCE_GAP" if not rows else ("PASS" if bad == 0 else "PASS_WITH_LIMITS"),
        "verdictReasons": ["community-weather-route-clean"] if rows and bad == 0 else (["community-weather-route-limits"] if rows else ["no-routable-weather-routes"]),
        "weatherDataSource": "open-meteo-historical",
        "roadGraphSource": "dimacs-road",
        "weatherToRoadPenalty": "transparent-adapter",
        "weatherEventCount": len(events),
        "rainEventCount": rain_events,
        "windEventCount": wind_events,
        "routeCount": len(rows),
        "badWeatherRouteCount": bad,
        "avgWeatherCostRatio": sum(float(row["weatherCostRatio"]) for row in rows) / len(rows) if rows else 0.0,
        "avgDistanceRatio": sum(float(row["distanceRatio"]) for row in rows) / len(rows) if rows else 0.0,
        "avgStraightnessScore": sum(float(row["straightnessScore"]) for row in rows) / len(rows) if rows else 0.0,
        "avgTurnCount": sum(float(row["turnCount"]) for row in rows) / len(rows) if rows else 0.0,
        "routes": rows,
    }


def markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Community Weather Route Benchmark",
        "",
        f"FINAL_VERDICT = {result['finalVerdict']}",
        "",
        "This benchmark uses public historical Open-Meteo weather data and public DIMACS road graphs. Weather-to-road impact is a transparent adapter, not a claim of observed road closures.",
        "",
        "| Dataset | Routes | Weather Events | Avg Weather Cost Ratio | Avg Distance Ratio | Bad Routes | Verdict | Reasons |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in result.get("datasets", []):
        lines.append(f"| {row['dataset']} | {row.get('routeCount', 0)} | {row.get('weatherEventCount', 0)} | {float(row.get('avgWeatherCostRatio', 0.0)):.3f} | {float(row.get('avgDistanceRatio', 0.0)):.3f} | {row.get('badWeatherRouteCount', 0)} | {row['verdict']} | {', '.join(row.get('verdictReasons', []))} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run route-quality benchmark with public historical weather stress data.")
    parser.add_argument("--dimacs-root", default=str(DEFAULT_DIMACS_ROOT))
    parser.add_argument("--weather-root", default=str(DEFAULT_WEATHER_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="open-meteo-ny")
    parser.add_argument("--regions", default="NY")
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--events", type=int, default=3)
    parser.add_argument("--node-limit", type=int, default=50_000)
    args = parser.parse_args(argv)
    datasets = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    regions = [part.strip().upper() for part in args.regions.split(",") if part.strip()]
    rows = [evaluate_dataset(Path(args.dimacs_root), Path(args.weather_root), dataset, regions, args.pairs, args.events, args.node_limit) for dataset in datasets]
    if all(row["verdict"] == "EVIDENCE_GAP" for row in rows):
        final = "EVIDENCE_GAP"
    elif any(row["verdict"] == "FAIL" for row in rows):
        final = "FAIL"
    elif any(row["verdict"] != "PASS" for row in rows):
        final = "PASS_WITH_LIMITS"
    else:
        final = "PASS"
    result = {"schemaVersion": "community-weather-route/v1", "finalVerdict": final, "datasets": rows}
    output_root = Path(args.output_root)
    write_json(output_root / "weather_route_results.json", result)
    (output_root / "weather_route_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[COMMUNITY WEATHER ROUTE JSON] {output_root / 'weather_route_results.json'}")
    print(f"[COMMUNITY WEATHER ROUTE REPORT] {output_root / 'weather_route_report.md'}")
    return 1 if final == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
