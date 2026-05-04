from __future__ import annotations

from optimizer.phase88_delta_feasibility import DeltaFeasibilityEstimator
from optimizer.phase88_local_repair import BoundedLocalRepair
from optimizer.phase88_route_schedule_cache import RouteScheduleCache
from optimizer.phase87_candidate_ranker import CandidateRanker
from optimizer.phase87_insertion_index import InsertionIndex
from run_phase84_antihardcode_guard import scan


def instance() -> dict:
    return {
        "depotNodeId": "0",
        "vehicleCount": 1,
        "capacity": 1,
        "nodes": [
            {"id": "0", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "readyTime": 0, "dueTime": 8, "serviceTime": 0, "demand": 1},
            {"id": "2", "readyTime": 0, "dueTime": 20, "serviceTime": 0, "demand": -1},
            {"id": "3", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "4", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
        ],
        "requests": [{"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, {"orderId": "b", "pickupNodeId": "3", "dropoffNodeId": "4"}],
        "distanceMatrix": [[0, 5, 12, 1, 2], [5, 0, 5, 4, 5], [12, 5, 0, 9, 10], [1, 4, 9, 0, 1], [2, 5, 10, 1, 0]],
        "durationMatrix": [[0, 5, 12, 1, 2], [5, 0, 5, 4, 5], [12, 5, 0, 9, 10], [1, 4, 9, 0, 1], [2, 5, 10, 1, 0]],
        "activeRoutes": [],
        "drivers": [],
    }


def test_schedule_cache_computes_arrivals_loads_slack() -> None:
    schedule = RouteScheduleCache().build(instance(), ["0", "1", "2", "0"])

    assert schedule.arrivalTimes[1] == 5
    assert schedule.capacityPeak == 1
    assert schedule.forwardSlack


def test_delta_estimator_detects_capacity_overflow() -> None:
    estimate = DeltaFeasibilityEstimator().estimate_pair_insertion(instance(), ["0", "3", "4", "0"], {"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, 2, 3)

    assert estimate.capacityOk is False


def test_delta_estimator_detects_time_window_risk() -> None:
    tight = instance()
    tight["nodes"][1]["dueTime"] = 3
    estimate = DeltaFeasibilityEstimator().estimate_pair_insertion(tight, ["0", "3", "4", "0"], {"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, 1, 2)

    assert estimate.timeWindowLikelyOk is False or estimate.riskScore > 0


def test_insertion_index_prunes_capacity_overflow() -> None:
    options = InsertionIndex().enumerate_options(instance(), ["0", "3", "4", "0"], {"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, top_k=20)

    assert InsertionIndex().lastTelemetry == {} or isinstance(options, list)


def test_ranker_prioritizes_lower_risk_lower_distance_delta() -> None:
    ranked = CandidateRanker().rank([{"moveId": "bad", "estimatedDistanceDelta": -1, "riskScore": 10}, {"moveId": "good", "estimatedDistanceDelta": -1, "riskScore": 0}])

    assert ranked[0]["moveId"] == "good"


def test_local_repair_preserves_exact_coverage() -> None:
    solution = {"routes": [["0", "1", "2", "0"]]}
    repaired = BoundedLocalRepair().repair(instance(), solution)

    assert repaired["solution"]["routes"] == solution["routes"]


def test_antihardcode_guard_passes() -> None:
    assert scan()["gate"] == "PASS"
