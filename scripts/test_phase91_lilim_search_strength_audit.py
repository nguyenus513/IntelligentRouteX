from __future__ import annotations

from pathlib import Path

from run_phase91_lilim_search_strength_audit import classify_operator


def test_classify_intermediate_only_operator() -> None:
    row = {"generatedCandidates": 1, "finalCandidatesProduced": 0, "candidateChecks": 0, "intermediateFeasibleStates": 2}

    assert classify_operator(row) == "intermediate-only"


def test_classify_deadline_cap_operator() -> None:
    row = {"generatedCandidates": 10, "earlyStopReason": "deadline", "safeReturn": True}

    assert classify_operator(row) == "deadline-cap"


def test_classify_final_candidate_not_improving() -> None:
    row = {"generatedCandidates": 3, "finalCandidatesProduced": 3, "finalCandidatesChecked": 3, "checkerFeasibleCandidates": 3, "objectiveImprovingCandidates": 0}

    assert classify_operator(row) == "final-candidate-not-improving"


def test_classify_productive_operator() -> None:
    row = {"acceptedCandidates": 1, "objectiveImprovingCandidates": 1}

    assert classify_operator(row) == "productive"


def test_classify_repair_failure_operator() -> None:
    row = {"generatedCandidates": 0, "finalCandidatesProduced": 0, "candidateChecks": 0, "repairFailReasons": {"regret_2_repair-failed": 2}}

    assert classify_operator(row) == "repair-failure"


def test_no_instance_name_branch() -> None:
    source = Path("scripts/run_phase91_lilim_search_strength_audit.py").read_text(encoding="utf-8")

    forbidden = ["instance ==", "instanceName ==", "startswith(\"LRC", "startswith('LRC"]
    assert not any(token in source for token in forbidden)
