from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from run_phase47_adaptive_budget_natural_optimizer import parse_time_limit, run as run_phase47


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase56-promoted-full-certification-v1"
DEFAULT_BASELINE_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1"

PHASE27_LOSSES = [
    "lrc202",
    "lrc206",
    "lrc106",
    "LRC1_2_7",
    "lrc104",
    "lrc108",
    "LRC281",
    "LC1_4_8",
    "lrc208",
    "lrc102",
    "lrc207",
    "LR2_2_8",
    "LC1_4_4",
    "LRC2_2_4",
    "LC2_4_2",
    "LC281",
    "LC1_6_2",
    "LC283",
    "LC181",
]


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def discover_li_lim_instances() -> List[str]:
    root = REPO_ROOT / "benchmarks" / "external" / "official" / "li-lim-pdptw"
    return sorted(path.stem for path in root.glob("*.txt"))


def resolve_instances(instance_set: str, custom_instances: str = "") -> List[str]:
    if instance_set == "phase27-losses":
        return list(PHASE27_LOSSES)
    if instance_set == "li-lim-full":
        return discover_li_lim_instances()
    instances = [part.strip() for part in custom_instances.split(",") if part.strip()]
    if not instances:
        raise ValueError("--instances is required when --instance-set custom is used")
    return instances


def load_diagnostics(root: Path) -> Dict[str, Dict[str, Any]]:
    rows = {}
    if not root.exists():
        return rows
    for path in sorted(root.glob("*/diagnostics.json")):
        row = read_json(path)
        key = str(row.get("instance") or path.parent.name).lower()
        rows[key] = row
    return rows


def over_budget(row: Dict[str, Any]) -> bool:
    return bool(row.get("stageRuntimeSummary", {}).get("overBudget"))


def vehicle_reduction(row: Dict[str, Any]) -> int:
    return max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0))


def objective_regression_accepted(row: Dict[str, Any]) -> bool:
    before = row.get("objectiveBefore")
    after = row.get("objectiveAfter")
    return before is not None and after is not None and float(after) > float(before)


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    verdict_counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    return {
        "instanceCount": len(rows),
        "verdictCounts": verdict_counts,
        "failCount": verdict_counts["FAIL"],
        "hardViolationCount": sum(int(row.get("hardViolations", 0) or 0) for row in rows),
        "overBudgetCount": sum(1 for row in rows if over_budget(row)),
        "leakageCount": sum(1 for row in rows if row.get("leakageDetected")),
        "objectiveRegressionAcceptedCount": sum(1 for row in rows if objective_regression_accepted(row)),
        "totalVehicleReduction": sum(vehicle_reduction(row) for row in rows),
        "vehicleImprovementCount": sum(1 for row in rows if row.get("vehicleCountImproved")),
        "objectiveImprovementCount": sum(1 for row in rows if row.get("objectiveImproved")),
        "totalRuntimeMs": sum(int(row.get("runtimeMs", 0) or 0) for row in rows),
    }


def compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "instance": row.get("instance"),
        "verdict": row.get("verdict"),
        "vehicleCountBefore": row.get("vehicleCountBefore"),
        "vehicleCountAfter": row.get("vehicleCountAfter"),
        "vehicleReduction": vehicle_reduction(row),
        "distanceBefore": row.get("distanceBefore"),
        "distanceAfter": row.get("distanceAfter"),
        "objectiveBefore": row.get("objectiveBefore"),
        "objectiveAfter": row.get("objectiveAfter"),
        "objectiveImproved": row.get("objectiveImproved"),
        "hardViolations": row.get("hardViolations"),
        "overBudget": over_budget(row),
        "leakageDetected": row.get("leakageDetected"),
        "runtimeMs": row.get("runtimeMs"),
    }


def classify_regressions(
    current_rows: Dict[str, Dict[str, Any]],
    baseline_rows: Dict[str, Dict[str, Any]],
    *,
    distance_tolerance: float,
    objective_tolerance: float,
) -> List[Dict[str, Any]]:
    regressions: List[Dict[str, Any]] = []
    for key in sorted(set(current_rows) & set(baseline_rows)):
        current = current_rows[key]
        baseline = baseline_rows[key]
        if vehicle_reduction(baseline) > 0 and vehicle_reduction(current) < vehicle_reduction(baseline):
            regressions.append(
                {
                    "type": "previously-improved-vehicle-regression",
                    "instance": current.get("instance"),
                    "baseline": compact_row(baseline),
                    "current": compact_row(current),
                }
            )
        baseline_objective = baseline.get("objectiveAfter")
        current_objective = current.get("objectiveAfter")
        if baseline_objective is not None and current_objective is not None and float(current_objective) > float(baseline_objective) + objective_tolerance:
            regressions.append(
                {
                    "type": "objective-after-regression",
                    "instance": current.get("instance"),
                    "baselineObjectiveAfter": baseline_objective,
                    "currentObjectiveAfter": current_objective,
                    "tolerance": objective_tolerance,
                }
            )
        baseline_distance = baseline.get("distanceAfter")
        current_distance = current.get("distanceAfter")
        if baseline_distance is not None and current_distance is not None:
            allowed = float(baseline_distance) * (1.0 + distance_tolerance)
            if float(current_distance) > allowed and int(current.get("vehicleCountAfter", 0) or 0) >= int(baseline.get("vehicleCountAfter", 0) or 0):
                regressions.append(
                    {
                        "type": "distance-after-regression",
                        "instance": current.get("instance"),
                        "baselineDistanceAfter": baseline_distance,
                        "currentDistanceAfter": current_distance,
                        "tolerance": distance_tolerance,
                    }
                )
    return regressions


