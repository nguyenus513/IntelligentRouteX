from __future__ import annotations

import json
from pathlib import Path

from scripts.build_active_repair_phase_gate import build_report, main


def write_ablation(path: Path, *, input_count: int = 3, output_count: int = 2, variant_output: int = 0) -> None:
    path.write_text(json.dumps({
        "scenarioPack": "traffic-shock",
        "workloadSize": "S",
        "executionMode": "controlled",
        "controlMetrics": {
            "selectorObjectiveValue": 3.8,
            "averageProjectedCompletionEtaMinutes": 20.0,
            "routeFallbackRate": 0.0,
        },
        "variantMetrics": {
            "selectorObjectiveValue": 3.7,
            "averageProjectedCompletionEtaMinutes": 21.0,
            "routeFallbackRate": 0.0,
        },
        "controlActiveRepairTelemetry": {
            "candidateInputCount": input_count,
            "candidateOutputCount": output_count,
            "operatorsTried": 8,
            "acceptedMoves": 2,
            "bestImprovementDelta": 0.05,
            "runtimeMs": 12,
            "improvementSummary": {
                "frozenPrefixViolationCount": 0,
                "foodDurationViolationCount": 0,
            },
        },
        "variantActiveRepairTelemetry": {
            "candidateInputCount": input_count,
            "candidateOutputCount": variant_output,
            "operatorsTried": 0,
            "acceptedMoves": 0,
            "bestImprovementDelta": 0.0,
            "runtimeMs": 0,
            "improvementSummary": {},
        },
    }), encoding="utf-8")


def test_gate_passes_when_active_repair_outputs_safe_improvements(tmp_path: Path) -> None:
    write_ablation(tmp_path / "dispatch-quality-ablation-active-repair-traffic-shock-s.json")

    report = build_report(tmp_path)

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["rows"][0]["controlCandidateOutputCount"] == 2


def test_gate_blocks_when_repair_has_no_output(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-active-repair-traffic-shock-s.json",
        output_count=0,
    )

    report = build_report(tmp_path)

    assert report["pass"] is False
    assert "active-repair-no-output-candidates" in report["blockers"]


def test_gate_blocks_when_variant_still_repairs(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-active-repair-traffic-shock-s.json",
        variant_output=1,
    )

    report = build_report(tmp_path)
    assert report["pass"] is False
    assert "active-repair-ablation-did-not-disable-repair" in report["blockers"]


def test_cli_writes_gate_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    write_ablation(input_dir / "dispatch-quality-ablation-active-repair-traffic-shock-s.json")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "active_repair_phase_gate.json").exists()
    assert (output_dir / "active_repair_phase_gate.md").exists()
