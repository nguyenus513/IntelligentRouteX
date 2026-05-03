from __future__ import annotations

from scripts.run_community_benchmark_phase8 import main


def test_phase8_runner_dry_run_plans_both_suites(tmp_path):
    assert main(["--output-dir", str(tmp_path), "--dry-run"]) == 0
