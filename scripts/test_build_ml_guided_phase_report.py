from __future__ import annotations

import json
from pathlib import Path

from scripts.build_ml_guided_phase_report import summarize


def test_phase_report_passes_when_core_ml_ready_and_traced() -> None:
    payload = {
        "finalVerdict": "PASS",
        "mlValueProven": True,
        "tabularWorkerImplementationPresent": True,
        "forecastWorkerReady": True,
        "greedRlWorkerReady": True,
        "routeFinderWorkerReady": True,
        "mlAblationRows": [
            {"component": "tabular", "robustUtilityDelta": 0.03, "selectorObjectiveDelta": 0.2},
            {"component": "forecast", "robustUtilityDelta": 0.01, "selectorObjectiveDelta": -0.01},
        ],
    }

    report = summarize(payload, "phase2")

    assert report["pass"] is True
    assert report["blockers"] == []
    assert report["componentSummary"]["tabular"]["positiveCount"] == 1


def test_phase_report_blocks_missing_core_rows() -> None:
    payload = {
        "finalVerdict": "PASS",
        "mlValueProven": True,
        "tabularWorkerImplementationPresent": True,
        "forecastWorkerReady": True,
        "mlAblationRows": [{"component": "tabular", "robustUtilityDelta": 0.0, "selectorObjectiveDelta": 0.0}],
    }

    report = summarize(payload, "phase2")

    assert report["pass"] is False
    assert "forecast-missing-ablation-rows" in report["blockers"]


def test_phase3_requires_positive_greedrl_contribution() -> None:
    payload = {
        "finalVerdict": "PASS",
        "mlValueProven": True,
        "tabularWorkerImplementationPresent": True,
        "forecastWorkerReady": True,
        "greedRlWorkerReady": True,
        "routeFinderWorkerReady": True,
        "mlAblationRows": [
            {"component": "greedrl", "robustUtilityDelta": 0.0, "selectorObjectiveDelta": 0.0},
        ],
    }

    report = summarize(payload, "phase3")

    assert report["pass"] is False
    assert "greedrl-positive-contribution-not-proven" in report["blockers"]


def test_phase4_requires_positive_routefinder_contribution() -> None:
    payload = {
        "finalVerdict": "PASS",
        "mlValueProven": True,
        "tabularWorkerImplementationPresent": True,
        "forecastWorkerReady": True,
        "greedRlWorkerReady": True,
        "routeFinderWorkerReady": True,
        "mlAblationRows": [
            {"component": "routefinder", "robustUtilityDelta": 0.0, "selectorObjectiveDelta": 0.2},
        ],
    }

    report = summarize(payload, "phase4")

    assert report["pass"] is True


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    from scripts.build_ml_guided_phase_report import main

    input_path = tmp_path / "ml.json"
    output_dir = tmp_path / "out"
    input_path.write_text(json.dumps({
        "finalVerdict": "PASS",
        "mlValueProven": True,
        "tabularWorkerImplementationPresent": True,
        "forecastWorkerReady": True,
        "mlAblationRows": [
            {"component": "tabular", "robustUtilityDelta": 0.1, "selectorObjectiveDelta": 0.0},
            {"component": "forecast", "robustUtilityDelta": 0.0, "selectorObjectiveDelta": 0.1},
        ],
    }), encoding="utf-8")

    assert main(["--ml-intelligence-results", str(input_path), "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "ml_guided_phase_report.json").exists()
    assert (output_dir / "ml_guided_phase_report.md").exists()
