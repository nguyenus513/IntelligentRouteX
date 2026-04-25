from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def gate_loop(loop: int, metrics: Dict[str, Any], provider_ready: bool = True) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if loop != 1:
        return "EVIDENCE_GAP", [f"loop-{loop:02d}-implementation-not-yet-wired"]

    if float(metrics.get("snapSuccessRate", 0.0)) < 0.95:
        reasons.append("snap-success-rate-below-0.95")
    if float(metrics.get("roadRouteCoverage", 0.0)) < 0.95:
        reasons.append("road-route-coverage-below-0.95")
    if int(metrics.get("selectedBadGeoPointCount", 0)) > 0:
        reasons.append("selected-bad-geo-point-present")
    if provider_ready and int(metrics.get("visualStraightLineSelectedRouteCount", 0)) > 0:
        reasons.append("selected-route-rendered-as-straight-line")
    if provider_ready and float(metrics.get("selectedRoutePolylineCoverage", 0.0)) < 0.95:
        reasons.append("selected-route-polyline-coverage-below-0.95")
    if int(metrics.get("executedAssignmentCount", 0)) <= 0:
        reasons.append("no-executed-assignments")

    if reasons:
        return "FAIL", reasons

    soft_limits = []
    if int(metrics.get("syntheticFallbackRouteCount", 0)) > 0:
        soft_limits.append("synthetic-fallback-route-observed")
    if soft_limits:
        return "PASS_WITH_LIMITS", soft_limits
    return "PASS", ["loop-01-road-route-evidence-pass"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Real Road Dispatch loop gate.")
    parser.add_argument("--loop", type=int, required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provider-ready", action="store_true", default=False)
    args = parser.parse_args()
    metrics = read_json(Path(args.metrics))
    verdict, reasons = gate_loop(args.loop, metrics, provider_ready=args.provider_ready)
    payload = {
        "schemaVersion": "real-road-loop-gate/v1",
        "loop": args.loop,
        "verdict": verdict,
        "reasons": reasons,
        "providerReady": args.provider_ready,
    }
    write_json(Path(args.output), payload)
    print(f"[REAL ROAD LOOP GATE] loop={args.loop:02d} verdict={verdict} reasons={reasons}")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
