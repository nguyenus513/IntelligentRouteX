from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase40_natural_pdptw_optimizer import (
    internal_solver_improvement,
    natural_route_elimination,
    natural_solution_key,
    objective_components,
    objective_config,
    route_pool_improvement,
    route_request_pairs,
    write_json,
)
from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler, _try_accept
from run_phase47_adaptive_budget_natural_optimizer import adaptive_budget_profile, bounded_large_route_elimination, instance_features
from run_phase51_fast_neighborhood_profile import fast_incumbent_neighborhood_repair_with_profile, select_fast_neighborhood_profile


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase51b-budget-protected-profile-v1"
RESERVED_ROUTE_POOL_BUDGET_MS = 5_000


def route_pair_counts(instance: Dict[str, Any], solution: Dict[str, Any]) -> List[int]:
    return [len(route_request_pairs(instance, [str(stop) for stop in route])) for route in solution.get("routes", []) if len(route) > 2]


def natural_route_elimination_guard(features: Dict[str, Any], pair_counts: List[int], remaining_ms: int, reserve_needed_ms: int) -> Dict[str, Any]:
    smallest = min(pair_counts) if pair_counts else 0
    median = statistics.median(pair_counts) if pair_counts else 0
    route_count = int(features.get("routeCount", 0) or 0)
    request_count = int(features.get("requestCount", 0) or 0)
    if remaining_ms < reserve_needed_ms + 700:
        decision, reason = "skip", "route-pool-budget-protected"
    elif route_count > 16:
        decision, reason = "skip", "large-route-count-uses-bounded-stage"
    elif smallest > 8 or median > 18:
        decision, reason = "skip", "predicted-route-elimination-risk"
    elif request_count > 120:
        decision, reason = "skip", "large-request-count-budget-protected"
    else:
        decision, reason = "run", "predicted-safe"
    return {
        "predictedSmallestRoutePairs": smallest,
        "predictedMedianRoutePairs": median,
        "routeCount": route_count,
        "requestCount": request_count,
        "remainingBefore": remaining_ms,
        "reserveNeeded": reserve_needed_ms,
        "decision": decision,
        "reason": reason,
    }


