from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase55-promotion-guard-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_diagnostics(root: Path) -> Dict[str, Dict[str, Any]]:
    rows = {}
    for path in sorted(root.glob("*/diagnostics.json")):
        row = read_json(path)
        key = str(row.get("instance") or path.parent.name).lower()
        rows[key] = row
    return rows


def over_budget(row: Dict[str, Any]) -> bool:
    return bool(row.get("stageRuntimeSummary", {}).get("overBudget"))


def vehicle_reduction(row: Dict[str, Any]) -> int:
    return max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0))


def aggregate(rows: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    values = list(rows.values())
    return {
        "instanceCount": len(values),
        "failCount": sum(1 for row in values if row.get("verdict") == "FAIL"),
        "hardViolationCount": sum(int(row.get("hardViolations", 0) or 0) for row in values),
        "overBudgetCount": sum(1 for row in values if over_budget(row)),
        "leakageCount": sum(1 for row in values if row.get("leakageDetected")),
        "totalVehicleReduction": sum(vehicle_reduction(row) for row in values),
        "objectiveRegressionAcceptedCount": sum(
            1
            for row in values
            if row.get("objectiveAfter") is not None
            and row.get("objectiveBefore") is not None
            and float(row.get("objectiveAfter")) > float(row.get("objectiveBefore"))
        ),
    }


def guard(baseline_rows: Dict[str, Dict[str, Any]], candidate_rows: Dict[str, Dict[str, Any]], candidate_name: str) -> Dict[str, Any]:
    matching = sorted(set(baseline_rows) & set(candidate_rows))
    missing_baseline_instances = sorted(set(baseline_rows) - set(candidate_rows))
    baseline = {key: baseline_rows[key] for key in matching}
    candidate = {key: candidate_rows[key] for key in matching}
    baseline_stats = aggregate(baseline)
    candidate_stats = aggregate(candidate)
    failures: List[Dict[str, Any]] = []
    for key in matching:
        base = baseline[key]
        cand = candidate[key]
        if vehicle_reduction(base) > 0 and vehicle_reduction(cand) < vehicle_reduction(base):
            failures.append({"type": "per-instance-vehicle-regression", "instance": cand.get("instance"), "baselineReduction": vehicle_reduction(base), "candidateReduction": vehicle_reduction(cand)})
    safety_checks = {
        "failCountZero": candidate_stats["failCount"] == 0,
        "hardViolationsZero": candidate_stats["hardViolationCount"] == 0,
        "overBudgetZero": candidate_stats["overBudgetCount"] == 0,
        "leakageZero": candidate_stats["leakageCount"] == 0,
        "vehicleReductionAtLeastBaseline": candidate_stats["totalVehicleReduction"] >= baseline_stats["totalVehicleReduction"],
        "noObjectiveRegressionAccepted": candidate_stats["objectiveRegressionAcceptedCount"] == 0,
        "noBaselineImprovedCaseRegression": not failures,
        "candidateCoversBaselineInstances": not missing_baseline_instances,
    }
    for key in missing_baseline_instances:
        failures.append({"type": "missing-baseline-instance", "instance": baseline_rows[key].get("instance")})
    if not safety_checks["failCountZero"]:
        failures.append({"type": "candidate-fail-count", "count": candidate_stats["failCount"]})
    if not safety_checks["hardViolationsZero"]:
        failures.append({"type": "candidate-hard-violations", "count": candidate_stats["hardViolationCount"]})
    if not safety_checks["overBudgetZero"]:
        failures.append({"type": "candidate-over-budget", "count": candidate_stats["overBudgetCount"]})
    if not safety_checks["leakageZero"]:
        failures.append({"type": "candidate-leakage", "count": candidate_stats["leakageCount"]})
    if not safety_checks["vehicleReductionAtLeastBaseline"]:
        failures.append({"type": "total-vehicle-reduction-regression", "baseline": baseline_stats["totalVehicleReduction"], "candidate": candidate_stats["totalVehicleReduction"]})
    if not safety_checks["noObjectiveRegressionAccepted"]:
        failures.append({"type": "objective-regression-accepted", "count": candidate_stats["objectiveRegressionAcceptedCount"]})
    verdict = "PROMOTE_CANDIDATE" if all(safety_checks.values()) else "DIAGNOSTIC_ONLY"
    return {
        "schemaVersion": "phase55-promotion-guard-summary/v1",
        "candidateName": candidate_name,
        "verdict": verdict,
        "matchingInstanceCount": len(matching),
        "missingBaselineInstances": missing_baseline_instances,
        "baselineAggregate": baseline_stats,
        "candidateAggregate": candidate_stats,
        "checks": safety_checks,
        "failures": failures,
    }


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 55 Promotion Guard",
        "",
        f"Candidate: `{summary['candidateName']}`",
        f"Verdict: **{summary['verdict']}**",
        "",
        "## Aggregate",
        "",
        "| Metric | Promoted Baseline | Candidate |",
        "|---|---:|---:|",
    ]
    for key in ("failCount", "hardViolationCount", "overBudgetCount", "leakageCount", "totalVehicleReduction", "objectiveRegressionAcceptedCount"):
        lines.append(f"| {key} | {summary['baselineAggregate'].get(key)} | {summary['candidateAggregate'].get(key)} |")
    lines.extend(["", "## Checks", ""])
    for key, value in summary["checks"].items():
        lines.append(f"- `{key}`: {value}")
    if summary["failures"]:
        lines.extend(["", "## Failures", ""])
        for failure in summary["failures"]:
            lines.append(f"- `{failure['type']}`: {failure}")
    return "\n".join(lines) + "\n"


def run(baseline_dir: Path, candidate_dir: Path, candidate_name: str, output_dir: Path) -> Dict[str, Any]:
    summary = guard(load_diagnostics(baseline_dir), load_diagnostics(candidate_dir), candidate_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase55_promotion_guard_summary.json", summary)
    (output_dir / "phase55_promotion_guard_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard promotion candidates against the Phase 47 promoted baseline.")
    parser.add_argument("--baseline-dir", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.baseline_dir), Path(args.candidate_dir), args.candidate_name, Path(args.output_dir))
    print(f"[PHASE55 PROMOTION GUARD] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
