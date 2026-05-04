from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase90_final_quality_v1"
QUALITY_OPPORTUNITY_SUITES = {"li-lim-8case", "phase90-opportunity-smoke"}
REQUIRED_ACCEPTANCE_SUITES = {"phase90-opportunity-smoke"}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted = 0
    checks = 0
    checker_feasible = 0
    objective_improving = 0
    objective_not_improved = 0
    pruned_no_quality = 0
    hard = 0
    over_budget = 0
    timeout_count = 0
    opportunity_cases = 0
    opportunity_without_improvement = 0
    safe_returns = 0
    requires_acceptance_missing = False
    suites: List[Dict[str, Any]] = []
    for suite in [part.strip() for part in args.suites.split(",") if part.strip()]:
        suite_row: Dict[str, Any] = {"suite": suite, "qualityOpportunitySuite": suite in QUALITY_OPPORTUNITY_SUITES}
        try:
            phase84_args = Namespace(suite=suite, vroom_url=args.vroom_url, time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, output_dir=str(output_dir / "per_suite" / suite.replace("-", "_")))
            phase_summary = run_phase84(phase84_args)
            suite_row.update({"gate": phase_summary.get("gate"), "aggregate": phase_summary.get("aggregate", {})})
            hard += int(phase_summary.get("aggregate", {}).get("hardViolations", 0) or 0)
            over_budget += int(phase_summary.get("aggregate", {}).get("overBudget", 0) or 0)
            suite_accepted_before = accepted
            suite_improving_before = objective_improving
            for row in phase_summary.get("rows", []):
                opportunity = row.get("improvementOpportunity", {}) or {}
                has_opportunity = bool(opportunity.get("hasImprovementOpportunity"))
                if has_opportunity:
                    opportunity_cases += 1
                if row.get("safeReturn"):
                    safe_returns += 1
                row_objective_improving = 0
                for budget in row.get("budgetTelemetry", []):
                    accepted += int(budget.get("acceptedCount", 0) or 0)
                    checks += int(budget.get("candidateChecks", 0) or 0)
                    checker_feasible += int(budget.get("checkerFeasibleCandidates", budget.get("feasibleCandidateCount", 0)) or 0)
                    improving = int(budget.get("objectiveImprovingCandidates", 0) or 0)
                    objective_improving += improving
                    row_objective_improving += improving
                    objective_not_improved += int(budget.get("objectiveNotImprovedCandidates", 0) or 0)
                    pruned_no_quality += int(budget.get("prunedNoQualityPotential", 0) or 0)
                if suite in QUALITY_OPPORTUNITY_SUITES and has_opportunity and row_objective_improving == 0:
                    opportunity_without_improvement += 1
            if suite in REQUIRED_ACCEPTANCE_SUITES and (accepted == suite_accepted_before or objective_improving == suite_improving_before):
                requires_acceptance_missing = True
        except Exception as exception:  # pragma: no cover - runner must always summarize
            timeout_count += 1
            suite_row.update({"gate": "FAIL", "error": str(exception), "aggregate": {"hardViolations": 0, "overBudget": 1}})
            over_budget += 1
        suites.append(suite_row)
    anti = antihardcode_scan()
    if hard or over_budget or timeout_count or anti.get("gate") != "PASS" or requires_acceptance_missing:
        gate = "FAIL"
    elif accepted > 0 and (opportunity_cases == 0 or opportunity_without_improvement == 0):
        gate = "PASS_STRONG"
    elif opportunity_without_improvement > 0:
        gate = "PASS_WITH_LIMITS"
    elif checker_feasible > 0 or opportunity_cases == 0:
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {
        "schemaVersion": "phase90-final-quality-completion/v1",
        "gate": gate,
        "productionMainReady": False,
        "antiHardcodeGate": anti.get("gate"),
        "acceptedCandidates": accepted,
        "candidateChecks": checks,
        "finalCandidateChecks": checks,
        "checkerFeasibleCandidates": checker_feasible,
        "objectiveImprovingCandidates": objective_improving,
        "objectiveNotImprovedCandidates": objective_not_improved,
        "prunedNoQualityPotential": pruned_no_quality,
        "hardViolations": hard,
        "overBudget": over_budget,
        "timeoutCount": timeout_count,
        "safeReturns": safe_returns,
        "qualityOpportunityCases": opportunity_cases,
        "qualityOpportunityWithoutImprovement": opportunity_without_improvement,
        "boundedSearchNoImprovement": opportunity_without_improvement > 0 and objective_improving == 0,
        "requiresAcceptanceMissing": requires_acceptance_missing,
        "suites": suites,
    }
    write_json(output_dir / "phase90_summary.json", summary)
    write_json(output_dir / "operator_roi.json", {"suites": suites})
    write_json(output_dir / "promotion_guard.json", {"gate": gate, "antiHardcodeGate": anti.get("gate")})
    (output_dir / "phase90_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 90 Final Quality Completion",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Accepted candidates: `{summary.get('acceptedCandidates')}`",
        f"- Checker-feasible candidates: `{summary.get('checkerFeasibleCandidates')}`",
        f"- Objective-improving candidates: `{summary.get('objectiveImprovingCandidates')}`",
        f"- Quality opportunity cases: `{summary.get('qualityOpportunityCases')}`",
        f"- Bounded no-improvement: `{summary.get('boundedSearchNoImprovement')}`",
        f"- Safe returns: `{summary.get('safeReturns')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        "",
        "Phase 90 keeps safety gates active and does not promote the optimizer to production main.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 90 final quality completion benchmark.")
    parser.add_argument("--suites", default="vroom-capability-full")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=5)
    parser.add_argument("--quality-opportunity-only", action="store_true")
    parser.add_argument("--max-runtime-tolerance-ms", type=int, default=1000)
    parser.add_argument("--final-reserve-ms", type=int, default=25)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE90 FINAL QUALITY] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
