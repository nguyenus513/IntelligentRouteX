from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_phase56f_doc_mentions_certification_runner() -> None:
    text = read("docs/benchmark/phase56f_stable_certification_runner.md")

    assert "Phase 56F" in text
    assert "certification and shadow-mode" in text or "certification/shadow-mode" in text
    assert "scripts/run_phase56b_stable_promoted_runner.py" in text
    assert "--stable-incumbent-replay" in text


def test_phase56f_doc_does_not_claim_quality_win_over_phase47() -> None:
    text = read("docs/benchmark/phase56f_stable_certification_runner.md")

    assert "not a claim that it beats the Phase 47 research-quality baseline" in text
    assert "Phase 47 remains useful for research quality comparisons" in text


def test_phase56f_doc_mentions_lrc202_quality_tradeoff() -> None:
    text = read("docs/benchmark/phase56f_stable_certification_runner.md")

    assert "LRC202" in text
    assert "5 -> 5" in text
    assert "5 -> 4" in text
    assert "quality tradeoff" in text.lower()


def test_registry_splits_certification_and_research_roles() -> None:
    text = read("docs/benchmark/diagnostic_branch_registry.md")

    assert "Phase 56F" in text
    assert "Promoted for stable certification/shadow-mode" in text
    assert "Research-quality baseline" in text
