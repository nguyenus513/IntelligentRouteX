from __future__ import annotations

import json
from pathlib import Path


REPORT_MD = Path("docs/benchmark/final_synthetic_food_evaluation_report.md")
REPORT_JSON = Path("docs/benchmark/final_synthetic_food_evaluation_report.json")
INTERPRETATION = Path("docs/benchmark/synthetic_food_result_interpretation.md")


def test_report_mentions_true_vroom_tw_violations() -> None:
    text = REPORT_MD.read_text(encoding="utf-8")

    assert "vroom-true-time-window-violation" in text
    assert "4/6" in text


def test_report_mentions_matrix_duration_mismatch() -> None:
    text = REPORT_MD.read_text(encoding="utf-8")

    assert "matrix-duration-mismatch" in text
    assert "2/6" in text


def test_json_contains_audit_summary() -> None:
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8-sig"))

    assert payload["vroomTimeWindowAuditSummary"]["trueVroomTwViolationCount"] == 4
    assert payload["vroomTimeWindowAuditSummary"]["matrixDurationMismatchCount"] == 2
    assert payload["vroomTimeWindowAuditSummary"]["unknownCount"] == 0
    assert payload["vroomTimeWindowAuditSummary"]["auditGate"] == "PASS"


def test_report_does_not_claim_full_quality_superiority() -> None:
    combined = REPORT_MD.read_text(encoding="utf-8") + INTERPRETATION.read_text(encoding="utf-8")

    forbidden = ["full quality superiority", "beats VROOM on quality", "quality superiority over VROOM"]
    assert not any(phrase in combined for phrase in forbidden)
    assert "Quality superiority remains inconclusive" in combined


def test_interpretation_doc_distinguishes_feasibility_vs_quality() -> None:
    text = INTERPRETATION.read_text(encoding="utf-8")

    assert "feasibility/stability win" in text
    assert "quality win" in text
    assert "both solvers to be feasible first" in text
    assert "matrix-duration mismatch" in text
