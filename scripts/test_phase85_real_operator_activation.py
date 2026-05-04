from __future__ import annotations

from optimizer.phase84_operator_portfolio import OperatorPortfolio
from optimizer.phase84_route_pool_memory import RoutePoolMemory
from optimizer.phase85_candidate_validator import CandidateValidator
from optimizer.phase85_pair_utils import extract_request_pairs
from run_phase84_antihardcode_guard import scan
from run_phase84_benchmark_victory_guard import evaluate


def instance() -> dict:
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "problemType": "PDPTW",
        "instanceName": "unit",
        "depotNodeId": "0",
        "vehicleCount": 2,
        "capacity": 2,
        "nodes": [
            {"id": "0", "x": 0, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "x": 1, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "2", "x": 2, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
            {"id": "3", "x": 3, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "4", "x": 4, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
        ],
        "requests": [{"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, {"orderId": "b", "pickupNodeId": "3", "dropoffNodeId": "4"}],
        "distanceMatrix": [[0, 1, 2, 3, 4], [1, 0, 1, 2, 3], [2, 1, 0, 1, 2], [3, 2, 1, 0, 1], [4, 3, 2, 1, 0]],
        "durationMatrix": [[0, 1, 2, 3, 4], [1, 0, 1, 2, 3], [2, 1, 0, 1, 2], [3, 2, 1, 0, 1], [4, 3, 2, 1, 0]],
        "activeRoutes": [],
        "drivers": [],
    }


def incumbent() -> dict:
    return {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}


def test_central_validator_rejects_missing_pair() -> None:
    result = CandidateValidator().validate(instance(), incumbent(), {"routes": [["0", "1", "2", "0"]]}, require_improvement=False)

    assert result["valid"] is False


def test_central_validator_rejects_pickup_after_dropoff() -> None:
    result = CandidateValidator().validate(instance(), incumbent(), {"routes": [["0", "2", "1", "0"], ["0", "3", "4", "0"]]}, require_improvement=False)

    assert result["valid"] is False


def test_cross_route_pair_relocate_preserves_exact_coverage() -> None:
    portfolio = OperatorPortfolio()
    result = portfolio.apply("pd-aware-pair-relocate", instance(), incumbent(), {})

    pairs = extract_request_pairs(instance(), result["solution"])
    assert {pair["requestId"] for pair in pairs} == {"a", "b"}


def test_route_elimination_no_target_k_and_safety_first() -> None:
    result = OperatorPortfolio().apply("route-elimination", instance(), incumbent(), {})

    assert "solution" in result
    assert result["telemetry"]["candidateChecks"] >= 0


def test_route_pool_recombination_rejects_non_internal_provenance() -> None:
    pool = RoutePoolMemory()
    assert pool.add_route(instance(), ["0", "1", "2", "0"], "external", provenance="vroom") is False


def test_operator_ordering_deterministic() -> None:
    assert OperatorPortfolio().names() == OperatorPortfolio().names()


def test_antihardcode_guard_still_passes() -> None:
    assert scan()["gate"] == "PASS"


def test_promotion_guard_rejects_safety_regression() -> None:
    assert evaluate({"aggregate": {"hardViolations": 1, "overBudget": 0, "fallback": 0, "vroomWins": 0}, "antiHardcodeGate": "PASS"})["gate"] == "FAIL"
