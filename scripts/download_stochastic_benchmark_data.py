from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Sequence

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "stochastic"
SVRPBENCH_URL = "https://huggingface.co/datasets/MBZUAI/svrp-bench/resolve/main/data/test-00000-of-00001.parquet"
SVRPBENCH_README_URL = "https://huggingface.co/datasets/MBZUAI/svrp-bench"
SVRPBENCH_ROWS_API = "https://datasets-server.huggingface.co/rows?dataset=MBZUAI%2Fsvrp-bench&config=default&split=test&offset=0&length=10"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, target: Path, timeout_seconds: int = 120) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    target.write_bytes(response.content)


def download_json(url: str, target: Path, timeout_seconds: int = 120) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    target.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_manifest(output_root: Path, download: bool = True) -> Dict[str, Any]:
    data_dir = output_root / "instances"
    data_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = data_dir / "svrp-bench-test.parquet"
    sample_path = data_dir / "svrp-bench-test-sample.json"
    download_error = None
    if download:
        try:
            download_file(SVRPBENCH_URL, parquet_path)
            download_json(SVRPBENCH_ROWS_API, sample_path)
        except Exception as exc:
            download_error = f"{type(exc).__name__}: {exc}"
    instance_paths = sorted(path for path in data_dir.glob("*.*") if path.is_file())
    instance_files = [path.name for path in instance_paths]
    if instance_files:
        verdict = "PASS_WITH_LIMITS"
        reasons = ["stochastic-parser-checker-not-yet-integrated"]
    else:
        verdict = "EVIDENCE_GAP"
        reasons = ["public-stochastic-vrp-data-missing", "svrpbench-data-source-not-configured"]
    return {
        "schemaVersion": "stochastic-community-data-manifest/v1",
        "benchmarkFamily": "public-stochastic-vrp",
        "dataRoot": str(output_root),
        "instanceDirectory": str(data_dir),
        "instanceFileCount": len(instance_files),
        "instanceFiles": instance_files,
        "sourceUrl": SVRPBENCH_URL,
        "sampleRowsUrl": SVRPBENCH_ROWS_API,
        "sourceLandingPage": SVRPBENCH_README_URL,
        "downloadError": download_error,
        "checksums": {path.name: "sha256:" + sha256(path) for path in instance_paths},
        "finalVerdict": verdict,
        "verdictReasons": reasons,
        "manualDataInstructions": [
            "Place public stochastic VRP benchmark instance files under benchmarks/external/official/stochastic/instances/.",
            "Keep source URLs and checksums beside the files before enabling PASS claims.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a manifest for public stochastic VRP benchmark data.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    manifest = build_manifest(output_root)
    write_json(output_root / "manifest.json", manifest)
    print(f"[STOCHASTIC MANIFEST] {output_root / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
