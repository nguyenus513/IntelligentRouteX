from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "traffic"
DATASETS: Dict[str, Dict[str, Any]] = {
    "metr-la": {
        "displayName": "METR-LA",
        "expectedFiles": ["METR-LA.npz", "adj_mx.pkl"],
        "source": "DCRNN/METR-LA community traffic forecasting benchmark",
        "manualNote": "Place METR-LA.npz and adj_mx.pkl in this directory if automatic download is unavailable.",
    },
    "pems-bay": {
        "displayName": "PeMS-BAY",
        "expectedFiles": ["PEMS-BAY.npz", "adj_mx_bay.pkl"],
        "source": "DCRNN/PeMS-BAY community traffic forecasting benchmark",
        "manualNote": "Place PEMS-BAY.npz and adj_mx_bay.pkl in this directory if automatic download is unavailable.",
    },
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare community traffic benchmark dataset directories and manifests.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="metr-la,pems-bay")
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    requested = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    entries = []
    for dataset in requested:
        spec = DATASETS[dataset]
        dataset_root = output_root / dataset
        dataset_root.mkdir(parents=True, exist_ok=True)
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
