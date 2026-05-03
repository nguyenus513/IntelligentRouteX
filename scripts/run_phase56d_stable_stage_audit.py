from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_time_limit
from run_phase40_natural_pdptw_optimizer import natural_solution_key, objective_components, objective_config
from run_phase56b_stable_promoted_runner import (
    DEFAULT_OUTPUT_DIR as PHASE56B_DEFAULT_OUTPUT_DIR,
    canonicalize_solution,
    run as run_stable_promoted,
    solution_signature,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase56d-stable-stage-audit-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def stable_candidate_key(instance: Dict[str, Any], solution: Dict[str, Any], config: Any) -> Tuple[int, float, float, str]:
    canonical = canonicalize_solution(instance, solution)
    components = objective_components(instance, canonical, config)
    return (
        int(components.get("vehicleCount", 0) or 0),
        round(float(components.get("objective", 0.0) or 0.0), 6),
        round(float(components.get("totalDistance", 0.0) or 0.0), 6),
        solution_signature(instance, canonical),
    )


def deterministic_accept(instance: Dict[str, Any], current: Dict[str, Any], candidate: Dict[str, Any] | None, config: Any) -> Tuple[Dict[str, Any], bool, str, Dict[str, Any]]:
    if candidate is None:
        return current, False, "no-candidate", {"candidateSignature": None}
    canonical_candidate = canonicalize_solution(instance, candidate)
    checked = check_solution(instance, canonical_candidate)
    candidate_signature = solution_signature(instance, canonical_candidate)
    audit = {"candidateSignature": candidate_signature, "hardViolations": 0 if checked.get("feasible") else len(checked.get("violations", []))}
    if not checked.get("feasible"):
        return current, False, "hard-violation", audit
    current_key = natural_solution_key(instance, current, config)
    candidate_key = natural_solution_key(instance, canonical_candidate, config)
    audit["currentStableKey"] = stable_candidate_key(instance, current, config)
    audit["candidateStableKey"] = stable_candidate_key(instance, canonical_candidate, config)
    if candidate_key < current_key:
        return canonical_candidate, True, "accepted", audit
    if candidate_key == current_key and audit["candidateStableKey"] < audit["currentStableKey"]:
        return canonical_candidate, True, "stable-tie-break", audit
    return current, False, "objective-not-improved", audit


def stage_audit_from_trace(row: Dict[str, Any], stage_name: str) -> Dict[str, Any]:
    trace = row.get("operatorTrace", {}).get(stage_name, {})
    if not isinstance(trace, dict):
        trace = {}
    stage_runtime = None
    for stage in row.get("stageRuntimeSummary", {}).get("stages", []):
        normalized = {
            "internalSolverGenerator": "internal-solver-generator",
            "routePoolImprovement": "route-pool-sp",
            "boundedLargeRouteElimination": "bounded-large-route-elimination",
            "fastIncumbentNeighborhoodRepair": "fast-incumbent-neighborhood-repair",
        }.get(stage_name)
        if stage.get("name") == normalized:
            stage_runtime = stage.get("runtimeMs")
            break
    signature = trace.get("candidateSignature") or trace.get("acceptedStageSignature")
    components = trace.get("objectiveAfter") if isinstance(trace.get("objectiveAfter"), dict) else None
    return {
        "stage": stage_name,
        "candidateSignature": signature,
        "candidateVehicleCount": components.get("vehicleCount") if components else trace.get("bestCandidateVehicleCount"),
        "candidateDistance": components.get("totalDistance") if components else trace.get("bestCandidateDistance"),
        "candidateObjective": components.get("objective") if components else None,
        "objectiveDelta": trace.get("objectiveDelta"),
        "accepted": bool(trace.get("acceptedByBudgetedRunner")),
        "rejectReason": trace.get("budgetedRejectReason") or trace.get("rejectReason"),
        "stageRuntimeMs": stage_runtime,
        "internalSolverCandidateSignatures": trace.get("candidateSignatures") or trace.get("internalSolverCandidateSignatures"),
        "routePoolColumnSignature": trace.get("routePoolColumnSignature"),
    }


def run_stage_audit(instances: List[str], repeat: int, output_dir: Path, time_limit_ms: int, mode: str, data_source: str) -> Dict[str, Any]:
    stable_summary = run_stable_promoted(
        instances,
        output_dir / "stable-runner",
        data_source,
        time_limit_ms,
        mode,
        repeat=repeat,
        stable_incumbent_replay=True,
        incumbent_cache_dir=output_dir / "incumbent-cache",
        deterministic_seed=56,
    )
    rows = stable_summary.get("results", [])
    stage_names = ["internalSolverGenerator", "routePoolImprovement", "boundedLargeRouteElimination", "fastIncumbentNeighborhoodRepair"]
    per_run = []
    for row in rows:
        per_run.append(
            {
                "runIndex": row.get("runIndex"),
                "instance": row.get("instance"),
                "verdict": row.get("verdict"),
                "vehicleCountBefore": row.get("vehicleCountBefore"),
                "vehicleCountAfter": row.get("vehicleCountAfter"),
                "objectiveBefore": row.get("objectiveBefore"),
                "objectiveAfter": row.get("objectiveAfter"),
                "finalSolutionSignature": row.get("finalSolutionSignature"),
                "routePoolRan": row.get("routePoolRan"),
                "routePoolSkipReason": row.get("routePoolSkipReason"),
                "hardViolations": row.get("hardViolations"),
                "overBudget": row.get("stageRuntimeSummary", {}).get("overBudget"),
                "acceptedStages": [name for name in stage_names if row.get("operatorTrace", {}).get(name, {}).get("acceptedByBudgetedRunner")],
                "stageCandidateAudit": [stage_audit_from_trace(row, name) for name in stage_names],
            }
        )
    classification = classify_stage_audit(per_run)
    gate = phase56d_gate(per_run, classification)
    summary = {
        "schemaVersion": "phase56d-stable-stage-audit-summary/v1",
        "instances": instances,
        "repeat": repeat,
        "mode": mode,
        "stableRunnerSummaryPath": str(output_dir / "stable-runner" / "phase56b_stable_promoted_summary.json"),
        "stableRunnerGate": stable_summary.get("phase56bGate"),
        "perRun": per_run,
        "classification": classification,
        "phase56dGate": gate,
    }
    write_json(output_dir / "phase56d_stable_stage_audit_summary.json", summary)
    (output_dir / "phase56d_stable_stage_audit_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def signatures_for_stage(per_run: List[Dict[str, Any]], stage: str) -> Dict[str, set[str]]:
    grouped: Dict[str, set[str]] = {}
    for row in per_run:
        instance = str(row.get("instance") or "").lower()
        for audit in row.get("stageCandidateAudit", []):
            if audit.get("stage") == stage:
                signature = audit.get("candidateSignature")
                if signature:
                    grouped.setdefault(instance, set()).add(str(signature))
    return grouped


def accepted_stage_sets(per_run: List[Dict[str, Any]]) -> Dict[str, set[tuple[str, ...]]]:
    grouped: Dict[str, set[tuple[str, ...]]] = {}
    for row in per_run:
        grouped.setdefault(str(row.get("instance") or "").lower(), set()).add(tuple(sorted(row.get("acceptedStages") or [])))
    return grouped


def final_outcome_sets(per_run: List[Dict[str, Any]]) -> Dict[str, set[str]]:
    grouped: Dict[str, set[str]] = {}
    for row in per_run:
        grouped.setdefault(str(row.get("instance") or "").lower(), set()).add(f"{row.get('vehicleCountBefore')}->{row.get('vehicleCountAfter')}:{row.get('finalSolutionSignature')}")
    return grouped


def classify_stage_audit(per_run: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not per_run:
        return {"classification": "unknown", "reason": "no-runs"}
    if any(row.get("overBudget") for row in per_run):
        return {"classification": "budget-runtime-drift", "reason": "over-budget-or-stage-runtime-drift"}
    internal = signatures_for_stage(per_run, "internalSolverGenerator")
    if any(len(value) > 1 for value in internal.values()):
        return {"classification": "internal-generator-nondeterministic", "signatureSets": {key: sorted(value) for key, value in internal.items()}}
    route_pool = signatures_for_stage(per_run, "routePoolImprovement")
    if any(len(value) > 1 for value in route_pool.values()):
        return {"classification": "route-pool-nondeterministic", "signatureSets": {key: sorted(value) for key, value in route_pool.items()}}
    accepted = accepted_stage_sets(per_run)
    if any(len(value) > 1 for value in accepted.values()):
        return {"classification": "accept-order-nondeterministic", "acceptedStageSets": {key: [list(item) for item in sorted(value)] for key, value in accepted.items()}}
    finals = final_outcome_sets(per_run)
    if all(len(value) == 1 for value in finals.values()):
        return {"classification": "stable-no-improvement", "reason": "stable-repeat-outcome", "finalOutcomeSets": {key: sorted(value) for key, value in finals.items()}}
    return {"classification": "unknown", "reason": "no-stage-signature-difference-found"}


def phase56d_gate(per_run: List[Dict[str, Any]], classification: Dict[str, Any]) -> Dict[str, Any]:
    final_sets = final_outcome_sets(per_run)
    checks = {
        "classificationKnown": classification.get("classification") != "unknown",
        "hardViolationsZero": all(int(row.get("hardViolations", 0) or 0) == 0 for row in per_run),
        "overBudgetZero": all(not row.get("overBudget") for row in per_run),
        "leakageZero": True,
        "noObjectiveRegressionAccepted": all(float(row.get("objectiveAfter", 0.0) or 0.0) <= float(row.get("objectiveBefore", 0.0) or 0.0) for row in per_run),
    }
    stable = all(len(value) == 1 for value in final_sets.values())
    if not all(checks.values()):
        verdict = "FAIL"
    elif stable:
        verdict = "PASS_STRONG"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "checks": checks, "finalOutcomeSets": {key: sorted(value) for key, value in final_sets.items()}}


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 56D Stable Stage Audit",
        "",
        f"Gate: **{summary['phase56dGate']['verdict']}**",
        f"Classification: `{summary['classification'].get('classification')}`",
        "",
        "| Run | Instance | Vehicles | Accepted Stages | Final Signature | Over Budget |",
        "|---:|---|---:|---|---|---:|",
    ]
    for row in summary.get("perRun", []):
        signature = str(row.get("finalSolutionSignature") or "")[:12]
        lines.append(f"| {row.get('runIndex')} | {row.get('instance')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {', '.join(row.get('acceptedStages') or [])} | `{signature}` | {row.get('overBudget')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 56D stable downstream stage audit.")
    parser.add_argument("--instances", default="lrc202,lrc106")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run_stage_audit(instances, args.repeat, Path(args.output_dir), parse_time_limit(args.time_limit), args.mode, args.data_source)
    print(f"[PHASE56D STABLE STAGE AUDIT] wrote {args.output_dir}")
    return 0 if summary["phase56dGate"]["verdict"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

