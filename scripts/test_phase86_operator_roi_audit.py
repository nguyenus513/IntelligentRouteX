from __future__ import annotations

from run_phase84_antihardcode_guard import scan
from run_phase86_operator_roi_audit import classify_rejection, recommendation_engine


def test_classifies_objective_not_improved() -> None:
    assert classify_rejection("objective-not-improved") == "no-quality-improvement"


def test_classifies_distance_improved_but_objective_rejected() -> None:
    assert classify_rejection("objective-not-improved", distance_delta=-1, objective_delta=1) == "distance-improved-but-objective-rejected"


def test_classifies_hard_violation_rejection() -> None:
    assert classify_rejection("hard-violation") == "hard-violation-rejected"


def test_classifies_candidate_cap() -> None:
    assert classify_rejection("candidate-cap") == "candidate-cap"


def test_recommendation_engine_suggests_objective_calibration() -> None:
    rows = [{"generatedCandidates": 3, "feasibleCandidates": 2, "acceptedCandidates": 0}]
    recommendations = recommendation_engine(rows, {"distance-improved-but-objective-rejected": 2})

    assert any("objective weight calibration" in item for item in recommendations)


def test_antihardcode_guard_still_passes() -> None:
    assert scan()["gate"] == "PASS"
