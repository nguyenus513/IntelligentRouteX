from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase9_baseline_comparison import compare, main


def write_result(path: Path, solver: str, distance: float, runtime: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "results": [{
            "suite": "solomon",
            "instance": "C101",
            "solver": solver,
            "feasible": True,
            "vehicleCount": 1,
            "totalDistance": distance,
            "runtimeMs": runtime,
        }],
    }), encoding="utf-8")


def test_comparison_passes_when_ours_not_worse(tmp_path: Path) -> None:
    write_result(tmp_path / "our" / "external_benchmark_results.json", "our-dispatch-v2", 100.0, 90)
    write_result(tmp_path / "ortools" / "external_benchmark_results.json", "ortools-baseline", 100.0, 120)

    report = compare(tmp_path)

    assert report["pass"] is True
    assert report["wins"] == 1
    assert report["losses"] == 0


def test_comparison_blocks_quality_loss(tmp_path: Path) -> None:
    write_result(tmp_path / "our" / "external_benchmark_results.json", "our-dispatch-v2", 120.0)
    write_result(tmp_path / "ortools" / "external_benchmark_results.json", "ortools-baseline", 100.0)

    report = compare(tmp_path)

    assert report["pass"] is False
    assert "phase9-comparison-has-quality-losses" in report["blockers"]


def test_comparison_cli_writes_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    write_result(input_dir / "our" / "external_benchmark_results.json", "our-dispatch-v2", 100.0)
    write_result(input_dir / "ortools" / "external_benchmark_results.json", "ortools-baseline", 100.0)

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "phase9_baseline_comparison.json").exists()
    assert (output_dir / "phase9_baseline_comparison.md").exists()
