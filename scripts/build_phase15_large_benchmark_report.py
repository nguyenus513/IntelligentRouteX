from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def vehicle_gap(row: dict[str, Any]) -> int | None:
    vehicles = row.get("vehicleCount")
    bks = row.get("bestKnownVehicleCount")
    if vehicles is None or bks is None:
        return None
    return max(0, int(vehicles) - int(bks))


def resource_metadata(row: dict[str, Any]) -> dict[str, Any]:
    solution_path = row.get("solutionPath")
    if not solution_path:
        return {}
    path = Path(str(solution_path))
    if not path.exists():
        return {}
    try:
        solution = read_json(path)
    except Exception:
        return {}
    return {
        "budgetUsage": solution.get("budgetUsage") or {},
        "budgetAllocation": solution.get("budgetAllocation") or {},
        "stageRuntimeSummary": solution.get("stageRuntimeSummary") or {},
    }


def resource_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    budget_used: list[float] = []
    legacy_overrun_count = 0
    solver_overrun_count = 0
    wall_clock_overrun_count = 0
    solver_time_limits: list[float] = []
    wall_clock_allowed: list[float] = []
    wall_clock_overheads: list[float] = []
    degrade_levels: dict[str, int] = {}
    stage_runtimes: dict[str, list[float]] = {}
    stage_feasible_ratios: dict[str, list[float]] = {}
    metadata_count = 0
    for row in rows:
        metadata = resource_metadata(row)
        if not metadata:
            continue
        metadata_count += 1
        budget_usage = metadata.get("budgetUsage") or {}
        if budget_usage.get("usedMs") is not None:
            budget_used.append(float(budget_usage.get("usedMs") or 0.0))
        if budget_usage.get("overrun"):
            legacy_overrun_count += 1
        if budget_usage.get("solverOverrun"):
            solver_overrun_count += 1
        if budget_usage.get("wallClockOverrun"):
            wall_clock_overrun_count += 1
        if budget_usage.get("solverTimeLimitMs") is not None:
            solver_time_limits.append(float(budget_usage.get("solverTimeLimitMs") or 0.0))
        if budget_usage.get("wallClockAllowedMs") is not None:
            wall_clock_allowed.append(float(budget_usage.get("wallClockAllowedMs") or 0.0))
        if budget_usage.get("wallClockOverheadMs") is not None:
            wall_clock_overheads.append(float(budget_usage.get("wallClockOverheadMs") or 0.0))
        degrade_level = budget_usage.get("degradeLevel") or (metadata.get("budgetAllocation") or {}).get("degrade_level")
        if degrade_level:
            degrade_levels[str(degrade_level)] = degrade_levels.get(str(degrade_level), 0) + 1
        stages = ((metadata.get("stageRuntimeSummary") or {}).get("stages") or {})
        for stage, stage_summary in stages.items():
            p95 = stage_summary.get("runtimeMsP95")
            if p95 is not None:
                stage_runtimes.setdefault(str(stage), []).append(float(p95))
            ratio = stage_summary.get("feasibleCandidateRatio")
            if ratio is not None:
                stage_feasible_ratios.setdefault(str(stage), []).append(float(ratio))
    return {
        "metadataCount": metadata_count,
        "overrunCount": wall_clock_overrun_count,
        "overrunRate": wall_clock_overrun_count / metadata_count if metadata_count else None,
        "legacyOverrunCount": legacy_overrun_count,
        "solverOverrunCount": solver_overrun_count,
        "solverOverrunRate": solver_overrun_count / metadata_count if metadata_count else None,
        "wallClockOverrunCount": wall_clock_overrun_count,
        "wallClockOverrunRate": wall_clock_overrun_count / metadata_count if metadata_count else None,
        "solverTimeLimitP95Ms": percentile(solver_time_limits, 95),
        "wallClockAllowedP95Ms": percentile(wall_clock_allowed, 95),
        "wallClockOverheadP95Ms": percentile(wall_clock_overheads, 95),
        "budgetUsedP50Ms": percentile(budget_used, 50),
        "budgetUsedP95Ms": percentile(budget_used, 95),
        "budgetUsedP99Ms": percentile(budget_used, 99),
        "degradeLevelCounts": degrade_levels,
        "stageRuntimeP95Ms": {stage: percentile(values, 95) for stage, values in sorted(stage_runtimes.items())},
        "stageFeasibleCandidateRatioMean": {
            stage: mean(values) for stage, values in sorted(stage_feasible_ratios.items()) if values
        },
    }


