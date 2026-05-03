from __future__ import annotations

import json
from pathlib import Path

from scripts.build_greedrl_phase_gate import build_report, main


def write_ablation(path: Path, *, selected_greedrl: int = 1, objective_delta: float = 0.2) -> None:
    path.write_text(json.dumps({
        "scenarioPack": "dense-bundle-20x5",
        "workloadSize": "S",
        "executionMode": "controlled",
        "controlMetrics": {
            "selectorObjectiveValue": 3.8,
            "bundleRate": 0.33,
            "maxSelectedBundleSize": 2,
        },
        "variantMetrics": {
            "selectorObjectiveValue": 3.8 - objective_delta,
            "bundleRate": 0.0,
            "maxSelectedBundleSize": 1,
        },
        "controlBundlePoolSummary": {
            "sourceCounts": {"DETERMINISTIC_FAMILY": 5, "GREEDRL_PROPOSAL": 1},
        },
        "controlSelectorSourceSummary": {
            "greedRlSelectorCandidateCount": 21,
            "selectedGreedRlCandidateCount": selected_greedrl,
        },
    }), encoding="utf-8")


def test_gate_passes_when_greedrl_is_retained_selected_and_improves_objective(tmp_path: Path) -> None:
    write_ablation(tmp_path / "dispatch-quality-ablation-greedrl-dense-bundle-20x5-s.json")

    report = build_report(tmp_path)

    assert report["pass"] is True
    assert report["blockers"] == []
    row = report["rows"][0]
    assert row["selectedGreedRlCandidateCount"] == 1
    assert row["greedRlSelectorCandidateCount"] == 21
    assert row["selectorObjectiveImprovement"] == 0.2


def test_gate_blocks_when_greedrl_is_not_selected(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-greedrl-dense-bundle-20x5-s.json",
        selected_greedrl=0,
    )

    report = build_report(tmp_path)

    assert report["pass"] is False
    assert "greedrl-not-selected" in report["blockers"]


def test_gate_blocks_empty_input(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["pass"] is False
    assert report["rowCount"] == 0


def test_cli_writes_gate_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    write_ablation(input_dir / "dispatch-quality-ablation-greedrl-dense-bundle-20x5-s.json")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "greedrl_phase_gate.json").exists()
    assert (output_dir / "greedrl_phase_gate.md").exists()
