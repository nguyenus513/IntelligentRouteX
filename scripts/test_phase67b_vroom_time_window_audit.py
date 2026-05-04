from __future__ import annotations

import run_phase67b_vroom_time_window_audit as phase67b


def step(vroom=None, distance=None, duration=None, waiting=0, service=1, vroom_service=1, step_type="pickup") -> dict:
    return {
        "stepType": step_type,
        "vroomViolationType": vroom,
        "distanceViolationType": distance,
        "durationViolationType": duration,
        "vroomWaitingTime": waiting,
        "serviceTime": service,
        "vroomService": vroom_service,
        "travelFromPreviousDistance": 1,
        "travelFromPreviousDuration": 1,
    }


def classify(steps: list[dict]) -> str:
    return phase67b.classify_instance([{"routeIndex": 0, "steps": steps}], {})["classification"]


def test_detects_late_arrival_true_vroom_violation() -> None:
    assert classify([step(vroom="late-arrival")]) == "vroom-true-time-window-violation"


def test_detects_waiting_semantics_mismatch() -> None:
    assert classify([step(distance="early-without-wait", waiting=5)]) == "internal-checker-waiting-semantics-mismatch"


def test_detects_duration_vs_distance_mismatch() -> None:
    assert classify([step(distance="late-arrival", duration=None)]) == "matrix-duration-mismatch"
    assert classify([step(distance=None, duration="late-arrival")]) == "matrix-duration-mismatch"


def test_detects_service_time_mismatch() -> None:
    assert classify([step(service=2, vroom_service=1)]) == "service-time-semantics-mismatch"


def test_detects_depot_window_mismatch() -> None:
    assert classify([step(vroom="late-arrival", step_type="start")]) == "vroom-true-time-window-violation"


def test_step_violation_types() -> None:
    assert phase67b.classify_step_violation(12, 0, 10, 0) == "late-arrival"
    assert phase67b.classify_step_violation(5, 10, 20, 0) == "early-without-wait"
    assert phase67b.classify_step_violation(9, 0, 10, 2) == "service-pushes-past-due"
