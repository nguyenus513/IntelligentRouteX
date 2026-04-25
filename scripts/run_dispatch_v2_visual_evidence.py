from __future__ import annotations

import argparse
import html
import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "proposal-reduction-label-fix-v2"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "visual" / "dispatch-v2"
DEFAULT_TILE_PROBE_ROOT = REPO_ROOT / "artifacts" / "validation" / "geo-tiles"
AVAILABLE_TILE_STATUSES = {"FETCHED", "CACHE_HIT"}


@dataclass(frozen=True)
class VisualCell:
    scenario: str
    size: str
    profile: str
    artifact_path: Path
    output_root: Path
    benchmark_row: dict

    @property
    def label(self) -> str:
        return f"{self.scenario}/{self.size}/{self.profile}"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def latest_standard_comparison(root: Path) -> Path:
    candidates = sorted(root.glob("standard_comparison-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No standard_comparison-*.json found under {root}")
    return candidates[0]


def latest_tile_probe(root: Path) -> Optional[Path]:
    if root.is_file():
        return root
    direct = root / "geo_tile_probe.json"
    if direct.exists():
        return direct
    candidates = sorted(root.rglob("geo_tile_probe.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def split_csv(value: str) -> Tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def select_cells(payload: dict, scenarios: Sequence[str], profiles: Sequence[str], size: str, single_turn: bool = False) -> List[VisualCell]:
    scenario_filter = set(scenarios)
    profile_filter = set(profiles)
    cells: List[VisualCell] = []
    for row in payload.get("cells", []):
        if not isinstance(row, dict):
            continue
        scenario = str(row.get("scenarioPack", ""))
        profile = str(row.get("profile", ""))
        row_size = str(row.get("size", ""))
        if scenario_filter and scenario not in scenario_filter:
            continue
        if profile_filter and profile not in profile_filter:
            continue
        if size and row_size.upper() != size.upper():
            continue
        artifact_value = row.get("artifactPath")
        output_value = row.get("outputRoot")
        if not artifact_value or not output_value:
            continue
        artifact_path = resolve_repo_path(str(artifact_value))
        output_root = resolve_repo_path(str(output_value))
        cells.append(VisualCell(scenario, row_size, profile, artifact_path, output_root, row))
        if single_turn:
            break
    return cells


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def safe_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def redact_url_template(value: object) -> str:
    text = str(value or "")
    if "key=" not in text:
        return text
    prefix, _, _suffix = text.partition("key=")
    return prefix + "key=<redacted>"


def tile_cache_path(value: object) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else REPO_ROOT / path


def load_tile_evidence(tile_probe_root: Optional[Path]) -> dict:
    root = tile_probe_root if tile_probe_root is not None else DEFAULT_TILE_PROBE_ROOT
    probe_path = latest_tile_probe(root)
    if probe_path is None:
        return {
            "status": "missing",
            "sourceArtifact": "",
            "missingReason": "geo-tile-probe-missing",
            "tiles": [],
        }
    probe = read_json(probe_path)
    tiles = []
    available_count = 0
    for row in probe.get("tiles", []):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "missing"))
        available = status in AVAILABLE_TILE_STATUSES and bool(row.get("byteCount", 0))
        if available:
            available_count += 1
        tiles.append({
            "provider": row.get("provider"),
            "tile": row.get("tile", probe.get("tile")),
            "status": status,
            "httpStatus": row.get("httpStatus"),
            "byteCount": row.get("byteCount", 0),
            "cacheHit": bool(row.get("cacheHit", False)),
            "latencyMs": row.get("latencyMs", 0),
            "degradeReason": row.get("degradeReason", ""),
            "cachePath": row.get("cachePath", ""),
            "urlTemplate": redact_url_template(row.get("urlTemplate", "")),
            "attribution": row.get("attribution", ""),
            "imageAvailable": False,
            "visualPath": "",
        })
    if available_count == 0:
        status = "unavailable"
    elif available_count < len(tiles):
        status = "partial"
    else:
        status = "available"
    return {
        "status": status,
        "sourceArtifact": safe_display_path(probe_path),
        "generatedAt": probe.get("generatedAt"),
        "center": probe.get("center"),
        "zoom": probe.get("zoom"),
        "tile": probe.get("tile"),
        "providers": probe.get("providers", []),
        "tiles": tiles,
    }


def copy_tile_images(tile_evidence: dict, output_root: Path) -> None:
    if tile_evidence.get("status") == "missing":
        return
    tile_root = output_root / "tiles"
    for row in tile_evidence.get("tiles", []):
        source = tile_cache_path(row.get("cachePath"))
        if row.get("status") not in AVAILABLE_TILE_STATUSES or not source.exists():
            row["imageAvailable"] = False
            row["visualPath"] = ""
            continue
        provider = str(row.get("provider") or "unknown")
        tile = row.get("tile") if isinstance(row.get("tile"), dict) else tile_evidence.get("tile", {})
        z = str(tile.get("z", "z"))
        x = str(tile.get("x", "x"))
        y = str(tile.get("y", source.stem))
        target = tile_root / provider / z / x / f"{y}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        row["imageAvailable"] = True
        row["visualPath"] = target.relative_to(output_root).as_posix()


def first_file(root: Path, pattern: str) -> Optional[Path]:
    matches = sorted(root.rglob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def replay_path(cell: VisualCell) -> Path:
    path = first_file(cell.output_root / "feedback", "replay/*.json")
    if path is None:
        raise FileNotFoundError(f"No replay JSON found under {cell.output_root / 'feedback'}")
    return path


def reuse_state_path(cell: VisualCell) -> Path:
    path = first_file(cell.output_root / "feedback", "reuse-states/*reuse-state*.json")
    if path is None:
        raise FileNotFoundError(f"No reuse-state JSON found under {cell.output_root / 'feedback'}")
    return path


def geo(point: dict) -> Tuple[float, float]:
    return float(point.get("latitude", 0.0)), float(point.get("longitude", 0.0))


def route_stop_point(stop_id: str, orders: Dict[str, dict]) -> Optional[Tuple[float, float]]:
    order_id, _, stop_kind = stop_id.partition(":")
    order = orders.get(order_id)
    if not order:
        return None
    if stop_kind == "dropoff":
        return geo(order.get("dropoffPoint", {}))
    return geo(order.get("pickupPoint", {}))


def proposal_path_points(proposal: dict, orders: Dict[str, dict], drivers: Dict[str, dict]) -> List[dict]:
    driver = drivers.get(str(proposal.get("driverId", "")))
    points: List[dict] = []
    if driver:
        lat, lon = geo(driver.get("currentLocation", {}))
        points.append({"id": proposal.get("driverId"), "kind": "driver", "lat": lat, "lon": lon})
    for order_id in proposal.get("stopOrder", []) or []:
        order = orders.get(str(order_id))
        if not order:
            continue
        pickup_lat, pickup_lon = geo(order.get("pickupPoint", {}))
        drop_lat, drop_lon = geo(order.get("dropoffPoint", {}))
        points.append({"id": f"{order_id}:pickup", "kind": "pickup", "lat": pickup_lat, "lon": pickup_lon})
        points.append({"id": f"{order_id}:dropoff", "kind": "dropoff", "lat": drop_lat, "lon": drop_lon})
    if proposal.get("legs"):
        leg_points: List[dict] = []
        if driver:
            lat, lon = geo(driver.get("currentLocation", {}))
            leg_points.append({"id": proposal.get("driverId"), "kind": "driver", "lat": lat, "lon": lon})
        for leg in proposal.get("legs", []) or []:
            for field in ("fromStopId", "toStopId"):
                point = route_stop_point(str(leg.get(field, "")), orders)
                if point:
                    leg_points.append({"id": leg.get(field), "kind": "stop", "lat": point[0], "lon": point[1]})
        if len(leg_points) > 1:
            return dedupe_adjacent_points(leg_points)
    return dedupe_adjacent_points(points)


def dedupe_adjacent_points(points: List[dict]) -> List[dict]:
    deduped: List[dict] = []
    for point in points:
        if deduped and deduped[-1].get("id") == point.get("id"):
            continue
        deduped.append(point)
    return deduped


def selected_proposals(reuse_state: dict, selected_ids: Iterable[str]) -> List[dict]:
    by_id = {str(proposal.get("proposalId")): proposal for proposal in reuse_state.get("routeProposals", []) if isinstance(proposal, dict)}
    selected: List[dict] = []
    for proposal_id in selected_ids:
        proposal = by_id.get(str(proposal_id))
        if proposal:
            selected.append(proposal)
    return selected


def build_visual_cell(cell: VisualCell) -> dict:
    replay = read_json(replay_path(cell))
    reuse_state = read_json(reuse_state_path(cell))
    benchmark = read_json(cell.artifact_path)
    request = replay.get("request", {})
    orders = {str(order.get("orderId")): order for order in request.get("openOrders", []) if isinstance(order, dict)}
    drivers = {str(driver.get("driverId")): driver for driver in request.get("availableDrivers", []) if isinstance(driver, dict)}
    decision_log = first_file(cell.output_root / "feedback", "decision-log/*.json")
    selected_ids = []
    executed_ids = []
    if decision_log:
        decision = read_json(decision_log)
        selected_ids = [str(value) for value in decision.get("selectedProposalIds", [])]
        executed_ids = [str(value) for value in decision.get("executedAssignmentIds", [])]
    selected = selected_proposals(reuse_state, selected_ids)
    selected_routes = []
    for rank, proposal in enumerate(selected, start=1):
        order_ids = [str(order_id) for order_id in proposal.get("stopOrder", [])]
        selected_routes.append({
            "rank": rank,
            "proposalId": proposal.get("proposalId"),
            "bundleId": proposal.get("bundleId"),
            "driverId": proposal.get("driverId"),
            "source": proposal.get("source"),
            "orderIds": order_ids,
            "path": proposal_path_points(proposal, orders, drivers),
            "routeValue": proposal.get("routeValue"),
            "pickupEtaMinutes": proposal.get("projectedPickupEtaMinutes"),
            "completionEtaMinutes": proposal.get("projectedCompletionEtaMinutes"),
            "distanceMeters": proposal.get("totalDistanceMeters"),
            "travelTimeSeconds": proposal.get("totalTravelTimeSeconds"),
            "routeCost": proposal.get("routeCost"),
            "congestionScore": proposal.get("congestionScore"),
            "turnCount": proposal.get("turnCount"),
            "reasons": proposal.get("reasons", []),
            "degradeReasons": proposal.get("degradeReasons", []),
        })
    stage_latencies = benchmark.get("stageLatencies") or cell.benchmark_row.get("stageLatencies", {})
    route_metrics = benchmark.get("routeVectorMetrics", {})
    metrics = benchmark.get("metrics", {})
    budget_metrics = benchmark.get("routeProposalBudgetMetrics") or cell.benchmark_row.get("routeProposalBudgetMetrics", {})
    selected_driver_count = len({route.get("driverId") for route in selected_routes if route.get("driverId")})
    return {
        "cell": cell.label,
        "scenario": cell.scenario,
        "size": cell.size,
        "profile": cell.profile,
        "traceId": request.get("traceId"),
        "weatherProfile": request.get("weatherProfile"),
        "decisionTime": request.get("decisionTime"),
        "orders": list(orders.values()),
        "drivers": list(drivers.values()),
        "selectedRoutes": selected_routes,
        "selectedProposalCount": len(selected_routes),
        "selectedDriverCount": selected_driver_count,
        "executedAssignmentCount": metrics.get("executedAssignmentCount", cell.benchmark_row.get("executedAssignmentCount")),
        "selectedSingleOrderCount": metrics.get("selectedSingleOrderCount", cell.benchmark_row.get("selectedSingleOrderCount")),
        "selectedBundleSize2Count": metrics.get("selectedBundleSize2Count", cell.benchmark_row.get("selectedBundleSize2Count")),
        "selectedBundleSize3Count": metrics.get("selectedBundleSize3Count", cell.benchmark_row.get("selectedBundleSize3Count")),
        "selectedBundleSize4Count": metrics.get("selectedBundleSize4Count", cell.benchmark_row.get("selectedBundleSize4Count")),
        "selectedBundleSize5Count": metrics.get("selectedBundleSize5Count", cell.benchmark_row.get("selectedBundleSize5Count")),
        "coveredOrderCount": metrics.get("coveredOrderCount", cell.benchmark_row.get("coveredOrderCount")),
        "maxSelectedBundleSize": metrics.get("maxSelectedBundleSize", cell.benchmark_row.get("maxSelectedBundleSize")),
        "executedAssignmentIds": executed_ids,
        "routeProposalCount": route_metrics.get("proposalCount", cell.benchmark_row.get("routeProposalCount")),
        "geometryCoverage": route_metrics.get("geometryCoverage", cell.benchmark_row.get("routeGeometryCoverage")),
        "robustUtilityAverage": metrics.get("robustUtilityAverage", cell.benchmark_row.get("robustUtilityAverage")),
        "stageLatencies": stage_latencies,
        "budgetMetrics": budget_metrics,
        "degradeReasons": benchmark.get("degradeReasons", []),
        "artifactPath": safe_display_path(cell.artifact_path),
    }


def all_geo_points(cell: dict) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    for order in cell.get("orders", []):
        points.append(geo(order.get("pickupPoint", {})))
        points.append(geo(order.get("dropoffPoint", {})))
    for driver in cell.get("drivers", []):
        points.append(geo(driver.get("currentLocation", {})))
    return [point for point in points if point != (0.0, 0.0)]


def bounds(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    min_lat = min(point[0] for point in points)
    max_lat = max(point[0] for point in points)
    min_lon = min(point[1] for point in points)
    max_lon = max(point[1] for point in points)
    lat_pad = max((max_lat - min_lat) * 0.08, 0.003)
    lon_pad = max((max_lon - min_lon) * 0.08, 0.003)
    return min_lat - lat_pad, max_lat + lat_pad, min_lon - lon_pad, max_lon + lon_pad


def project(lat: float, lon: float, box: Tuple[float, float, float, float], width: int, height: int) -> Tuple[float, float]:
    min_lat, max_lat, min_lon, max_lon = box
    x = (lon - min_lon) / max(max_lon - min_lon, 0.000001) * width
    y = height - ((lat - min_lat) / max(max_lat - min_lat, 0.000001) * height)
    return x, y


def color(index: int) -> str:
    palette = ["#e85d75", "#2f80ed", "#27ae60", "#f2994a", "#9b51e0", "#00a7a7", "#d35400", "#34495e"]
    return palette[(index - 1) % len(palette)]


def visible_routes(cell: dict, max_routes: int, max_drivers: int) -> List[dict]:
    routes = []
    seen_drivers = set()
    for route in cell.get("selectedRoutes", []):
        driver_id = route.get("driverId")
        if driver_id in seen_drivers:
            continue
        routes.append(route)
        seen_drivers.add(driver_id)
        if len(routes) >= min(max_routes, max_drivers):
            break
    return routes


def visible_order_ids(cell: dict, routes: Sequence[dict], max_orders: int) -> set:
    order_ids = []
    for route in routes:
        for order_id in route.get("orderIds", []):
            if order_id not in order_ids:
                order_ids.append(order_id)
    for order in cell.get("orders", []):
        order_id = str(order.get("orderId"))
        if order_id not in order_ids:
            order_ids.append(order_id)
        if len(order_ids) >= max_orders:
            break
    return set(order_ids[:max_orders])


def route_path_d(projected_points: Sequence[str]) -> str:
    if not projected_points:
        return ""
    first, *rest = projected_points
    return "M " + first + " " + " ".join(f"L {point}" for point in rest)


def background_tile(tile_evidence: dict) -> Optional[dict]:
    preferred = ("osm-raster", "tomtom-raster-basic")
    by_provider = {str(row.get("provider")): row for row in tile_evidence.get("tiles", []) if isinstance(row, dict)}
    for provider in preferred:
        row = by_provider.get(provider)
        if row and row.get("imageAvailable") and row.get("visualPath"):
            return row
    return None


def traffic_tile(tile_evidence: dict) -> Optional[dict]:
    for row in tile_evidence.get("tiles", []):
        if row.get("provider") == "tomtom-traffic-flow" and row.get("imageAvailable") and row.get("visualPath"):
            return row
    return None


def render_svg(cell: dict, max_routes: int, max_orders: int, max_drivers: int, tile_evidence: Optional[dict] = None) -> str:
    width = 980
    height = 620
    routes = visible_routes(cell, max_routes, max_drivers)
    shown_order_ids = visible_order_ids(cell, routes, max_orders)
    shown_driver_ids = {route.get("driverId") for route in routes}
    points = []
    for order in cell.get("orders", []):
        if str(order.get("orderId")) in shown_order_ids:
            points.append(geo(order.get("pickupPoint", {})))
            points.append(geo(order.get("dropoffPoint", {})))
    for driver in cell.get("drivers", []):
        if str(driver.get("driverId")) in shown_driver_ids:
            points.append(geo(driver.get("currentLocation", {})))
    if not points:
        return "<svg viewBox='0 0 980 620' class='map'><text x='40' y='60'>No coordinates available</text></svg>"
    box = bounds(points)
    selected_order_ids = {order_id for route in routes for order_id in route.get("orderIds", [])}
    selected_driver_ids = {route.get("driverId") for route in routes}
    tile_evidence = tile_evidence or {}
    base_tile = background_tile(tile_evidence)
    flow_tile = traffic_tile(tile_evidence)
    parts = [
        f"<svg viewBox='0 0 {width} {height}' class='map' role='img' aria-label='Dispatch visual map'>",
        "<defs><pattern id='grid' width='42' height='42' patternUnits='userSpaceOnUse'><path d='M 42 0 L 0 0 0 42' fill='none' stroke='#d9e7e0' stroke-width='1'/></pattern><marker id='arrow' markerWidth='10' markerHeight='10' refX='8' refY='3' orient='auto'><path d='M0,0 L0,6 L9,3 z' fill='#17201b'/></marker></defs>",
    ]
    if base_tile:
        parts.append(f"<image href='{html.escape(str(base_tile.get('visualPath')))}' x='0' y='0' width='{width}' height='{height}' preserveAspectRatio='xMidYMid slice' opacity='0.48'/>")
        parts.append(f"<rect x='0' y='0' width='{width}' height='{height}' fill='rgba(251,247,239,0.42)' rx='28'/>")
    else:
        parts.append(f"<rect x='0' y='0' width='{width}' height='{height}' fill='url(#grid)' rx='28'/>")
    if flow_tile:
        parts.append(f"<image href='{html.escape(str(flow_tile.get('visualPath')))}' x='0' y='0' width='{width}' height='{height}' preserveAspectRatio='xMidYMid slice' opacity='0.30'/>")
    for order in cell.get("orders", []):
        order_id = str(order.get("orderId"))
        if order_id not in shown_order_ids:
            continue
        px, py = project(*geo(order.get("pickupPoint", {})), box, width, height)
        dx, dy = project(*geo(order.get("dropoffPoint", {})), box, width, height)
        active = order_id in selected_order_ids
        opacity = "0.92" if active else "0.18"
        active_class = " selected-order" if active else ""
        status_class = " order-pending"
        parts.append(f"<line x1='{px:.1f}' y1='{py:.1f}' x2='{dx:.1f}' y2='{dy:.1f}' class='order-link playback-order{active_class}' style='opacity:{opacity}'/>")
        parts.append(f"<circle cx='{px:.1f}' cy='{py:.1f}' r='{7 if active else 4}' class='pickup playback-order{active_class}{status_class}' style='opacity:{opacity}'><title>{html.escape(order_id)} pickup</title></circle>")
        parts.append(f"<rect x='{dx - 5:.1f}' y='{dy - 5:.1f}' width='{10 if active else 7}' height='{10 if active else 7}' class='dropoff playback-order{active_class}{status_class}' style='opacity:{opacity}'><title>{html.escape(order_id)} dropoff</title></rect>")
        parts.append(f"<text x='{px + 8:.1f}' y='{py - 8:.1f}' class='point-label playback-order'>{html.escape(order_id)} P</text>")
        parts.append(f"<text x='{dx + 8:.1f}' y='{dy + 14:.1f}' class='point-label playback-order'>{html.escape(order_id)} D</text>")
    for driver in cell.get("drivers", []):
        driver_id = str(driver.get("driverId"))
        if driver_id not in shown_driver_ids:
            continue
        x, y = project(*geo(driver.get("currentLocation", {})), box, width, height)
        active = driver_id in selected_driver_ids
        active_class = " selected-driver" if active else ""
        parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='62' class='driver-radius playback-driver{active_class}'/>")
        triangle = f"{x:.1f},{y - 12:.1f} {x - 11:.1f},{y + 10:.1f} {x + 11:.1f},{y + 10:.1f}"
        parts.append(f"<polygon points='{triangle}' class='driver-triangle playback-driver{active_class}'><title>{html.escape(driver_id)}</title></polygon>")
        if active:
            parts.append(f"<text x='{x + 14:.1f}' y='{y - 15:.1f}' class='driver-label'>{html.escape(driver_id)}</text>")
    for route_index, route in enumerate(routes, start=1):
        route_color = color(int(route.get("rank", 1)))
        path_points = []
        for point in route.get("path", []):
            x, y = project(float(point.get("lat", 0.0)), float(point.get("lon", 0.0)), box, width, height)
            path_points.append(f"{x:.1f},{y:.1f}")
        path_d = route_path_d(path_points)
        if len(path_points) > 1:
            parts.append(f"<path id='route-path-{route_index}' d='{path_d}' class='playback-route' fill='none' stroke='{route_color}' stroke-width='4.5' stroke-linecap='round' stroke-linejoin='round' marker-end='url(#arrow)' opacity='0.82'><title>{html.escape(str(route.get('driverId')))} -> {html.escape(', '.join(route.get('orderIds', [])))}</title></path>")
            parts.append(f"<polygon class='moving-driver playback-execute' points='0,-10 -9,8 9,8' fill='{route_color}'><animateMotion dur='7s' repeatCount='indefinite' rotate='auto'><mpath href='#route-path-{route_index}'/></animateMotion></polygon>")
        for sequence, point in enumerate(route.get("path", [])[1:], start=1):
            x, y = project(float(point.get("lat", 0.0)), float(point.get("lon", 0.0)), box, width, height)
            parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='10' fill='{route_color}' class='route-step playback-execute'/><text x='{x:.1f}' y='{y + 4:.1f}' class='route-step-label playback-execute'>{sequence}</text>")
            parts.append(f"<text x='{x + 12:.1f}' y='{y + 3:.1f}' class='point-label route-label playback-execute'>Step {sequence}: {html.escape(str(point.get('id')))}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def fmt_number(value: object, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if math.isfinite(number):
        return f"{number:.{digits}f}"
    return "n/a"


def route_step_text(route: dict) -> str:
    labels = []
    for index, point in enumerate(route.get("path", [])[1:], start=1):
        labels.append(f"{index}. {point.get('id')}")
    return " -> ".join(labels)


def reasoning_text(route: dict) -> str:
    reasons = ", ".join(route.get("reasons", [])) or "highest feasible selected score"
    return (
        f"System chooses {route.get('driverId')} because route value={fmt_number(route.get('routeValue'))}, "
        f"pickup ETA={fmt_number(route.get('pickupEtaMinutes'))} min, completion={fmt_number(route.get('completionEtaMinutes'))} min, "
        f"congestion={fmt_number(route.get('congestionScore'))}, reason={reasons}."
    )


def render_route_cards(cell: dict, max_routes: int, max_drivers: int) -> str:
    cards = []
    for route in visible_routes(cell, max_routes, max_drivers):
        order_text = " -> ".join(route.get("orderIds", []))
        cards.append(
            "<article class='route-card'>"
            f"<div class='route-rank' style='background:{color(int(route.get('rank', 1)))}'>#{route.get('rank')}</div>"
            f"<h3>{html.escape(str(route.get('driverId')))} picks {html.escape(order_text)}</h3>"
            f"<p><b>Route text</b> {html.escape(route_step_text(route))}</p>"
            f"<p><b>Source</b> {html.escape(str(route.get('source')))} · <b>Bundle</b> {html.escape(str(route.get('bundleId')))}</p>"
            f"<p><b>Pickup ETA</b> {fmt_number(route.get('pickupEtaMinutes'))} min · <b>Complete</b> {fmt_number(route.get('completionEtaMinutes'))} min · <b>Distance</b> {fmt_number(route.get('distanceMeters'), 0)} m</p>"
            f"<p><b>Congestion</b> {fmt_number(route.get('congestionScore'))} · <b>Turns</b> {html.escape(str(route.get('turnCount')))} · <b>Value</b> {fmt_number(route.get('routeValue'))}</p>"
            f"<p class='reason'>{html.escape(reasoning_text(route))}</p>"
            "</article>"
        )
    return "\n".join(cards)


def render_tile_evidence(tile_evidence: dict) -> str:
    status = html.escape(str(tile_evidence.get("status", "missing")))
    source = html.escape(str(tile_evidence.get("sourceArtifact", "")) or "n/a")
    center = html.escape(str(tile_evidence.get("center", "n/a")))
    zoom = html.escape(str(tile_evidence.get("zoom", "n/a")))
    rows = []
    for row in tile_evidence.get("tiles", []):
        provider = html.escape(str(row.get("provider", "unknown")))
        row_status = html.escape(str(row.get("status", "missing")))
        bytes_text = html.escape(str(row.get("byteCount", 0)))
        latency = html.escape(str(row.get("latencyMs", 0)))
        reason = html.escape(str(row.get("degradeReason", "")) or "ok")
        visual = html.escape(str(row.get("visualPath", "")) or "not copied")
        rows.append(
            "<tr>"
            f"<td>{provider}</td><td><b>{row_status}</b></td><td>{bytes_text}</td>"
            f"<td>{latency}</td><td>{reason}</td><td>{visual}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='6'>No tile probe artifact found. Visual falls back to abstract grid.</td></tr>")
    return (
        "<section class='tile-evidence'>"
        "<div><p class='eyebrow'>Geo Tile Evidence</p>"
        f"<h2>Tile source status: {status}</h2>"
        f"<p>Source artifact: <code>{source}</code>. Center: <code>{center}</code>. Zoom: <code>{zoom}</code>.</p></div>"
        "<table><thead><tr><th>Provider</th><th>Status</th><th>Bytes</th><th>Latency ms</th><th>Reason</th><th>Visual copy</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )


def render_playback_script() -> str:
    return """
    <script>
    (() => {
      const steps = ['orders', 'bundles', 'routes', 'select', 'execute'];
      let current = 0;
      let timer = null;
      const label = document.querySelector('[data-playback-label]');
      const setStep = (index) => {
        current = Math.max(0, Math.min(index, steps.length - 1));
        document.body.dataset.playbackStep = steps[current];
        document.querySelectorAll('[data-step]').forEach((node, idx) => {
          node.classList.toggle('active', idx === current);
          node.classList.toggle('complete', idx < current);
        });
        if (label) label.textContent = `${current + 1}/${steps.length} ${steps[current]}`;
      };
      const stop = () => { if (timer) window.clearInterval(timer); timer = null; };
      const play = () => {
        stop();
        setStep(0);
        timer = window.setInterval(() => {
          if (current >= steps.length - 1) { stop(); return; }
          setStep(current + 1);
        }, 1150);
      };
      document.querySelector('[data-play]')?.addEventListener('click', play);
      document.querySelector('[data-restart]')?.addEventListener('click', () => { stop(); setStep(0); });
      document.querySelectorAll('[data-step]').forEach((node, idx) => node.addEventListener('click', () => { stop(); setStep(idx); }));
      setStep(0);
      window.setTimeout(play, 500);
    })();
    </script>
    """


def render_html(payload: dict, max_routes: int, max_orders: int = 20, max_drivers: int = 5) -> str:
    cells = payload.get("cells", [])
    first = cells[0] if cells else {}
    tile_evidence = payload.get("tileEvidence", {"status": "missing", "tiles": []})
    cell_tabs = "".join(f"<a href='#{html.escape(cell.get('scenario', 'cell'))}'>{html.escape(cell.get('cell', 'cell'))}</a>" for cell in cells)
    sections = []
    for cell in cells:
        budget = cell.get("budgetMetrics", {})
        latencies = cell.get("stageLatencies", {})
        sections.append(
            f"<section class='cell-section' id='{html.escape(str(cell.get('scenario')))}'>"
            f"<div class='section-head'><div><p class='eyebrow'>{html.escape(str(cell.get('weatherProfile')))} · {html.escape(str(cell.get('profile')))}</p><h2>{html.escape(str(cell.get('cell')))}</h2></div>"
            f"<div class='metric-pill'>Executed <b>{cell.get('executedAssignmentCount')}</b></div></div>"
            "<div class='metrics-grid'>"
            f"<div><span>Shown orders</span><b>{min(max_orders, len(cell.get('orders', [])))}</b></div>"
            f"<div><span>Shown drivers</span><b>{min(max_drivers, cell.get('selectedDriverCount', len(cell.get('drivers', []))))}</b></div>"
            f"<div><span>Selected drivers</span><b>{cell.get('selectedDriverCount', cell.get('selectedProposalCount'))}</b></div>"
            f"<div><span>Covered orders</span><b>{cell.get('coveredOrderCount')}</b></div>"
            f"<div><span>Bundle sizes 1/2/3/4/5</span><b>{cell.get('selectedSingleOrderCount')}/{cell.get('selectedBundleSize2Count')}/{cell.get('selectedBundleSize3Count')}/{cell.get('selectedBundleSize4Count')}/{cell.get('selectedBundleSize5Count')}</b></div>"
            f"<div><span>Max bundle size</span><b>{cell.get('maxSelectedBundleSize')}</b></div>"
            f"<div><span>Route proposals</span><b>{cell.get('routeProposalCount')}</b></div>"
            f"<div><span>Budget mode</span><b>{html.escape(str(budget.get('budgetMode', 'n/a')))}</b></div>"
            f"<div><span>Route pool ms</span><b>{html.escape(str(latencies.get('route-proposal-pool', 'n/a')))}</b></div>"
            f"<div><span>Geometry</span><b>{fmt_number(cell.get('geometryCoverage'))}</b></div>"
            f"<div><span>Utility</span><b>{fmt_number(cell.get('robustUtilityAverage'))}</b></div>"
            "</div>"
            "<div class='playback-controls'><button data-play>Play realtime turn</button><button data-restart>Restart</button><span data-playback-label>1/5 orders</span></div>"
            "<div class='visual-grid'>"
            f"<div>{render_svg(cell, max_routes, max_orders, max_drivers, tile_evidence)}</div>"
            "<aside class='timeline'><h3>Quy trình ghép đơn</h3>"
            f"<div class='step' data-step='orders'><b>1. Order buffer</b><span>Showing {min(max_orders, len(cell.get('orders', [])))} orders. Red means placed/waiting.</span></div>"
            f"<div class='step' data-step='bundles'><b>2. Bundle pool</b><span>Nearby pickups and compatible corridors are grouped into candidate bundles.</span></div>"
            f"<div class='step' data-step='routes'><b>3. Route proposal pool</b><span>System draws candidate routes. Yellow means picking up, green means delivering. {cell.get('routeProposalCount')} proposals remain after prune.</span></div>"
            f"<div class='step' data-step='select'><b>4. Global selector</b><span>Showing {min(max_drivers, cell.get('selectedDriverCount', cell.get('selectedProposalCount')))} selected drivers. Radius circles show local pickup search area.</span></div>"
            f"<div class='step' data-step='execute'><b>5. Execute</b><span>Driver triangles move along selected routes, then orders turn green when delivery is active.</span></div>"
            "</aside></div>"
            "<h3>Selected assignments</h3>"
            f"<div class='route-cards'>{render_route_cards(cell, max_routes, max_drivers)}</div>"
            "</section>"
        )
    css = """
    :root { --ink:#17201b; --muted:#65756c; --paper:#fbf7ef; --panel:#fffaf2; --line:#d8e4dc; --green:#0f8b68; --orange:#f2994a; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, Segoe UI, Tahoma, sans-serif; color:var(--ink); background: radial-gradient(circle at 12% 8%, #dff4e7, transparent 28%), linear-gradient(135deg, #fff7e5, #eef8f1 55%, #e6f0ff); }
    header { padding:44px 48px 28px; }
    h1 { margin:0; font-size:42px; letter-spacing:-1.4px; max-width:980px; }
    h2 { margin:0; font-size:30px; letter-spacing:-0.7px; }
    h3 { margin:0 0 12px; }
    .subtitle { max-width:980px; color:var(--muted); font-size:17px; line-height:1.55; }
    nav { display:flex; gap:10px; flex-wrap:wrap; margin-top:22px; }
    nav a { color:var(--ink); text-decoration:none; padding:9px 13px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,0.68); }
    main { padding:0 32px 56px; }
    .cell-section { margin:0 auto 30px; max-width:1420px; background:rgba(255,250,242,0.9); border:1px solid rgba(35,60,45,0.12); border-radius:32px; padding:28px; box-shadow:0 24px 70px rgba(42,65,51,0.12); }
    .section-head { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:20px; }
    .eyebrow { margin:0 0 6px; color:var(--green); font-weight:700; text-transform:uppercase; letter-spacing:0.08em; font-size:12px; }
    .metric-pill { padding:12px 18px; border-radius:18px; background:#17201b; color:white; min-width:140px; text-align:center; }
    .metrics-grid { display:grid; grid-template-columns: repeat(8, minmax(120px, 1fr)); gap:10px; margin-bottom:22px; }
    .metrics-grid div { background:white; border:1px solid var(--line); border-radius:18px; padding:13px; }
    .metrics-grid span { display:block; color:var(--muted); font-size:12px; margin-bottom:4px; }
    .metrics-grid b { font-size:18px; }
    .visual-grid { display:grid; grid-template-columns: minmax(0, 1fr) 340px; gap:22px; align-items:stretch; }
    .map { width:100%; min-height:520px; border-radius:28px; background:#eef7f0; border:1px solid var(--line); overflow:hidden; }
    .order-link { stroke:#8da99b; stroke-width:1.5; stroke-dasharray:4 7; }
    .pickup, .dropoff { fill:#d64045; stroke:white; stroke-width:1.8; }
    body[data-playback-step='routes'] .selected-order, body[data-playback-step='select'] .selected-order { fill:#f2b84b !important; }
    body[data-playback-step='execute'] .selected-order { fill:#21a67a !important; }
    .driver-radius { fill:rgba(47,128,237,0.08); stroke:rgba(47,128,237,0.36); stroke-width:2; stroke-dasharray:8 7; }
    .driver-triangle { fill:#17201b; stroke:white; stroke-width:2.3; }
    body[data-playback-step='routes'] .selected-driver .driver-triangle, body[data-playback-step='select'] .driver-triangle { fill:#f2b84b; }
    body[data-playback-step='execute'] .driver-triangle { fill:#21a67a; }
    .driver-label, .point-label { font-size:12px; font-weight:800; paint-order:stroke; stroke:white; stroke-width:3px; fill:#17201b; }
    .route-label { font-size:11px; fill:#34495e; }
    .moving-driver { filter: drop-shadow(0 4px 8px rgba(0,0,0,0.22)); }
    .route-step { stroke:white; stroke-width:2; }
    .route-step-label { fill:white; font-size:10px; font-weight:900; text-anchor:middle; pointer-events:none; }
    .playback-controls { display:flex; gap:10px; align-items:center; margin:4px 0 18px; }
    .playback-controls button { border:0; border-radius:999px; padding:11px 16px; background:#17201b; color:white; font-weight:800; cursor:pointer; }
    .playback-controls span { color:var(--green); font-weight:900; letter-spacing:0.04em; text-transform:uppercase; }
    .playback-order, .playback-driver, .playback-route, .playback-execute { transition: opacity 360ms ease, filter 360ms ease, transform 360ms ease; }
    body[data-playback-step='orders'] .playback-driver, body[data-playback-step='orders'] .playback-route, body[data-playback-step='orders'] .playback-execute { opacity:0.04 !important; }
    body[data-playback-step='orders'] .selected-order { filter: drop-shadow(0 0 6px rgba(15,139,104,0.55)); }
    body[data-playback-step='bundles'] .playback-driver, body[data-playback-step='bundles'] .playback-route, body[data-playback-step='bundles'] .playback-execute { opacity:0.08 !important; }
    body[data-playback-step='bundles'] .selected-order { opacity:0.95 !important; filter: drop-shadow(0 0 8px rgba(242,153,74,0.6)); }
    body[data-playback-step='routes'] .playback-route { opacity:0.88 !important; filter: drop-shadow(0 0 8px rgba(47,128,237,0.4)); }
    body[data-playback-step='routes'] .playback-execute { opacity:0.18 !important; }
    body[data-playback-step='select'] .selected-driver, body[data-playback-step='select'] .playback-route { opacity:1 !important; filter: drop-shadow(0 0 10px rgba(111,231,183,0.7)); }
    body[data-playback-step='execute'] .playback-execute { opacity:1 !important; filter: drop-shadow(0 0 10px rgba(232,93,117,0.65)); }
    .tile-evidence { margin:0 auto 26px; max-width:1420px; background:rgba(255,255,255,0.78); border:1px solid rgba(35,60,45,0.14); border-radius:28px; padding:24px; box-shadow:0 16px 48px rgba(42,65,51,0.09); }
    .tile-evidence p { color:var(--muted); line-height:1.45; }
    .tile-evidence table { width:100%; border-collapse:collapse; overflow:hidden; border-radius:18px; background:white; }
    .tile-evidence th, .tile-evidence td { text-align:left; padding:11px 12px; border-bottom:1px solid var(--line); font-size:13px; }
    .tile-evidence th { color:#0f8b68; background:#f2fbf6; }
    code { background:#eef7f1; border:1px solid #d8e4dc; border-radius:8px; padding:2px 6px; }
    .timeline { background:#17201b; color:white; border-radius:28px; padding:24px; }
    .timeline .step { border-left:3px solid rgba(110,231,183,0.35); padding:0 0 18px 16px; margin-left:4px; cursor:pointer; opacity:0.62; transition:opacity 240ms ease, border-color 240ms ease; }
    .timeline .step.active { opacity:1; border-color:#6ee7b7; }
    .timeline .step.complete { opacity:0.86; border-color:#f2994a; }
    .timeline span { display:block; color:#d8eee5; margin-top:4px; line-height:1.45; }
    .route-cards { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:14px; }
    .route-card { position:relative; background:white; border:1px solid var(--line); border-radius:22px; padding:18px 18px 18px 64px; min-height:132px; }
    .route-rank { position:absolute; left:16px; top:18px; width:34px; height:34px; border-radius:12px; color:white; display:grid; place-items:center; font-weight:900; }
    .route-card h3 { font-size:17px; }
    .route-card p { margin:7px 0; color:var(--muted); line-height:1.4; }
    .reason { color:#0f8b68 !important; font-weight:700; }
    footer { color:var(--muted); padding:0 48px 36px; }
    @media (max-width: 980px) { header { padding:28px 22px; } main { padding:0 14px 28px; } .visual-grid, .route-cards { grid-template-columns:1fr; } .metrics-grid { grid-template-columns:repeat(2, 1fr); } .section-head { flex-direction:column; } }
    """
    return "\n".join([
        "<!doctype html>",
        "<html lang='vi'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<link rel='icon' href='data:,'>",
        "<title>Dispatch V2 Visual Evidence</title>",
        f"<style>{css}</style>",
        "</head>",
        "<body>",
        "<header>",
        "<p class='eyebrow'>Dispatch V2 Visual Evidence</p>",
        "<h1>Visual evidence for order bundling, pickup, dropoff, and driver selection</h1>",
        f"<p class='subtitle'>This report is rendered from real benchmark artifacts, not a mock UI. It reads replay requests for pickup/dropoff/driver coordinates and reuse-state files for route proposals selected by the global selector. It shows up to {max_routes} selected routes per scenario so the dispatch flow stays readable.</p>",
        f"<nav>{cell_tabs}</nav>",
        "</header>",
        "<main>",
        render_tile_evidence(tile_evidence),
        *sections,
        "</main>",
        f"<footer>Generated at {html.escape(str(payload.get('generatedAt')))} from {html.escape(str(payload.get('sourceArtifact')))}. First cell: {html.escape(str(first.get('cell', 'n/a')))}</footer>",
        render_playback_script(),
        "</body></html>",
    ])


def build_payload(
    input_root: Path,
    scenarios: Sequence[str],
    profiles: Sequence[str],
    size: str,
    single_turn: bool = False,
    tile_probe_root: Optional[Path] = None,
) -> dict:
    comparison_path = latest_standard_comparison(input_root)
    comparison = read_json(comparison_path)
    cells = select_cells(comparison, scenarios, profiles, size, single_turn=single_turn)
    if not cells:
        raise ValueError("No matching benchmark cells found for visualization.")
    return {
        "schemaVersion": "dispatch-v2-visual-evidence/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceArtifact": safe_display_path(comparison_path),
        "gitCommit": comparison.get("gitCommit"),
        "tileEvidence": load_tile_evidence(tile_probe_root),
        "cells": [build_visual_cell(cell) for cell in cells],
    }


def write_reports(payload: dict, output_root: Path, max_routes: int, max_orders: int = 20, max_drivers: int = 5) -> Tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    copy_tile_images(payload.get("tileEvidence", {}), output_root)
    json_path = output_root / "dispatch_visual_evidence.json"
    html_path = output_root / "dispatch_visual_evidence.html"
    write_json(json_path, payload)
    html_path.write_text(render_html(payload, max_routes, max_orders=max_orders, max_drivers=max_drivers), encoding="utf-8")
    return json_path, html_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render a visual Dispatch V2 evidence report from benchmark artifacts.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT), help="Root containing standard_comparison-*.json")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for HTML/JSON visual evidence")
    parser.add_argument("--scenarios", default="normal-clear,heavy-rain,traffic-shock")
    parser.add_argument("--profiles", default="full-adaptive")
    parser.add_argument("--size", default="S")
    parser.add_argument("--max-routes", type=int, default=8, help="Maximum selected routes drawn per scenario")
    parser.add_argument("--max-orders", type=int, default=20, help="Maximum orders shown on the playback map")
    parser.add_argument("--max-drivers", type=int, default=5, help="Maximum selected drivers shown on the playback map")
    parser.add_argument("--tile-probe-root", default=str(DEFAULT_TILE_PROBE_ROOT), help="geo_tile_probe.json file or root containing tile probe artifacts")
    parser.add_argument("--single-turn", action="store_true", help="Render only the first matching dispatch turn with realtime playback")
    args = parser.parse_args(argv)

    payload = build_payload(
        resolve_repo_path(args.input_root),
        split_csv(args.scenarios),
        split_csv(args.profiles),
        args.size,
        single_turn=args.single_turn,
        tile_probe_root=resolve_repo_path(args.tile_probe_root),
    )
    json_path, html_path = write_reports(payload, resolve_repo_path(args.output_root), args.max_routes, args.max_orders, args.max_drivers)
    print(f"[VISUAL EVIDENCE JSON] {json_path}")
    print(f"[VISUAL EVIDENCE HTML] {html_path}")
    for cell in payload.get("cells", []):
        print(
            f"[VISUAL CELL] {cell.get('cell')} orders={len(cell.get('orders', []))} drivers={len(cell.get('drivers', []))} "
            f"selected={cell.get('selectedProposalCount')} executed={cell.get('executedAssignmentCount')} proposals={cell.get('routeProposalCount')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
