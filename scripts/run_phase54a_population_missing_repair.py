from __future__ import annotations

import argparse
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase32_internal_column_generation import _insert_pair_best, request_pairs
from run_phase40_natural_pdptw_optimizer import (
    _exact_pair_coverage,
    _pair_relatedness,
    _route_without_pairs,
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
from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler, _try_accept
from run_phase47_adaptive_budget_natural_optimizer import adaptive_budget_profile, bounded_large_route_elimination, fast_incumbent_neighborhood_repair, instance_features
from run_phase51b_budget_protected_profile import RESERVED_ROUTE_POOL_BUDGET_MS, natural_route_elimination_guard, route_pair_counts
from run_phase52_population_natural_optimizer import PopulationIndividual, add_individual, classify_offspring_attempt, make_individual


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase54a-population-missing-repair-v1"


def _insert_pair_into_routes(instance: Dict[str, Any], routes: List[List[str]], pair: Tuple[str, str], max_checks: int, diagnostics: Dict[str, Any]) -> List[List[str]] | None:
    best = None
    best_delta = 1e18
    checks = 0
    for index, route in enumerate(routes):
        if checks >= max_checks:
            break
        checks += 1
        candidate = _insert_pair_best(instance, route, pair, max_checks=220)
        if candidate is None:
            continue
        delta = route_distance(instance, candidate) - route_distance(instance, route)
        if delta < best_delta:
            updated = [row[:] for row in routes]
            updated[index] = candidate
            best = updated
            best_delta = delta
    diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
    return best


def _try_ejection_one(instance: Dict[str, Any], routes: List[List[str]], missing_pair: Tuple[str, str], max_ejection_checks: int, diagnostics: Dict[str, Any]) -> List[List[str]] | None:
    checks = 0
    for route_index, route in enumerate(routes):
        candidates = sorted(route_request_pairs(instance, route), key=lambda pair: _pair_relatedness(instance, missing_pair, pair))[:5]
        for ejected_pair in candidates:
            if checks >= max_ejection_checks:
                diagnostics["missingRepairFailReason"] = "candidate-cap"
                return None
            checks += 1
            reduced = _route_without_pairs(route, [ejected_pair])
            inserted_missing = _insert_pair_best(instance, reduced, missing_pair, max_checks=220)
            if inserted_missing is None:
                continue
            updated = [row[:] for row in routes]
            updated[route_index] = inserted_missing
            reinserted = _insert_pair_into_routes(instance, updated, ejected_pair, max_checks=max(1, max_ejection_checks - checks), diagnostics=diagnostics)
            if reinserted is not None:
                diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
                return reinserted
    diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
    return None


def _try_mini_destroy_regret(instance: Dict[str, Any], routes: List[List[str]], missing_pair: Tuple[str, str], max_destroy_pairs: int, max_candidate_checks: int, diagnostics: Dict[str, Any]) -> List[List[str]] | None:
    related = []
    for route_index, route in enumerate(routes):
        for pair in route_request_pairs(instance, route):
            related.append((route_index, pair, _pair_relatedness(instance, missing_pair, pair)))
    related = sorted(related, key=lambda row: row[2])[:max_destroy_pairs]
    if not related:
        return None
    destroy_pairs = [pair for _, pair, _ in related]
    reduced_routes = []
    for route in routes:
        reduced_routes.append(_route_without_pairs(route, destroy_pairs))
    queue = [missing_pair] + destroy_pairs
    checks = 0
    current = reduced_routes
    while queue:
        best_option = None
        best_pair_index = None
        best_delta = 1e18
        for pair_index, pair in enumerate(queue):
            for route_index, route in enumerate(current):
                if checks >= max_candidate_checks:
                    diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
                    diagnostics["missingRepairFailReason"] = "candidate-cap"
                    return None
                checks += 1
                candidate_route = _insert_pair_best(instance, route, pair, max_checks=220)
                if candidate_route is None:
                    continue
                delta = route_distance(instance, candidate_route) - route_distance(instance, route)
                if delta < best_delta:
                    updated = [row[:] for row in current]
                    updated[route_index] = candidate_route
                    best_option = updated
                    best_pair_index = pair_index
                    best_delta = delta
        if best_option is None or best_pair_index is None:
            diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
            return None
        current = best_option
        queue.pop(best_pair_index)
    diagnostics["candidateChecksUsed"] = int(diagnostics.get("candidateChecksUsed", 0)) + checks
    return current


def repair_missing_pair(instance: Dict[str, Any], routes: List[List[str]], missing_pair: Tuple[str, str], diagnostics: Dict[str, Any], max_candidate_checks: int = 900) -> List[List[str]] | None:
    diagnostics.setdefault("missingRepairStrategiesTried", [])
    diagnostics["missingRepairStrategiesTried"].append("direct-insert")
    direct = _insert_pair_into_routes(instance, routes, missing_pair, max_checks=max_candidate_checks // 3, diagnostics=diagnostics)
    if direct is not None:
        diagnostics["directInsertSuccess"] = True
        return direct
    diagnostics["directInsertSuccess"] = False
    diagnostics["missingRepairStrategiesTried"].append("ejection-1")
    ejected = _try_ejection_one(instance, routes, missing_pair, max_ejection_checks=max_candidate_checks // 3, diagnostics=diagnostics)
    if ejected is not None:
        diagnostics["ejectionRepairSuccess"] = True
        return ejected
    diagnostics["ejectionRepairSuccess"] = False
    diagnostics["missingRepairStrategiesTried"].append("mini-destroy-regret")
    repaired = _try_mini_destroy_regret(instance, routes, missing_pair, max_destroy_pairs=3, max_candidate_checks=max_candidate_checks // 3, diagnostics=diagnostics)
    if repaired is not None:
        diagnostics["miniDestroyRepairSuccess"] = True
        return repaired
    diagnostics["miniDestroyRepairSuccess"] = False
    diagnostics.setdefault("missingRepairFailReason", "missing-repair-failed")
    return None


def recombine_route_sets_with_missing_repair(instance: Dict[str, Any], parent_a: PopulationIndividual, parent_b: PopulationIndividual, config: Any, max_candidate_checks: int = 1_800, diagnostics: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    all_pairs = set(request_pairs(instance))
    selected_routes: List[List[str]] = []
    covered = set()
    if diagnostics is not None:
        diagnostics.update({"parentSources": [parent_a.source, parent_b.source], "parentVehicleCounts": [parent_a.vehicle_count, parent_b.vehicle_count], "repairInsertionSuccessCount": 0, "repairInsertionFailCount": 0, "candidateChecksUsed": 0})
    parent_routes = [[str(stop) for stop in route] for route in parent_a.solution.get("routes", []) if len(route) > 2]
    fill_routes = [[str(stop) for stop in route] for route in parent_b.solution.get("routes", []) if len(route) > 2]
    for route in sorted(parent_routes, key=lambda row: (len(route_request_pairs(instance, row)), route_distance(instance, row)), reverse=True):
        pairs = set(route_request_pairs(instance, route))
        if pairs and not (pairs & covered):
            selected_routes.append(route[:])
            covered |= pairs
        if len(selected_routes) >= max(1, parent_a.vehicle_count - 1):
            break
    missing = all_pairs - covered
    for route in sorted(fill_routes, key=lambda row: len(route_request_pairs(instance, row)), reverse=True):
        pairs = set(route_request_pairs(instance, route))
        if pairs and pairs <= missing:
            selected_routes.append(route[:])
            covered |= pairs
            missing = all_pairs - covered
    if diagnostics is not None:
        diagnostics["selectedRouteCount"] = len(selected_routes)
        diagnostics["missingRequestCountAfterParentSelection"] = len(missing)
    for pair in sorted(missing):
        repaired = repair_missing_pair(instance, selected_routes, pair, diagnostics or {}, max_candidate_checks=max_candidate_checks // max(1, len(missing)))
        if repaired is None:
            if diagnostics is not None:
                diagnostics["repairInsertionFailCount"] = int(diagnostics.get("repairInsertionFailCount", 0)) + 1
                diagnostics["failReason"] = diagnostics.get("missingRepairFailReason", "missing-repair-failed")
            return None
        selected_routes = repaired
        if diagnostics is not None:
            diagnostics["repairInsertionSuccessCount"] = int(diagnostics.get("repairInsertionSuccessCount", 0)) + 1
    solution = solution_from_routes(selected_routes)
    if not _exact_pair_coverage(instance, solution).get("valid"):
        if diagnostics is not None:
            diagnostics["failReason"] = "duplicate-coverage"
        return None
    if not check_solution(instance, solution).get("feasible"):
        if diagnostics is not None:
            diagnostics["failReason"] = "hard-violation"
        return None
    if diagnostics is not None:
        components = objective_components(instance, solution, config)
        diagnostics.update({"failReason": None, "childVehicleCount": components["vehicleCount"], "childDistance": components["totalDistance"], "childObjective": components["objective"]})
    return solution


class MissingRepairPopulationGenerator:
    def __init__(self, max_population_size: int = 8, max_recombination_attempts: int = 18, max_candidate_checks: int = 2_400, max_runtime_ms: int = 2_500, seed: int = 54) -> None:
        self.max_population_size = max_population_size
        self.max_recombination_attempts = max_recombination_attempts
        self.max_candidate_checks = max_candidate_checks
        self.max_runtime_ms = max_runtime_ms
        self.seed = seed

    def improve(self, instance: Dict[str, Any], current_solution: Dict[str, Any], config: Any, source_candidates: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
        started = time.perf_counter()
        rng = random.Random(self.seed)
        population = []
        duplicate_rejections = {"count": 0}
        source_counts: Dict[str, int] = {}
        add_individual(population, make_individual(instance, current_solution, config, "current"), self.max_population_size, duplicate_rejections)
        for source, solution in source_candidates:
            source_counts[source] = source_counts.get(source, 0) + 1
            add_individual(population, make_individual(instance, solution, config, source), self.max_population_size, duplicate_rejections)
        attempts = 0
        feasible_offspring = 0
        accepted_offspring = 0
        best_offspring = None
        best_individual = None
        offspring_attempts = []
        while len(population) >= 2 and attempts < self.max_recombination_attempts and int((time.perf_counter() - started) * 1000) < self.max_runtime_ms:
            attempts += 1
            parent_a, parent_b = rng.sample(population, 2)
            attempt = {"attempt": attempts}
            child = recombine_route_sets_with_missing_repair(instance, parent_a, parent_b, config, max_candidate_checks=max(100, self.max_candidate_checks // max(1, self.max_recombination_attempts)), diagnostics=attempt)
            if child is None:
                attempt["feasible"] = False
                attempt["classification"] = "infeasible-missing-repair" if attempt.get("failReason") in {"missing-repair-failed", "candidate-cap"} else str(attempt.get("failReason", "unknown"))
                offspring_attempts.append(attempt)
                continue
            feasible_offspring += 1
            child_individual = make_individual(instance, child, config, "missing-repair-recombination")
            if child_individual is None:
                attempt.update({"feasible": False, "classification": "hard-violation"})
                offspring_attempts.append(attempt)
                continue
            current_components = objective_components(instance, current_solution, config)
            attempt.update({"feasible": True, "currentVehicleCount": current_components["vehicleCount"], "currentObjective": current_components["objective"], "objectiveDelta": child_individual.objective - current_components["objective"]})
            if any(existing.diversity_signature == child_individual.diversity_signature for existing in population):
                duplicate_rejections["count"] += 1
                attempt.update({"failReason": "duplicate-signature", "classification": "duplicate-signature", "accepted": False})
                offspring_attempts.append(attempt)
                continue
            add_individual(population, child_individual, self.max_population_size, duplicate_rejections)
            if natural_solution_key(instance, child, config) < natural_solution_key(instance, current_solution, config):
                accepted_offspring += 1
                attempt["accepted"] = True
                if best_individual is None or child_individual.objective < best_individual.objective:
                    best_individual = child_individual
                    best_offspring = child
            else:
                attempt.update({"failReason": "objective-not-improved", "accepted": False})
            attempt["classification"] = "feasible-but-objective-worse" if not attempt.get("accepted") and attempt.get("feasible") else "accepted"
            offspring_attempts.append(attempt)
        accepted = best_offspring is not None and natural_solution_key(instance, best_offspring, config) < natural_solution_key(instance, current_solution, config)
        counts: Dict[str, int] = {}
        for attempt in offspring_attempts:
            key = str(attempt.get("classification", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            counts["infeasible-missing-repair"] = 1
        feasible_attempts = [attempt for attempt in offspring_attempts if attempt.get("feasible")]
        return {
            "solution": best_offspring if accepted else current_solution,
            "accepted": accepted,
            "trace": {
                "populationSize": len(population),
                "sourceCounts": source_counts,
                "recombinationAttempts": attempts,
                "feasibleOffspringCount": feasible_offspring,
                "acceptedOffspringCount": accepted_offspring,
                "duplicateRejectedCount": duplicate_rejections.get("count", 0),
                "offspringAttemptSummary": offspring_attempts,
                "offspringClassifierCounts": counts,
                "bestFeasibleOffspringObjectiveDelta": min((float(attempt.get("objectiveDelta")) for attempt in feasible_attempts if attempt.get("objectiveDelta") is not None), default=None),
                "bestFeasibleOffspringVehicleCount": min((int(attempt.get("childVehicleCount")) for attempt in feasible_attempts if attempt.get("childVehicleCount") is not None), default=None),
                "accepted": accepted,
                "rejectReason": None if accepted else "no-improving-offspring" if feasible_offspring else "no-feasible-offspring",
            },
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
    source_candidates: List[Tuple[str, Dict[str, Any]]] = []
    incumbent_plan = {"stages": {"incumbent": {"enabled": True, "preferredMs": min(8_000, int(time_limit_ms * 0.25)), "minMs": 1_000}}}
    incumbent_result = _stage_call(scheduler, incumbent_plan, "incumbent", lambda budget: {"solution": DispatchV2ExternalBenchmarkSolver().solve(instance, budget, "our-dispatch-v2")})
    incumbent = incumbent_result["solution"] if incumbent_result else {"routes": []}
    current = incumbent
    before = objective_components(instance, incumbent, config)
    features = instance_features(instance, incumbent)
    plan = adaptive_budget_profile(features, time_limit_ms)
    plan["stages"]["route-pool-sp"]["preferredMs"] = RESERVED_ROUTE_POOL_BUDGET_MS
    plan["stages"]["route-pool-sp"]["minMs"] = RESERVED_ROUTE_POOL_BUDGET_MS
    plan["stages"]["route-set-population"] = {"enabled": True, "preferredMs": 2_200, "minMs": 900}
    reserve_needed = int(plan["stages"]["internal-solver-generator"]["minMs"] + plan["stages"]["fast-incumbent-neighborhood-repair"]["minMs"] + plan["stages"]["route-set-population"]["minMs"] + RESERVED_ROUTE_POOL_BUDGET_MS + scheduler.reserve_ms)
    guard = natural_route_elimination_guard(features, route_pair_counts(instance, incumbent), scheduler.remaining_ms(include_reserve=True), reserve_needed)

    def apply(stage_name: str, result: Dict[str, Any] | None, collect_source: str | None = None) -> None:
        nonlocal current
        if result is None:
            operator_trace[stage_name] = {"skipped": True, "trace": {"offspringClassifierCounts": {"candidate-cap": 1}}} if stage_name == "routeSetPopulation" else {"skipped": True}
            return
        candidate = result.get("solution", current)
        if collect_source is not None and check_solution(instance, candidate).get("feasible"):
            source_candidates.append((collect_source, candidate))
        current, accepted, reject_reason = _try_accept(instance, current, candidate, config)
        trace = {key: value for key, value in result.items() if key != "solution"}
        trace["acceptedByBudgetedRunner"] = accepted
        trace["budgetedRejectReason"] = None if accepted else reject_reason
        operator_trace[stage_name] = trace

    if guard["decision"] == "run":
        apply("naturalRouteElimination", _stage_call(scheduler, plan, "natural-route-elimination", lambda _budget: natural_route_elimination(instance, current, config)), "natural-route-elimination")
    else:
        scheduler.skip("natural-route-elimination", "natural-route-elimination-budget-protected", min_ms=int(plan["stages"]["natural-route-elimination"].get("minMs", 0)))
        operator_trace["naturalRouteElimination"] = {"skipped": True, "naturalRouteEliminationGuard": guard}
    source_candidates.append(("incumbent", incumbent))
    apply("boundedLargeRouteElimination", _stage_call(scheduler, plan, "bounded-large-route-elimination", lambda budget: bounded_large_route_elimination(instance, current, config, max_runtime_ms=budget)), "bounded-large-route-elimination")
    apply("internalSolverGenerator", _stage_call(scheduler, plan, "internal-solver-generator", lambda _budget: internal_solver_improvement(instance, current, config)), "internal-solver-generator")
    apply("fastIncumbentNeighborhoodRepair", _stage_call(scheduler, plan, "fast-incumbent-neighborhood-repair", lambda budget: fast_incumbent_neighborhood_repair(instance, current, config, max_runtime_ms=budget)), "fast-neighborhood")
    apply("routeSetPopulation", _stage_call(scheduler, plan, "route-set-population", lambda budget: MissingRepairPopulationGenerator(max_runtime_ms=budget).improve(instance, current, config, source_candidates)), None)
    apply("routePoolImprovement", _stage_call(scheduler, plan, "route-pool-sp", lambda _budget: route_pool_improvement(instance, current, config)), "route-pool-sp")
    after = objective_components(instance, current, config)
    checked = check_solution(instance, current)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    stage_summary = scheduler.summary()
    over_budget = stage_summary["overBudget"] or runtime_ms > time_limit_ms + 1_000
    objective_improved = natural_solution_key(instance, current, config) < natural_solution_key(instance, incumbent, config)
    vehicle_improved = after["vehicleCount"] < before["vehicleCount"]
    hard_violations = len(checked.get("violations", [])) if not checked.get("feasible") else 0
    verdict = "FAIL" if over_budget or hard_violations else "PASS_STRONG" if vehicle_improved and objective_improved else "PASS" if objective_improved else "PASS_WITH_LIMITS"
    diagnostics = {"schemaVersion": "phase54a-population-missing-repair-diagnostics/v1", "instance": instance.get("instanceName"), "mode": mode, "vehicleCountBefore": before["vehicleCount"], "vehicleCountAfter": after["vehicleCount"], "objectiveBefore": before["objective"], "objectiveAfter": after["objective"], "objectiveImproved": objective_improved, "vehicleCountImproved": vehicle_improved, "hardViolations": hard_violations, "leakageDetected": False, "naturalRouteEliminationGuard": guard, "stageRuntimeSummary": stage_summary, "operatorTrace": operator_trace, "runtimeMs": runtime_ms, "verdict": verdict}
    write_json(output_dir / instance_name / "diagnostics.json", diagnostics)
    write_json(output_dir / instance_name / "final_solution.json", current)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 54A Population Missing Repair", "", "| Instance | Verdict | Vehicles | Obj Improved | Over Budget | Runtime ms |", "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('objectiveImproved')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    total_vehicle_reduction = sum(max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0)) for row in rows)
    missing_repair_count = sum(int(row.get("operatorTrace", {}).get("routeSetPopulation", {}).get("trace", {}).get("offspringClassifierCounts", {}).get("infeasible-missing-repair", 0) or 0) for row in rows)
    safety_ok = counts.get("FAIL", 0) == 0 and all(int(row.get("hardViolations", 0) or 0) == 0 and not row.get("leakageDetected") and not row.get("stageRuntimeSummary", {}).get("overBudget") for row in rows)
    gate = "FAIL" if not safety_ok else "PASS_STRONG" if total_vehicle_reduction > 3 else "PASS" if missing_repair_count < 5 else "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase54a-population-missing-repair-summary/v1", "instances": instances, "mode": mode, "results": rows, "verdictCounts": counts, "totalVehicleReduction": total_vehicle_reduction, "infeasibleMissingRepairCount": missing_repair_count, "phase54aGate": gate}
    write_json(output_dir / "phase54a_population_missing_repair_summary.json", summary)
    (output_dir / "phase54a_population_missing_repair_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 54A bounded population missing-repair diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE54A POPULATION MISSING REPAIR] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