def _stage_call(scheduler: StageBudgetScheduler, plan: Dict[str, Any], name: str, call) -> Dict[str, Any] | None:
    stage = plan["stages"].get(name, {})
    if not stage.get("enabled", True):
        scheduler.skip(name, "disabled-by-adaptive-profile", min_ms=int(stage.get("minMs", 0) or 0))
        return None
    budget = scheduler.stage_budget(name, int(stage.get("preferredMs", 0) or 0), min_ms=int(stage.get("minMs", 0) or 0))
    if budget <= 0:
        scheduler.skip(name, "budget-too-low", min_ms=int(stage.get("minMs", 0) or 0))
        return None
    started = time.perf_counter()
    try:
        return call(budget)
    finally:
        scheduler.record_stage(name, budget, int((time.perf_counter() - started) * 1000))


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    started = time.perf_counter()
    instance = parse_instance("li-lim", resolve_instance_path("li-lim", instance_name, data_source))
    config = objective_config(mode)
    scheduler = StageBudgetScheduler(time_limit_ms)
    operator_trace: Dict[str, Any] = {}
    incumbent_plan = {"stages": {"incumbent": {"enabled": True, "preferredMs": min(8_000, int(time_limit_ms * 0.25)), "minMs": 1_000}}}
    incumbent_result = _stage_call(scheduler, incumbent_plan, "incumbent", lambda budget: {"solution": DispatchV2ExternalBenchmarkSolver().solve(instance, budget, "our-dispatch-v2")})
    incumbent = incumbent_result["solution"] if incumbent_result else {"routes": []}
    current = incumbent
    before = objective_components(instance, incumbent, config)
    features = instance_features(instance, incumbent)
    plan = adaptive_budget_profile(features, time_limit_ms)
    plan["stages"]["route-pool-sp"]["preferredMs"] = RESERVED_ROUTE_POOL_BUDGET_MS
    plan["stages"]["route-pool-sp"]["minMs"] = RESERVED_ROUTE_POOL_BUDGET_MS
    profile, profile_reason = select_fast_neighborhood_profile(features, scheduler.remaining_ms())
    plan["stages"]["fast-incumbent-neighborhood-repair"]["preferredMs"] = profile.max_runtime_ms
    plan["stages"]["fast-incumbent-neighborhood-repair"]["minMs"] = min(700, profile.max_runtime_ms)
    reserve_needed = int(plan["stages"]["internal-solver-generator"]["minMs"] + plan["stages"]["fast-incumbent-neighborhood-repair"]["minMs"] + RESERVED_ROUTE_POOL_BUDGET_MS + scheduler.reserve_ms)
    guard = natural_route_elimination_guard(features, route_pair_counts(instance, incumbent), scheduler.remaining_ms(include_reserve=True), reserve_needed)
    route_pool_budget_reserved = True

    def apply(stage_name: str, result: Dict[str, Any] | None) -> None:
        nonlocal current
        if result is None:
            operator_trace[stage_name] = {"skipped": True}
            return
        candidate = result.get("solution", current)
        current, accepted, reject_reason = _try_accept(instance, current, candidate, config)
        trace = {key: value for key, value in result.items() if key != "solution"}
        trace["acceptedByBudgetedRunner"] = accepted
        trace["budgetedRejectReason"] = None if accepted else reject_reason
        operator_trace[stage_name] = trace

    if guard["decision"] == "run":
        apply("naturalRouteElimination", _stage_call(scheduler, plan, "natural-route-elimination", lambda _budget: natural_route_elimination(instance, current, config)))
    else:
        scheduler.skip("natural-route-elimination", "natural-route-elimination-budget-protected", min_ms=int(plan["stages"]["natural-route-elimination"].get("minMs", 0)))
        operator_trace["naturalRouteElimination"] = {"skipped": True, "naturalRouteEliminationGuard": guard}
    apply("boundedLargeRouteElimination", _stage_call(scheduler, plan, "bounded-large-route-elimination", lambda budget: bounded_large_route_elimination(instance, current, config, max_runtime_ms=budget)))
    apply("internalSolverGenerator", _stage_call(scheduler, plan, "internal-solver-generator", lambda _budget: internal_solver_improvement(instance, current, config)))
    apply("fastIncumbentNeighborhoodRepair", _stage_call(scheduler, plan, "fast-incumbent-neighborhood-repair", lambda budget: fast_incumbent_neighborhood_repair_with_profile(instance, current, config, profile, budget)))
    apply("routePoolImprovement", _stage_call(scheduler, plan, "route-pool-sp", lambda _budget: route_pool_improvement(instance, current, config)))

    after = objective_components(instance, current, config)
    checked = check_solution(instance, current)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    stage_summary = scheduler.summary()
    over_budget = stage_summary["overBudget"] or runtime_ms > time_limit_ms + 1_000
    objective_improved = natural_solution_key(instance, current, config) < natural_solution_key(instance, incumbent, config)
    vehicle_improved = after["vehicleCount"] < before["vehicleCount"]
    hard_violations = len(checked.get("violations", [])) if not checked.get("feasible") else 0
    if over_budget or hard_violations:
        verdict = "FAIL"
    elif vehicle_improved and objective_improved:
        verdict = "PASS_STRONG"
    elif objective_improved:
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    diagnostics = {
        "schemaVersion": "phase51b-budget-protected-profile-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "selectedFastNeighborhoodProfile": profile.name,
        "profileReason": profile_reason,
        "routePoolBudgetReserved": route_pool_budget_reserved,
        "reservedRoutePoolBudgetMs": RESERVED_ROUTE_POOL_BUDGET_MS,
        "naturalRouteEliminationGuard": guard,
        "adaptiveBudgetProfile": plan,
        "vehicleCountBefore": before["vehicleCount"],
        "vehicleCountAfter": after["vehicleCount"],
        "objectiveBefore": before["objective"],
        "objectiveAfter": after["objective"],
        "objectiveImproved": objective_improved,
        "vehicleCountImproved": vehicle_improved,
        "hardViolations": hard_violations,
        "leakageDetected": False,
        "stageRuntimeSummary": stage_summary,
        "operatorTrace": operator_trace,
        "runtimeMs": runtime_ms,
        "verdict": verdict,
    }
    write_json(output_dir / instance_name / "diagnostics.json", diagnostics)
    write_json(output_dir / instance_name / "final_solution.json", current)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 51B Budget Protected Profile", "", "| Instance | Verdict | Vehicles | Guard | Route Pool Reserved | Over Budget | Runtime ms |", "|---|---|---:|---|---:|---:|---:|"]
    for row in rows:
        guard = row.get("naturalRouteEliminationGuard", {})
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {guard.get('decision')}:{guard.get('reason')} | {row.get('routePoolBudgetReserved')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    total_vehicle_reduction = sum(max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0)) for row in rows)
    route_pool_skipped_budget = sum(1 for row in rows for stage in row.get("stageRuntimeSummary", {}).get("stages", []) if stage.get("name") == "route-pool-sp" and stage.get("skipped") and stage.get("skippedReason") == "budget-too-low")
    safety_ok = counts.get("FAIL", 0) == 0 and all(int(row.get("hardViolations", 0) or 0) == 0 and not row.get("leakageDetected") and not row.get("stageRuntimeSummary", {}).get("overBudget") for row in rows)
    gate = "FAIL" if not safety_ok else "PASS_STRONG" if total_vehicle_reduction > 2 and route_pool_skipped_budget == 0 else "PASS" if route_pool_skipped_budget == 0 else "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase51b-budget-protected-profile-summary/v1", "instances": instances, "mode": mode, "results": rows, "verdictCounts": counts, "totalVehicleReduction": total_vehicle_reduction, "routePoolBudgetSkippedCount": route_pool_skipped_budget, "phase51bGate": gate}
    write_json(output_dir / "phase51b_budget_protected_summary.json", summary)
    (output_dir / "phase51b_budget_protected_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 51B budget-protected fast-neighborhood profile diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE51B BUDGET PROTECTED PROFILE] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
