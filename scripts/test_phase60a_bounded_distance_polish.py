from __future__ import annotations

import inspect

import run_phase60a_bounded_distance_polish as phase60a


def tiny_instance() -> dict:
    nodes = [
        {"id": "0", "x": 0, "y": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0, "demand": 0},
        {"id": "3", "x": 1, "y": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0, "demand": 1},
        {"id": "4", "x": 2, "y": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0, "demand": -1},
        {"id": "1", "x": 3, "y": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0, "demand": 1},
        {"id": "2", "x": 4, "y": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0, "demand": -1},
    ]
    matrix = [[abs(float(left["x"]) - float(right["x"])) for right in nodes] for left in nodes]
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "benchmarkFamily": "synthetic",
        "instanceName": "tiny",
        "problemType": "PDPTW",
        "depotNodeId": "0",
        "vehicleCount": 2,
        "capacity": 2,
        "nodes": nodes,
        "requests": [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}],
        "distanceMatrix": matrix,
        "durationMatrix": matrix,
        "bestKnown": {},
    }


def test_intra_route_two_opt_candidate_preserves_pickup_before_dropoff_when_valid() -> None:
    instance = tiny_instance()
    valid = {"routes": [["0", "3", "4", "1", "2", "0"]]}

    coverage = phase60a.exact_pair_coverage(instance, valid)

    assert coverage["valid"]


def test_pair_relocate_preserves_exact_coverage_and_improves_distance() -> None:
    instance = tiny_instance()
    solution = {"routes": [["0", "1", "2", "3", "4", "0"]]}

    result = phase60a.bounded_distance_polish(instance, solution, "academic_certification", max_candidate_checks=80)

    assert phase60a.exact_pair_coverage(instance, result["solution"])["valid"]
    assert result["diagnostics"]["bestDistanceDelta"] < 0
    assert result["diagnostics"]["acceptedCandidates"] == 1


def test_rejects_infeasible_polish_candidate() -> None:
    instance = tiny_instance()
    invalid = {"routes": [["0", "2", "1", "3", "4", "0"]]}

    valid, reason = phase60a.validate_candidate(instance, invalid)

    assert not valid
    assert reason == "coverage-invalid"


def test_accepts_lower_distance_objective_improving_candidate() -> None:
    instance = tiny_instance()
    config = phase60a.objective_config("academic_certification")
    current = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    candidate = {"routes": [["0", "3", "4", "1", "2", "0"]]}
    reject_reasons: dict[str, int] = {}

    accepted, key, reason = phase60a.try_candidate(instance, config, current, candidate, phase60a.stable_candidate_key(instance, current, config), reject_reasons)

    assert accepted is not None
    assert key is not None
    assert reason == "accepted"


def test_deterministic_ordering_stable() -> None:
    instance = tiny_instance()
    config = phase60a.objective_config("academic_certification")
    left = {"routes": [["0", "3", "4", "1", "2", "0"]]}
    right = {"routes": [["0", "3", "4", "1", "2", "0"]]}

    assert phase60a.stable_candidate_key(instance, left, config) == phase60a.stable_candidate_key(instance, right, config)


def test_no_instance_name_branch() -> None:
    source = inspect.getsource(phase60a)
    assert "startswith(\"LRC\")" not in source
    assert "startswith('LRC')" not in source
    assert "instanceName ==" not in source
