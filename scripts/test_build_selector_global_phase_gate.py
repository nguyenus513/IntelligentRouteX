from __future__ import annotations

import json
from pathlib import Path

from scripts.build_selector_global_phase_gate import build_report, main


def write_ablation(path: Path, *, objective_on: float = 4.0, objective_off: float = 3.9, selected_ml: int = 1) -> None:
    path.write_text(json.dumps({
        "toggledComponent": "selector-global",
        "scenarioPack": "dense-bundle-20x5",
        "workloadSize": "S",
        "executionMode": "controlled",
        "controlMetrics": {"selectorObjectiveValue": objective_on, "routeFallbackRate": 0.0},
        "variantMetrics": {"selectorObjectiveValue": objective_off, "routeFallbackRate": 0.0},
        "controlSelectorSourceSummary": {
            "selectedMlRouteCandidateCount": selected_ml,
            "selectedGreedRlCandidateCount": 0,
        },
        "variantSelectorSourceSummary": {
            "selectedMlRouteCandidateCount": 0,
            "selectedGreedRlCandidateCount": 0,
        },
        "controlRuntimeTelemetry": {
            "totalDispatchLatencyMs": 180,
            "selectorTelemetry": {
                "mode": "MINI_EXACT",
                "fallbackLevel": "NONE",
                "timedOut": False,
                "acceptanceGatePassed": True,
                "poolInputCount": 300,
                "poolReducedCount": 128,
                "selectorMaxPoolSize": 128,
            },
        },
        "variantRuntimeTelemetry": {
            "totalDispatchLatencyMs": 120,
            "selectorTelemetry": {
                "mode": "DEGRADED_GREEDY",
                "fallbackLevel": "GLOBAL_SELECTOR_DISABLED",
                "timedOut": False,
                "acceptanceGatePassed": True,
                "poolInputCount": 300,
                "poolReducedCount": 128,
                "selectorMaxPoolSize": 128,
            },
        },
    }), encoding="utf-8")


def test_gate_passes_when_global_selector_improves_quality_and_keeps_ml(tmp_path: Path) -> None:
    write_ablation(tmp_path / "dispatch-quality-ablation-selector-global-dense-bundle-20x5-s.json")

    report = build_report(tmp_path)

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["rows"][0]["selectorObjectiveDelta"] == 0.1


def test_gate_blocks_when_global_selector_regresses_objective(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-selector-global-dense-bundle-20x5-s.json",
        objective_on=3.0,
        objective_off=3.2,
    )

    report = build_report(tmp_path)

    assert report["pass"] is False
    assert "selector-global-objective-regressed" in report["blockers"]


def test_gate_blocks_when_no_ml_candidate_survives_selection(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-selector-global-dense-bundle-20x5-s.json",
        selected_ml=0,
    )

    report = build_report(tmp_path)

    assert report["pass"] is False
    assert "selector-global-no-ml-candidate-selected" in report["blockers"]


def test_cli_writes_gate_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    write_ablation(input_dir / "dispatch-quality-ablation-selector-global-dense-bundle-20x5-s.json")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "selector_global_phase_gate.json").exists()
    assert (output_dir / "selector_global_phase_gate.md").exists()
