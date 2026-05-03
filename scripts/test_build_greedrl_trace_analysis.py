from __future__ import annotations

import json
from pathlib import Path

from scripts.build_greedrl_trace_analysis import build_report, main


def test_greedrl_trace_analysis_detects_disabled_quality_rows(tmp_path: Path) -> None:
    feedback = tmp_path / "feedback" / "decision-stage" / "adaptive_compute_trace"
    feedback.mkdir(parents=True)
    (feedback / "trace.json").write_text(json.dumps({
        "workerName": "ml-greedrl-worker",
        "decision": "ESCALATE_GREEDRL",
        "escalated": True,
        "workerReady": True,
        "workingOrderCount": 4,
    }), encoding="utf-8")

    teacher = tmp_path / "teacher"
    teacher.mkdir()
    (teacher / "rows.jsonl").write_text(json.dumps({
        "teacherFamily": "greedrl",
        "applied": True,
        "fallbackUsed": False,
        "featureVector": {"workingOrderIds": ["o1", "o2"]},
        "bundleProposals": [{"orderIds": ["o1", "o2"]}],
    }) + "\n", encoding="utf-8")

    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "dispatch-quality-normal-clear-s-legacy-v2-controlled-a.json").write_text(json.dumps({
        "config": {"greedrlEnabled": False},
        "bundleDiversity": {"familyDiversityCount": 1, "familyRetainedCounts": {"URGENT_SINGLE_FALLBACK": 2}},
    }), encoding="utf-8")

    report = build_report(tmp_path, teacher, quality)

    assert report["adaptive"]["greedrlEscalatedCount"] == 1
    assert report["teacher"]["proposalCount"] == 1
    assert "quality-benchmark-greedrl-disabled" in report["diagnoses"]


def test_cli_writes_greedrl_analysis(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([
        "--feedback-root", str(tmp_path / "missing-feedback"),
        "--teacher-root", str(tmp_path / "missing-teacher"),
        "--quality-root", str(tmp_path / "missing-quality"),
        "--output-dir", str(out),
    ]) == 0
    assert (out / "greedrl_trace_analysis.json").exists()
    assert (out / "greedrl_trace_analysis.md").exists()
