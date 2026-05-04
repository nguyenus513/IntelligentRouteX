from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import run_phase61_benchmark_suite_registry as phase61
import run_phase63_unified_benchmark_suite as phase63
import generate_phase64_synthetic_food_dataset as phase64
import run_phase65_final_system_evaluation_report as phase65


def test_suite_registry_loads_suite_correctly() -> None:
    suite = phase61.load_suite("li-lim-8case")

    assert suite["suite"] == "li-lim-8case"
    assert suite["problemType"] == "PDPTW"
    assert len(suite["instances"]) == 8


def test_vroom_docker_docs_mention_health_and_root_404() -> None:
    text = Path("docker/vroom/README.md").read_text(encoding="utf-8")

    assert "/health" in text
    assert "404" in text
    assert "GET /" in text


def test_unified_runner_can_run_dry_run_conversion(monkeypatch, tmp_path: Path) -> None:
    def fake_phase56f(instances, output_dir, data_source, time_limit_ms, mode, repeat=1, benchmark_source="li-lim", stable_incumbent_replay=True):
        return {"phase56bGate": {"verdict": "PASS"}, "results": []}

    def fake_vroom(instances, args, output_dir):
        return {"rows": [], "aggregate": {"diagnosticGate": "DIAGNOSTIC_PASS"}}

    monkeypatch.setattr(phase63, "run_phase56f", fake_phase56f)
    monkeypatch.setattr(phase63, "run_vroom_comparator", fake_vroom)
    args = Namespace(suite="smoke", champions="vroom", challenger="phase56f", data_source="auto", time_limit="30s", mode="academic_certification", dry_run_conversion=True, skip_vroom_run=False, vroom_url="", vroom_bin="", vroom_timeout_seconds=120, output_dir=str(tmp_path))

    summary = phase63.run(args)

    assert summary["suite"]["suite"] == "smoke"
    assert summary["challengerGate"] == "PASS"


def test_synthetic_generator_produces_valid_pickup_dropoff_pairs(tmp_path: Path) -> None:
    manifest = phase64.generate(tmp_path, seed=64)
    first = phase64.generate_scenario(manifest["scenarios"][0]["scenario"], seed=64)
    node_ids = {str(node["id"]) for node in first["nodes"]}

    assert manifest["scenarioCount"] == 6
    assert all(str(request["pickupNodeId"]) in node_ids and str(request["dropoffNodeId"]) in node_ids for request in first["requests"])
    assert all(str(request["pickupNodeId"]) != str(request["dropoffNodeId"]) for request in first["requests"])


def test_final_report_handles_missing_vroom_gracefully(tmp_path: Path) -> None:
    report = phase65.evaluate(tmp_path)

    assert report["robustness"]["vroomTimeoutCount"] == 0
    assert report["qualityVsVroom"]["vroomCounts"] == {}
    assert "productionSafe" in report["finalVerdict"]


def test_no_instance_name_special_case_in_packaging_scripts() -> None:
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in [
            "scripts/run_phase61_benchmark_suite_registry.py",
            "scripts/run_phase63_unified_benchmark_suite.py",
            "scripts/generate_phase64_synthetic_food_dataset.py",
            "scripts/run_phase65_final_system_evaluation_report.py",
        ]
    )
    assert "startswith(\"LRC\")" not in sources
    assert "startswith('LRC')" not in sources
    assert "instanceName ==" not in sources
