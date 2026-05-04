from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "final" / "synthetic_food_full_real_20260504_131148"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase68_system_scorecard_v1"
DEFAULT_DOC = REPO_ROOT / "docs" / "benchmark" / "system_scorecard.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_read_json(path: Path) -> Any | None:
    return read_json(path) if path.exists() else None


def percentile(values: List[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))]


def compute_scorecard(input_dir: Path) -> Dict[str, Any]:
    challenger = maybe_read_json(input_dir / "challenger_phase56f" / "phase56b_stable_promoted_summary.json") or {}
    vroom = maybe_read_json(input_dir / "vroom_comparator" / "aggregate_summary.json") or {}
    gap = maybe_read_json(input_dir / "vroom_gap_analyzer" / "phase59_vroom_gap_summary.json") or {}
    audit = maybe_read_json(input_dir / "vroom_time_window_audit" / "phase67b_vroom_tw_audit.json") or {}
    rows = challenger.get("results", [])
    runtimes = [float(row.get("runtimeMs")) for row in rows if row.get("runtimeMs") is not None]
    hard_violations = sum(int(row.get("hardViolations", 0) or 0) for row in rows)
    over_budget_count = sum(1 for row in rows if row.get("wallClockOverBudget") or row.get("stageRuntimeSummary", {}).get("overBudget"))
    stable_gate = challenger.get("phase56bGate", {}).get("checks", {})
    safety = {
        "hardViolations": hard_violations,
        "missingDuplicateRequests": 0 if hard_violations == 0 else None,
        "pickupBeforeDropoffViolations": 0 if hard_violations == 0 else None,
        "capacityViolations": 0 if hard_violations == 0 else None,
        "timeWindowViolations": 0 if hard_violations == 0 else None,
    }
    runtime = {
        "runtimeP50Ms": percentile(runtimes, 0.50),
        "runtimeP95Ms": percentile(runtimes, 0.95),
        "runtimeP99Ms": percentile(runtimes, 0.99),
        "overBudgetCount": over_budget_count,
        "timeoutCount": sum(1 for row in rows if row.get("verdict") == "FAIL" and row.get("wallClockOverBudget")),
    }
    quality = {
        "vehicleCountTotal": sum(int(row.get("vehicleCountAfter", 0) or 0) for row in rows),
        "totalDistance": sum(float(row.get("distanceAfter", 0.0) or 0.0) for row in rows),
        "objectiveTotal": sum(float(row.get("objectiveAfter", 0.0) or 0.0) for row in rows),
        "routeBalance": route_balance(rows),
    }
    stability = {
        "repeatOutcomeStable": bool(stable_gate.get("duplicateOutcomesStable", True)),
        "finalSignatureStable": bool(stable_gate.get("duplicateFinalSignaturesStable", True)),
        "cacheReplayStable": bool(challenger.get("stableIncumbentReplay", True)),
    }
    comparator = {
        "vroomCounts": vroom.get("aggregate", {}).get("classificationCounts", {}),
        "gapCounts": gap.get("classificationCounts", {}),
        "vroomHardFailCount": gap.get("vroomHardFailCount", vroom.get("aggregate", {}).get("classificationCounts", {}).get("vroom-hard-fail", 0)),
        "vroomTimeoutCount": gap.get("vroomTimeoutCount", vroom.get("aggregate", {}).get("classificationCounts", {}).get("vroom-timeout", 0)),
        "semanticMismatchCount": sum(1 for row in audit.get("rows", []) if row.get("classification") == "matrix-duration-mismatch"),
    }
    food_dispatch = {
        "estimatedDeliveryTime": None,
        "p95DeliveryTime": None,
        "p99DeliveryTime": None,
        "latenessRate": None,
        "batchingRatio": None,
        "driverLoadBalance": quality["routeBalance"],
        "cancellationRiskExposure": None,
    }
    gate = scorecard_gate(safety, runtime, stability, comparator)
    return {"schemaVersion": "phase68-system-scorecard/v1", "inputDir": str(input_dir), "gate": gate, "safety": safety, "runtime": runtime, "quality": quality, "stability": stability, "comparator": comparator, "foodDispatch": food_dispatch}


def route_balance(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = [int(row.get("vehicleCountAfter", 0) or 0) for row in rows]
    if not counts:
        return {"min": None, "max": None, "spread": None}
    return {"min": min(counts), "max": max(counts), "spread": max(counts) - min(counts)}


def scorecard_gate(safety: Dict[str, Any], runtime: Dict[str, Any], stability: Dict[str, Any], comparator: Dict[str, Any]) -> str:
    if safety.get("hardViolations", 0) != 0 or runtime.get("overBudgetCount", 0) != 0 or not stability.get("repeatOutcomeStable", True) or not stability.get("finalSignatureStable", True):
        return "FAIL"
    if comparator.get("gapCounts", {}).get("vroom-quality-win-distance", 0) or comparator.get("gapCounts", {}).get("vroom-quality-win-vehicle-count", 0):
        return "PARTIAL"
    return "PASS"


def write_outputs(scorecard: Dict[str, Any], output_dir: Path, doc_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase68_system_scorecard.json").write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    text = markdown(scorecard)
    (output_dir / "phase68_system_scorecard.md").write_text(text, encoding="utf-8")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(text, encoding="utf-8")


def markdown(scorecard: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 68 System Scorecard",
        "",
        f"Gate: **{scorecard['gate']}**",
        "",
        "## Safety",
        f"- Hard violations: {scorecard['safety']['hardViolations']}",
        f"- Time-window violations: {scorecard['safety']['timeWindowViolations']}",
        "",
        "## Runtime",
        f"- Runtime p50/p95/p99 ms: {scorecard['runtime']['runtimeP50Ms']} / {scorecard['runtime']['runtimeP95Ms']} / {scorecard['runtime']['runtimeP99Ms']}",
        f"- OverBudget count: {scorecard['runtime']['overBudgetCount']}",
        "",
        "## Comparator",
        f"- VROOM counts: `{json.dumps(scorecard['comparator']['vroomCounts'], sort_keys=True)}`",
        f"- Gap counts: `{json.dumps(scorecard['comparator']['gapCounts'], sort_keys=True)}`",
        f"- Semantic mismatch count: {scorecard['comparator']['semanticMismatchCount']}",
        "",
        "## Food Dispatch",
        "- Detailed food dispatch metrics are produced by Phase 71.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a unified system scorecard for IntelligentRouteX artifacts.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    args = parser.parse_args()
    scorecard = compute_scorecard(Path(args.input_dir))
    write_outputs(scorecard, Path(args.output_dir), Path(args.doc))
    print(f"[PHASE68 SYSTEM SCORECARD] wrote {args.output_dir}")
    return 0 if scorecard["gate"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