def row_quality_key(row: dict[str, Any]) -> tuple[int, int, float, float]:
    feasible_penalty = 0 if row.get("feasible") else 1
    return feasible_penalty, int(row.get("vehicleCount") or 10**9), float(row.get("totalDistance") or 1e18), float(row.get("runtimeMs") or 1e18)


def compare_pair(ours: dict[str, Any], baseline: dict[str, Any]) -> str:
    if ours.get("verdict") == "EVIDENCE_GAP" and baseline.get("verdict") == "EVIDENCE_GAP":
        return "TIE_EVIDENCE_GAP"
    ours_key = row_quality_key(ours)
    baseline_key = row_quality_key(baseline)
    if ours_key[:2] < baseline_key[:2]:
        return "WIN"
    if ours_key[:2] > baseline_key[:2]:
        return "LOSS"
    distance_tolerance = max(1e-6, abs(float(baseline.get("totalDistance") or 0.0)) * 0.01)
    distance_delta = float(ours.get("totalDistance") or 1e18) - float(baseline.get("totalDistance") or 1e18)
    if distance_delta < -distance_tolerance:
        return "WIN"
    if distance_delta > distance_tolerance:
        return "LOSS"
    if ours_key[3] <= baseline_key[3]:
        return "WIN_RUNTIME"
    return "TIE_QUALITY"


