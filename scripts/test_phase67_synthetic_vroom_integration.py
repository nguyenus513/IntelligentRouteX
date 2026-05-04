from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import generate_phase64_synthetic_food_dataset as phase64
import run_phase58a_vroom_industry_comparator as phase58
import run_phase63_unified_benchmark_suite as phase63
import run_phase65_final_system_evaluation_report as phase65
from phase67_synthetic_instance_loader import load_benchmark_instance


def test_synthetic_loader_reads_normalized_json(tmp_path: Path) -> None:
    phase64.generate(tmp_path, seed=64)

    instance = load_benchmark_instance("synthetic-food", "lunch_peak", synthetic_dir=tmp_path)

    assert instance["problemType"] == "PDPTW"
    assert instance["benchmarkFamily"] == "synthetic-food"
    assert instance["requests"]


def test_phase58_dry_run_conversion_runs_on_synthetic(tmp_path: Path) -> None:
    phase64.generate(Path("benchmarks/synthetic_food/generated_v1"), seed=64)
    args = Namespace(
        benchmark_source="synthetic-food",
        data_source="auto",
        time_scale=1.0,
        rounding="round",
        skip_vroom_run=True,
        dry_run_conversion=True,
        vroom_url="",
        vroom_bin="",
        vroom_timeout_seconds=120,
        mode="academic_certification",
        challenger_time_limit="30s",
    )

    row = phase58.run_instance("lunch_peak", args, tmp_path)

    assert row["supportedMapping"]
    assert row["requestValidation"]["valid"]
    assert row["classification"] in {"vroom-unavailable", "unsupported-mapping"}


def test_phase63_resolves_synthetic_food_suite(monkeypatch, tmp_path: Path) -> None:
    def fake_phase56f(instances, output_dir, data_source, time_limit_ms, mode, repeat=1, benchmark_source="li-lim", stable_incumbent_replay=True):
        assert benchmark_source == "synthetic-food"
        return {"phase56bGate": {"verdict": "PASS"}, "results": []}

    def fake_vroom(instances, args, output_dir):
        assert args.benchmark_source == "synthetic-food"
        return {"rows": [], "aggregate": {"diagnosticGate": "DIAGNOSTIC_PASS"}}

    monkeypatch.setattr(phase63, "run_phase56f", fake_phase56f)
    monkeypatch.setattr(phase63, "run_vroom_comparator", fake_vroom)
    args = Namespace(suite="synthetic-food-smoke", champions="vroom", challenger="phase56f", data_source="auto", time_limit="30s", mode="academic_certification", dry_run_conversion=True, skip_vroom_run=True, vroom_url="", vroom_bin="", vroom_timeout_seconds=120, output_dir=str(tmp_path))

    summary = phase63.run(args)

    assert summary["suite"]["source"] == "synthetic-food"


def test_final_report_contains_scenario_table(tmp_path: Path) -> None:
    phase64.generate(Path("benchmarks/synthetic_food/generated_v1"), seed=64)
    report = phase65.evaluate(tmp_path)
    text = phase65.markdown(report)

    assert "| Scenario | VROOM Class | Challenger Vehicles |" in text
    assert "lunch_peak" in text


def test_no_instance_name_branch() -> None:
    combined = Path("phase67_synthetic_instance_loader.py").read_text(encoding="utf-8") if Path("phase67_synthetic_instance_loader.py").exists() else Path("scripts/phase67_synthetic_instance_loader.py").read_text(encoding="utf-8")
    assert "startswith(\"LRC\")" not in combined
    assert "startswith('LRC')" not in combined
    assert "instanceName ==" not in combined