def gate(summary: Dict[str, Any], regressions: List[Dict[str, Any]]) -> Dict[str, Any]:
    aggregate_stats = summary["aggregate"]
    checks = {
        "failCountZero": aggregate_stats["failCount"] == 0,
        "hardViolationsZero": aggregate_stats["hardViolationCount"] == 0,
        "overBudgetZero": aggregate_stats["overBudgetCount"] == 0,
        "leakageZero": aggregate_stats["leakageCount"] == 0,
        "noAcceptedObjectiveRegression": aggregate_stats["objectiveRegressionAcceptedCount"] == 0,
        "noPerInstanceRegression": not regressions,
    }
    return {"verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def markdown(summary: Dict[str, Any]) -> str:
    aggregate_stats = summary["aggregate"]
    lines = [
        "# Phase 56 Promoted Full Certification",
        "",
        f"Gate: **{summary['gate']['verdict']}**",
        f"Instance set: `{summary['instanceSet']}`",
        f"Mode: `{summary['mode']}`",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| instanceCount | {aggregate_stats['instanceCount']} |",
        f"| FAIL | {aggregate_stats['failCount']} |",
        f"| hardViolationCount | {aggregate_stats['hardViolationCount']} |",
        f"| overBudgetCount | {aggregate_stats['overBudgetCount']} |",
        f"| leakageCount | {aggregate_stats['leakageCount']} |",
        f"| objectiveRegressionAcceptedCount | {aggregate_stats['objectiveRegressionAcceptedCount']} |",
        f"| totalVehicleReduction | {aggregate_stats['totalVehicleReduction']} |",
        "",
        "## Per Instance",
        "",
        "| Instance | Verdict | Vehicles | Objective Improved | Hard | Over Budget | Leakage |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["results"]:
        lines.append(
            f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('objectiveImproved')} | {row.get('hardViolations')} | {over_budget(row)} | {row.get('leakageDetected')} |"
        )
    if summary["perInstanceRegression"]:
        lines.extend(["", "## Regressions", ""])
        for regression in summary["perInstanceRegression"]:
            lines.append(f"- `{regression['type']}` on `{regression.get('instance')}`")
    return "\n".join(lines) + "\n"


def run(
    *,
    instance_set: str,
    instances: str,
    output_dir: Path,
    data_source: str,
    time_limit_ms: int,
    mode: str,
    baseline_artifact: Path | None,
    distance_tolerance: float,
    objective_tolerance: float,
) -> Dict[str, Any]:
    selected_instances = resolve_instances(instance_set, instances)
    phase47_summary = run_phase47(selected_instances, output_dir, data_source, time_limit_ms, mode)
    current_rows = {str(row.get("instance")).lower(): row for row in phase47_summary.get("results", [])}
    baseline_rows = load_diagnostics(baseline_artifact) if baseline_artifact else {}
    regressions = classify_regressions(current_rows, baseline_rows, distance_tolerance=distance_tolerance, objective_tolerance=objective_tolerance) if baseline_rows else []
    rows = list(phase47_summary.get("results", []))
    summary: Dict[str, Any] = {
        "schemaVersion": "phase56-promoted-full-certification-summary/v1",
        "promotedRunner": "scripts/run_phase47_adaptive_budget_natural_optimizer.py",
        "instanceSet": instance_set,
        "instances": selected_instances,
        "mode": mode,
        "timeLimitMs": time_limit_ms,
        "baselineArtifact": str(baseline_artifact) if baseline_artifact else None,
        "distanceTolerance": distance_tolerance,
        "objectiveTolerance": objective_tolerance,
        "aggregate": aggregate(rows),
        "results": rows,
        "perInstanceRegression": regressions,
    }
    summary["gate"] = gate(summary, regressions)
    write_json(output_dir / "phase56_full_certification_summary.json", summary)
    write_json(output_dir / "per_instance_regression.json", regressions)
    (output_dir / "phase56_full_certification_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 56 full certification for the promoted Phase 47 natural optimizer.")
    parser.add_argument("--instance-set", choices=("phase27-losses", "li-lim-full", "custom"), default="phase27-losses")
    parser.add_argument("--instances", default="")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--baseline-artifact", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--distance-tolerance", type=float, default=0.01)
    parser.add_argument("--objective-tolerance", type=float, default=0.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    baseline_artifact = None if args.no_baseline else Path(args.baseline_artifact)
    summary = run(
        instance_set=args.instance_set,
        instances=args.instances,
        output_dir=Path(args.output_dir),
        data_source=args.data_source,
        time_limit_ms=parse_time_limit(args.time_limit),
        mode=args.mode,
        baseline_artifact=baseline_artifact,
        distance_tolerance=args.distance_tolerance,
        objective_tolerance=args.objective_tolerance,
    )
    print(f"[PHASE56 FULL CERTIFICATION] wrote {args.output_dir}")
    return 0 if summary["gate"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

