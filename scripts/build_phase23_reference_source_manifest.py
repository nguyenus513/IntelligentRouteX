from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase23-reference-sources-v1"


def build_manifest(instance: str) -> dict[str, Any]:
    return {
        "schemaVersion": "phase23-reference-source-manifest/v1",
        "instance": instance,
        "localDropPaths": [
            f"artifacts/benchmark/reference-solutions/{instance}.json",
            f"artifacts/benchmark/reference-solutions/{instance}.txt",
            f"artifacts/benchmark/reference-solutions/{instance}.sol",
            f"benchmarks/external/reference/{instance}.json",
            f"benchmarks/external/official/solomon/solutions/{instance}.json",
            f"benchmarks/external/solomon/solutions/{instance}.txt",
        ],
        "candidateSources": [
            {
                "name": "VRPTW Solomon benchmark supplemental",
                "url": "https://sites.google.com/view/vrptwaalihodzic",
                "status": "manual-review-required",
                "note": "Contains feasible routes for Solomon instances; verify vehicle count, distance, and exact instance compatibility before import.",
            },
            {
                "name": "Solomon best solutions list",
                "url": "https://sun.aei.polsl.pl/~zjc/best-solutions-solomon.html",
                "status": "bks-metadata-only",
                "note": "Confirms RC101 best known vehicle count and objective; does not provide route file directly.",
            },
            {
                "name": "SINTEF TOP",
                "url": "https://www.sintef.no/projectweb/top/",
                "status": "official-benchmark-reference",
                "note": "Use as benchmark/BKS provenance reference.",
            },
        ],
    }


def markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Phase 23 Reference Source Manifest",
        "",
        f"- instance: `{manifest['instance']}`",
        "",
        "## Local Drop Paths",
        "",
    ]
    for path in manifest["localDropPaths"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Candidate Sources", ""])
    for source in manifest["candidateSources"]:
        lines.append(f"- `{source['name']}`: {source['url']} — `{source['status']}` — {source['note']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 23 reference source manifest.")
    parser.add_argument("--instance", default="RC101")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    manifest = build_manifest(args.instance)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase23_reference_source_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase23_reference_source_manifest.md").write_text(markdown(manifest), encoding="utf-8")
    print(f"[PHASE23 REFERENCE SOURCE MANIFEST] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
