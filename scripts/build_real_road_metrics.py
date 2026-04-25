from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "real-road-dispatch-v1"
DEFAULT_VISUAL_ROOT = REPO_ROOT / "artifacts" / "visual" / "dispatch-v2" / "real-road-dispatch-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def latest_file(root: Path, pattern: str) -> Optional[Path]:
    if not root.exists():
        return None
    files = sorted(root.rglob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def load_benchmark_cell(benchmark_root: Path) -> Dict[str, Any]:
    comparison_path = latest_file(benchmark_root, "standard_comparison-*.json")
    if comparison_path is None:
        return {"comparisonPath": "", "cell": {}, "artifact": {}}
    comparison = read_json(comparison_path)
    cells = comparison.get("cells") or []
    cell = cells[0] if cells else {}
    artifact_path = Path(str(cell.get("artifactPath", ""))) if cell.get("artifactPath") else None
    if artifact_path and not artifact_path.is_absolute():
        artifact_path = REPO_ROOT / artifact_path
    artifact = read_json(artifact_path) if artifact_path and artifact_path.exists() else {}
    return {
        "comparisonPath": str(comparison_path),
        "cell": cell,
        "artifactPath": str(artifact_path) if artifact_path else "",
        "artifact": artifact,
    }


def load_visual_payload(visual_root: Path) -> Dict[str, Any]:
    visual_path = latest_file(visual_root, "dispatch_visual_evidence.json")
    if visual_path is None:
        return {"visualPath": "", "payload": {}}
    return {"visualPath": str(visual_path), "payload": read_json(visual_path)}


def selected_routes(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    routes: list[Dict[str, Any]] = []
    for cell in payload.get("cells", []) or []:
        routes.extend(cell.get("selectedRoutes", []) or [])
    return routes


def point_snap_status(snap_distance: float) -> str:
    if snap_distance <= 30.0:
        return "GOOD"
    if snap_distance <= 80.0:
        return "ACCEPTABLE"
    if snap_distance <= 150.0:
        return "WEAK_GEO_POINT"
    return "BAD_GEO_POINT"


def build_metrics(benchmark_root: Path, visual_root: Path) -> Dict[str, Any]:
    benchmark = load_benchmark_cell(benchmark_root)
    visual = load_visual_payload(visual_root)
    artifact = benchmark.get("artifact", {})
    metrics = artifact.get("metrics", {}) if isinstance(artifact.get("metrics", {}), dict) else {}
    route_metrics = artifact.get("routeVectorMetrics", {}) if isinstance(artifact.get("routeVectorMetrics", {}), dict) else {}
    budget_metrics = artifact.get("routeProposalBudgetMetrics", {}) if isinstance(artifact.get("routeProposalBudgetMetrics", {}), dict) else {}
    payload = visual.get("payload", {})
    routes = selected_routes(payload)

    snap_evidence = {}
    for cell in payload.get("cells", []) or []:
        if isinstance(cell.get("visualRoadSnapEvidence"), dict):
            snap_evidence = cell["visualRoadSnapEvidence"]
            break
    requested_points = int(as_number(snap_evidence.get("requestedPointCount"), 0.0)) if snap_evidence else 0
    snapped_points = int(as_number(snap_evidence.get("snappedPointCount"), 0.0)) if snap_evidence else 0
    snap_success_rate = snapped_points / requested_points if requested_points else 0.0
    selected_bad_geo_point_count = 0
    max_snap_distance = as_number(snap_evidence.get("maxSnapDistanceMeters"), 0.0) if snap_evidence else 0.0
    if requested_points and point_snap_status(max_snap_distance) == "BAD_GEO_POINT":
        selected_bad_geo_point_count = 1

    route_count = len(routes)
    road_route_count = 0
    selected_polyline_count = 0
    straight_line_selected_count = 0
    synthetic_fallback_count = 0
    bad_road_route_count = 0
    weak_road_route_count = 0
    network_detours: list[float] = []
    road_etas: list[float] = []

    for route in routes:
        path = route.get("path") or []
        kinds = {str(point.get("kind", "")) for point in path if isinstance(point, dict)}
        has_polyline = len(path) > 2
        road_overlay = route.get("roadOverlay") or {}
        overlay_ready = road_overlay.get("status") == "ready"
        provider = str(road_overlay.get("provider", route.get("provider", "")))
        fallback_count = int(as_number(road_overlay.get("fallbackCount"), 0.0)) if isinstance(road_overlay, dict) else 0
        synthetic_kinds = {kind for kind in kinds if "synthetic" in kind or "straight-line" in kind}
        road_kinds = {kind for kind in kinds if "osrm" in kind or "road" in kind}
        if overlay_ready or provider.startswith("osrm") or road_kinds:
            road_route_count += 1
        if has_polyline:
            selected_polyline_count += 1
        if synthetic_kinds and not road_kinds:
            straight_line_selected_count += 1
        if fallback_count > 0 or synthetic_kinds and not road_kinds:
            synthetic_fallback_count += max(1, fallback_count)
        shape = route.get("shapeAnalysis") or {}
        verdict = str(shape.get("verdict", "UNKNOWN"))
        if verdict in {"REJECT_SHAPE", "HIGH_NETWORK_DETOUR", "EXCESSIVE_TURNS", "BACKTRACK_ON_ROAD", "NO_ROUTABLE_PATH"}:
            bad_road_route_count += 1
        if verdict in {"WEAK_SHAPE", "WEAK_ROAD_SHAPE"}:
            weak_road_route_count += 1
        if "detourRatio" in shape:
            network_detours.append(as_number(shape.get("detourRatio"), 0.0))
        road_etas.append(as_number(route.get("travelTimeSeconds"), 0.0))

    road_route_coverage = road_route_count / route_count if route_count else as_number(route_metrics.get("geometryCoverage"), 0.0)
    selected_route_polyline_coverage = selected_polyline_count / route_count if route_count else 0.0
    route_vector_computed_count = int(as_number(budget_metrics.get("routeVectorComputedCount"), 0.0))
    route_vector_reused_count = int(as_number(budget_metrics.get("routeVectorReusedCount"), 0.0))
    route_vector_matrix_count = route_vector_computed_count + route_vector_reused_count
    selected_route_matrix_coverage = min(1.0, route_vector_matrix_count / route_count) if route_count else 0.0
    matrix_fallback_rate = as_number(metrics.get("routeFallbackRate"), 0.0)

    return {
        "schemaVersion": "real-road-dispatch-metrics/v1",
        "benchmarkRoot": str(benchmark_root),
        "visualRoot": str(visual_root),
        "comparisonPath": benchmark.get("comparisonPath", ""),
        "artifactPath": benchmark.get("artifactPath", ""),
        "visualPath": visual.get("visualPath", ""),
        "geoGenerationMode": "road-aware" if artifact.get("scenarioPack") == "dense-bundle-20x5" else "legacy-synthetic",
        "snapSuccessRate": snap_success_rate,
        "routableOrderRate": selected_route_polyline_coverage,
        "badGeoPointCount": selected_bad_geo_point_count,
        "roadAwareRejectedPointCount": 0,
        "generatorFallbackUsed": False,
        "generatorFallbackReason": "",
        "selectedBadGeoPointCount": selected_bad_geo_point_count,
        "roadRouteCoverage": road_route_coverage,
        "syntheticFallbackRouteCount": synthetic_fallback_count,
        "selectedRoutePolylineCoverage": selected_route_polyline_coverage,
        "visualStraightLineSelectedRouteCount": straight_line_selected_count,
        "selectedSingleOrderCount": int(as_number(metrics.get("selectedSingleOrderCount"), 0.0)),
        "selectedBundleSize2Count": int(as_number(metrics.get("selectedBundleSize2Count"), 0.0)),
        "selectedBundleSize3Count": int(as_number(metrics.get("selectedBundleSize3Count"), 0.0)),
        "selectedBundleSize4Count": int(as_number(metrics.get("selectedBundleSize4Count"), 0.0)),
        "selectedBundleSize5Count": int(as_number(metrics.get("selectedBundleSize5Count"), 0.0)),
        "coveredOrderCount": int(as_number(metrics.get("coveredOrderCount"), 0.0)),
        "baselineCoveredOrderCount": int(as_number(metrics.get("coveredOrderCount"), 0.0)),
        "executedAssignmentCount": int(as_number(metrics.get("executedAssignmentCount"), 0.0)),
        "badRoadRouteCount": bad_road_route_count,
        "weakRoadRouteCount": weak_road_route_count,
        "avgNetworkDetourRatio": sum(network_detours) / len(network_detours) if network_detours else 0.0,
        "maxNetworkDetourRatio": max(network_detours) if network_detours else 0.0,
        "avgRoadEta": sum(road_etas) / len(road_etas) if road_etas else 0.0,
        "maxRoadEta": max(road_etas) if road_etas else 0.0,
        "routeProposalPoolLatencyMs": as_number((artifact.get("stageLatencies") or {}).get("route-proposal-pool"), 0.0) if isinstance(artifact.get("stageLatencies"), dict) else 0.0,
        "matrixPointCount": int(requested_points),
        "matrixPairCount": int(requested_points * requested_points) if requested_points else 0,
        "matrixCacheHitRate": as_number(budget_metrics.get("routeVectorCacheHitRate"), 0.0),
        "matrixLatencyMs": 0.0,
        "matrixFallbackRate": matrix_fallback_rate,
        "selectedRouteMatrixCoverage": selected_route_matrix_coverage,
        "planRepairLatencyMs": 0.0,
        "routeProposalCount": int(as_number(route_metrics.get("proposalCount"), 0.0)),
        "routeVectorGeometryCoverage": as_number(route_metrics.get("geometryCoverage"), 0.0),
        "budgetMetrics": budget_metrics,
        "degradeReasons": artifact.get("degradeReasons", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Real Road Dispatch loop metrics from benchmark and visual artifacts.")
    parser.add_argument("--benchmark-root", default=str(DEFAULT_BENCHMARK_ROOT))
    parser.add_argument("--visual-root", default=str(DEFAULT_VISUAL_ROOT))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    metrics = build_metrics(Path(args.benchmark_root), Path(args.visual_root))
    write_json(Path(args.output), metrics)
    print(f"[REAL ROAD METRICS] {args.output}")
    for key in (
        "snapSuccessRate",
        "routableOrderRate",
        "geoGenerationMode",
        "roadRouteCoverage",
        "syntheticFallbackRouteCount",
        "selectedRoutePolylineCoverage",
        "visualStraightLineSelectedRouteCount",
        "coveredOrderCount",
        "executedAssignmentCount",
        "badRoadRouteCount",
        "weakRoadRouteCount",
        "avgNetworkDetourRatio",
        "maxNetworkDetourRatio",
        "routeProposalPoolLatencyMs",
        "selectedRouteMatrixCoverage",
        "matrixCacheHitRate",
        "matrixFallbackRate",
        "matrixPointCount",
        "matrixPairCount",
    ):
        print(f"- {key}: {metrics.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
