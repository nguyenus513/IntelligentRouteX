from __future__ import annotations

import json
from pathlib import Path

from scripts.build_routefinder_phase_gate import build_report, main


def write_ablation(path: Path, *, objective_delta: float = 0.2, ml_routes: int = 8) -> None:
    path.write_text(json.dumps({
        "scenarioPack": "dense-bundle-20x5",
        "workloadSize": "S",
        "executionMode": "controlled",
        "controlMetrics": {
            "selectorObjectiveValue": 3.8,
            "averageProjectedCompletionEtaMinutes": 20.0,
            "averageProjectedPickupEtaMinutes": 10.0,
            "routeFallbackRate": 0.0,
        },
        "variantMetrics": {
            "selectorObjectiveValue": 3.8 - objective_delta,
            "averageProjectedCompletionEtaMinutes": 21.0,
            "averageProjectedPickupEtaMinutes": 11.0,
            "routeFallbackRate": 0.0,
        },
        "controlSelectorSourceSummary": {
            "mlRouteSelectorCandidateCount": ml_routes,
            "selectedMlRouteCandidateCount": 1,
            "bestMlRouteSelectionScore": 1.2,
        },
        "variantSelectorSourceSummary": {
            "mlRouteSelectorCandidateCount": 0,
            "selectedMlRouteCandidateCount": 0,
            "bestMlRouteSelectionScore": 0.0,
        },
        "controlMlStageMetadata": [{
            "stageName": "route-proposal-pool",
            "sourceModel": "routefinder-local",
            "applied": True,
            "fallbackUsed": False,
        }],
    }), encoding="utf-8")


def test_gate_passes_when_routefinder_expands_pool_and_improves_objective(tmp_path: Path) -> None:
    write_ablation(tmp_path / "dispatch-quality-ablation-routefinder-dense-bundle-20x5-s.json")

    report = build_report(tmp_path)

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["rows"][0]["mlRouteSelectorCandidateCount"] == 8
    assert report["rows"][0]["selectorObjectiveImprovement"] == 0.2


def test_gate_blocks_when_routefinder_does_not_add_ml_routes(tmp_path: Path) -> None:
    write_ablation(
        tmp_path / "dispatch-quality-ablation-routefinder-dense-bundle-20x5-s.json",
        ml_routes=0,
    )

    report = build_report(tmp_path)

    assert report["pass"] is False
    assert "ml-route-not-present-in-selector-pool" in report["blockers"]


def test_gate_blocks_empty_input(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["pass"] is False
    assert report["rowCount"] == 0


def test_cli_writes_gate_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    write_ablation(input_dir / "dispatch-quality-ablation-routefinder-dense-bundle-20x5-s.json")

    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "routefinder_phase_gate.json").exists()
    assert (output_dir / "routefinder_phase_gate.md").exists()
