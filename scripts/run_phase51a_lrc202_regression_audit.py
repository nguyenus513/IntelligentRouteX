from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PHASE47 = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1" / "lrc202" / "diagnostics.json"
DEFAULT_PHASE51 = REPO_ROOT / "artifacts" / "benchmark" / "community-phase51-fast-neighborhood-profile-v2" / "lrc202" / "diagnostics.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase51a-lrc202-regression-audit-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def stage_map(diagnostics: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("name")): row for row in diagnostics.get("stageRuntimeSummary", {}).get("stages", [])}


def trace_map(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    trace = diagnostics.get("operatorTrace", {})
    return trace if isinstance(trace, dict) else {}


def _accepted(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("acceptedByBudgetedRunner") or value.get("accepted"))
    return False


def _reject_reasons(value: Any) -> List[str]:
    reasons = []
    if isinstance(value, dict):
        for key in ("rejectReason", "budgetedRejectReason", "skippedReason", "status"):
            reason = value.get(key)
            if isinstance(reason, str) and reason:
                reasons.append(reason)
        for child in value.values():
            reasons.extend(_reject_reasons(child))
    elif isinstance(value, list):
        for child in value:
            reasons.extend(_reject_reasons(child))
    return reasons


def _candidate_counts(value: Any) -> Dict[str, int]:
    keys = ("candidateCount", "feasibleCandidateCount", "feasibleSubproblemCandidates", "recombinedFeasibleCandidates", "neighborhoodsGenerated", "neighborhoodsSkippedByAffectedCap")
    counts = {key: 0 for key in keys}
    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key in keys:
                if isinstance(item.get(key), (int, float)):
                    counts[key] += int(item[key])
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return counts


def accepted_stages(diagnostics: Dict[str, Any]) -> List[str]:
    return [name for name, value in trace_map(diagnostics).items() if _accepted(value)]


def skipped_stages(diagnostics: Dict[str, Any]) -> List[str]:
    return [name for name, row in stage_map(diagnostics).items() if row.get("skipped")]


def first_divergence(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_stages = stage_map(left)
    right_stages = stage_map(right)
    left_trace = trace_map(left)
    right_trace = trace_map(right)
    stage_order = [str(row.get("name")) for row in left.get("stageRuntimeSummary", {}).get("stages", [])]
    for stage in stage_order:
        if stage not in right_stages:
            return {"type": "missing-stage", "stage": stage, "details": "stage-present-in-phase47-missing-in-phase51"}
        left_row = left_stages[stage]
        right_row = right_stages[stage]
        if bool(left_row.get("skipped")) != bool(right_row.get("skipped")):
            return {"type": "different-skip", "stage": stage, "phase47": left_row, "phase51": right_row}
        if left_row.get("skippedReason") != right_row.get("skippedReason"):
            return {"type": "different-skip-reason", "stage": stage, "phase47": left_row, "phase51": right_row}
        left_runtime = int(left_row.get("runtimeMs", 0) or 0)
        right_runtime = int(right_row.get("runtimeMs", 0) or 0)
        if left_runtime > 0 and right_runtime > left_runtime * 4 and right_runtime - left_runtime > 1_000:
            return {"type": "budget-starvation", "stage": stage, "phase47": left_row, "phase51": right_row, "details": "phase51-stage-runtime-grew-enough-to-starve-later-stages"}
        trace_stage = _trace_name_for_stage(stage)
        if trace_stage in left_trace or trace_stage in right_trace:
            left_value = left_trace.get(trace_stage, {})
            right_value = right_trace.get(trace_stage, {})
            if _accepted(left_value) != _accepted(right_value):
                return {"type": "accepted-vs-rejected", "stage": stage, "traceStage": trace_stage, "phase47Accepted": _accepted(left_value), "phase51Accepted": _accepted(right_value)}
            if _candidate_counts(left_value) != _candidate_counts(right_value):
                return {"type": "different-candidate-counts", "stage": stage, "traceStage": trace_stage, "phase47": _candidate_counts(left_value), "phase51": _candidate_counts(right_value)}
    for stage in right_stages:
        if stage not in left_stages:
            return {"type": "missing-stage", "stage": stage, "details": "stage-present-in-phase51-missing-in-phase47"}
    return {"type": "none", "stage": None, "details": "no-divergence-detected"}


def _trace_name_for_stage(stage: str) -> str:
    mapping = {
        "natural-route-elimination": "naturalRouteElimination",
        "bounded-large-route-elimination": "boundedLargeRouteElimination",
        "internal-solver-generator": "internalSolverGenerator",
        "fast-incumbent-neighborhood-repair": "fastIncumbentNeighborhoodRepair",
        "route-pool-sp": "routePoolImprovement",
    }
    return mapping.get(stage, stage)


def compact(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schemaVersion": diagnostics.get("schemaVersion"),
        "instance": diagnostics.get("instance"),
        "verdict": diagnostics.get("verdict"),
        "vehicleCountBefore": diagnostics.get("vehicleCountBefore"),
        "vehicleCountAfter": diagnostics.get("vehicleCountAfter"),
        "objectiveBefore": diagnostics.get("objectiveBefore"),
        "objectiveAfter": diagnostics.get("objectiveAfter"),
        "runtimeMs": diagnostics.get("runtimeMs"),
        "acceptedStages": accepted_stages(diagnostics),
        "skippedStages": skipped_stages(diagnostics),
        "rejectReasons": _reject_reasons(diagnostics.get("operatorTrace", {})),
        "stageRuntimeSummary": diagnostics.get("stageRuntimeSummary"),
    }


def markdown(summary: Dict[str, Any]) -> str:
    divergence = summary["firstDivergence"]
    lines = [
        "# Phase 51A LRC202 Regression Audit",
        "",
        f"Gate verdict: **{summary['gateVerdict']}**",
        "",
        "## First Divergence",
        "",
        f"- Type: `{divergence.get('type')}`",
        f"- Stage: `{divergence.get('stage')}`",
        f"- Details: {divergence.get('details', '')}",
        "",
        "## Outcome Comparison",
        "",
        "| Runner | Vehicles | Objective | Runtime ms | Accepted Stages | Skipped Stages |",
        "|---|---:|---:|---:|---|---|",
    ]
    for key in ("phase47", "phase51"):
        row = summary[key]
        lines.append(f"| {key} | {row['vehicleCountBefore']} -> {row['vehicleCountAfter']} | {row['objectiveBefore']} -> {row['objectiveAfter']} | {row['runtimeMs']} | {', '.join(row['acceptedStages'])} | {', '.join(row['skippedStages'])} |")
    lines.extend(["", "## Interpretation", ""])
    if divergence.get("type") == "budget-starvation":
        lines.append("Phase 51 spends substantially more time in an earlier stage, starving later stages. For LRC202, inspect whether route-pool/SP lost budget after natural-route-elimination runtime growth.")
    elif divergence.get("type") == "accepted-vs-rejected":
        lines.append("A stage acceptance differs between Phase 47 and Phase 51. Keep the Phase 47 path unless the new candidate is safer and objective-improving.")
    elif divergence.get("type") == "different-skip":
        lines.append("A stage skip differs between Phase 47 and Phase 51. Check adaptive profile budget thresholds before changing algorithms.")
    else:
        lines.append("Divergence was found, but needs manual inspection before Phase 51B changes.")
    return "\n".join(lines) + "\n"


def run(phase47_path: Path, phase51_path: Path, output_dir: Path) -> Dict[str, Any]:
    phase47 = read_json(phase47_path)
    phase51 = read_json(phase51_path)
    divergence = first_divergence(phase47, phase51)
    gate = "PASS" if divergence.get("type") != "none" else "FAIL"
    summary = {
        "schemaVersion": "phase51a-lrc202-regression-audit/v1",
        "phase47Path": str(phase47_path),
        "phase51Path": str(phase51_path),
        "gateVerdict": gate,
        "firstDivergence": divergence,
        "phase47": compact(phase47),
        "phase51": compact(phase51),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase51a_lrc202_regression_audit.json", summary)
    (output_dir / "phase51a_lrc202_regression_audit.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit LRC202 regression between Phase 47 and Phase 51 diagnostics.")
    parser.add_argument("--phase47", default=str(DEFAULT_PHASE47))
    parser.add_argument("--phase51", default=str(DEFAULT_PHASE51))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.phase47), Path(args.phase51), Path(args.output_dir))
    print(f"[PHASE51A LRC202 REGRESSION AUDIT] wrote {args.output_dir}")
    return 0 if summary["gateVerdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
