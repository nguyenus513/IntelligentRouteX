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
    if loop not in (1, 2, 3, 4, 5, 6, 7, 8):
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
    if loop == 2:
        if metrics.get("geoGenerationMode") != "road-aware":
            reasons.append("geo-generation-mode-not-road-aware")
        if float(metrics.get("routableOrderRate", 0.0)) < 0.95:
            reasons.append("routable-order-rate-below-0.95")
        if int(metrics.get("badGeoPointCount", 0)) > 0:
            reasons.append("bad-geo-point-count-non-zero")
        if int(metrics.get("coveredOrderCount", 0)) < int(metrics.get("baselineCoveredOrderCount", 0)):
            reasons.append("covered-order-count-regressed")
    if loop == 3:
        if float(metrics.get("selectedRouteMatrixCoverage", 0.0)) < 0.95:
            reasons.append("selected-route-matrix-coverage-below-0.95")
        if float(metrics.get("matrixFallbackRate", 1.0)) > 0.05:
            reasons.append("matrix-fallback-rate-above-0.05")
        if int(metrics.get("matrixPointCount", 0)) <= 0:
            reasons.append("matrix-point-count-missing")
        if int(metrics.get("matrixPairCount", 0)) <= 0:
            reasons.append("matrix-pair-count-missing")
    if loop == 4:
        if not bool(metrics.get("pickupBeforeDropoffValid", False)):
            reasons.append("pickup-before-dropoff-invalid")
        if int(metrics.get("evaluatedSequenceCount", 0)) <= 0:
            reasons.append("evaluated-sequence-count-missing")
        if int(metrics.get("coveredOrderCount", 0)) < int(metrics.get("baselineCoveredOrderCount", 0)):
            reasons.append("covered-order-count-regressed")
        if int(metrics.get("selectedSingleOrderCount", 0)) > 0:
            reasons.append("selected-single-order-remains-in-visual-case")
    if loop == 5:
        if int(metrics.get("badRoadRouteCount", 0)) > 0:
            reasons.append("bad-road-route-selected")
        if int(metrics.get("selectedDominatedRouteCount", 0)) > 0:
            reasons.append("selected-route-dominated-within-same-driver-order-set")
        if float(metrics.get("maxNetworkDetourRatio", 0.0)) > 1.65:
            reasons.append("max-network-detour-ratio-above-1.65")
        if float(metrics.get("roadQualityScore", 0.0)) < 0.95:
            reasons.append("road-quality-score-below-0.95")
    if loop == 6:
        if int(metrics.get("coveredOrderCount", 0)) < int(metrics.get("baselineCoveredOrderCount", 0)):
            reasons.append("covered-order-count-regressed")
        if int(metrics.get("executedAssignmentCount", 0)) < int(metrics.get("baselineExecutedAssignmentCount", 0)):
            reasons.append("executed-assignment-count-regressed")
        if float(metrics.get("roadQualityScore", 0.0)) < 0.95:
            reasons.append("selected-road-quality-score-below-0.95")
        if int(metrics.get("selectedBundleSize2To5Count", 0)) < int(metrics.get("executedAssignmentCount", 0)):
            reasons.append("selected-bundle-size-outside-2-to-5")
    if loop == 7:
        if int(metrics.get("coveredOrderCount", 0)) < int(metrics.get("baselineCoveredOrderCount", 0)):
            reasons.append("covered-order-count-regressed")
        if int(metrics.get("executedAssignmentCount", 0)) < int(metrics.get("baselineExecutedAssignmentCount", 0)):
            reasons.append("executed-assignment-count-regressed")
        if int(metrics.get("badRoadRouteCount", 0)) > 0:
            reasons.append("bad-road-route-remains-after-repair")
        if float(metrics.get("planRepairLatencyMs", 0.0)) > 250.0:
            reasons.append("plan-repair-latency-above-budget")
        if not metrics.get("repairAction"):
            reasons.append("repair-action-missing")
    if loop == 8:
        if int(metrics.get("badRoadRouteCount", 0)) > 0:
            reasons.append("bad-road-route-selected")
        if int(metrics.get("syntheticFallbackRouteCount", 0)) > 0:
            reasons.append("synthetic-fallback-selected-route")
        if float(metrics.get("maxNetworkDetourRatio", 0.0)) > 1.65:
            reasons.append("max-network-detour-ratio-above-1.65")
        if not bool(metrics.get("pickupBeforeDropoffValid", False)):
            reasons.append("pickup-before-dropoff-invalid")

    if reasons:
        return "FAIL", reasons

    soft_limits = []
    if int(metrics.get("syntheticFallbackRouteCount", 0)) > 0:
        soft_limits.append("synthetic-fallback-route-observed")
    if soft_limits:
        return "PASS_WITH_LIMITS", soft_limits
    pass_reason = {
        1: "loop-01-road-route-evidence-pass",
        2: "loop-02-road-aware-generator-pass",
        3: "loop-03-osrm-table-matrix-cache-pass",
        4: "loop-04-road-native-sequence-optimizer-pass",
        5: "loop-05-road-route-quality-classifier-pass",
        6: "loop-06-ortools-road-native-objective-pass",
        7: "loop-07-road-aware-plan-repair-pass",
        8: "loop-08-visual-road-evidence-closure-pass",
    }[loop]
    return "PASS", [pass_reason]


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
