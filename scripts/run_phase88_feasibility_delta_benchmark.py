from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase88_feasibility_delta_v1"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted = 0
    checks = 0
    feasible = 0
    hard = 0
    over_budget = 0
    suites = []
    for suite in [part.strip() for part in args.suites.split(",") if part.strip()]:
        phase84_args = Namespace(suite=suite, vroom_url=args.vroom_url, time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, output_dir=str(output_dir / "per_suite" / suite.replace("-", "_")))
        summary = run_phase84(phase84_args)
        suites.append({"suite": suite, "gate": summary.get("gate"), "aggregate": summary.get("aggregate", {})})
        hard += int(summary.get("aggregate", {}).get("hardViolations", 0) or 0)
        over_budget += int(summary.get("aggregate", {}).get("overBudget", 0) or 0)
        for row in summary.get("rows", []):
            for budget in row.get("budgetTelemetry", []):
                accepted += int(budget.get("acceptedCount", 0) or 0)
                checks += int(budget.get("candidateChecks", 0) or 0)
                feasible += int(budget.get("feasibleCandidateCount", 0) or 0)
    anti = antihardcode_scan()
    full_check_pass_rate = feasible / max(1, checks)
    if hard or over_budget or anti.get("gate") != "PASS":
        gate = "FAIL"
    elif accepted > 0:
        gate = "PASS_STRONG"
    elif full_check_pass_rate > 0:
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase88-feasibility-delta-benchmark/v1", "gate": gate, "productionMainReady": False, "antiHardcodeGate": anti.get("gate"), "acceptedCandidates": accepted, "candidateChecks": checks, "feasibleCandidates": feasible, "fullCheckPassRate": full_check_pass_rate, "hardViolations": hard, "overBudget": over_budget, "suites": suites}
    write_json(output_dir / "phase88_summary.json", summary)
    (output_dir / "phase88_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 88 Feasibility Delta Benchmark",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Full check pass rate: `{summary.get('fullCheckPassRate')}`",
        f"- Accepted candidates: `{summary.get('acceptedCandidates')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        "",
        "Phase 88 improves feasibility-preserving candidate generation and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 88 feasibility delta benchmark.")
    parser.add_argument("--suites", default="vroom-capability-full")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=5)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE88 FEASIBILITY DELTA] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
