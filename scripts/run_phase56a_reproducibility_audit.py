from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from run_phase47_adaptive_budget_natural_optimizer import parse_time_limit, run as run_phase47


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase56a-reproducibility-audit-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_baseline(baseline_dir: Path, instance: str) -> Dict[str, Any]:
    direct = baseline_dir / instance / "diagnostics.json"
    if direct.exists():
        return read_json(direct)
    lower = instance.lower()
    for path in baseline_dir.glob("*/diagnostics.json"):
        row = read_json(path)
        if str(row.get("instance") or path.parent.name).lower() == lower:
            return row
    return {}


def solution_signature(solution_path: Path) -> str | None:
    if not solution_path.exists():
        return None
    payload = read_json(solution_path)
    canonical = json.dumps(payload.get("routes", payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stage_rows(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(row.get("stageRuntimeSummary", {}).get("stages", []))


def accepted_stages(row: Dict[str, Any]) -> List[str]:
    accepted: List[str] = []
    for name, trace in row.get("operatorTrace", {}).items():
        if isinstance(trace, dict) and (trace.get("acceptedByBudgetedRunner") or trace.get("accepted")):
            accepted.append(name)
    return accepted


def skipped_stages(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"name": stage.get("name"), "reason": stage.get("skippedReason")}
        for stage in stage_rows(row)
        if stage.get("skipped")
    ]


def compact_stage_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "overBudget": bool(row.get("stageRuntimeSummary", {}).get("overBudget")),
        "totalRuntimeMs": row.get("stageRuntimeSummary", {}).get("totalRuntimeMs"),
        "stages": [
            {
                "name": stage.get("name"),
                "budgetMs": stage.get("budgetMs"),
                "runtimeMs": stage.get("runtimeMs"),
                "remainingMsAfter": stage.get("remainingMsAfter"),
                "skipped": stage.get("skipped"),
                "skippedReason": stage.get("skippedReason"),
            }
            for stage in stage_rows(row)
        ],
    }


def compact_run(row: Dict[str, Any], signature: str | None, index: int) -> Dict[str, Any]:
    return {
        "runIndex": index,
        "instance": row.get("instance"),
        "verdict": row.get("verdict"),
        "vehicleCountBefore": row.get("vehicleCountBefore"),
        "vehicleCountAfter": row.get("vehicleCountAfter"),
        "objectiveBefore": row.get("objectiveBefore"),
        "objectiveAfter": row.get("objectiveAfter"),
        "objectiveImproved": row.get("objectiveImproved"),
        "acceptedStages": accepted_stages(row),
        "skippedStages": skipped_stages(row),
        "stageRuntimeSummary": compact_stage_summary(row),
        "runtimeMs": row.get("runtimeMs"),
        "solutionSignature": signature,
        "seedInfo": row.get("seedInfo") or row.get("deterministicSeed") or None,
    }


def vehicle_outcome(row: Dict[str, Any]) -> str:
    return f"{row.get('vehicleCountBefore')}->{row.get('vehicleCountAfter')}"


def outcome_distribution(runs: List[Dict[str, Any]]) -> Dict[str, int]:
    distribution: Dict[str, int] = {}
    for row in runs:
        key = vehicle_outcome(row)
        distribution[key] = distribution.get(key, 0) + 1
    return distribution


def baseline_matches_run(baseline: Dict[str, Any], row: Dict[str, Any]) -> bool:
    return bool(baseline) and int(baseline.get("vehicleCountAfter", -1) or -1) == int(row.get("vehicleCountAfter", -2) or -2) and bool(baseline.get("objectiveImproved")) == bool(row.get("objectiveImproved"))


def has_route_pool_budget_starvation(row: Dict[str, Any]) -> bool:
    for stage in stage_rows(row):
        if stage.get("name") == "route-pool-sp" and stage.get("skipped") and stage.get("skippedReason") not in {"disabled-by-adaptive-profile", "stage-disabled"}:
            return True
    return False


def baseline_has_missing_improvement_artifact(baseline: Dict[str, Any]) -> bool:
    return bool(baseline) and bool(baseline.get("vehicleCountImproved")) and not accepted_stages(baseline)


def classify_reproducibility(baseline: Dict[str, Any], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not runs:
        return {"classification": "unknown", "reason": "no-runs"}
    matching_runs = [row for row in runs if baseline_matches_run(baseline, row)]
    unique_outcomes = outcome_distribution(runs)
    unique_signatures = sorted({row.get("solutionSignature") for row in runs if row.get("solutionSignature")})
    all_same_outcome = len(unique_outcomes) == 1
    all_same_signature = len(unique_signatures) <= 1
    if len(unique_outcomes) > 1 or len(unique_signatures) > 1:
        return {
            "classification": "nondeterministic-runner",
            "reason": "multiple-outcomes-or-solution-signatures",
            "baselineMatchedRunCount": len(matching_runs),
            "outcomeDistribution": unique_outcomes,
            "solutionSignatureCount": len(unique_signatures),
        }
    if any(has_route_pool_budget_starvation(row) for row in runs):
        return {
            "classification": "budget-starvation",
            "reason": "route-pool-sp-skipped-after-budget-pressure",
            "baselineMatchedRunCount": len(matching_runs),
            "outcomeDistribution": unique_outcomes,
        }
    if baseline_has_missing_improvement_artifact(baseline):
        return {
            "classification": "baseline-artifact-stale",
            "reason": "baseline-claims-vehicle-improvement-without-accepted-stage-trace",
            "baselineMatchedRunCount": len(matching_runs),
            "outcomeDistribution": unique_outcomes,
        }
    if matching_runs:
        return {
            "classification": "stable-reproducible",
            "reason": "all-runs-match-baseline-outcome" if len(matching_runs) == len(runs) else "some-runs-match-baseline-outcome",
            "baselineMatchedRunCount": len(matching_runs),
            "outcomeDistribution": unique_outcomes,
        }
    if all_same_outcome and all_same_signature and baseline:
        return {
            "classification": "deterministic-regression",
            "reason": "all-runs-consistent-but-do-not-match-baseline",
            "baselineMatchedRunCount": 0,
            "outcomeDistribution": unique_outcomes,
        }
    return {"classification": "unknown", "reason": "unclassified-reproducibility-pattern", "outcomeDistribution": unique_outcomes}


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 56A Reproducibility Audit",
        "",
        f"Gate: **{summary['gate']['verdict']}**",
        f"Classification: `{summary['classification']['classification']}`",
        f"Instance: `{summary['instance']}`",
        "",
        "## Outcome Distribution",
        "",
    ]
    for outcome, count in summary["classification"].get("outcomeDistribution", {}).items():
        lines.append(f"- `{outcome}`: {count}")
    lines.extend(["", "## Runs", "", "| Run | Verdict | Vehicles | Accepted Stages | Runtime ms | Over Budget | Signature |", "|---:|---|---:|---|---:|---:|---|"])
    for row in summary["runs"]:
        signature = str(row.get("solutionSignature") or "")[:12]
        lines.append(f"| {row['runIndex']} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {', '.join(row.get('acceptedStages') or [])} | {row.get('runtimeMs')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | `{signature}` |")
    return "\n".join(lines) + "\n"


def run(
    *,
    instance: str,
    repeat: int,
    output_dir: Path,
    baseline_dir: Path,
    data_source: str,
    time_limit_ms: int,
    mode: str,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline(baseline_dir, instance)
    runs: List[Dict[str, Any]] = []
    for index in range(1, repeat + 1):
        run_dir = output_dir / f"run-{index:02d}"
        phase47_summary = run_phase47([instance], run_dir, data_source, time_limit_ms, mode)
        diagnostics = phase47_summary.get("results", [{}])[0]
        signature = solution_signature(run_dir / instance / "final_solution.json") or solution_signature(run_dir / str(diagnostics.get("instance") or instance) / "final_solution.json")
        runs.append(compact_run(diagnostics, signature, index))
    classification = classify_reproducibility(baseline, runs)
    summary: Dict[str, Any] = {
        "schemaVersion": "phase56a-reproducibility-audit-summary/v1",
        "instance": instance,
        "repeat": repeat,
        "mode": mode,
        "timeLimitMs": time_limit_ms,
        "baselineArtifact": str(baseline_dir),
        "baseline": compact_run(baseline, solution_signature(baseline_dir / instance / "final_solution.json"), 0) if baseline else None,
        "runs": runs,
        "classification": classification,
        "gate": {"verdict": "FAIL" if classification.get("classification") == "unknown" else "PASS"},
    }
    write_json(output_dir / "phase56a_reproducibility_audit_summary.json", summary)
    (output_dir / "phase56a_reproducibility_audit_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit reproducibility of the promoted Phase 47 runner on one instance.")
    parser.add_argument("--instance", default="lrc202")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--baseline-dir", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(
        instance=args.instance,
        repeat=args.repeat,
        output_dir=Path(args.output_dir),
        baseline_dir=Path(args.baseline_dir),
        data_source=args.data_source,
        time_limit_ms=parse_time_limit(args.time_limit),
        mode=args.mode,
    )
    print(f"[PHASE56A REPRODUCIBILITY AUDIT] wrote {args.output_dir}")
    return 0 if summary["gate"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

