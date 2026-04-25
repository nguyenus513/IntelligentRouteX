#!/usr/bin/env python3
"""Fetch real map tiles for Dispatch V2 geo-source validation.

The probe intentionally keeps raw PNG tiles in an artifact cache only. Runtime
prompts and benchmark reports should consume summaries/metadata, not raw tiles.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_OUTPUT_ROOT = Path("artifacts/validation/geo-tiles")
DEFAULT_USER_AGENT = "IntelligentRouteX/dispatch-v2-tile-probe (+local-validation)"
OSM_TILE_BASE_URL = "https://tile.openstreetmap.org"
TOMTOM_MAP_BASE_URL = "https://api.tomtom.com/map/1/tile/basic/main"
TOMTOM_TRAFFIC_FLOW_BASE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/relative0"


@dataclass(frozen=True)
class TileId:
    z: int
    x: int
    y: int


@dataclass(frozen=True)
class TileFetchResult:
    provider: str
    tile: TileId
    urlTemplate: str
    status: str
    httpStatus: Optional[int]
    byteCount: int
    cachePath: str
    cacheHit: bool
    latencyMs: int
    degradeReason: str
    attribution: str


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> TileId:
    lat = max(min(lat, 85.05112878), -85.05112878)
    scale = 1 << zoom
    x = int((lon + 180.0) / 360.0 * scale)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * scale)
    return TileId(zoom, max(0, min(scale - 1, x)), max(0, min(scale - 1, y)))


def osm_url(tile: TileId) -> str:
    return f"{OSM_TILE_BASE_URL}/{tile.z}/{tile.x}/{tile.y}.png"


def tomtom_map_url(tile: TileId, api_key: str) -> str:
    return f"{TOMTOM_MAP_BASE_URL}/{tile.z}/{tile.x}/{tile.y}.png?{urlencode({'key': api_key})}"


def tomtom_traffic_flow_url(tile: TileId, api_key: str) -> str:
    return f"{TOMTOM_TRAFFIC_FLOW_BASE_URL}/{tile.z}/{tile.x}/{tile.y}.png?{urlencode({'key': api_key})}"


def safe_url_template(provider: str) -> str:
    if provider == "osm-raster":
        return f"{OSM_TILE_BASE_URL}/{{z}}/{{x}}/{{y}}.png"
    if provider == "tomtom-raster-basic":
        return f"{TOMTOM_MAP_BASE_URL}/{{z}}/{{x}}/{{y}}.png?key=<redacted>"
    if provider == "tomtom-traffic-flow":
        return f"{TOMTOM_TRAFFIC_FLOW_BASE_URL}/{{z}}/{{x}}/{{y}}.png?key=<redacted>"
    return "unknown"


def cache_path(output_root: Path, provider: str, tile: TileId) -> Path:
    return output_root / "cache" / provider / str(tile.z) / str(tile.x) / f"{tile.y}.png"


def fetch_tile(
    provider: str,
    tile: TileId,
    url: str,
    output_root: Path,
    user_agent: str,
    timeout_seconds: float,
    force_refresh: bool,
    attribution: str,
) -> TileFetchResult:
    target = cache_path(output_root, provider, tile)
    started = time.perf_counter()
    if target.exists() and not force_refresh:
        return TileFetchResult(
            provider,
            tile,
            safe_url_template(provider),
            "CACHE_HIT",
            200,
            target.stat().st_size,
            str(target),
            True,
            int((time.perf_counter() - started) * 1000),
            "",
            attribution,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "image/png,image/*;q=0.8"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            status = int(getattr(response, "status", 200) or 200)
        if status < 200 or status >= 300:
            return failed(provider, tile, output_root, started, f"http-{status}", status, attribution)
        if not body:
            return failed(provider, tile, output_root, started, "empty-tile-response", status, attribution)
        target.write_bytes(body)
        return TileFetchResult(
            provider,
            tile,
            safe_url_template(provider),
            "FETCHED",
            status,
            len(body),
            str(target),
            False,
            int((time.perf_counter() - started) * 1000),
            "",
            attribution,
        )
    except HTTPError as exception:
        return failed(provider, tile, output_root, started, f"http-{exception.code}", exception.code, attribution)
    except TimeoutError:
        return failed(provider, tile, output_root, started, "tile-fetch-timeout", None, attribution)
    except URLError as exception:
        reason = getattr(exception, "reason", exception)
        if provider.startswith("tomtom-") and "CERTIFICATE_VERIFY_FAILED" in str(reason) and os.name == "nt":
            try:
                byte_count = powershell_fetch_tile(url, target, user_agent, timeout_seconds)
                return TileFetchResult(
                    provider,
                    tile,
                    safe_url_template(provider),
                    "FETCHED",
                    200,
                    byte_count,
                    str(target),
                    False,
                    int((time.perf_counter() - started) * 1000),
                    "python-ssl-fallback-powershell",
                    attribution,
                )
            except RuntimeError as fallback_error:
                return failed(provider, tile, output_root, started, f"tile-fetch-unavailable:{fallback_error}", None, attribution)
        return failed(provider, tile, output_root, started, f"tile-fetch-unavailable:{reason}", None, attribution)
    except OSError as exception:
        return failed(provider, tile, output_root, started, f"tile-fetch-io-error:{exception}", None, attribution)


def failed(
    provider: str,
    tile: TileId,
    output_root: Path,
    started: float,
    reason: str,
    http_status: Optional[int],
    attribution: str,
) -> TileFetchResult:
    return TileFetchResult(
        provider,
        tile,
        safe_url_template(provider),
        "FAILED",
        http_status,
        0,
        str(cache_path(output_root, provider, tile)),
        False,
        int((time.perf_counter() - started) * 1000),
        reason,
        attribution,
    )


def skipped(provider: str, tile: TileId, output_root: Path, reason: str, attribution: str) -> TileFetchResult:
    return TileFetchResult(
        provider,
        tile,
        safe_url_template(provider),
        "SKIPPED",
        None,
        0,
        str(cache_path(output_root, provider, tile)),
        False,
        0,
        reason,
        attribution,
    )


def powershell_fetch_tile(url: str, target: Path, user_agent: str, timeout_seconds: float) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PROBE_TILE_URL"] = url
    env["PROBE_TILE_OUT"] = str(target)
    env["PROBE_TILE_UA"] = user_agent
    env["PROBE_TILE_TIMEOUT"] = str(max(1, int(timeout_seconds)))
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "$ProgressPreference='SilentlyContinue'; "
        "Invoke-WebRequest -Uri $env:PROBE_TILE_URL -OutFile $env:PROBE_TILE_OUT "
        "-TimeoutSec $env:PROBE_TILE_TIMEOUT -Headers @{ 'User-Agent'=$env:PROBE_TILE_UA }; "
        "$item=Get-Item $env:PROBE_TILE_OUT; Write-Output $item.Length",
    ]
    completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout_seconds + 10)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "powershell-fetch-failed").strip().splitlines()[-1]
        raise RuntimeError(detail)
    try:
        return int((completed.stdout or "0").strip().splitlines()[-1])
    except (ValueError, IndexError) as exception:
        raise RuntimeError("powershell-fetch-invalid-byte-count") from exception


def build_report(payload: dict) -> str:
    rows = payload.get("tiles", [])
    lines = [
        "# Dispatch V2 Geo Tile Probe",
        "",
        f"- generated at: `{payload.get('generatedAt')}`",
        f"- center: `{payload.get('center')}`",
        f"- zoom: `{payload.get('zoom')}`",
        f"- tile: `{payload.get('tile')}`",
        "",
        "| provider | status | http | bytes | cache hit | latency ms | reason | cache path |",
        "| --- | --- | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {provider} | {status} | {http} | {bytes} | {hit} | {latency} | {reason} | `{path}` |".format(
                provider=row.get("provider", ""),
                status=row.get("status", ""),
                http=row.get("httpStatus") if row.get("httpStatus") is not None else "",
                bytes=row.get("byteCount", 0),
                hit=row.get("cacheHit", False),
                latency=row.get("latencyMs", 0),
                reason=row.get("degradeReason", ""),
                path=row.get("cachePath", ""),
            )
        )
    lines.extend([
        "",
        "## Source Policy Notes",
        "",
        "- OSM tiles are fetched with an explicit User-Agent and cached under the artifact root.",
        "- TomTom tiles require `TOMTOM_API_KEY` or `--tomtom-api-key`; keys are redacted from reports.",
        "- Raw tile PNGs are artifact/cache data only; prompt/training rails should consume summaries or encoded vectors.",
    ])
    return "\n".join(lines) + "\n"


def run_probe(args: argparse.Namespace) -> dict:
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    tile = lat_lon_to_tile(args.lat, args.lon, args.zoom)
    tomtom_key = args.tomtom_api_key or os.environ.get("TOMTOM_API_KEY", "")
    results: list[TileFetchResult] = []

    if "osm" in args.providers:
        results.append(fetch_tile(
            "osm-raster",
            tile,
            osm_url(tile),
            output_root,
            args.user_agent,
            args.timeout_seconds,
            args.force_refresh,
            "© OpenStreetMap contributors",
        ))
    if "tomtom" in args.providers:
        if tomtom_key.strip():
            results.append(fetch_tile(
                "tomtom-raster-basic",
                tile,
                tomtom_map_url(tile, tomtom_key.strip()),
                output_root,
                args.user_agent,
                args.timeout_seconds,
                args.force_refresh,
                "© TomTom",
            ))
            results.append(fetch_tile(
                "tomtom-traffic-flow",
                tile,
                tomtom_traffic_flow_url(tile, tomtom_key.strip()),
                output_root,
                args.user_agent,
                args.timeout_seconds,
                args.force_refresh,
                "© TomTom",
            ))
        else:
            results.append(skipped("tomtom-raster-basic", tile, output_root, "tomtom-api-key-missing", "© TomTom"))
            results.append(skipped("tomtom-traffic-flow", tile, output_root, "tomtom-api-key-missing", "© TomTom"))

    payload = {
        "schemaVersion": "dispatch-v2-geo-tile-probe/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "center": {"lat": args.lat, "lon": args.lon},
        "zoom": args.zoom,
        "tile": asdict(tile),
        "providers": args.providers,
        "tiles": [asdict(result) for result in results],
    }
    (output_root / "geo_tile_probe.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_root / "geo_tile_probe_report.md").write_text(build_report(payload), encoding="utf-8")
    return payload


def providers(value: str) -> list[str]:
    allowed = {"osm", "tomtom"}
    parsed = [part.strip().lower() for part in value.split(",") if part.strip()]
    unknown = sorted(set(parsed) - allowed)
    if unknown:
        raise argparse.ArgumentTypeError(f"Unknown providers: {unknown}")
    return parsed or ["osm", "tomtom"]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OSM and TomTom tiles for Dispatch V2 geo validation.")
    parser.add_argument("--lat", type=float, default=10.7769, help="Tile center latitude. Default is central Ho Chi Minh City.")
    parser.add_argument("--lon", type=float, default=106.7009, help="Tile center longitude. Default is central Ho Chi Minh City.")
    parser.add_argument("--zoom", type=int, default=14)
    parser.add_argument("--providers", type=providers, default=["osm", "tomtom"], help="Comma-separated: osm,tomtom")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--tomtom-api-key", default="", help="TomTom API key. Defaults to TOMTOM_API_KEY env var.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload = run_probe(args)
    print("[GEO TILE PROBE JSON]", Path(args.output_root) / "geo_tile_probe.json")
    for tile in payload.get("tiles", []):
        print(
            "[GEO TILE] {provider} status={status} bytes={bytes} reason={reason}".format(
                provider=tile.get("provider"),
                status=tile.get("status"),
                bytes=tile.get("byteCount"),
                reason=tile.get("degradeReason"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
