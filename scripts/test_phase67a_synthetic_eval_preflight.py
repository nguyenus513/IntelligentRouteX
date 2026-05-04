from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/run_phase67a_synthetic_eval_preflight.ps1")


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_contains_regenerate_command() -> None:
    text = script_text()

    assert "scripts/generate_phase64_synthetic_food_dataset.py" in text
    assert "--seed $Seed" in text


def test_script_uses_fresh_timestamp_output() -> None:
    text = script_text()

    assert "Get-Date -Format" in text
    assert "synthetic_food_smoke_real_$RunId" in text
    assert "synthetic_food_full_real_$RunId" in text
    assert "incumbent-cache" in text


def test_script_does_not_use_dry_run_conversion_by_default() -> None:
    text = script_text()

    assert "--dry-run-conversion" not in text
    assert "--skip-vroom-run" not in text


def test_script_points_report_to_full_real_run_artifact() -> None:
    text = script_text()

    assert "--input-dir $FullOutputDir" in text
    assert "docs/benchmark/final_synthetic_food_evaluation_report.md" in text


def test_script_runs_smoke_before_full() -> None:
    text = script_text()

    assert text.index("--suite synthetic-food-smoke") < text.index("--suite synthetic-food-full")
