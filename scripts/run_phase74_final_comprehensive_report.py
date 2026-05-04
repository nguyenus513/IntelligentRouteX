from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "benchmark" / "final_comprehensive_system_report.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else "_Not generated yet._\n"


def build_report() -> str:
    sections = [
        ("Executive Summary", "IntelligentRouteX is currently CERTIFICATION_SAFE and a PRODUCTION_CANDIDATE for synthetic feasibility/shadow-mode evaluation, but not PRODUCTION_MAIN_READY."),
        ("System Architecture", "Stable optimizer: Phase 56F. Research baseline: Phase 47. Industry comparator: VROOM. Feasibility oracle: internal checker."),
        ("Dataset Matrix", read_text(REPO_ROOT / "docs" / "benchmark" / "dataset_matrix.md")),
        ("Baseline Matrix", read_text(REPO_ROOT / "docs" / "benchmark" / "baseline_matrix.md")),
        ("Safety Scorecard", read_text(REPO_ROOT / "docs" / "benchmark" / "system_scorecard.md")),
        ("Food Dispatch Metrics", read_text(REPO_ROOT / "docs" / "benchmark" / "food_dispatch_metrics.md")),
        ("Stress Sensitivity", read_text(REPO_ROOT / "docs" / "benchmark" / "stress_sensitivity_suite.md")),
        ("Ablation Study", read_text(REPO_ROOT / "docs" / "benchmark" / "ablation_study.md")),
        ("VROOM Comparison", read_text(REPO_ROOT / "docs" / "benchmark" / "synthetic_food_result_interpretation.md")),
        ("Known Limitations", "No live production adapter, no fallback/canary policy, no real replay logs, and synthetic quality vs VROOM is inconclusive when VROOM is infeasible."),
        ("Production Readiness Verdict", "Current verdict: CERTIFICATION_SAFE / PRODUCTION_CANDIDATE for synthetic feasibility. Not PRODUCTION_MAIN_READY."),
    ]
    lines = ["# Phase 74 Final Comprehensive System Report", ""]
    for title, body in sections:
        lines.extend([f"## {title}", "", body.strip(), ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 74 final comprehensive system report.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(), encoding="utf-8")
    print(f"[PHASE74 COMPREHENSIVE REPORT] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
