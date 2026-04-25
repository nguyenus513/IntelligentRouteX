from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "production-readiness"
HCMC_POINTS = [
    (10.7769, 106.7009),
    (10.7820, 106.6958),
    (10.8016, 106.7147),
    (10.7626, 106.6601),
    (10.8411, 106.8098),
]


def fetch_json(url: str, timeout: float) -> tuple[dict[str, Any], int, int]:
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return json.loads(body), response.status, latency_ms


def route_probe(base_url: str, timeout: float) -> dict[str, Any]:
    left, right = HCMC_POINTS[0], HCMC_POINTS[1]
    coordinates = f"{left[1]},{left[0]};{right[1]},{right[0]}"
    query = urllib.parse.urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    body, status, latency_ms = fetch_json(f"{base_url}/route/v1/driving/{coordinates}?{query}", timeout)
    route = (body.get("routes") or [{}])[0]
    return {
        "endpoint": "/route",
        "httpStatus": status,
        "code": body.get("code"),
        "latencyMs": latency_ms,
        "distanceMeters": route.get("distance"),
        "durationSeconds": route.get("duration"),
        "polylinePoints": len(((route.get("geometry") or {}).get("coordinates") or [])),
    }


def nearest_probe(base_url: str, timeout: float) -> dict[str, Any]:
    point = HCMC_POINTS[0]
    query = urllib.parse.urlencode({"number": "1"})
    body, status, latency_ms = fetch_json(f"{base_url}/nearest/v1/driving/{point[1]},{point[0]}?{query}", timeout)
    waypoint = (body.get("waypoints") or [{}])[0]
    return {
        "endpoint": "/nearest",
        "httpStatus": status,
        "code": body.get("code"),
        "latencyMs": latency_ms,
        "snapDistanceMeters": waypoint.get("distance"),
        "name": waypoint.get("name", ""),
    }


def table_probe(base_url: str, timeout: float, point_count: int) -> dict[str, Any]:
    points = []
    while len(points) < point_count:
        for lat, lon in HCMC_POINTS:
            if len(points) >= point_count:
                break
            offset = len(points) * 0.00015
            points.append((lat + offset, lon + offset))
    coordinates = ";".join(f"{lon},{lat}" for lat, lon in points)
    query = urllib.parse.urlencode({"annotations": "duration,distance"})
    body, status, latency_ms = fetch_json(f"{base_url}/table/v1/driving/{coordinates}?{query}", timeout)
    durations = body.get("durations") or []
    distances = body.get("distances") or []
    duration_cells = [cell for row in durations for cell in row]
    distance_cells = [cell for row in distances for cell in row]
    return {
        "endpoint": "/table",
        "httpStatus": status,
        "code": body.get("code"),
        "latencyMs": latency_ms,
        "pointCount": point_count,
        "durationCellCount": len(duration_cells),
        "distanceCellCount": len(distance_cells),
        "nullDurationCount": sum(1 for cell in duration_cells if cell is None),
        "nullDistanceCount": sum(1 for cell in distance_cells if cell is None),
    }


def write_report(payload: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_root / f"osrm-audit-{timestamp}.json"
    md_path = output_root / "osrm-audit-report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Dispatch V2 OSRM Audit",
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- baseUrl: `{payload['baseUrl']}`",
        "",
        "| endpoint | status | code | latency ms | details |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for row in payload.get("probes", []):
        details = ", ".join(f"{key}={value}" for key, value in row.items() if key not in {"endpoint", "httpStatus", "code", "latencyMs"})
        lines.append(f"| {row['endpoint']} | {row.get('httpStatus')} | {row.get('code')} | {row.get('latencyMs')} | {details} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local OSRM endpoints used by Dispatch V2.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--table-points", type=int, default=20)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    probes = []
    for probe in (route_probe, nearest_probe):
        try:
            probes.append(probe(base_url, args.timeout))
        except Exception as exception:  # noqa: BLE001 - audit must report failures instead of crashing early.
            probes.append({"endpoint": probe.__name__.replace("_probe", ""), "error": str(exception)})
    try:
        probes.append(table_probe(base_url, args.timeout, args.table_points))
    except Exception as exception:  # noqa: BLE001
        probes.append({"endpoint": "/table", "error": str(exception), "pointCount": args.table_points})
    payload = {
        "schemaVersion": "dispatch-v2-osrm-audit/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base_url,
        "probes": probes,
    }
    json_path, md_path = write_report(payload, Path(args.output_root))
    print(f"[OSRM AUDIT JSON] {json_path}")
    print(f"[OSRM AUDIT REPORT] {md_path}")
    return 1 if any("error" in row for row in probes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
