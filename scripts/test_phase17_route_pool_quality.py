from __future__ import annotations

import json
from pathlib import Path

from scripts.analyze_phase17_route_pool_gaps import coverage_stats, route_size_histogram
from scripts.build_phase17_route_pool_quality_gate import build_report


def tiny_instance() -> dict:
    return {
        "depotNodeId": "0",
        "nodes": [
            {"id": "0", "x": 0, "y": 0, "demand": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
            {"id": "1", "x": 1, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
            {"id": "2", "x": 2, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
            {"id": "3", "x": 3, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
        ],
    }


def test_route_pool_diagnostics_detect_low_coverage() -> None:
    route_pool = [
        {"customerSet": ["1", "2"], "sequence": ["0", "1", "2", "0"]},
        {"customerSet": ["1"], "sequence": ["0", "1", "0"]},
    ]

    coverage = coverage_stats(tiny_instance(), route_pool)
    histogram = route_size_histogram(route_pool)

    assert coverage["coverageMin"] == 0
    assert "3" in coverage["lowCoverageCustomers"]
    assert histogram == {"1": 1, "2": 1}


def write_candidate(root: Path, *, seed_gap: int = 2, gap: int = 2, pool_after: int = 12, runtime: int = 1000) -> None:
    row = {
        "suite": "solomon",
        "instance": "RC101",
        "status": "PASS",
        "feasible": True,
        "seedVehicleGap": seed_gap,
        "vehicleGap": gap,
        "hardViolationCount": 0,
        "routePoolSizeBefore": 10,
        "routePoolSizeAfter": pool_after,
        "setPartitioningProducedSolution": True,
        "runtimeMs": runtime,
        "diagnosticsAfter": {
            "actionableNextStep": "expand-low-coverage-customer-route-variants",
            "coverage": {"lowCoverageCustomerCount": 3},
            "mergeDiagnostics": {"mergeRejectReasons": {"time-window": 5}},
        },
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase17_route_pool_quality_results.json").write_text(json.dumps({"results": [row]}), encoding="utf-8")


def test_gate_passes_with_limits_when_actionable_without_gap_delta(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert report["actionableDiagnostics"] is True


def test_gate_passes_strict_when_gap_reduces(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, seed_gap=2, gap=1)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "PASS"
    assert report["totalGapDelta"] == 1


def test_gate_fails_when_pool_not_expanded(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, pool_after=10)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "FAIL"
    assert "phase17-route-pool-not-expanded" in report["blockers"]
