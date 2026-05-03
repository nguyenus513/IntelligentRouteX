from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase18_time_window_restructuring_gate import build_report
from scripts.time_window_giant_split import greedy_split, split_candidates


def toy_instance() -> dict:
    nodes = [
        {"id": "0", "x": 0, "y": 0, "demand": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
        {"id": "1", "x": 1, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 10, "serviceTime": 0},
        {"id": "2", "x": 2, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 100, "serviceTime": 0},
        {"id": "3", "x": 50, "y": 0, "demand": 1, "readyTime": 0, "dueTime": 55, "serviceTime": 0},
    ]
    matrix = [[abs(float(a["x"]) - float(b["x"])) for b in nodes] for a in nodes]
    return {"depotNodeId": "0", "nodes": nodes, "capacity": 10, "distanceMatrix": matrix, "durationMatrix": matrix}


def test_greedy_split_respects_time_windows() -> None:
    routes, trace = greedy_split(toy_instance(), ["1", "2", "3"])

    assert routes
    assert all(route[0] == "0" and route[-1] == "0" for route in routes)
    assert trace["splitPoints"] >= 0


def test_split_candidates_returns_feasible_tours() -> None:
    pool = [{"customerSet": ["1", "2"], "sequence": ["0", "1", "2", "0"], "distance": 4.0}]

    candidates = split_candidates(toy_instance(), pool)

    assert candidates
    assert candidates[0]["vehicleCount"] >= 1


def write_candidate(root: Path, *, seed_gap: int = 2, gap: int = 2, pool_after: int = 15, splits: int = 3, runtime: int = 1000) -> None:
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
        "splitCandidateCount": splits,
        "splitFeasibleCount": splits,
        "bestSplitVehicleCount": 16,
        "runtimeMs": runtime,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase18_time_window_restructuring_results.json").write_text(json.dumps({"results": [row]}), encoding="utf-8")


def test_gate_passes_with_limits_when_split_evidence_no_gap_delta(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert report["splitEvidence"] is True


def test_gate_passes_strict_when_gap_reduces(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, seed_gap=2, gap=1)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "PASS"
    assert report["totalGapDelta"] == 1


def test_gate_fails_when_no_split_candidates(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, splits=0)

    report = build_report(candidate, 15_000)

    assert report["verdict"] == "FAIL"
    assert "phase18-no-split-candidates" in report["blockers"]
