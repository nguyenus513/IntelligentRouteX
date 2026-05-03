from __future__ import annotations

from pathlib import Path

from scripts.run_phase10_gap_targets import main, planned_commands


def test_phase10_runner_dry_run_plans_target_suites(tmp_path: Path) -> None:
    assert main(["--output-dir", str(tmp_path), "--dry-run"]) == 0


def test_phase10_runner_targets_known_gap_instances(tmp_path: Path) -> None:
    commands = planned_commands(tmp_path, "15s", "auto")

    text = "\n".join(" ".join(command) for command in commands)
    assert "--suite solomon --instances RC101" in text
    assert "--suite li-lim --instances LR101,LRC101" in text
    assert "our-dispatch-v2" in text
