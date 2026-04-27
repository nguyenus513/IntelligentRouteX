from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "weather"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DATASETS: Dict[str, Dict[str, Any]] = {
    "open-meteo-ny": {
        "displayName": "Open-Meteo Historical Weather - New York",
        "source": "Open-Meteo Historical Weather API",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timezone": "America/New_York",
        "startDate": "2024-06-01",
        "endDate": "2024-06-07",
        "expectedFiles": ["weather.json"],
        "manualNote": "If automatic download is unavailable, place the Open-Meteo archive JSON at weather.json.",
    }
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def fetch_open_meteo(spec: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    query = {
        "latitude": spec["latitude"],
        "longitude": spec["longitude"],
        "start_date": spec["startDate"],
        "end_date": spec["endDate"],
        "hourly": "precipitation,rain,wind_speed_10m,weather_code",
        "timezone": spec["timezone"],
        "wind_speed_unit": "kmh",
    }
    url = f"{OPEN_METEO_ARCHIVE_URL}?{urllib.parse.urlencode(query)}"
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    payload["benchmarkMetadata"] = {
        "dataset": spec["displayName"],
        "source": spec["source"],
        "downloadUrl": url,
        "downloadedDate": date.today().isoformat(),
        "licenseNote": "Public Open-Meteo API data; see Open-Meteo terms for reuse conditions.",
    }
    return payload


def prepare_dataset(output_root: Path, dataset: str, timeout_seconds: int) -> Dict[str, Any]:
    spec = DATASETS[dataset]
    dataset_root = output_root / dataset
    dataset_root.mkdir(parents=True, exist_ok=True)
    weather_path = dataset_root / "weather.json"
    error = None
    if not weather_path.exists():
        try:
            write_json(weather_path, fetch_open_meteo(spec, timeout_seconds))
        except Exception as exc:  # pragma: no cover - network failure is environment-dependent.
            error = str(exc)
    missing = [name for name in spec["expectedFiles"] if not (dataset_root / name).exists()]
    entry = {
        "schemaVersion": "community-weather-data/v1",
        "dataset": dataset,
        "displayName": spec["displayName"],
        "source": spec["source"],
        "path": str(dataset_root),
        "expectedFiles": spec["expectedFiles"],
        "missingFiles": missing,
        "ready": not missing,
        "latitude": spec["latitude"],
        "longitude": spec["longitude"],
        "startDate": spec["startDate"],
        "endDate": spec["endDate"],
        "manualNote": spec["manualNote"],
    }
    if error:
        entry["downloadError"] = error
    write_json(dataset_root / "manifest.json", entry)
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download public historical weather data for community route benchmarks.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="open-meteo-ny")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    requested = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    entries = [prepare_dataset(output_root, dataset, args.timeout_seconds) for dataset in requested]
    manifest = {
        "schemaVersion": "community-weather-data/v1",
        "datasets": entries,
        "readyDatasetCount": sum(1 for entry in entries if entry["ready"]),
        "finalVerdict": "PASS" if entries and all(entry["ready"] for entry in entries) else "EVIDENCE_GAP",
    }
    write_json(output_root / "manifest.json", manifest)
    print(f"[COMMUNITY WEATHER DATA MANIFEST] {output_root / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
