from __future__ import annotations

import json
from pathlib import Path

from scripts.build_runtime_policy_phase_gate import build_report, main


def write_ablation(path: Path, *, control_latency: int = 80, variant_latency: int = 120) -> None:
    path.write_text(json.dumps({
        "scenarioPack": "dense-bundle-20x5",
        "workloadSize": "S",
        "executionMode": "controlled",
        "controlMetrics": {"selectorObjectiveValue": 3.8, "routeFallbackRate": 0.0},
        "variantMetrics": {"selectorObjectiveValue": 3.7, "routeFallbackRate": 0.0},
        "controlRuntimeTelemetry": {
            "runtimePolicyApplied": True,
            "totalDispatchLatencyMs": control_latency,
            "totalBudgetBreached": False,
            "selectorTelemetry": {"poolReducedCount": 80},
            "routeProposalBudget": {"candidateCountAfterBudget": 90},
        },
        "variantRuntimeTelemetry": {
            "runtimePolicyApplied": False,
            "totalDispatchLatencyMs": variant_latency,
            "totalBudgetBreached": False,
            "selectorTelemetry": {"poolReducedCount": 120},
            "routeProposalBudget": {"candidateCountAfterBudget": 150},
        },
    }), encoding="utf-8")


def test_gate_passes_when_policy_reduces_runtime_without_quality_regression(tmp_path: Path) -> None:
    write_ablation(tmp_path / "dispatch-quality-ablation-runtime-policy-dense-bundle-20x5-s.json")

    report = build_report(tmp_path)

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["rows"][0]["latencyDeltaMs"] == -40


def test_gate_blocks_when_runtime_policy_is_not_applied(tmp_path: Path) -> None:
    path = tmp_path / "dispatch-quality-ablation-runtime-policy-dense-bundle-20x5-s.json"
    write_ablation(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["controlRuntimeTelemetry"]["runtimePolicyApplied"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_report(tmp_path)
    assert report["pass"] is False
    assert "runtime-policy-not-applied" in report["blockers"]


def test_gate_blocks_when_latency_increases(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-runtime-policy-dense-bundle-20x5-s.json",
        control_latency=130,
        variant_latency=120,
    )

    report = build_report(tmp_path)
    assert report["pass"] is False
    assert "runtime-policy-latency-not-reduced" in report["blockers"]


def test_cli_writes_gate_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    write_ablation(input_dir / "dispatch-quality-ablation-runtime-policy-dense-bundle-20x5-s.json")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "runtime_policy_phase_gate.json").exists()
    assert (output_dir / "runtime_policy_phase_gate.md").exists()