def build_report(input_dir: Path) -> dict[str, Any]:
    payload = read_json(input_dir / "phase15_large_benchmark_results.json")
    rows = payload.get("results", [])
    by_solver: dict[str, list[dict[str, Any]]] = {}
    by_cell: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_solver.setdefault(str(row.get("solver")), []).append(row)
        by_cell.setdefault((str(row.get("suite")), str(row.get("instance"))), {})[str(row.get("solver"))] = row
    solver_summaries = []
    for solver, solver_rows in sorted(by_solver.items()):
        runtimes = [float(row.get("runtimeMs") or 0) for row in solver_rows]
        gaps = [gap for row in solver_rows if (gap := vehicle_gap(row)) is not None]
        hard_violations = sum(
            int(row.get("capacityViolationCount") or 0)
            + int(row.get("timeWindowViolationCount") or 0)
            + int(row.get("pickupBeforeDropoffViolationCount") or 0)
            + int(row.get("vehicleLimitViolationCount") or 0)
            + int(row.get("unservedRequestCount") or 0)
            for row in solver_rows
        )
        solver_summaries.append({
            "solver": solver,
            "rowCount": len(solver_rows),
            "passCount": sum(1 for row in solver_rows if row.get("verdict") == "PASS"),
            "passWithLimitsCount": sum(1 for row in solver_rows if row.get("verdict") == "PASS_WITH_LIMITS"),
            "failCount": sum(1 for row in solver_rows if row.get("verdict") == "FAIL"),
            "evidenceGapCount": sum(1 for row in solver_rows if row.get("verdict") == "EVIDENCE_GAP"),
            "feasibleCount": sum(1 for row in solver_rows if row.get("feasible")),
            "feasibilityRate": 0.0 if not solver_rows else sum(1 for row in solver_rows if row.get("feasible")) / len(solver_rows),
            "vehicleGapSum": sum(gaps),
            "vehicleGapMean": None if not gaps else mean(gaps),
            "hardViolationCount": hard_violations,
            "runtimeP50Ms": percentile(runtimes, 50),
            "runtimeP95Ms": percentile(runtimes, 95),
            "runtimeP99Ms": percentile(runtimes, 99),
            "runtimeMeanMs": None if not runtimes else mean(runtimes),
            "runtimeMedianMs": None if not runtimes else median(runtimes),
            "resourceSummary": resource_summary(solver_rows),
        })
    comparisons = []
    wins = ties = losses = 0
    for key, solvers in sorted(by_cell.items()):
        ours = solvers.get("our-dispatch-v2")
        if ours is None:
            continue
        for baseline_solver, baseline in sorted(solvers.items()):
            if baseline_solver == "our-dispatch-v2":
                continue
            verdict = compare_pair(ours, baseline)
            if verdict.startswith("WIN"):
                wins += 1
            elif verdict == "LOSS":
                losses += 1
            else:
                ties += 1
            comparisons.append({
                "suite": key[0],
                "instance": key[1],
                "baselineSolver": baseline_solver,
                "verdict": verdict,
                "oursVehicleCount": ours.get("vehicleCount"),
                "baselineVehicleCount": baseline.get("vehicleCount"),
                "oursDistance": ours.get("totalDistance"),
                "baselineDistance": baseline.get("totalDistance"),
                "oursRuntimeMs": ours.get("runtimeMs"),
                "baselineRuntimeMs": baseline.get("runtimeMs"),
            })
    return {
        "schemaVersion": "phase15-large-benchmark-report/v1",
        "inputDir": str(input_dir),
        "tier": payload.get("tier"),
        "rowCount": len(rows),
        "completedCells": payload.get("completedCells"),
        "totalCells": payload.get("totalCells"),
        "solverSummaries": solver_summaries,
        "comparisonCount": len(comparisons),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "comparisons": comparisons,
        "resourceSummaries": {summary["solver"]: summary.get("resourceSummary", {}) for summary in solver_summaries},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 15 Large Benchmark Aggregate Report",
        "",
        f"- tier: `{report['tier']}`",
        f"- completed cells: `{report['completedCells']}/{report['totalCells']}`",
        f"- wins/ties/losses: `{report['wins']}/{report['ties']}/{report['losses']}`",
        "",
        "## Solver Summary",
        "",
        "| Solver | Rows | Pass/Limits/Fail/Gap | Feasible | Gap Sum | Hard Violations | Runtime p50/p95/p99 | Wall overrun | Budget used p95 | Overhead p95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["solverSummaries"]:
        resource = row.get("resourceSummary") or {}
        lines.append(
            f"| {row['solver']} | {row['rowCount']} | {row['passCount']}/{row['passWithLimitsCount']}/{row['failCount']}/{row['evidenceGapCount']} | "
            f"{row['feasibleCount']} | {row['vehicleGapSum']} | {row['hardViolationCount']} | "
            f"{row['runtimeP50Ms']}/{row['runtimeP95Ms']}/{row['runtimeP99Ms']} | "
            f"{resource.get('wallClockOverrunRate')} | {resource.get('budgetUsedP95Ms')} | {resource.get('wallClockOverheadP95Ms')} |"
        )
    lines.extend([
        "",
        "## Resource Summary",
        "",
        "| Solver | Metadata Rows | Degrade Levels | Stage Runtime P95 |",
        "|---|---:|---|---|",
    ])
    for row in report["solverSummaries"]:
        resource = row.get("resourceSummary") or {}
        lines.append(
            f"| {row['solver']} | {resource.get('metadataCount')} | `{resource.get('degradeLevelCounts')}` | `{resource.get('stageRuntimeP95Ms')}` |"
        )
    lines.extend([
        "",
        "## Comparisons",
        "",
        "| Suite | Instance | Baseline | Verdict | Vehicles O/B | Distance O/B | Runtime O/B |",
        "|---|---|---|---|---:|---:|---:|",
    ])
    for row in report["comparisons"]:
        lines.append(
            f"| {row['suite']} | {row['instance']} | {row['baselineSolver']} | {row['verdict']} | "
            f"{row['oursVehicleCount']}/{row['baselineVehicleCount']} | {row['oursDistance']}/{row['baselineDistance']} | "
            f"{row['oursRuntimeMs']}/{row['baselineRuntimeMs']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 15 large benchmark aggregate report.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase15_large_benchmark_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase15_large_benchmark_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE15 LARGE REPORT] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
