from __future__ import annotations

from pathlib import Path


REPORT = Path("docs/benchmark/vroom_capability_result_report.md")
COMPREHENSIVE = Path("docs/benchmark/final_comprehensive_system_report.md")
BASELINE = Path("docs/benchmark/baseline_matrix.md")


def test_report_mentions_both_feasible_15_of_15() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "Both feasible | 15/15" in text
    assert "VROOM hard-fail | 0" in text
    assert "Phase 56F hard-fail | 0" in text


def test_report_mentions_tie_and_challenger_distance_wins() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "Fair quality tie | 10" in text
    assert "Phase 56F distance wins | 5" in text
    assert "VROOM distance wins | 0" in text


def test_report_does_not_claim_production_main_readiness() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "Do not claim `PRODUCTION_MAIN_READY`" in text
    assert "not full production-main readiness" in text


def test_final_comprehensive_report_includes_phase76_section() -> None:
    text = COMPREHENSIVE.read_text(encoding="utf-8")

    assert "Phase 76 VROOM Capability Micro-Suite" in text
    assert "both-feasible | 15/15" in text
    assert "Phase 56F distance wins | 5" in text


def test_baseline_matrix_marks_vroom_capability_verified() -> None:
    text = BASELINE.read_text(encoding="utf-8")

    assert "capability verified on Phase 76" in text
    assert "both feasible `15/15`" in text
