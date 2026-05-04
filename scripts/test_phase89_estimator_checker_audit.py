from __future__ import annotations

from optimizer.phase88_route_schedule_cache import RouteScheduleCache
from run_phase84_antihardcode_guard import scan
from run_phase89_estimator_checker_audit import classify_alignment, classify_pruned, normalize_violation


def test_detects_estimator_too_strict_time_window() -> None:
    assert classify_pruned({"pruneReason": "timeWindow"}) == "estimator-too-strict-time-window"


def test_detects_estimator_too_loose_time_window() -> None:
    trace = {"fullChecker": {"feasible": False, "violations": ["time-window-violation"]}, "lockValidator": {"valid": True}}

    assert classify_alignment(trace) == "estimator-too-loose-time-window"


def test_detects_capacity_overflow_violation() -> None:
    assert normalize_violation("capacity-violation") == "capacity-overflow"


def test_detects_pickup_dropoff_coverage_invalid() -> None:
    trace = {"fullChecker": {"feasible": False, "violations": ["pickup-before-dropoff-violation"]}, "lockValidator": {"valid": True}}

    assert classify_alignment(trace) == "pickup-dropoff-coverage-invalid"


def test_detects_route_structure_invalid() -> None:
    trace = {"fullChecker": {"feasible": False, "violations": ["unknown-node-in-route"]}, "lockValidator": {"valid": True}}

    assert classify_alignment(trace) == "route-structure-invalid"


def test_schedule_semantic_diff_detects_service_time_mismatch_shape() -> None:
    instance = {"nodes": [{"id": "0", "readyTime": 0, "dueTime": 100, "serviceTime": 2, "demand": 0}], "durationMatrix": [[0]], "distanceMatrix": [[0]], "depotNodeId": "0"}
    schedule = RouteScheduleCache().build(instance, ["0"])

    assert schedule.departureTimes[0] - schedule.serviceStartTimes[0] == 2


def test_antihardcode_guard_passes() -> None:
    assert scan()["gate"] == "PASS"
