from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_line(metrics: Dict[str, Any], key: str) -> str:
    return f"| `{key}` | `{metrics.get(key, '')}` |"


def write_report(metrics_path: Path, gate_path: Path, manifest_path: Path, output_path: Path) -> None:
    metrics = read_json(metrics_path)
    gate = read_json(gate_path)
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    lines = [
        "# Real Road Dispatch Loop Report",
        "",
        f"- generatedAt: `{datetime.now(timezone.utc).isoformat()}`",
        f"- loop: `{gate.get('loop')}`",
        f"- verdict: `{gate.get('verdict')}`",
        f"- reasons: `{gate.get('reasons')}`",
        f"- benchmark: `{metrics.get('comparisonPath', '')}`",
        f"- visual: `{metrics.get('visualPath', '')}`",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key in (
        "snapSuccessRate",
        "roadRouteCoverage",
        "syntheticFallbackRouteCount",
        "selectedRoutePolylineCoverage",
        "visualStraightLineSelectedRouteCount",
        "selectedSingleOrderCount",
        "selectedBundleSize2Count",
        "selectedBundleSize3Count",
        "selectedBundleSize4Count",
        "selectedBundleSize5Count",
        "coveredOrderCount",
        "executedAssignmentCount",
        "badRoadRouteCount",
        "weakRoadRouteCount",
        "avgNetworkDetourRatio",
        "maxNetworkDetourRatio",
        "avgRoadEta",
        "maxRoadEta",
        "routeProposalPoolLatencyMs",
        "matrixLatencyMs",
        "planRepairLatencyMs",
    ):
        lines.append(metric_line(metrics, key))
    lines.extend([
        "",
        "## Manifest",
        "",
        "```json",
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
    ])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[REAL ROAD LOOP REPORT] {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a Real Road Dispatch loop report.")
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_report(Path(args.metrics), Path(args.gate), Path(args.manifest), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
