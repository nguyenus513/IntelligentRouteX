from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from run_phase92a_live_operator_probe import evaluate_gate, phase91_compatible_summary, run


def test_hard_wall_clock_guard_writes_partial_artifact(tmp_path: Path) -> None:
    summary = run(Namespace(suite="li-lim-8case", max_instances=1, time_limit="30s", hard_wall_clock_ms=1, output_dir=str(tmp_path)))

    assert (tmp_path / "phase92a_live_operator_probe_summary.json").exists()
    assert summary["safeReturn"] is True
    assert summary["earlyStopReason"] == "hard-wall-clock"


def test_fresh_telemetry_converts_to_phase91_rows() -> None:
    rows = [{"instance": "x", "budgetTelemetry": [{"operator": "op", "generatedCandidates": 1, "finalCandidatesProduced": 1, "finalCandidatesChecked": 1, "checkerFeasibleCandidates": 1, "objectiveImprovingCandidates": 0}]}]
    converted = phase91_compatible_summary(rows)

    assert converted["unknownCount"] == 0
    assert converted["rows"][0]["classification"] == "final-candidate-not-improving"


def test_unknown_classifications_are_rejected() -> None:
    assert evaluate_gate({"hardViolations": 0, "antiHardcodeGate": "PASS", "unknownCount": 1}) == "FAIL"


def test_no_instance_name_branch() -> None:
    source = Path("scripts/run_phase92a_live_operator_probe.py").read_text(encoding="utf-8")
    forbidden = ["instance ==", "instanceName ==", "startswith(\"LRC", "startswith('LRC"]

    assert not any(token in source for token in forbidden)
