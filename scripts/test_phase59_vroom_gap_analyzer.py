from __future__ import annotations

import inspect

import run_phase59_vroom_gap_analyzer as phase59


def row(classification: str, vroom_vehicles: int | None, challenger_vehicles: int | None, vroom_distance: float | None, challenger_distance: float | None, vroom_hard: int = 0, challenger_hard: int = 0) -> dict:
    return {
        "instance": "case",
        "classification": classification,
        "champion": {"hardViolations": vroom_hard, "vehicleCount": vroom_vehicles, "totalDistance": vroom_distance},
        "challenger": {"hardViolations": challenger_hard, "vehicleCount": challenger_vehicles, "totalDistance": challenger_distance, "runtimeMs": 1000},
        "vroomRuntimeMs": 500,
    }


def test_detects_vehicle_count_gap() -> None:
    result = phase59.classify_gap(row("vroom-win", 10, 11, 100.0, 90.0))

    assert result == "vroom-quality-win-vehicle-count"


def test_detects_distance_gap() -> None:
    result = phase59.classify_gap(row("vroom-win", 10, 10, 100.0, 104.0), distance_tolerance=0.01)

    assert result == "vroom-quality-win-distance"


def test_detects_challenger_feasibility_advantage() -> None:
    result = phase59.classify_gap(row("vroom-hard-fail", 9, 10, 100.0, 130.0, vroom_hard=1))

    assert result == "challenger-better-feasibility"


def test_handles_vroom_timeout() -> None:
    result = phase59.classify_gap(row("vroom-timeout", None, 10, None, 130.0, vroom_hard=1))

    assert result == "vroom-timeout"


def test_handles_vroom_unavailable_without_quality_tie() -> None:
    result = phase59.classify_gap(row("vroom-unavailable", None, 10, None, 130.0))

    assert result == "vroom-unavailable"


def test_analyze_rows_recommends_stability_and_quality_work() -> None:
    summary = phase59.analyze_rows(
        [
            row("vroom-hard-fail", 9, 10, 100.0, 130.0, vroom_hard=1),
            row("vroom-win", 10, 11, 100.0, 90.0),
            row("vroom-win", 10, 10, 100.0, 104.0),
        ]
    )

    assert summary["classificationCounts"]["challenger-better-feasibility"] == 1
    assert summary["classificationCounts"]["vroom-quality-win-vehicle-count"] == 1
    assert summary["classificationCounts"]["vroom-quality-win-distance"] == 1
    assert "route elimination or route-pool fast mode" in summary["recommendations"]
    assert "bounded distance polish" in summary["recommendations"]


def test_no_instance_name_branch() -> None:
    source = inspect.getsource(phase59)
    assert "startswith(\"LRC\")" not in source
    assert "startswith('LRC')" not in source
    assert "instanceName ==" not in source
