from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase90c_lilim_probe_v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase91_lilim_search_strength_audit_v1"


def classify_operator(row: Dict[str, Any]) -> str:
    generated = int(row.get("generatedCandidates", 0) or 0)
    final_produced = int(row.get("finalCandidatesProduced", 0) or 0)
    final_checked = int(row.get("finalCandidatesChecked", row.get("candidateChecks", 0)) or 0)
    accepted = int(row.get("acceptedCandidates", row.get("acceptedCount", 0)) or 0)
    objective_improving = int(row.get("objectiveImprovingCandidates", row.get("finalObjectiveImprovingCandidates", 0)) or 0)
    checker_feasible = int(row.get("checkerFeasibleCandidates", row.get("feasibleCandidateCount", 0)) or 0)
    intermediate = int(row.get("intermediateFeasibleStates", 0) or 0) + int(row.get("worseIntermediateAccepted", row.get("intermediateWorseAcceptedForSearch", 0)) or 0) + int(row.get("improvingIntermediateAccepted", 0) or 0)
    candidate_checks = int(row.get("candidateChecks", 0) or 0)
    fail_reasons = row.get("failReasons") or {}
    repair_fail_reasons = row.get("repairFailReasons") or {}
    early_stop = str(row.get("earlyStopReason") or "")
    safe_return = bool(row.get("safeReturn", False))
    if accepted > 0 or objective_improving > 0:
        return "productive"
    if early_stop == "deadline" or safe_return or int(fail_reasons.get("runtime-cap", 0) or 0) > 0:
        return "deadline-cap"
    if int(fail_reasons.get("candidate-cap", 0) or 0) > 0:
        return "candidate-cap"
    if row.get("noGenerationReason") in {"no-opportunity-detected", "activation-filtered", "no-route-pair-found", "no-feasible-move", "deadline-before-generation", "candidate-cap-before-generation"}:
        return "no-generation"
    if generated == 0 and final_produced == 0 and candidate_checks == 0:
        if repair_fail_reasons and sum(int(value or 0) for value in repair_fail_reasons.values()) > 0:
            return "repair-failure"
        return "no-generation"
    if final_produced == 0 and intermediate > 0:
        return "intermediate-only"
    if final_produced > 0 and final_checked == 0:
        return "candidate-cap"
    if final_checked > 0 and checker_feasible == 0:
        return "objective-protected" if int(row.get("prunedNoQualityPotential", 0) or 0) > 0 else "repair-failure"
    if (final_produced > 0 or generated > 0 or final_checked > 0) and objective_improving == 0:
        return "final-candidate-not-improving"
    if repair_fail_reasons and sum(int(value or 0) for value in repair_fail_reasons.values()) > 0:
        return "repair-failure"
    return "unknown"


def load_phase90_rows(input_dir: Path) -> List[Dict[str, Any]]:
    summary_path = input_dir / "per_suite" / "li_lim_8case" / "phase84_summary.json"
    if not summary_path.exists():
        summary_path = input_dir / "phase84_summary.json"
    if not summary_path.exists():
        return []
    return json.loads(summary_path.read_text(encoding="utf-8")).get("rows", [])


def run_phase90_probe(output_dir: Path, time_limit: str, max_instances: int) -> List[Dict[str, Any]]:
    args = Namespace(suite="li-lim-8case", vroom_url="", time_limit=time_limit, max_instances_per_suite=max_instances, output_dir=str(output_dir / "phase90_probe"))
    summary = run_phase84(args)
    return summary.get("rows", [])


