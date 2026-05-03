from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase20_reference_or_offline_solver_gate import build_report
from scripts.run_phase20_reference_or_offline_solver import evaluate_candidate, import_solution_routes


def toy_instance() -> dict:
    nodes = [
        {"id": "0", "x": 0, "y": 0, "demand": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
        {"id": "1", "x": 1, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
    ]
    matrix = [[abs(float(a["x"]) - float(b["x"])) for b in nodes] for a in nodes]
    return {"depotNodeId": "0", "nodes": nodes, "capacity": 10, "distanceMatrix": matrix, "durationMatrix": matrix, "bestKnown": {"vehicleCount": 1, "objective": 2.0}}


def test_evaluate_and_import_reference_route() -> None:
    instance = toy_instance()
    solution = {"routes": [["0", "1", "0"]]}
    route_pool = []

    evaluated = evaluate_candidate(instance, solution, "unit")
    imported = import_solution_routes(instance, route_pool, solution, "unit")

    assert evaluated["feasible"] is True
    assert evaluated["vehicleCount"] == 1
    assert imported == 1
    assert route_pool[0]["sourceRun"] == "unit"


def write_candidate(root: Path, *, seed_gap: int = 2, gap: int = 2, offline_runs: int = 4, pool_after: int = 20, runtime: int = 1000, feasible: bool = True) -> None:
    row = {
        "suite": "solomon",
        "instance": "RC101",
        "status": "PASS" if feasible else "FAIL",
        "feasible": feasible,
        "seedVehicleGap": seed_gap,
        "vehicleGap": gap,
        "hardViolationCount": 0 if feasible else 1,
        "referenceRouteAvailable": False,
        "referenceRouteFeasible": False,
        "offlineRunCount": offline_runs,
        "offlineFeasibleRunCount": offline_runs,
        "bestOfflineVehicleCount": 16,
        "routePoolSizeBefore": 10,
        "routePoolSizeAfter": pool_after,
        "setPartitioningProducedSolution": True,
        "bestLabel": "phase20-set-partitioning-reference-offline-pool",
        "runtimeMs": runtime,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase20_reference_offline_results.json").write_text(json.dumps({"results": [row]}), encoding="utf-8")


def test_gate_passes_with_limits_when_offline_evidence_no_gap_delta(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    report = build_report(candidate, 60_000)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert report["referenceOrOfflineEvidence"] is True


def test_gate_passes_strict_when_gap_reduces(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, seed_gap=2, gap=1)

    report = build_report(candidate, 60_000)

    assert report["verdict"] == "PASS"
    assert report["totalGapDelta"] == 1


def test_gate_fails_when_no_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, offline_runs=0)

    report = build_report(candidate, 60_000)

    assert report["verdict"] == "FAIL"
    assert "phase20-no-reference-or-offline-evidence" in report["blockers"]


def test_gate_fails_when_infeasible(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, feasible=False)

    report = build_report(candidate, 60_000)

    assert report["verdict"] == "FAIL"
    assert "phase20-final-infeasible" in report["blockers"]
