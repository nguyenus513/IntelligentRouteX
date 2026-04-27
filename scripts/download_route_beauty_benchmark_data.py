from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "dimacs-road"
DIMACS_REGIONS = ("NY", "BAY", "COL", "FLA")


def dimacs_urls(regions: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    for region in regions:
        code = region.upper()
        urls[f"USA-road-d.{code}.gr.gz"] = f"https://www.diag.uniroma1.it/challenge9/data/USA-road-d/USA-road-d.{code}.gr.gz"
        urls[f"USA-road-d.{code}.co.gz"] = f"https://www.diag.uniroma1.it/challenge9/data/USA-road-d/USA-road-d.{code}.co.gz"
    return urls


def download_file(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        return
    with urllib.request.urlopen(url, timeout=120) as response:
        output.write_bytes(response.read())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download public DIMACS road graph data for route-quality benchmarking.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--regions", default="NY", help="Comma-separated DIMACS regions, e.g. NY,BAY,COL,FLA.")
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    files = []
    regions = [part.strip().upper() for part in args.regions.split(",") if part.strip()]
    for filename, url in dimacs_urls(regions).items():
        target = output_root / filename
        download_file(url, target)
        files.append({"filename": filename, "url": url, "path": str(target), "bytes": target.stat().st_size})
    manifest = {
        "schemaVersion": "route-beauty-benchmark-data/v1",
        "benchmarkFamily": "dimacs-road",
        "regions": regions,
        "licenseNote": "Public DIMACS 9th Implementation Challenge road-network benchmark files; keep provenance with downloaded artifacts.",
        "files": files,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[ROUTE BEAUTY DATA MANIFEST] {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
