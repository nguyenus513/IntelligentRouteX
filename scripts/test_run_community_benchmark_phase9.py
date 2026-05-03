from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from scripts.run_community_benchmark_phase9 import main, planned_commands


def test_phase9_runner_dry_run_plans_official_smoke(tmp_path: Path) -> None:
    assert main(["--output-dir", str(tmp_path), "--dry-run"]) == 0


def test_phase9_runner_core_with_baselines_plans_all_solvers(tmp_path: Path) -> None:
    args = Namespace(
        output_dir=str(tmp_path),
        preset="official-core",
        time_limit="15s",
        data_source="auto",
        include_ortools=True,
        include_pyvrp=True,
    )

    commands = planned_commands(args)

    assert len(commands) == 6
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "--instances C101,C201,R101,R201,RC101,RC201" in command_text
    assert "--instances LC101,LC102,LC103,LR101,LR102,LR103,LRC101,LRC102,LRC103" in command_text
    assert "ortools-baseline" in command_text
    assert "pyvrp-baseline" in command_text
