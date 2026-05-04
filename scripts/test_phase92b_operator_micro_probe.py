from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from run_phase92b_operator_micro_probe import evaluate_gate, extract_lilim_subproblem, phase91_compatible_rows_for_test, run, selected_requests_by_features
from test_phase90_final_quality_completion import instance


def test_micro_subproblem_extractor_uses_features_only() -> None:
    inst = instance()
    inst["instanceName"] = "DO_NOT_BRANCH_ON_THIS"
    subproblem = extract_lilim_subproblem(inst, 1)

    assert subproblem["schemaVersion"] == "external-benchmark-normalized/v1"
    assert len(subproblem["requests"]) == 1
    assert subproblem["instanceName"] == "phase92b_micro_subproblem"


def test_hard_wall_clock_writes_partial_artifact(tmp_path: Path) -> None:
    summary = run(Namespace(source="phase90-opportunity", time_limit="5s", hard_wall_clock_ms=1, max_instances=1, max_operators=0, output_dir=str(tmp_path)))

    assert (tmp_path / "phase92b_operator_micro_probe_summary.json").exists()
    assert summary["safeReturn"] is True
    assert summary["earlyStopReason"] == "hard-wall-clock"


def test_phase91_compatible_rows_are_produced() -> None:
    rows = [{"instance": "x", "budgetTelemetry": [{"operator": "op", "generatedCandidates": 1, "candidateChecks": 0, "noGenerationReason": "no-feasible-move"}]}]
    converted = phase91_compatible_rows_for_test(rows)

    assert converted["unknownCount"] == 0
    assert converted["rows"]


def test_no_instance_name_branch() -> None:
    source = Path("scripts/run_phase92b_operator_micro_probe.py").read_text(encoding="utf-8")
    forbidden = ["instance ==", "instanceName ==", "startswith(\"LRC", "startswith('LRC"]

    assert not any(token in source for token in forbidden)


def test_gate_pass_strong_with_generation_and_feasible() -> None:
    assert evaluate_gate({"antiHardcodeGate": "PASS", "hardViolations": 0, "unknownCount": 0, "hardWallClockExpired": False, "generatedCandidates": 1, "checkerFeasibleCandidates": 1}) == "PASS_STRONG"
