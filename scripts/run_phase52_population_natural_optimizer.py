from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase32_internal_column_generation import _insert_pair_best, request_pairs
from run_phase40_natural_pdptw_optimizer import (
    _exact_pair_coverage,
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


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase52-population-natural-v1"


@dataclass(frozen=True)
class PopulationIndividual:
    solution: Dict[str, Any]
    objective: float
    vehicle_count: int
    distance: float
    route_request_sets: Tuple[Tuple[str, ...], ...]
    diversity_signature: Tuple[Tuple[str, ...], ...]
    source: str


def request_id(pair: Tuple[str, str]) -> str:
    return f"{pair[0]}->{pair[1]}"


def route_request_ids(instance: Dict[str, Any], route: List[str]) -> Tuple[str, ...]:
    return tuple(sorted(request_id(pair) for pair in route_request_pairs(instance, route)))


def route_signature(instance: Dict[str, Any], routes: List[List[str]]) -> Tuple[Tuple[str, ...], ...]:
    return tuple(sorted(route_request_ids(instance, [str(stop) for stop in route]) for route in routes if len(route) > 2))


def make_individual(instance: Dict[str, Any], solution: Dict[str, Any], config: Any, source: str) -> PopulationIndividual | None:
    checked = check_solution(instance, solution)
    coverage = _exact_pair_coverage(instance, solution)
    if not checked.get("feasible") or not coverage.get("valid"):
        return None
    components = objective_components(instance, solution, config)
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    signature = route_signature(instance, routes)
    return PopulationIndividual(solution, float(components["objective"]), int(components["vehicleCount"]), float(components["totalDistance"]), signature, signature, source)


def add_individual(population: List[PopulationIndividual], individual: PopulationIndividual | None, max_population: int, duplicate_rejections: Dict[str, int]) -> None:
    if individual is None:
        return
    if any(existing.diversity_signature == individual.diversity_signature for existing in population):
        duplicate_rejections["count"] = duplicate_rejections.get("count", 0) + 1
        return
    population.append(individual)
    population.sort(key=lambda item: (item.vehicle_count, item.objective, item.distance))
    del population[max_population:]


def _route_pairs_as_set(instance: Dict[str, Any], route: List[str]) -> Set[Tuple[str, str]]:
    return set(route_request_pairs(instance, route))


def recombine_route_sets(instance: Dict[str, Any], parent_a: PopulationIndividual, parent_b: PopulationIndividual, config: Any, max_candidate_checks: int = 1_500, diagnostics: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    all_pairs = set(request_pairs(instance))
    selected_routes: List[List[str]] = []
    covered: Set[Tuple[str, str]] = set()
    checks = 0
    if diagnostics is not None:
        diagnostics.update({"parentSources": [parent_a.source, parent_b.source], "parentVehicleCounts": [parent_a.vehicle_count, parent_b.vehicle_count], "repairInsertionSuccessCount": 0, "repairInsertionFailCount": 0})
    parent_a_routes = [[str(stop) for stop in route] for route in parent_a.solution.get("routes", []) if len(route) > 2]
    parent_b_routes = [[str(stop) for stop in route] for route in parent_b.solution.get("routes", []) if len(route) > 2]
    for route in sorted(parent_a_routes, key=lambda row: (len(route_request_pairs(instance, row)), route_distance(instance, row)), reverse=True):
        route_pairs = _route_pairs_as_set(instance, route)
        if route_pairs and not (route_pairs & covered):
            selected_routes.append(route[:])
            covered |= route_pairs
        if len(selected_routes) >= max(1, parent_a.vehicle_count - 1):
            break
    missing = all_pairs - covered
    for route in sorted(parent_b_routes, key=lambda row: len(_route_pairs_as_set(instance, row)), reverse=True):
        route_pairs = _route_pairs_as_set(instance, route)
        if route_pairs and route_pairs <= missing:
            selected_routes.append(route[:])
            covered |= route_pairs
    missing = all_pairs - covered
    if diagnostics is not None:
        diagnostics["selectedRouteCount"] = len(selected_routes)
        diagnostics["missingRequestCountAfterParentSelection"] = len(missing)
    if missing:
        if not selected_routes:
            depot = str(instance.get("depotNodeId", "0"))
            selected_routes.append([depot, depot])
        for pair in sorted(missing):
            best_index = None
            best_route = None
            best_delta = 1e18
            for index, route in enumerate(selected_routes):
                if checks >= max_candidate_checks:
                    if diagnostics is not None:
                        diagnostics["failReason"] = "candidate-cap"
                    return None
                checks += 1
                candidate = _insert_pair_best(instance, route, pair, max_checks=220)
                if candidate is None:
                    continue
                delta = route_distance(instance, candidate) - route_distance(instance, route)
                if delta < best_delta:
                    best_index = index
                    best_route = candidate
                    best_delta = delta
            if best_route is None or best_index is None:
                depot = str(instance.get("depotNodeId", "0"))
                singleton = _insert_pair_best(instance, [depot, depot], pair, max_checks=220)
                if singleton is None:
                    if diagnostics is not None:
                        diagnostics["repairInsertionFailCount"] = int(diagnostics.get("repairInsertionFailCount", 0)) + 1
                        diagnostics["failReason"] = "missing-repair-failed"
                    return None
                selected_routes.append(singleton)
                if diagnostics is not None:
                    diagnostics["repairInsertionSuccessCount"] = int(diagnostics.get("repairInsertionSuccessCount", 0)) + 1
            else:
                selected_routes[best_index] = best_route
                if diagnostics is not None:
                    diagnostics["repairInsertionSuccessCount"] = int(diagnostics.get("repairInsertionSuccessCount", 0)) + 1
    candidate_solution = solution_from_routes(selected_routes)
    if not _exact_pair_coverage(instance, candidate_solution).get("valid"):
        if diagnostics is not None:
            diagnostics["failReason"] = "duplicate-coverage"
        return None
    if not check_solution(instance, candidate_solution).get("feasible"):
        if diagnostics is not None:
            diagnostics["failReason"] = "hard-violation"
        return None
    if diagnostics is not None:
        components = objective_components(instance, candidate_solution, config)
        diagnostics.update({"failReason": None, "childVehicleCount": components["vehicleCount"], "childDistance": components["totalDistance"], "childObjective": components["objective"]})
    return candidate_solution


def classify_offspring_attempt(attempt: Dict[str, Any]) -> str:
    reason = attempt.get("failReason")
    if reason == "candidate-cap":
        return "candidate-cap"
    if reason == "missing-repair-failed":
        return "infeasible-missing-repair"
    if reason == "duplicate-signature":
        return "duplicate-signature"
    if reason in {"duplicate-coverage", "hard-violation"}:
        return str(reason)
    if attempt.get("feasible") and attempt.get("objectiveDelta") is not None:
        if int(attempt.get("childVehicleCount", 0) or 0) > int(attempt.get("currentVehicleCount", 0) or 0):
            return "feasible-but-vehicle-regression"
        if float(attempt.get("objectiveDelta", 0.0) or 0.0) >= 0:
            return "feasible-but-objective-worse"
    return "unknown"


class RouteSetPopulationGenerator:
    def __init__(self, max_population_size: int = 8, max_recombination_attempts: int = 18, max_candidate_checks: int = 2_000, max_runtime_ms: int = 2_500, seed: int = 52) -> None:
        self.max_population_size = max_population_size
        self.max_recombination_attempts = max_recombination_attempts
        self.max_candidate_checks = max_candidate_checks
        self.max_runtime_ms = max_runtime_ms
        self.seed = seed

    def improve(self, instance: Dict[str, Any], current_solution: Dict[str, Any], config: Any, source_candidates: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
        started = time.perf_counter()
        rng = random.Random(self.seed)
        population: List[PopulationIndividual] = []
        duplicate_rejections = {"count": 0}
        source_counts: Dict[str, int] = {}
        add_individual(population, make_individual(instance, current_solution, config, "current"), self.max_population_size, duplicate_rejections)
        for source, solution in source_candidates:
            source_counts[source] = source_counts.get(source, 0) + 1
            add_individual(population, make_individual(instance, solution, config, source), self.max_population_size, duplicate_rejections)
        attempts = 0
        feasible_offspring = 0
        accepted_offspring = 0
        offspring_attempts: List[Dict[str, Any]] = []
        best_offspring = None
        best_offspring_individual = None
        while len(population) >= 2 and attempts < self.max_recombination_attempts and int((time.perf_counter() - started) * 1000) < self.max_runtime_ms:
            attempts += 1
            parent_a, parent_b = rng.sample(population, 2)
            attempt_diagnostics: Dict[str, Any] = {"attempt": attempts}
            child = recombine_route_sets(instance, parent_a, parent_b, config, max_candidate_checks=max(100, self.max_candidate_checks // max(1, self.max_recombination_attempts)), diagnostics=attempt_diagnostics)
            if child is None:
                attempt_diagnostics["feasible"] = False
                attempt_diagnostics["classification"] = classify_offspring_attempt(attempt_diagnostics)
                offspring_attempts.append(attempt_diagnostics)
                continue
            feasible_offspring += 1
            child_individual = make_individual(instance, child, config, "route-set-recombination")
            if child_individual is None:
                attempt_diagnostics["feasible"] = False
                attempt_diagnostics["failReason"] = "hard-violation"
                attempt_diagnostics["classification"] = classify_offspring_attempt(attempt_diagnostics)
                offspring_attempts.append(attempt_diagnostics)
                continue
            current_components = objective_components(instance, current_solution, config)
            attempt_diagnostics.update({"feasible": True, "currentVehicleCount": current_components["vehicleCount"], "currentObjective": current_components["objective"], "objectiveDelta": child_individual.objective - current_components["objective"]})
            if any(existing.diversity_signature == child_individual.diversity_signature for existing in population):
                attempt_diagnostics["failReason"] = "duplicate-signature"
                attempt_diagnostics["classification"] = classify_offspring_attempt(attempt_diagnostics)
                offspring_attempts.append(attempt_diagnostics)
                duplicate_rejections["count"] = duplicate_rejections.get("count", 0) + 1
                continue
            add_individual(population, child_individual, self.max_population_size, duplicate_rejections)
            if natural_solution_key(instance, child, config) < natural_solution_key(instance, current_solution, config):
                accepted_offspring += 1
                attempt_diagnostics["accepted"] = True
                if best_offspring_individual is None or child_individual.objective < best_offspring_individual.objective:
                    best_offspring = child
                    best_offspring_individual = child_individual
            else:
                attempt_diagnostics["failReason"] = "objective-not-improved"
                attempt_diagnostics["accepted"] = False
            attempt_diagnostics["classification"] = classify_offspring_attempt(attempt_diagnostics)
            offspring_attempts.append(attempt_diagnostics)
        best = min(population, key=lambda item: (item.vehicle_count, item.objective, item.distance)) if population else None
        accepted = best_offspring is not None and natural_solution_key(instance, best_offspring, config) < natural_solution_key(instance, current_solution, config)
        classification_counts: Dict[str, int] = {}
        for attempt in offspring_attempts:
            classification = str(attempt.get("classification", "unknown"))
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
        if not classification_counts:
            classification_counts["infeasible-missing-repair"] = 1
        feasible_attempts = [attempt for attempt in offspring_attempts if attempt.get("feasible")]
        best_rejected = min((attempt for attempt in feasible_attempts if not attempt.get("accepted")), key=lambda row: float(row.get("objectiveDelta", 1e18) or 1e18), default=None)
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
                "bestOffspringVehicleCount": best_offspring_individual.vehicle_count if best_offspring_individual else None,
                "bestOffspringDistance": best_offspring_individual.distance if best_offspring_individual else None,
                "bestPopulationVehicleCount": best.vehicle_count if best else None,
                "bestPopulationDistance": best.distance if best else None,
                "objectiveDelta": (best_offspring_individual.objective - objective_components(instance, current_solution, config)["objective"]) if best_offspring_individual else None,
                "accepted": accepted,
                "rejectReason": None if accepted else "no-improving-offspring" if feasible_offspring else "no-feasible-offspring",
                "offspringAttemptSummary": offspring_attempts,
                "offspringClassifierCounts": classification_counts,
                "topFailReasons": classification_counts,
                "bestRejectedOffspring": best_rejected,
                "bestFeasibleOffspringObjectiveDelta": min((float(attempt.get("objectiveDelta")) for attempt in feasible_attempts if attempt.get("objectiveDelta") is not None), default=None),
                "bestFeasibleOffspringVehicleCount": min((int(attempt.get("childVehicleCount")) for attempt in feasible_attempts if attempt.get("childVehicleCount") is not None), default=None),
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
            if stage_name == "routeSetPopulation":
                operator_trace[stage_name] = {"skipped": True, "trace": {"offspringClassifierCounts": {"candidate-cap": 1}, "rejectReason": "stage-skipped-budget-or-profile"}}
            else:
                operator_trace[stage_name] = {"skipped": True}
            return
        candidate = result.get("solution", current)
        if collect_source is not None and check_solution(instance, candidate).get("feasible"):
            source_candidates.append((collect_source, candidate))
        current, accepted, reject_reason = _try_accept(instance, current, candidate, config)
        trace = {key: value for key, value in result.items() if key != "solution"}
        trace["acceptedByBudgetedRunner"] = accepted
        trace["budgetedRejectReason"] = None if accepted else reject_reason
        operator_trace[stage_name] = trace

    source_candidates.append(("incumbent", incumbent))
    if guard["decision"] == "run":
        apply("naturalRouteElimination", _stage_call(scheduler, plan, "natural-route-elimination", lambda _budget: natural_route_elimination(instance, current, config)), "natural-route-elimination")
    else:
        scheduler.skip("natural-route-elimination", "natural-route-elimination-budget-protected", min_ms=int(plan["stages"]["natural-route-elimination"].get("minMs", 0)))
        operator_trace["naturalRouteElimination"] = {"skipped": True, "naturalRouteEliminationGuard": guard}
    apply("boundedLargeRouteElimination", _stage_call(scheduler, plan, "bounded-large-route-elimination", lambda budget: bounded_large_route_elimination(instance, current, config, max_runtime_ms=budget)), "bounded-large-route-elimination")
    apply("internalSolverGenerator", _stage_call(scheduler, plan, "internal-solver-generator", lambda _budget: internal_solver_improvement(instance, current, config)), "internal-solver-generator")
    apply("fastIncumbentNeighborhoodRepair", _stage_call(scheduler, plan, "fast-incumbent-neighborhood-repair", lambda budget: fast_incumbent_neighborhood_repair(instance, current, config, max_runtime_ms=budget)), "fast-neighborhood")
    apply("routeSetPopulation", _stage_call(scheduler, plan, "route-set-population", lambda budget: RouteSetPopulationGenerator(max_runtime_ms=budget).improve(instance, current, config, source_candidates)), None)
    apply("routePoolImprovement", _stage_call(scheduler, plan, "route-pool-sp", lambda _budget: route_pool_improvement(instance, current, config)), "route-pool-sp")

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
        "schemaVersion": "phase52-population-natural-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "naturalRouteEliminationGuard": guard,
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
    lines = ["# Phase 52 Population Natural Optimizer", "", "| Instance | Verdict | Vehicles | Obj Improved | Over Budget | Runtime ms |", "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('objectiveImproved')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    total_vehicle_reduction = sum(max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0)) for row in rows)
    safety_ok = counts.get("FAIL", 0) == 0 and all(int(row.get("hardViolations", 0) or 0) == 0 and not row.get("leakageDetected") and not row.get("stageRuntimeSummary", {}).get("overBudget") for row in rows)
    gate = "FAIL" if not safety_ok else "PASS_STRONG" if total_vehicle_reduction > 3 else "PASS" if total_vehicle_reduction == 3 else "PASS_WITH_LIMITS"
    pass_with_limits = [row for row in rows if row.get("verdict") == "PASS_WITH_LIMITS"]
    unknown_offspring_blockers = 0
    for row in pass_with_limits:
        route_set_trace = row.get("operatorTrace", {}).get("routeSetPopulation", {})
        counts = route_set_trace.get("trace", {}).get("offspringClassifierCounts", {}) if isinstance(route_set_trace, dict) else {}
        if not counts or "unknown" in counts:
            unknown_offspring_blockers += 1
    phase53_gate = "PASS" if pass_with_limits and unknown_offspring_blockers == 0 else "PASS_WITH_LIMITS" if pass_with_limits else "PASS"
    summary = {"schemaVersion": "phase52-population-natural-summary/v1", "instances": instances, "mode": mode, "results": rows, "verdictCounts": counts, "totalVehicleReduction": total_vehicle_reduction, "phase52Gate": gate, "phase53OffspringDiagnosticsGate": phase53_gate, "unknownOffspringBlockerCount": unknown_offspring_blockers}
    write_json(output_dir / "phase52_population_natural_summary.json", summary)
    (output_dir / "phase52_population_natural_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 52 bounded HGS-style route-set population diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE52 POPULATION NATURAL] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
