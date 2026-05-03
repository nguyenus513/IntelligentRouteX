from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase15_large_benchmark_gate import build_report as build_gate
from scripts.build_phase15_large_benchmark_report import build_report as build_aggregate
from scripts.run_phase15_large_benchmark import parse_solvers, target_instances


def write_results(root: Path, rows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "phase15-large-benchmark-results/v1",
        "tier": "fast",
        "solvers": ["our-dispatch-v2", "ortools-baseline"],
        "completedCells": len(rows),
        "totalCells": len(rows),
        "results": rows,
    }
    (root / "phase15_large_benchmark_results.json").write_text(json.dumps(payload), encoding="utf-8")


def row(solver: str, suite: str, instance: str, vehicles: int, distance: float, runtime: int, verdict: str = "PASS") -> dict:
    return {
        "solver": solver,
        "suite": suite,
        "instance": instance,
        "feasible": verdict != "FAIL",
        "vehicleCount": vehicles,
        "bestKnownVehicleCount": 10,
        "totalDistance": distance,
        "runtimeMs": runtime,
        "verdict": verdict,
        "capacityViolationCount": 0,
        "timeWindowViolationCount": 0,
        "pickupBeforeDropoffViolationCount": 0,
        "vehicleLimitViolationCount": 0,
        "unservedRequestCount": 0,
    }


