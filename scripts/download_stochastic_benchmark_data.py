from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "stochastic"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_manifest(output_root: Path) -> Dict[str, Any]:
    data_dir = output_root / "instances"
    data_dir.mkdir(parents=True, exist_ok=True)
    instance_files = sorted(path.name for path in data_dir.glob("*.json"))
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
