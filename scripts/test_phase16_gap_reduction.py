from __future__ import annotations

import json
from pathlib import Path

from scripts.external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from scripts.build_phase16_gap_reduction_gate import build_report


def test_short_budget_policy_allocates_full_construction() -> None:
    solver = DispatchV2ExternalBenchmarkSolver()

    assert solver._fixed_probe_time_limit(3_000) == 0
    assert solver._construction_time_limit(3_000) == 3_000
    assert solver._fixed_probe_time_limit(5_000) == 0
    assert solver._construction_time_limit(5_000) == 5_000
    assert solver._fixed_probe_time_limit(6_000) > 0
    assert solver._construction_time_limit(6_000 - solver._fixed_probe_time_limit(6_000)) > 1


def write_phase16_candidate(root: Path, *, mode: str = "short-budget-parity", construction: int = 3000, consolidation: int = 0) -> None:
    rows = [
        {
            "suite": "solomon",
            "instance": "RC101",
            "solver": "our-dispatch-v2",
            "feasible": True,
            "vehicleCount": 16,
            "bestKnownVehicleCount": 14,
            "totalDistance": 1721.0,
            "runtimeMs": 3100,
            "verdict": "PASS_WITH_LIMITS",
            "capacityViolationCount": 0,
            "timeWindowViolationCount": 0,
            "pickupBeforeDropoffViolationCount": 0,
            "vehicleLimitViolationCount": 0,
            "unservedRequestCount": 0,
        },
        {
            "suite": "solomon",
            "instance": "RC101",
            "solver": "ortools-baseline",
            "feasible": True,
            "vehicleCount": 16,
            "bestKnownVehicleCount": 14,
            "totalDistance": 1721.0,
            "runtimeMs": 3000,
            "verdict": "PASS_WITH_LIMITS",
            "capacityViolationCount": 0,
            "timeWindowViolationCount": 0,
            "pickupBeforeDropoffViolationCount": 0,
            "vehicleLimitViolationCount": 0,
            "unservedRequestCount": 0,
        },
    ]
    payload = {
        "schemaVersion": "phase15-large-benchmark-results/v1",
        "tier": "gap",
        "completedCells": 2,
        "totalCells": 2,
        "results": rows,
    }
    phase16 = {
        "schemaVersion": "phase16-gap-reduction-results/v1",
        "timeLimitMs": 3000,
        "phase15Payload": payload,
        "budgetRows": [
            {
                "suite": "solomon",
                "instance": "RC101",
                "vehicleCount": 16,
                "runtimeMs": 3100,
                "budgetPolicy": {"mode": mode, "constructionMs": construction, "consolidationMs": consolidation},
            }
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase15_large_benchmark_results.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / "phase16_gap_reduction_results.json").write_text(json.dumps(phase16), encoding="utf-8")


def test_phase16_gate_passes_with_short_budget_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    output = tmp_path / "gate"
    write_phase16_candidate(candidate)

    report = build_report(candidate, output, 15_000)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert report["blockers"] == []


def test_phase16_gate_fails_when_short_budget_starved(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    output = tmp_path / "gate"
    write_phase16_candidate(candidate, construction=2500)

    report = build_report(candidate, output, 15_000)

    assert report["verdict"] == "FAIL"
    assert "phase16-short-budget-construction-starved" in report["blockers"]
