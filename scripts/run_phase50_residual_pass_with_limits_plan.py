from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PHASE47_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1"
DEFAULT_PHASE46_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase46-stage-roi-v2"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase50-residual-plan-v1"

DISALLOWED_RECOMMENDATION_TERMS = ("target-k production", "benchmark-name", "comparator/reference", "unbounded stage")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_phase47(phase47_dir: Path) -> Dict[str, Dict[str, Any]]:
    rows = {}
    for path in sorted(phase47_dir.glob("*/diagnostics.json")):
        diagnostics = read_json(path)
        key = str(diagnostics.get("instance") or path.parent.name).lower()
        rows[key] = diagnostics
    return rows


def load_phase46_classifications(phase46_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = phase46_dir / "per_instance_classification.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    rows = {}
    for row in payload.get("instances", []):
        key = str(row.get("instance") or "").lower()
        if key:
            rows[key] = row
    return rows


def _trace_reasons(value: Any) -> List[str]:
    reasons = []
    if isinstance(value, dict):
        for key in ("rejectReason", "budgetedRejectReason", "skippedReason", "status"):
            reason = value.get(key)
            if isinstance(reason, str) and reason:
                reasons.append(reason)
        for child in value.values():
            reasons.extend(_trace_reasons(child))
    elif isinstance(value, list):
        for child in value:
            reasons.extend(_trace_reasons(child))
    return reasons


def _stage_summary(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    stages = diagnostics.get("stageRuntimeSummary", {}).get("stages", [])
    return {
        "skippedStages": [row.get("name") for row in stages if row.get("skipped")],
        "executedStages": [row.get("name") for row in stages if not row.get("skipped")],
        "stageRuntimes": {row.get("name"): row.get("runtimeMs") for row in stages},
        "stageSkipReasons": {row.get("name"): row.get("skippedReason") for row in stages if row.get("skipped")},
    }


def action_for_classifications(classifications: List[str], reasons: List[str]) -> Dict[str, Any]:
    class_set = set(classifications)
    reason_set = set(reasons)
    if "candidate-cap" in class_set or "candidate-cap" in reason_set:
        return {
            "blockerCategory": "candidate-cap",
            "recommendedAction": "Increase fastIncumbentNeighborhoodRepair caps in a bounded profile: slightly raise max_ortools_pairs/max_neighborhoods, keep strict stage runtime and objective-improvement-only acceptance.",
            "phase51Target": "fast-neighborhood-cap-profile",
        }
    if "route-count-too-large-skip" in class_set or "route-count-too-large-for-unbounded-stage" in reason_set:
        return {
            "blockerCategory": "route-count-too-large-skip",
            "recommendedAction": "Improve boundedLargeRouteElimination for large route-count cases: top-3 route shortlist, removed-pair cap, candidate-check cap, direct regret insertion only, strict runtime cap.",
            "phase51Target": "bounded-large-route-elimination-profile",
        }
    if "runtime-cap" in class_set or "runtime-cap" in reason_set:
        return {
            "blockerCategory": "runtime-cap",
            "recommendedAction": "Split the capped stage or add earlier stop/classification; keep global time limit unchanged.",
            "phase51Target": "stage-split-and-early-stop",
        }
    if "feasible-candidate-rejected-by-objective" in class_set or "objective-not-improved" in reason_set:
        return {
            "blockerCategory": "objective-protected",
            "recommendedAction": "Do not change NaturalPDPTWObjective; objective rejected non-improving feasible candidates correctly.",
            "phase51Target": "no-objective-change",
        }
    if "no-candidate-generated" in class_set:
        return {
            "blockerCategory": "no-candidate-generated",
            "recommendedAction": "Generate narrower neighborhoods before adding any new solver; keep candidate generation bounded.",
            "phase51Target": "narrow-neighborhood-generation",
        }
    return {
        "blockerCategory": "unknown",
        "recommendedAction": "Trace is missing or unclassified; inspect diagnostics before changing algorithms.",
        "phase51Target": "manual-trace-inspection",
    }


def plan_instance(diagnostics: Dict[str, Any], classification: Dict[str, Any] | None) -> Dict[str, Any]:
    trace = diagnostics.get("operatorTrace", {})
    reasons = _trace_reasons(trace) + _trace_reasons(diagnostics.get("stageRuntimeSummary", {}))
    classifications = list((classification or {}).get("classifications", []))
    action = action_for_classifications(classifications, reasons)
    stage_summary = _stage_summary(diagnostics)
    return {
        "instance": diagnostics.get("instance"),
        "verdict": diagnostics.get("verdict"),
        "vehicleCountBefore": diagnostics.get("vehicleCountBefore"),
        "vehicleCountAfter": diagnostics.get("vehicleCountAfter"),
        "runtimeMs": diagnostics.get("runtimeMs"),
        "overBudget": diagnostics.get("stageRuntimeSummary", {}).get("overBudget"),
        "hardViolations": diagnostics.get("hardViolations"),
        "leakageDetected": diagnostics.get("leakageDetected"),
        "phase46Classifications": classifications,
        "phase46PrimaryClassification": (classification or {}).get("primaryClassification"),
        "stageSummary": stage_summary,
        "rejectReasons": dict(Counter(reasons).most_common()),
        **action,
    }


def recommendation_is_safe(row: Dict[str, Any]) -> bool:
    text = f"{row.get('recommendedAction', '')} {row.get('phase51Target', '')}".lower()
    return not any(term in text for term in DISALLOWED_RECOMMENDATION_TERMS)


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 50 Residual PASS_WITH_LIMITS Plan",
        "",
        f"Gate verdict: **{summary['gateVerdict']}**",
        "",
        "## Residual Cases",
        "",
        "| Instance | Vehicles | Runtime ms | Blocker | Phase 51 Target |",
        "|---|---:|---:|---|---|",
    ]
    for row in summary["residualPlans"]:
        lines.append(f"| {row['instance']} | {row['vehicleCountBefore']} -> {row['vehicleCountAfter']} | {row['runtimeMs']} | {row['blockerCategory']} | {row['phase51Target']} |")
    lines.extend(["", "## Action Counts", ""])
    for action, count in summary["actionCounts"].items():
        lines.append(f"- `{action}`: {count}")
    lines.extend(
        [
            "",
            "## Phase 51 Guidance",
            "",
            "- `candidate-cap`: bounded fast-neighborhood cap profile only; keep runtime guard and objective-improvement acceptance.",
            "- `route-count-too-large-skip`: improve bounded large-route elimination; do not re-enable old unbounded route elimination.",
            "- `runtime-cap`: split stages or add early-stop classification; do not increase global time limit.",
            "- `objective-protected`: do not weaken objective or accept regression.",
            "",
            "## Do Not Do",
            "",
            "- Do not promote target-K into production-natural path.",
            "- Do not add benchmark-name rules.",
            "- Do not use comparator/reference/BKS data.",
            "- Do not re-enable unbounded stages inside the 30s budget profile.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(phase47_dir: Path, phase46_dir: Path, output_dir: Path) -> Dict[str, Any]:
    phase47_rows = load_phase47(phase47_dir)
    classifications = load_phase46_classifications(phase46_dir)
    residuals = [row for row in phase47_rows.values() if row.get("verdict") == "PASS_WITH_LIMITS"]
    plans = [plan_instance(row, classifications.get(str(row.get("instance") or "").lower())) for row in residuals]
    unknown_count = sum(1 for row in plans if row.get("blockerCategory") == "unknown")
    unsafe_count = sum(1 for row in plans if not recommendation_is_safe(row))
    action_counts = dict(Counter(row["blockerCategory"] for row in plans).most_common())
    gate = "PASS" if plans and unknown_count == 0 and unsafe_count == 0 else "FAIL"
    summary = {
        "schemaVersion": "phase50-residual-pass-with-limits-plan/v1",
        "phase47Dir": str(phase47_dir),
        "phase46Dir": str(phase46_dir),
        "residualCaseCount": len(plans),
        "unknownCount": unknown_count,
        "unsafeRecommendationCount": unsafe_count,
        "actionCounts": action_counts,
        "safetyInvariantChecks": {
            "noTargetKProductionRecommendation": unsafe_count == 0,
            "noComparatorReferenceLeakageRecommendation": unsafe_count == 0,
            "noBenchmarkNameRecommendation": unsafe_count == 0,
            "noUnboundedStageRecommendation": unsafe_count == 0,
        },
        "gateVerdict": gate,
        "residualPlans": plans,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase50_residual_plan.json", summary)
    (output_dir / "phase50_residual_plan.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan residual PASS_WITH_LIMITS optimization from Phase 47 and Phase 46 artifacts.")
    parser.add_argument("--phase47-dir", default=str(DEFAULT_PHASE47_DIR))
    parser.add_argument("--phase46-dir", default=str(DEFAULT_PHASE46_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.phase47_dir), Path(args.phase46_dir), Path(args.output_dir))
    print(f"[PHASE50 RESIDUAL PLAN] wrote {args.output_dir}")
    return 0 if summary["gateVerdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
