from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase14_pyvrp_calibration_gate import build_report, main


def write_results(root: Path, *, gap: int = 2, hgs_pass: int = 3, pool_before: int = 20, pool_after: int = 25, runtime: int = 1000) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "suite": "solomon",
            "instance": "RC101",
            "status": "PASS",
            "vehicleGap": gap,
            "hgsVariantCount": 5,
            "hgsPassCount": hgs_pass,
            "bestHgsVariant": "travel-only-scale1000",
            "bestHgsVehicleCount": 16,
            "routePoolSizeBeforeHgs": pool_before,
            "routePoolSizeAfterHgs": pool_after,
            "setPartitioningProducedSolution": True,
            "bestLabel": "phase14-set-partitioning-calibrated-route-pool",
            "runtimeMs": runtime,
        },
        {"suite": "li-lim", "instance": "LR101", "status": "SKIPPED", "vehicleGap": None, "runtimeMs": 0},
        {"suite": "li-lim", "instance": "LRC101", "status": "SKIPPED", "vehicleGap": None, "runtimeMs": 0},
    ]
    (root / "phase14_pyvrp_calibration_results.json").write_text(json.dumps({"results": rows}), encoding="utf-8")


def test_gate_passes_with_limits_when_calibration_runs_without_gap_reduction(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_results(baseline, gap=2)
    write_results(candidate, gap=2)

    report = build_report(baseline, candidate, 15_000)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert report["calibrationEvidence"] is True


def test_gate_passes_strict_when_gap_reduces(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_results(baseline, gap=2)
    write_results(candidate, gap=1)

    report = build_report(baseline, candidate, 15_000)

    assert report["verdict"] == "PASS"
    assert report["totalGapDelta"] == 1


def test_gate_fails_when_hgs_does_not_add_pool_evidence(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_results(baseline, gap=2)
    write_results(candidate, gap=2, pool_before=20, pool_after=20)

    report = build_report(baseline, candidate, 15_000)

    assert report["verdict"] == "FAIL"
    assert "phase14-hgs-routes-not-added" in report["blockers"]


def test_gate_fails_when_runtime_exceeds_limit(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_results(baseline, gap=2)
    write_results(candidate, gap=2, runtime=20_000)

    report = build_report(baseline, candidate, 15_000)

    assert report["verdict"] == "FAIL"
    assert "phase14-runtime-timeout" in report["blockers"]


def test_cli_writes_outputs(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    output = tmp_path / "out"
    write_results(baseline, gap=2)
    write_results(candidate, gap=2)

    assert main(["--baseline-dir", str(baseline), "--candidate-dir", str(candidate), "--output-dir", str(output)]) == 0
    assert (output / "phase14_pyvrp_calibration_gate.json").exists()
    assert (output / "phase14_pyvrp_calibration_gate.md").exists()