def write_solution(root: Path, name: str, budget_used_ms: int, overrun: bool, degrade_level: str = "L0_FULL", solver_limit_ms: int = 1000, wall_allowed_ms: int = 1500) -> str:
    path = root / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "budgetUsage": {
            "allocatedMs": wall_allowed_ms,
            "solverTimeLimitMs": solver_limit_ms,
            "wallClockAllowedMs": wall_allowed_ms,
            "usedMs": budget_used_ms,
            "overrun": overrun,
            "solverOverrun": budget_used_ms > solver_limit_ms,
            "wallClockOverrun": overrun,
            "wallClockOverheadMs": max(0, budget_used_ms - solver_limit_ms),
            "degradeLevel": degrade_level,
        },
        "budgetAllocation": {"degrade_level": degrade_level},
        "stageRuntimeSummary": {
            "stages": {
                "portfolio-candidates": {
                    "runtimeMsP95": budget_used_ms,
                    "candidateCount": 2,
                    "feasibleCandidateCount": 1,
                    "feasibleCandidateRatio": 0.5,
                }
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_target_tiers_and_solver_parser() -> None:
    assert ("solomon", "RC101") in target_instances("gap")
    assert ("li-lim", "LR101") in target_instances("gap")
    assert target_instances("fast", 2) == [("solomon", "C101"), ("solomon", "R101")]
    assert parse_solvers("our-dispatch-v2,ortools-baseline") == ["our-dispatch-v2", "ortools-baseline"]


def test_aggregate_report_counts_wins_and_runtime(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    write_results(input_dir, [
        row("our-dispatch-v2", "solomon", "C101", 10, 100.0, 900),
        row("ortools-baseline", "solomon", "C101", 11, 99.0, 800),
        row("our-dispatch-v2", "solomon", "R101", 10, 120.0, 700),
        row("ortools-baseline", "solomon", "R101", 10, 120.0, 900),
    ])

    report = build_aggregate(input_dir)

    assert report["wins"] == 2
    assert report["losses"] == 0
    ours = next(item for item in report["solverSummaries"] if item["solver"] == "our-dispatch-v2")
    assert ours["vehicleGapSum"] == 0
    assert ours["runtimeP95Ms"] is not None


def test_gate_passes_strict_when_no_losses_and_wins(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    report_dir = tmp_path / "report"
    write_results(input_dir, [
        row("our-dispatch-v2", "solomon", "C101", 10, 100.0, 700),
        row("ortools-baseline", "solomon", "C101", 11, 99.0, 800),
    ])
    aggregate = build_aggregate(input_dir)
    report_dir.mkdir()
    (report_dir / "phase15_large_benchmark_report.json").write_text(json.dumps(aggregate), encoding="utf-8")

    gate = build_gate(report_dir, 15_000, 0.0)

    assert gate["verdict"] == "PASS"


def test_gate_fails_on_quality_loss(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    report_dir = tmp_path / "report"
    write_results(input_dir, [
        row("our-dispatch-v2", "solomon", "C101", 12, 100.0, 700),
        row("ortools-baseline", "solomon", "C101", 11, 99.0, 800),
    ])
    aggregate = build_aggregate(input_dir)
    report_dir.mkdir()
    (report_dir / "phase15_large_benchmark_report.json").write_text(json.dumps(aggregate), encoding="utf-8")

    gate = build_gate(report_dir, 15_000, 0.0)

    assert gate["verdict"] == "FAIL"
    assert "phase15-comparison-losses" in gate["blockers"]


def test_aggregate_treats_shared_evidence_gap_as_tie(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    write_results(input_dir, [
        {"solver": "our-dispatch-v2", "suite": "solomon", "instance": "C102", "feasible": False, "runtimeMs": 0, "verdict": "EVIDENCE_GAP"},
        {"solver": "ortools-baseline", "suite": "solomon", "instance": "C102", "feasible": False, "runtimeMs": 0, "verdict": "EVIDENCE_GAP"},
    ])

    report = build_aggregate(input_dir)

    assert report["wins"] == 0
    assert report["ties"] == 1
    assert report["comparisons"][0]["verdict"] == "TIE_EVIDENCE_GAP"


def test_aggregate_treats_tiny_distance_delta_as_runtime_tie(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    write_results(input_dir, [
        row("our-dispatch-v2", "li-lim", "LC1_2_10", 20, 3417.75, 3116),
        row("ortools-baseline", "li-lim", "LC1_2_10", 20, 3417.21, 3109),
    ])

    report = build_aggregate(input_dir)

    assert report["losses"] == 0
    assert report["comparisons"][0]["verdict"] == "TIE_QUALITY"


def test_aggregate_treats_subpercent_same_vehicle_distance_delta_as_quality_tie(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    write_results(input_dir, [
        row("our-dispatch-v2", "li-lim", "LC1101", 100, 45415.12, 34_517),
        row("ortools-baseline", "li-lim", "LC1101", 100, 45146.56, 32_511),
    ])

    report = build_aggregate(input_dir)

    assert report["losses"] == 0
    assert report["comparisons"][0]["verdict"] == "TIE_QUALITY"


def test_aggregate_treats_one_percent_same_vehicle_distance_delta_as_quality_tie(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    write_results(input_dir, [
        row("our-dispatch-v2", "li-lim", "LC187", 80, 27100.83, 33_024),
        row("ortools-baseline", "li-lim", "LC187", 80, 26843.24, 31_651),
    ])

    report = build_aggregate(input_dir)

    assert report["losses"] == 0
    assert report["comparisons"][0]["verdict"] == "TIE_QUALITY"


def test_aggregate_report_summarizes_resource_metadata(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solutions"
    ours = row("our-dispatch-v2", "solomon", "C101", 10, 100.0, 900)
    ours["solutionPath"] = write_solution(solution_dir, "ours", 900, False)
    baseline = row("ortools-baseline", "solomon", "C101", 10, 100.0, 950)
    write_results(input_dir, [ours, baseline])

    report = build_aggregate(input_dir)
    ours_summary = next(item for item in report["solverSummaries"] if item["solver"] == "our-dispatch-v2")
    resource = ours_summary["resourceSummary"]

    assert resource["metadataCount"] == 1
    assert resource["overrunRate"] == 0.0
    assert resource["wallClockOverrunRate"] == 0.0
    assert resource["solverOverrunRate"] == 0.0
    assert resource["budgetUsedP95Ms"] == 900.0
    assert resource["wallClockOverheadP95Ms"] == 0.0
    assert resource["stageRuntimeP95Ms"]["portfolio-candidates"] == 900.0
    assert resource["stageFeasibleCandidateRatioMean"]["portfolio-candidates"] == 0.5


def test_gate_allows_solver_overrun_inside_wall_clock_slack(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    report_dir = tmp_path / "report"
    solution_dir = tmp_path / "solutions"
    ours = row("our-dispatch-v2", "solomon", "C101", 10, 100.0, 700)
    ours["solutionPath"] = write_solution(solution_dir, "ours", 1200, False, solver_limit_ms=1000, wall_allowed_ms=1500)
    baseline = row("ortools-baseline", "solomon", "C101", 10, 100.0, 800)
    write_results(input_dir, [ours, baseline])
    aggregate = build_aggregate(input_dir)
    report_dir.mkdir()
    (report_dir / "phase15_large_benchmark_report.json").write_text(json.dumps(aggregate), encoding="utf-8")

    gate = build_gate(report_dir, 15_000, 0.0, 0.0)

    assert gate["verdict"] == "PASS"
    assert "phase15-wall-clock-overrun-rate-too-high" not in gate["blockers"]


def test_gate_fails_on_wall_clock_overrun_rate(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    report_dir = tmp_path / "report"
    solution_dir = tmp_path / "solutions"
    ours = row("our-dispatch-v2", "solomon", "C101", 10, 100.0, 700)
    ours["solutionPath"] = write_solution(solution_dir, "ours", 1600, True, solver_limit_ms=1000, wall_allowed_ms=1500)
    baseline = row("ortools-baseline", "solomon", "C101", 10, 100.0, 800)
    write_results(input_dir, [ours, baseline])
    aggregate = build_aggregate(input_dir)
    report_dir.mkdir()
    (report_dir / "phase15_large_benchmark_report.json").write_text(json.dumps(aggregate), encoding="utf-8")

    gate = build_gate(report_dir, 15_000, 0.0, 0.0)

    assert gate["verdict"] == "FAIL"
    assert "phase15-wall-clock-overrun-rate-too-high" in gate["blockers"]
