from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase21_medium_benchmark_gate import build_report


def write_phase21(root: Path, *, wins: int = 1, losses: int = 0, runtime_p95: int = 5000, instance_limit: int | None = None) -> None:
    aggregate = {
        "completedCells": 4,
        "totalCells": 4,
        "wins": wins,
        "ties": 4 - wins - losses,
        "losses": losses,
        "solverSummaries": [
            {
                "solver": "our-dispatch-v2",
                "rowCount": 2,
                "passCount": 1,
                "passWithLimitsCount": 1,
                "failCount": 0,
                "evidenceGapCount": 0,
                "feasibleCount": 2,
                "vehicleGapSum": 2,
                "hardViolationCount": 0,
                "runtimeP50Ms": 4000,
                "runtimeP95Ms": runtime_p95,
                "runtimeP99Ms": runtime_p95,
            }
        ],
    }
    payload = {
        "schemaVersion": "phase21-medium-benchmark-results/v1",
        "instanceLimit": instance_limit,
        "aggregateReport": aggregate,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase21_medium_benchmark_results.json").write_text(json.dumps(payload), encoding="utf-8")


def test_gate_passes_strict_with_win_no_losses(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_phase21(candidate, wins=1, losses=0)

    report = build_report(candidate, 15_000, False)

    assert report["verdict"] == "PASS"


def test_gate_passes_with_limits_when_tie_only(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_phase21(candidate, wins=0, losses=0)

    report = build_report(candidate, 15_000, False)

    assert report["verdict"] == "PASS_WITH_LIMITS"


def test_gate_fails_on_loss(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_phase21(candidate, wins=0, losses=1)

    report = build_report(candidate, 15_000, False)

    assert report["verdict"] == "FAIL"
    assert "phase21-comparison-losses" in report["blockers"]


def test_gate_fails_when_full_medium_required_but_limited(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_phase21(candidate, instance_limit=2)

    report = build_report(candidate, 15_000, True)

    assert report["verdict"] == "FAIL"
    assert "phase21-not-full-medium" in report["blockers"]
