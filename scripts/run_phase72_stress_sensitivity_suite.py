from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmarks" / "synthetic_food" / "stress_v1"
DEFAULT_DOC = REPO_ROOT / "docs" / "benchmark" / "stress_sensitivity_suite.md"


def generate_manifest() -> Dict[str, Any]:
    rows = []
    for orders in [20, 40, 80, 120]:
        for driver_mode in ["loose", "balanced", "tight"]:
            for traffic in [1.0, 1.2, 1.5, 2.0]:
                for tightness in ["loose", "normal", "tight", "extreme"]:
                    for cluster_ratio in [0.1, 0.5, 0.8]:
                        rows.append({"orders": orders, "driverMode": driver_mode, "trafficMultiplier": traffic, "timeWindowTightness": tightness, "clusterRatio": cluster_ratio, "rain": traffic >= 1.5, "expectedFailureMode": expected_failure(orders, driver_mode, traffic, tightness)})
    return {"schemaVersion": "phase72-stress-sensitivity-suite/v1", "variantCount": len(rows), "variants": rows}


def expected_failure(orders: int, driver_mode: str, traffic: float, tightness: str) -> str:
    if tightness == "extreme" and traffic >= 1.5:
        return "time-window-risk"
    if driver_mode == "tight" and orders >= 80:
        return "vehicle-shortage-risk"
    if orders >= 120:
        return "runtime-risk"
    return "quality-risk"


def markdown(manifest: Dict[str, Any]) -> str:
    rows = manifest.get("variants", [])[:20]
    lines = ["# Phase 72 Stress & Sensitivity Suite", "", f"Variant count: {manifest['variantCount']}", "", "| Orders | Drivers | Traffic | TW | Cluster | Expected Failure |", "|---:|---|---:|---|---:|---|"]
    for row in rows:
        lines.append(f"| {row['orders']} | {row['driverMode']} | {row['trafficMultiplier']} | {row['timeWindowTightness']} | {row['clusterRatio']} | {row['expectedFailureMode']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 72 synthetic stress/sensitivity manifest.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    args = parser.parse_args()
    manifest = generate_manifest()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase72_stress_sensitivity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    text = markdown(manifest)
    (output_dir / "phase72_stress_sensitivity_manifest.md").write_text(text, encoding="utf-8")
    doc = Path(args.doc)
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    print(f"[PHASE72 STRESS SENSITIVITY] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
