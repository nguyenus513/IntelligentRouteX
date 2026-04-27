from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "traffic"
DATASETS: Dict[str, Dict[str, Any]] = {
    "metr-la": {
        "displayName": "METR-LA",
        "expectedFiles": ["METR-LA.csv", "adj_mx_METR-LA.pkl"],
        "source": "Zenodo traffic speed benchmark mirror of METR-LA",
        "files": {
            "METR-LA.csv": "https://zenodo.org/api/records/5724362/files/METR-LA.csv/content",
            "adj_mx_METR-LA.pkl": "https://zenodo.org/api/records/5724362/files/adj_mx_METR-LA.pkl/content",
        },
        "manualNote": "Place METR-LA.csv and adj_mx_METR-LA.pkl in this directory if automatic download is unavailable.",
    },
    "pems-bay": {
        "displayName": "PeMS-BAY",
        "expectedFiles": ["PEMS-BAY.csv", "adj_mx_PEMS-BAY.pkl"],
        "source": "Zenodo traffic speed benchmark mirror of PeMS-BAY",
        "files": {
            "PEMS-BAY.csv": "https://zenodo.org/api/records/5724362/files/PEMS-BAY.csv/content",
            "adj_mx_PEMS-BAY.pkl": "https://zenodo.org/api/records/5724362/files/adj_mx_PEMS-BAY.pkl/content",
        },
        "manualNote": "Place PEMS-BAY.csv and adj_mx_PEMS-BAY.pkl in this directory if automatic download is unavailable.",
    },
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def download_file(url: str, destination: Path, timeout_seconds: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare community traffic benchmark dataset directories and manifests.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="metr-la,pems-bay")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    requested = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    entries = []
    for dataset in requested:
        spec = DATASETS[dataset]
        dataset_root = output_root / dataset
        dataset_root.mkdir(parents=True, exist_ok=True)
        errors = []
        if not args.no_download:
            for filename, url in spec.get("files", {}).items():
                destination = dataset_root / filename
                if destination.exists():
                    continue
                try:
                    download_file(url, destination, args.timeout_seconds)
                except Exception as exc:  # pragma: no cover - network failure is environment-dependent.
                    errors.append({"file": filename, "url": url, "error": str(exc)})
        expected = [dataset_root / name for name in spec["expectedFiles"]]
        missing = [path.name for path in expected if not path.exists()]
        entry = {
            "dataset": dataset,
            "displayName": spec["displayName"],
            "source": spec["source"],
            "path": str(dataset_root),
            "expectedFiles": spec["expectedFiles"],
            "missingFiles": missing,
            "ready": not missing,
            "manualNote": spec["manualNote"],
        }
        if errors:
            entry["downloadErrors"] = errors
        write_json(dataset_root / "manifest.json", entry)
        entries.append(entry)
    manifest = {
        "schemaVersion": "community-traffic-data/v1",
        "datasets": entries,
        "readyDatasetCount": sum(1 for entry in entries if entry["ready"]),
        "finalVerdict": "PASS" if all(entry["ready"] for entry in entries) else "EVIDENCE_GAP",
    }
    write_json(output_root / "manifest.json", manifest)
    print(f"[COMMUNITY TRAFFIC DATA MANIFEST] {output_root / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
