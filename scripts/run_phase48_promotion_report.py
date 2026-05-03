from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PHASE45_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase45-budgeted-vehicle-losses-v3"
DEFAULT_PHASE47_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-vehicle-losses-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase48-promotion-v1"

VERDICT_RANK = {"PASS_STRONG": 3, "PASS": 2, "PASS_WITH_LIMITS": 1, "FAIL": 0}


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_diagnostics(root: Path) -> Dict[str, Dict[str, Any]]:
    rows = {}
    for path in sorted(root.glob("*/diagnostics.json")):
        diagnostics = read_json(path)
        key = str(diagnostics.get("instance") or path.parent.name).lower()
        rows[key] = diagnostics
    return rows


def over_budget(row: Dict[str, Any]) -> bool:
    return bool(row.get("stageRuntimeSummary", {}).get("overBudget"))


def vehicle_reduction(row: Dict[str, Any]) -> int:
    return int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0)


def non_negative_vehicle_reduction(row: Dict[str, Any]) -> int:
    return max(0, vehicle_reduction(row))


def objective_delta(row: Dict[str, Any]) -> float:
    before = float(row.get("objectiveBefore", 0.0) or 0.0)
    after = float(row.get("objectiveAfter", before) or before)
    return before - after


def aggregate(rows: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    values = list(rows.values())
    verdict_counts = {verdict: sum(1 for row in values if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    return {
        "instanceCount": len(values),
        "totalVehicleReduction": sum(non_negative_vehicle_reduction(row) for row in values),
        "objectiveImprovementCount": sum(1 for row in values if row.get("objectiveImproved")),
        "vehicleImprovementCount": sum(1 for row in values if row.get("vehicleCountImproved")),
        "failCount": verdict_counts["FAIL"],
        "passStrongCount": verdict_counts["PASS_STRONG"],
        "passCount": verdict_counts["PASS"],
        "overBudgetCount": sum(1 for row in values if over_budget(row)),
        "hardViolationCount": sum(int(row.get("hardViolations", 0) or 0) for row in values),
        "leakageCount": sum(1 for row in values if row.get("leakageDetected")),
        "totalRuntimeMs": sum(int(row.get("runtimeMs", 0) or 0) for row in values),
        "verdictCounts": verdict_counts,
    }


def safety_tuple(stats: Dict[str, Any]) -> tuple[int, int, int, int]:
    return (int(stats.get("failCount", 0)), int(stats.get("hardViolationCount", 0)), int(stats.get("overBudgetCount", 0)), int(stats.get("leakageCount", 0)))


def quality_tuple(stats: Dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        int(stats.get("totalVehicleReduction", 0)),
        int(stats.get("passStrongCount", 0)),
        int(stats.get("passCount", 0)),
        int(stats.get("objectiveImprovementCount", 0)),
        -int(stats.get("totalRuntimeMs", 0)),
    )


def recommend_runner(phase45: Dict[str, Any], phase47: Dict[str, Any]) -> Dict[str, Any]:
    phase45_safety = safety_tuple(phase45)
    phase47_safety = safety_tuple(phase47)
    if phase47_safety > phase45_safety:
        return {"promotedRunner": "phase45", "reason": "phase47-safety-regression"}
    if phase47_safety < phase45_safety:
        return {"promotedRunner": "phase47", "reason": "phase47-safer"}
    if quality_tuple(phase47) > quality_tuple(phase45):
        return {"promotedRunner": "phase47", "reason": "phase47-quality-improves-with-same-safety"}
    return {"promotedRunner": "phase45", "reason": "phase47-not-better"}


def compare_instances(phase45_rows: Dict[str, Dict[str, Any]], phase47_rows: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for key in sorted(set(phase45_rows) & set(phase47_rows)):
        left = phase45_rows[key]
        right = phase47_rows[key]
        rows.append(
            {
                "instance": right.get("instance") or left.get("instance"),
                "phase45": compact_row(left),
                "phase47": compact_row(right),
                "vehicleReductionDelta": vehicle_reduction(right) - vehicle_reduction(left),
                "objectiveDeltaImprovement": objective_delta(right) - objective_delta(left),
                "runtimeDeltaMs": int(right.get("runtimeMs", 0) or 0) - int(left.get("runtimeMs", 0) or 0),
                "winner": instance_winner(left, right),
            }
        )
    return rows


def compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": row.get("verdict"),
        "runtimeMs": row.get("runtimeMs"),
        "overBudget": over_budget(row),
        "hardViolations": row.get("hardViolations"),
        "leakageDetected": row.get("leakageDetected"),
        "vehicleCountBefore": row.get("vehicleCountBefore"),
        "vehicleCountAfter": row.get("vehicleCountAfter"),
        "objectiveBefore": row.get("objectiveBefore"),
        "objectiveAfter": row.get("objectiveAfter"),
        "vehicleCountImproved": row.get("vehicleCountImproved"),
        "objectiveImproved": row.get("objectiveImproved"),
    }


def instance_winner(left: Dict[str, Any], right: Dict[str, Any]) -> str:
    left_safety = (1 if left.get("verdict") == "FAIL" else 0, int(left.get("hardViolations", 0) or 0), 1 if over_budget(left) else 0, 1 if left.get("leakageDetected") else 0)
    right_safety = (1 if right.get("verdict") == "FAIL" else 0, int(right.get("hardViolations", 0) or 0), 1 if over_budget(right) else 0, 1 if right.get("leakageDetected") else 0)
    if right_safety < left_safety:
        return "phase47"
    if right_safety > left_safety:
        return "phase45"
    left_quality = (vehicle_reduction(left), VERDICT_RANK.get(str(left.get("verdict")), 0), 1 if left.get("objectiveImproved") else 0, -int(left.get("runtimeMs", 0) or 0))
    right_quality = (vehicle_reduction(right), VERDICT_RANK.get(str(right.get("verdict")), 0), 1 if right.get("objectiveImproved") else 0, -int(right.get("runtimeMs", 0) or 0))
    return "phase47" if right_quality > left_quality else "phase45"


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 48 Promotion Report",
        "",
        f"Recommended runner: **{summary['recommendation']['promotedRunner']}** ({summary['recommendation']['reason']})",
        "",
        "## Aggregate",
        "",
        "| Runner | FAIL | Hard Viol | Over Budget | Leakage | Vehicle Reduction | PASS_STRONG | PASS | Objective Improvements | Runtime ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for runner in ("phase45", "phase47"):
        row = summary["aggregate"][runner]
        lines.append(f"| {runner} | {row['failCount']} | {row['hardViolationCount']} | {row['overBudgetCount']} | {row['leakageCount']} | {row['totalVehicleReduction']} | {row['passStrongCount']} | {row['passCount']} | {row['objectiveImprovementCount']} | {row['totalRuntimeMs']} |")
    lines.extend(["", "## Per Instance", "", "| Instance | Winner | Phase 45 Vehicles | Phase 47 Vehicles | Vehicle Delta | Runtime Delta ms |", "|---|---|---:|---:|---:|---:|"])
    for row in summary["perInstance"]:
        left = row["phase45"]
        right = row["phase47"]
        lines.append(f"| {row['instance']} | {row['winner']} | {left['vehicleCountBefore']} -> {left['vehicleCountAfter']} | {right['vehicleCountBefore']} -> {right['vehicleCountAfter']} | {row['vehicleReductionDelta']} | {row['runtimeDeltaMs']} |")
    return "\n".join(lines) + "\n"


def run(phase45_dir: Path, phase47_dir: Path, output_dir: Path) -> Dict[str, Any]:
    phase45_rows = load_diagnostics(phase45_dir)
    phase47_rows = load_diagnostics(phase47_dir)
    missing = {"phase45Only": sorted(set(phase45_rows) - set(phase47_rows)), "phase47Only": sorted(set(phase47_rows) - set(phase45_rows))}
    phase45_stats = aggregate({key: phase45_rows[key] for key in sorted(set(phase45_rows) & set(phase47_rows))})
    phase47_stats = aggregate({key: phase47_rows[key] for key in sorted(set(phase45_rows) & set(phase47_rows))})
    recommendation = recommend_runner(phase45_stats, phase47_stats)
    summary = {
        "schemaVersion": "phase48-promotion-summary/v1",
        "phase45Dir": str(phase45_dir),
        "phase47Dir": str(phase47_dir),
        "matchingInstanceCount": len(set(phase45_rows) & set(phase47_rows)),
        "missingInstances": missing,
        "aggregate": {"phase45": phase45_stats, "phase47": phase47_stats},
        "recommendation": recommendation,
        "perInstance": compare_instances(phase45_rows, phase47_rows),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase48_promotion_summary.json", summary)
    (output_dir / "phase48_promotion_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 45 and Phase 47 diagnostics and recommend promotion.")
    parser.add_argument("--phase45-dir", default=str(DEFAULT_PHASE45_DIR))
    parser.add_argument("--phase47-dir", default=str(DEFAULT_PHASE47_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.phase45_dir), Path(args.phase47_dir), Path(args.output_dir))
    print(f"[PHASE48 PROMOTION] wrote {args.output_dir}")
    return 0 if summary["recommendation"]["promotedRunner"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
