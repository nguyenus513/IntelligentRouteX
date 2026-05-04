from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_readme_mentions_vroom_and_phase56f() -> None:
    text = read("README_BENCHMARK.md")

    assert "VROOM" in text
    assert "Phase 56F" in text
    assert "phase56f" in text


def test_readme_explains_result_interpretation() -> None:
    text = read("README_BENCHMARK.md")

    assert "Production-safe" in text
    assert "Industry-quality partial" in text
    assert "hard-fail/timeout" in text


def test_walkthrough_mentions_final_report() -> None:
    text = read("docs/benchmark/demo_walkthrough.md")

    assert "scripts/run_phase65_final_system_evaluation_report.py" in text
    assert "docs/benchmark/final_system_evaluation_report.md" in text


def test_demo_script_contains_all_key_commands() -> None:
    text = read("scripts/run_phase66_demo_all.ps1")

    assert "docker compose -f docker/vroom/docker-compose.yml up -d" in text
    assert "docker/vroom/healthcheck.ps1" in text
    assert "scripts/run_phase63_unified_benchmark_suite.py" in text
    assert "scripts/generate_phase64_synthetic_food_dataset.py" in text
    assert "scripts/run_phase65_final_system_evaluation_report.py" in text


def test_demo_pack_does_not_claim_full_vroom_superiority() -> None:
    combined = read("README_BENCHMARK.md") + read("docs/benchmark/demo_walkthrough.md")

    assert "we beat VROOM" not in combined
    assert "IndustryRouteX beats VROOM" not in combined
