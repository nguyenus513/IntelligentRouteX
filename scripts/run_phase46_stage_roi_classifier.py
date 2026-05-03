from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase45-budgeted-vehicle-losses-v3"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase46-stage-roi-v1"

CLASSIFICATIONS = (
    "no-candidate-generated",
    "feasible-candidate-rejected-by-objective",
    "candidate-cap",
    "runtime-cap",
    "skipped-due-budget",
    "route-count-too-large-skip",
    "incumbent-recovered-only",
    "unknown",
)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _walk_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _stage_rows(diagnostics: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(diagnostics.get("stageRuntimeSummary", {}).get("stages", []))


def _operator_trace(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    trace = diagnostics.get("operatorTrace", {})
    return trace if isinstance(trace, dict) else {}


def _reject_reasons(value: Any) -> List[str]:
    reasons = []
    for row in _walk_dicts(value):
        for key in ("rejectReason", "budgetedRejectReason", "skippedReason", "status"):
            reason = row.get(key)
            if isinstance(reason, str) and reason:
                reasons.append(reason)
    return reasons


def _feasible_candidate_count(value: Any) -> int:
    total = 0
    for row in _walk_dicts(value):
        for key in ("feasibleCandidateCount", "feasibleSubproblemCandidates", "recombinedFeasibleCandidates"):
            count = row.get(key)
            if isinstance(count, (int, float)):
                total += int(count)
    return total


def _stage_accept_count(value: Any) -> int:
    if isinstance(value, dict):
        if value.get("acceptedByBudgetedRunner") is True or value.get("accepted") is True:
            return 1
        return 0
    if isinstance(value, list):
        return sum(1 for row in value if isinstance(row, dict) and (row.get("acceptedByBudgetedRunner") is True or row.get("accepted") is True))
    return 0


def classify_instance(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    trace = _operator_trace(diagnostics)
    reasons = _reject_reasons(trace) + _reject_reasons(diagnostics.get("stageRuntimeSummary", {}))
    feasible_candidates = _feasible_candidate_count(trace)
    accepted_stages = [name for name, value in trace.items() if _stage_accept_count(value) > 0]
    skipped_stages = [row.get("name") for row in _stage_rows(diagnostics) if row.get("skipped")]
    classes: List[str] = []

    if diagnostics.get("vehicleCountBefore") == 0 and diagnostics.get("hardViolations", 0) == 0 and diagnostics.get("objectiveImproved"):
        classes.append("incumbent-recovered-only")
    if "route-count-too-large-for-unbounded-stage" in reasons:
        classes.append("route-count-too-large-skip")
    if "candidate-cap" in reasons:
        classes.append("candidate-cap")
    if "runtime-cap" in reasons or diagnostics.get("stageRuntimeSummary", {}).get("overBudget"):
        classes.append("runtime-cap")
    if "budget-too-low" in reasons:
        classes.append("skipped-due-budget")
    if feasible_candidates > 0 and "objective-not-improved" in reasons and not diagnostics.get("objectiveImproved"):
        classes.append("feasible-candidate-rejected-by-objective")
    if feasible_candidates == 0 and not accepted_stages and not diagnostics.get("objectiveImproved"):
        classes.append("no-candidate-generated")
    if not classes:
        classes.append("unknown")

    return {
        "instance": diagnostics.get("instance"),
        "verdict": diagnostics.get("verdict"),
        "runtimeMs": diagnostics.get("runtimeMs"),
        "overBudget": diagnostics.get("stageRuntimeSummary", {}).get("overBudget"),
        "vehicleCountBefore": diagnostics.get("vehicleCountBefore"),
        "vehicleCountAfter": diagnostics.get("vehicleCountAfter"),
        "objectiveBefore": diagnostics.get("objectiveBefore"),
        "objectiveAfter": diagnostics.get("objectiveAfter"),
        "objectiveImproved": diagnostics.get("objectiveImproved"),
        "hardViolations": diagnostics.get("hardViolations"),
        "leakageDetected": diagnostics.get("leakageDetected"),
        "classifications": classes,
        "primaryClassification": classes[0],
        "acceptedStages": accepted_stages,
        "skippedStages": skipped_stages,
        "feasibleCandidateCount": feasible_candidates,
        "rejectReasons": dict(Counter(reasons).most_common()),
    }


def stage_roi(diagnostics_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    runtime_by_stage: Dict[str, List[int]] = defaultdict(list)
    skip_counts: Counter[str] = Counter()
    accepted_counts: Counter[str] = Counter()
    feasible_counts: Counter[str] = Counter()
    objective_improvement_counts: Counter[str] = Counter()
    reject_reasons: Dict[str, Counter[str]] = defaultdict(Counter)

    for diagnostics in diagnostics_rows:
        trace = _operator_trace(diagnostics)
        for row in _stage_rows(diagnostics):
            name = str(row.get("name"))
            runtime_by_stage[name].append(int(row.get("runtimeMs", 0) or 0))
            if row.get("skipped"):
                skip_counts[name] += 1
                reason = row.get("skippedReason")
                if reason:
                    reject_reasons[name][str(reason)] += 1
        for stage_name, value in trace.items():
            accepted = _stage_accept_count(value)
            feasible = _feasible_candidate_count(value)
            accepted_counts[stage_name] += accepted
            feasible_counts[stage_name] += feasible
            if accepted and diagnostics.get("objectiveImproved"):
                objective_improvement_counts[stage_name] += 1
            reject_reasons[stage_name].update(_reject_reasons(value))

    stage_names = sorted(set(runtime_by_stage) | set(accepted_counts) | set(feasible_counts) | set(skip_counts))
    return {
        stage: {
            "acceptedCount": accepted_counts[stage],
            "generatedFeasibleCandidateCount": feasible_counts[stage],
            "objectiveImprovementCount": objective_improvement_counts[stage],
            "averageRuntimeMs": round(sum(runtime_by_stage[stage]) / len(runtime_by_stage[stage]), 2) if runtime_by_stage[stage] else 0.0,
            "skipCount": skip_counts[stage],
            "topRejectReasons": dict(reject_reasons[stage].most_common(8)),
        }
        for stage in stage_names
    }


def load_diagnostics(input_dir: Path) -> List[Dict[str, Any]]:
    rows = []
    for diagnostics_path in sorted(input_dir.glob("*/diagnostics.json")):
        rows.append(read_json(diagnostics_path))
    return rows


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 46 Stage ROI Classifier",
        "",
        "## Per Instance",
        "",
        "| Instance | Verdict | Vehicles | Runtime ms | Primary Class | Classes |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in summary["perInstance"]:
        vehicles = f"{row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')}"
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {vehicles} | {row.get('runtimeMs')} | {row.get('primaryClassification')} | {', '.join(row.get('classifications', []))} |")
    lines.extend(["", "## Stage ROI", "", "| Stage | Accepted | Feasible Candidates | Obj Improvements | Avg Runtime ms | Skips | Top Reasons |", "|---|---:|---:|---:|---:|---:|---|"])
    for stage, row in summary["stageRoi"].items():
        reasons = ", ".join(f"{key}:{value}" for key, value in row.get("topRejectReasons", {}).items())
        lines.append(f"| {stage} | {row.get('acceptedCount')} | {row.get('generatedFeasibleCandidateCount')} | {row.get('objectiveImprovementCount')} | {row.get('averageRuntimeMs')} | {row.get('skipCount')} | {reasons} |")
    return "\n".join(lines) + "\n"


def run(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    diagnostics_rows = load_diagnostics(input_dir)
    per_instance = [classify_instance(row) for row in diagnostics_rows]
    unknown_count = sum(1 for row in per_instance if row.get("primaryClassification") == "unknown")
    summary = {
        "schemaVersion": "phase46-stage-roi-summary/v1",
        "inputDir": str(input_dir),
        "instanceCount": len(per_instance),
        "classificationCounts": dict(Counter(row["primaryClassification"] for row in per_instance)),
        "unknownCount": unknown_count,
        "verdict": "PASS" if len(per_instance) == 8 and unknown_count == 0 else "PASS_WITH_LIMITS" if per_instance else "FAIL",
        "perInstance": per_instance,
        "stageRoi": stage_roi(diagnostics_rows),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase46_stage_roi_summary.json", summary)
    write_json(output_dir / "per_instance_classification.json", {"instances": per_instance})
    (output_dir / "phase46_stage_roi_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify Phase 45 stage ROI and residual blockers.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.input_dir), Path(args.output_dir))
    print(f"[PHASE46 STAGE ROI] wrote {args.output_dir}")
    return 0 if summary.get("verdict") in {"PASS", "PASS_WITH_LIMITS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
