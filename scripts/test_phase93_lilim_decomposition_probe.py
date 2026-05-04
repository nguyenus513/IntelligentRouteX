from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from run_phase93_lilim_decomposition_probe import active_route_count, exact_request_coverage, extract_subproblem, recombine_solution, run, select_requests_by_features, strict_recombination_validator
from test_phase90_final_quality_completion import instance


def test_subproblem_extractor_keeps_complete_pickup_dropoff_pairs() -> None:
    inst = instance()
    selected = select_requests_by_features(inst, 1)
    subproblem, _ = extract_subproblem(inst, selected)
    node_ids = {str(node["id"]) for node in subproblem["nodes"]}

    assert len(subproblem["requests"]) == 1
    for request in subproblem["requests"]:
        assert str(request["pickupNodeId"]) in node_ids
        assert str(request["dropoffNodeId"]) in node_ids


def test_extractor_uses_features_only() -> None:
    inst = instance()
    inst["instanceName"] = "DO_NOT_BRANCH"
    selected = select_requests_by_features(inst, 1)

    assert selected


def test_recombination_preserves_exact_coverage() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    selected = [inst["requests"][0]]
    candidate = recombine_solution(inst, incumbent, selected, {"routes": [["0", "1", "2", "0"]]})

    assert exact_request_coverage(inst, candidate)


def test_objective_regression_rejected() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "3", "4", "2", "0"]]}
    worse = {"routes": [["0", "1", "2", "3", "4", "0"]]}

    assert UnifiedNaturalObjective().improves(inst, incumbent, worse) is False


def test_hard_wall_clock_writes_safe_artifact(tmp_path: Path) -> None:
    summary = run(Namespace(suite="phase90-opportunity-smoke", subproblem_count=1, request_limit=1, subproblem_time_limit="1s", hard_wall_clock_ms=0, output_dir=str(tmp_path)))

    assert (tmp_path / "phase93_lilim_decomposition_probe_summary.json").exists()
    assert summary["subproblemCount"] >= 0


def test_no_instance_name_branch() -> None:
    source = Path("scripts/run_phase93_lilim_decomposition_probe.py").read_text(encoding="utf-8")
    forbidden = ["instance ==", "instanceName ==", "startswith(\"LRC", "startswith('LRC"]

    assert not any(token in source for token in forbidden)


def test_recombination_rejects_subproblem_route_overflow_before_check_solution() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    candidate = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

    result = strict_recombination_validator(inst, incumbent, candidate, affected_route_count=1, candidate_subproblem_route_count=2)

    assert result == {"valid": False, "reason": "subproblem-route-slot-overflow"}


def test_same_slot_polish_preserves_active_route_count() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    selected = inst["requests"]
    candidate = recombine_solution(inst, incumbent, selected, {"routes": [["0", "1", "3", "4", "2", "0"]]})

    assert active_route_count(candidate) == active_route_count(incumbent)


def test_slot_compression_reduces_active_route_count_on_synthetic_case() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    selected = inst["requests"]
    candidate = recombine_solution(inst, incumbent, selected, {"routes": [["0", "1", "3", "4", "2", "0"]]})

    assert active_route_count(candidate) < active_route_count(incumbent)
