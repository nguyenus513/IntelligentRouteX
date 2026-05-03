from __future__ import annotations

import json
from pathlib import Path

from scripts.build_community_benchmark_phase_gate import summarize, main


def write_results(path: Path, suite: str = "solomon", verdict: str = "PASS", feasible: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schemaVersion": "external-benchmark-certification/v1",
        "suite": suite,
        "solver": "our-dispatch-v2",
        "results": [{
            "suite": suite,
            "instance": "C101" if suite == "solomon" else "LC101",
            "solver": "our-dispatch-v2",
            "solverImplementation": "external-benchmark-dispatch-adapter-v2",
            "effectiveDataSource": "fixture",
            "feasible": feasible,
            "vehicleCount": 10,
            "bestKnownVehicleCount": 10,
            "totalDistance": 100.0,
            "bestKnownDistance": 100.0,
            "objectiveGapPercent": 0.0,
            "servedRequestCount": 100,
            "unservedRequestCount": 0,
            "capacityViolationCount": 0,
            "timeWindowViolationCount": 0,
            "pickupBeforeDropoffViolationCount": 0,
            "vehicleLimitViolationCount": 0,
            "runtimeMs": 120,
            "verdict": verdict,
            "verdictReasons": [],
        }],
    }), encoding="utf-8")


def test_gate_passes_with_both_required_suites(tmp_path: Path) -> None:
    write_results(tmp_path / "our-dispatch-v2" / "solomon" / "external_benchmark_results.json", "solomon")
    write_results(tmp_path / "our-dispatch-v2" / "li-lim" / "external_benchmark_results.json", "li-lim")

    report = summarize(tmp_path, 30_000, False)

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["ourDispatchRowCount"] == 2


def test_gate_blocks_missing_suite(tmp_path: Path) -> None:
    write_results(tmp_path / "our-dispatch-v2" / "solomon" / "external_benchmark_results.json", "solomon")

    report = summarize(tmp_path, 30_000, False)

    assert report["pass"] is False
    assert "community-benchmark-missing-suite-li-lim" in report["blockers"]


def test_gate_blocks_hard_violation(tmp_path: Path) -> None:
    path = tmp_path / "our-dispatch-v2" / "solomon" / "external_benchmark_results.json"
    write_results(path, "solomon")
    write_results(tmp_path / "our-dispatch-v2" / "li-lim" / "external_benchmark_results.json", "li-lim")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["results"][0]["timeWindowViolationCount"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = summarize(tmp_path, 30_000, False)

    assert report["pass"] is False
    assert "community-benchmark-hard-violation" in report["blockers"]


def test_cli_writes_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    write_results(input_dir / "our-dispatch-v2" / "solomon" / "external_benchmark_results.json", "solomon")
    write_results(input_dir / "our-dispatch-v2" / "li-lim" / "external_benchmark_results.json", "li-lim")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "community_benchmark_gate.json").exists()
    assert (output_dir / "community_benchmark_gate.md").exists()
