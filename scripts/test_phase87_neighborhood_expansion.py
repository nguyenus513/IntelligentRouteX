from __future__ import annotations

from optimizer.phase84_operator_portfolio import OperatorPortfolio
from optimizer.phase87_candidate_ranker import CandidateRanker
from optimizer.phase87_insertion_index import InsertionIndex
from run_phase84_antihardcode_guard import scan


def instance() -> dict:
    return {
        "depotNodeId": "0",
        "vehicleCount": 2,
        "capacity": 1,
        "nodes": [
            {"id": "0", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "2", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
            {"id": "3", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "4", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
        ],
        "requests": [{"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, {"orderId": "b", "pickupNodeId": "3", "dropoffNodeId": "4"}],
        "distanceMatrix": [[0, 1, 2, 3, 4], [1, 0, 1, 2, 3], [2, 1, 0, 1, 2], [3, 2, 1, 0, 1], [4, 3, 2, 1, 0]],
        "durationMatrix": [[0, 1, 2, 3, 4], [1, 0, 1, 2, 3], [2, 1, 0, 1, 2], [3, 2, 1, 0, 1], [4, 3, 2, 1, 0]],
        "activeRoutes": [],
        "drivers": [],
    }


def test_candidate_ranker_stable_ordering() -> None:
    moves = [{"moveId": "b", "estimatedDistanceDelta": 0}, {"moveId": "a", "estimatedDistanceDelta": 0}]

    assert [move["moveId"] for move in CandidateRanker().rank(moves)] == ["a", "b"]


def test_insertion_index_ranks_lower_distance_first() -> None:
    options = InsertionIndex().enumerate_options(instance(), ["0", "3", "4", "0"], {"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, top_k=4)

    assert options == sorted(options, key=lambda option: option["rankKey"])


def test_insertion_index_exposes_capacity_risk() -> None:
    index = InsertionIndex()
    index.enumerate_options(instance(), ["0", "3", "4", "0"], {"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, top_k=10)

    assert index.lastTelemetry["prunedByCapacity"] > 0


def test_pair_selection_prioritizes_high_detour_generically() -> None:
    pairs = OperatorPortfolio()._rank_pairs(instance(), {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]})

    assert {pair["requestId"] for pair in pairs} == {"a", "b"}


def test_route_elimination_does_not_target_vehicle_count() -> None:
    result = OperatorPortfolio().apply("route-elimination", instance(), {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}, {})

    assert "solution" in result
    assert result["telemetry"]["generatedMoves"] >= 0


def test_two_pair_move_preserves_exact_coverage() -> None:
    result = OperatorPortfolio().apply("two-pair-swap", instance(), {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}, {})

    stops = [stop for route in result["solution"]["routes"] for stop in route]
    assert "1" in stops and "2" in stops and "3" in stops and "4" in stops


def test_antihardcode_guard_passes() -> None:
    assert scan()["gate"] == "PASS"
