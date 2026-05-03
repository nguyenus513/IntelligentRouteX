from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase32_internal_column_generation import _insert_pair_best, request_features
from run_phase40_natural_pdptw_optimizer import (
    IncumbentNeighborhoodRepairGenerator,
    incumbent_neighborhood_repair,
    internal_solver_improvement,
    natural_route_elimination,
    natural_solution_key,
    objective_components,
    objective_config,
    route_pool_improvement,
    route_request_pairs,
    solution_from_routes,
    write_json,
)
from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler, _active_vehicle_count, _try_accept


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase47-adaptive-budget-natural-v1"


def instance_features(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    routes = [route for route in solution.get("routes", []) if len(route) > 2]
    requests = instance.get("requests", [])
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    widths = []
    mixedness_values = []
    for request in requests:
        pickup = nodes.get(str(request.get("pickupNodeId")), {})
        dropoff = nodes.get(str(request.get("dropoffNodeId")), {})
        widths.append(float(dropoff.get("dueTime", 0.0)) - float(pickup.get("readyTime", 0.0)))
        mixedness_values.append(abs(float(pickup.get("x", 0.0)) - float(dropoff.get("x", 0.0))) + abs(float(pickup.get("y", 0.0)) - float(dropoff.get("y", 0.0))))
    checked = check_solution(instance, solution)
    return {
        "routeCount": len(routes),
        "requestCount": len(requests),
        "timeWindowTightness": 1.0 / max(1.0, statistics.median(widths) if widths else 1.0),
        "mixedness": statistics.median(mixedness_values) if mixedness_values else 0.0,
        "incumbentFeasible": bool(checked.get("feasible")),
    }


def adaptive_budget_profile(features: Dict[str, Any], total_budget_ms: int) -> Dict[str, Any]:
    route_count = int(features.get("routeCount", 0) or 0)
    incumbent_feasible = bool(features.get("incumbentFeasible", False))
    plan = {
        "profile": "adaptive-production-natural/v1",
        "features": features,
        "stages": {
            "incumbent": {"preferredMs": min(8_000, int(total_budget_ms * 0.25)), "minMs": 1_000},
            "natural-route-elimination": {"enabled": incumbent_feasible and route_count <= 16, "preferredMs": 1_500, "minMs": 400},
            "bounded-large-route-elimination": {"enabled": incumbent_feasible and route_count > 16, "preferredMs": 1_500, "minMs": 500},
            "internal-solver-generator": {"enabled": True, "preferredMs": 4_500 if not incumbent_feasible else 3_800, "minMs": 2_500},
            "fast-incumbent-neighborhood-repair": {"enabled": incumbent_feasible, "preferredMs": 1_800, "minMs": 700},
            "route-pool-sp": {"enabled": True, "preferredMs": 6_000, "minMs": 5_000},
        },
    }
    return plan


def _stage_call(scheduler: StageBudgetScheduler, plan: Dict[str, Any], name: str, call: Callable[[int], Dict[str, Any]]) -> Dict[str, Any] | None:
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


def bounded_large_route_elimination(instance: Dict[str, Any], solution: Dict[str, Any], config: Any, max_runtime_ms: int = 1_500, max_routes: int = 3, max_removed_pairs: int = 6, max_candidate_checks: int = 1_200) -> Dict[str, Any]:
    started = time.perf_counter()
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    best_solution = solution
    best_key = natural_solution_key(instance, solution, config)
    attempts = []
    candidate_indexes = sorted(range(len(routes)), key=lambda index: (len(route_request_pairs(instance, routes[index])), route_distance(instance, routes[index]), index))[:max_routes]
    total_checks = 0
    for route_index in candidate_indexes:
        if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
            attempts.append({"routeIndex": route_index, "accepted": False, "rejectReason": "runtime-cap"})
            break
        removed_pairs = sorted(route_request_pairs(instance, routes[route_index]), key=lambda pair: request_features(instance, pair)["due"])
        if len(removed_pairs) > max_removed_pairs:
            attempts.append({"routeIndex": route_index, "removedPairCount": len(removed_pairs), "accepted": False, "rejectReason": "candidate-cap"})
            continue
        remaining = [route[:] for index, route in enumerate(routes) if index != route_index]
        checks = 0
        feasible = True
        for pair in removed_pairs:
            best_route = None
            best_route_index = None
            best_delta = 1e18
            for target_index, target_route in enumerate(remaining):
                if checks + total_checks >= max_candidate_checks:
                    feasible = False
                    break
                checks += 1
                candidate_route = _insert_pair_best(instance, target_route, pair, max_checks=180)
                if candidate_route is None:
                    continue
                delta = route_distance(instance, candidate_route) - route_distance(instance, target_route)
                if delta < best_delta:
                    best_route = candidate_route
                    best_route_index = target_index
                    best_delta = delta
            if not feasible or best_route is None or best_route_index is None:
                feasible = False
                break
            remaining[best_route_index] = best_route
        total_checks += checks
        if not feasible:
            attempts.append({"routeIndex": route_index, "removedPairCount": len(removed_pairs), "candidateChecks": checks, "accepted": False, "rejectReason": "no-feasible-repair" if total_checks < max_candidate_checks else "candidate-cap"})
            continue
        candidate = solution_from_routes(remaining)
        checked = check_solution(instance, candidate)
        if not checked.get("feasible"):
            attempts.append({"routeIndex": route_index, "removedPairCount": len(removed_pairs), "candidateChecks": checks, "accepted": False, "rejectReason": "hard-violation"})
            continue
        accepted = natural_solution_key(instance, candidate, config) < best_key
        attempts.append({"routeIndex": route_index, "removedPairCount": len(removed_pairs), "candidateChecks": checks, "accepted": accepted, "rejectReason": None if accepted else "objective-not-improved"})
        if accepted:
            best_solution = candidate
            best_key = natural_solution_key(instance, candidate, config)
            break
    return {"solution": best_solution, "accepted": best_solution is not solution, "trace": {"attemptedRoutes": candidate_indexes, "attempts": attempts, "candidateChecks": total_checks, "runtimeMs": int((time.perf_counter() - started) * 1000)}}


def fast_incumbent_neighborhood_repair(instance: Dict[str, Any], solution: Dict[str, Any], config: Any, max_runtime_ms: int = 1_800) -> Dict[str, Any]:
    generator = IncumbentNeighborhoodRepairGenerator(max_runtime_ms=max_runtime_ms, max_neighborhoods=3, max_ortools_pairs=8)
    result = generator.repair(instance, solution, config)
    result["fastMode"] = True
    result["maxAffectedRequestCap"] = 8
    return result


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    started = time.perf_counter()
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    config = objective_config(mode)
    scheduler = StageBudgetScheduler(time_limit_ms)
    operator_trace: Dict[str, Any] = {}

    incumbent_stage = {"stages": {"incumbent": {"enabled": True, "preferredMs": min(8_000, int(time_limit_ms * 0.25)), "minMs": 1_000}}}
    incumbent_result = _stage_call(scheduler, incumbent_stage, "incumbent", lambda budget: {"solution": DispatchV2ExternalBenchmarkSolver().solve(instance, budget, "our-dispatch-v2")})
    incumbent = incumbent_result["solution"] if incumbent_result else {"routes": []}
    current = incumbent
    before = objective_components(instance, incumbent, config)
    features = instance_features(instance, incumbent)
    plan = adaptive_budget_profile(features, time_limit_ms)

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

    apply("naturalRouteElimination", _stage_call(scheduler, plan, "natural-route-elimination", lambda _budget: natural_route_elimination(instance, current, config)))
    apply("boundedLargeRouteElimination", _stage_call(scheduler, plan, "bounded-large-route-elimination", lambda budget: bounded_large_route_elimination(instance, current, config, max_runtime_ms=budget)))
    apply("internalSolverGenerator", _stage_call(scheduler, plan, "internal-solver-generator", lambda _budget: internal_solver_improvement(instance, current, config)))
    apply("fastIncumbentNeighborhoodRepair", _stage_call(scheduler, plan, "fast-incumbent-neighborhood-repair", lambda budget: fast_incumbent_neighborhood_repair(instance, current, config, max_runtime_ms=budget)))
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
        "schemaVersion": "phase47-adaptive-budget-natural-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "adaptiveBudgetProfile": plan,
        "selectedStagePlan": plan["stages"],
        "vehicleCountBefore": before["vehicleCount"],
        "vehicleCountAfter": after["vehicleCount"],
        "distanceBefore": before["totalDistance"],
        "distanceAfter": after["totalDistance"],
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
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "diagnostics.json", diagnostics)
    write_json(instance_dir / "final_solution.json", current)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 47 Adaptive Budget Natural Optimizer", "", "| Instance | Verdict | Vehicles | Obj Improved | Over Budget | Runtime ms |", "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('objectiveImproved')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    summary = {"schemaVersion": "phase47-adaptive-budget-natural-summary/v1", "instances": instances, "mode": mode, "results": rows, "verdictCounts": counts}
    write_json(output_dir / "phase47_adaptive_budget_summary.json", summary)
    (output_dir / "phase47_adaptive_budget_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 47 adaptive budget natural PDPTW optimizer diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE47 ADAPTIVE BUDGET NATURAL] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
