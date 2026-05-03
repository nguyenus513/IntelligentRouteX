from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase22_final_benchmark_report import build_report
from scripts.build_phase22_release_gate import build_gate


def write_gate(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def phase_paths(root: Path) -> dict[str, Path]:
    return {f"phase{index}": root / f"phase{index}.json" for index in range(15, 22)}


def write_minimal_phase_gates(root: Path, *, losses: int = 0, wins: int = 0, rc_gap: int = 2, failed_phase: str | None = None) -> dict[str, Path]:
    paths = phase_paths(root)
    for phase, path in paths.items():
        write_gate(path, {"verdict": "PASS_WITH_LIMITS", "blockers": []})
    if failed_phase:
        write_gate(paths[failed_phase], {"verdict": "FAIL", "blockers": ["unit-failure"]})
    write_gate(paths["phase19"], {"verdict": "PASS_WITH_LIMITS", "blockers": [], "referenceRouteAvailable": False, "compatibilityConclusion": "model-compatible-reference-route-missing-solver-gap-likely"})
    write_gate(paths["phase20"], {"verdict": "PASS_WITH_LIMITS", "blockers": [], "rows": [{"candidateGap": rc_gap}]})
    write_gate(paths["phase21"], {
        "verdict": "PASS_WITH_LIMITS",
        "blockers": [],
        "wins": wins,
        "ties": 3,
        "losses": losses,
        "ourSummary": {"hardViolationCount": 0, "runtimeP95Ms": 3200, "vehicleGapSum": 0},
    })
    return paths


def test_final_report_passes_with_limits_when_stable_but_bks_gap(tmp_path: Path) -> None:
    paths = write_minimal_phase_gates(tmp_path, losses=0, wins=0, rc_gap=2)

    report = build_report(paths)

    assert report["decision"]["verdict"] == "PASS_WITH_LIMITS"
    assert "phase22-rc101-bks-gap-remains" in report["decision"]["warnings"]


def test_final_report_fails_on_medium_losses(tmp_path: Path) -> None:
    paths = write_minimal_phase_gates(tmp_path, losses=1, wins=0, rc_gap=2)

    report = build_report(paths)

    assert report["decision"]["verdict"] == "FAIL"
    assert "phase22-medium-benchmark-losses" in report["decision"]["blockers"]


def test_final_report_passes_when_win_and_no_bks_gap(tmp_path: Path) -> None:
    paths = write_minimal_phase_gates(tmp_path, losses=0, wins=1, rc_gap=0)
    write_gate(paths["phase19"], {"verdict": "PASS", "blockers": [], "referenceRouteAvailable": True, "compatibilityConclusion": "reference-route-feasible-model-compatible"})

    report = build_report(paths)

    assert report["decision"]["verdict"] == "PASS"


def test_release_gate_reads_report(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    payload = {
        "decision": {"verdict": "PASS_WITH_LIMITS", "claim": "stable-no-loss-limited-bks-claim", "blockers": [], "warnings": ["phase22-rc101-bks-gap-remains"]},
        "summary": {"mediumWins": 0, "mediumTies": 3, "mediumLosses": 0, "mediumRuntimeP95Ms": 3200, "mediumHardViolations": 0, "rc101GapAfterPhase20": 2},
    }
    (report_dir / "phase22_final_benchmark_report.json").write_text(json.dumps(payload), encoding="utf-8")

    gate = build_gate(report_dir)

    assert gate["pass"] is True
    assert gate["claim"] == "stable-no-loss-limited-bks-claim"