def operator_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for row in rows:
        instance = row.get("instance")
        for budget in row.get("budgetTelemetry", []):
            final_candidate_checks = int(budget.get("finalCandidatesChecked", budget.get("candidateChecks", 0)) or 0)
            flattened.append(
                {
                    "instance": instance,
                    "operator": budget.get("operator"),
                    "attempts": 1 if int(budget.get("generatedCandidates", 0) or 0) or int(budget.get("candidateChecks", 0) or 0) or int(budget.get("alnsIterations", 0) or 0) else 0,
                    "generatedCandidates": int(budget.get("generatedCandidates", 0) or 0),
                    "checkerFeasibleCandidates": int(budget.get("checkerFeasibleCandidates", budget.get("feasibleCandidateCount", 0)) or 0),
                    "objectiveImprovingCandidates": int(budget.get("objectiveImprovingCandidates", budget.get("finalObjectiveImprovingCandidates", 0)) or 0),
                    "acceptedCandidates": int(budget.get("acceptedCount", 0) or 0),
                    "finalCandidatesProduced": int(budget.get("finalCandidatesProduced", 0) or 0),
                    "finalCandidatesChecked": final_candidate_checks,
                    "finalObjectiveImprovingCandidates": int(budget.get("finalObjectiveImprovingCandidates", 0) or 0),
                    "intermediateFeasibleStates": int(budget.get("intermediateFeasibleStates", 0) or 0),
                    "worseIntermediateAccepted": int(budget.get("worseIntermediateAccepted", budget.get("intermediateWorseAcceptedForSearch", 0)) or 0),
                    "improvingIntermediateAccepted": int(budget.get("improvingIntermediateAccepted", 0) or 0),
                    "ejectionAttempts": int(budget.get("ejectionAttempts", 0) or 0),
                    "ejectionSuccesses": int(budget.get("ejectionSuccesses", 0) or 0),
                    "earlyStopReason": budget.get("earlyStopReason"),
                    "safeReturn": bool(budget.get("safeReturn", False)),
                    "candidateChecks": int(budget.get("candidateChecks", 0) or 0),
                    "bestDistanceDelta": budget.get("bestDistanceDelta", budget.get("bestActualDistanceDelta")),
                    "bestVehicleDelta": budget.get("bestVehicleDelta"),
                    "noGenerationReason": budget.get("noGenerationReason"),
                    "activationPolicy": budget.get("activationPolicy"),
                    "activationReasons": budget.get("activationReasons"),
                    "bridgedFinalCandidates": int(budget.get("bridgedFinalCandidates", 0) or 0),
                    "failReasons": budget.get("failReasons") or {},
                    "repairFailReasons": budget.get("repairFailReasons") or {},
                    "classification": classify_operator(budget),
                }
            )
    return flattened


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    by_operator: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        classification = str(row.get("classification", "unknown"))
        counts[classification] = counts.get(classification, 0) + 1
        operator = str(row.get("operator"))
        target = by_operator.setdefault(operator, {"operator": operator, "classifications": {}, "generatedCandidates": 0, "finalCandidatesProduced": 0, "acceptedCandidates": 0, "deadlineCaps": 0})
        target["classifications"][classification] = target["classifications"].get(classification, 0) + 1
        target["generatedCandidates"] += int(row.get("generatedCandidates", 0) or 0)
        target["finalCandidatesProduced"] += int(row.get("finalCandidatesProduced", 0) or 0)
        target["acceptedCandidates"] += int(row.get("acceptedCandidates", 0) or 0)
        target["deadlineCaps"] += 1 if classification == "deadline-cap" else 0
    return {"classificationCounts": counts, "byOperator": sorted(by_operator.values(), key=lambda item: item["operator"])}


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 91 Li-Lim Search Strength Audit", "", f"- Gate: **{summary.get('gate')}**", f"- Unknown classifications: `{summary.get('unknownCount')}`", f"- Operator rows: `{summary.get('operatorRowCount')}`", "", "| Classification | Count |", "|---|---:|"]
    for key, value in sorted(summary.get("classificationCounts", {}).items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "Phase 91 is diagnostic only; it does not add target-K forcing, benchmark-name rules, or reference-solution leakage.", ""])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = Path(args.input_dir)
    rows = load_phase90_rows(input_dir)
    source = "artifact"
    if not rows or args.rerun:
        rows = run_phase90_probe(output_dir, args.time_limit, args.max_instances_per_suite)
        source = "rerun"
    flattened = operator_rows(rows)
    agg = aggregate(flattened)
    unknown_count = agg["classificationCounts"].get("unknown", 0)
    gate = "PASS" if flattened and unknown_count == 0 else "FAIL"
    summary = {"schemaVersion": "phase91-lilim-search-strength-audit/v1", "gate": gate, "source": source, "operatorRowCount": len(flattened), "unknownCount": unknown_count, **agg}
    write_json(output_dir / "phase91_lilim_search_strength_summary.json", summary)
    write_json(output_dir / "operator_roi_matrix.json", {"rows": flattened})
    (output_dir / "phase91_lilim_search_strength_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 91 Li-Lim bounded search-strength audit.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=1)
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE91 LILIM SEARCH STRENGTH AUDIT] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
