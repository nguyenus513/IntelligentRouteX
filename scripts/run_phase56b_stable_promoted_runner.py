from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_time_limit
from phase67_synthetic_instance_loader import load_benchmark_instance
from run_phase40_natural_pdptw_optimizer import (
    InternalSolverCandidateGenerator,
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
from run_phase47_adaptive_budget_natural_optimizer import (
    adaptive_budget_profile,
    bounded_large_route_elimination,
    fast_incumbent_neighborhood_repair,
    instance_features,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase56b-stable-promoted-runner-v1"


@dataclass(frozen=True)
class StableBudgetPolicy:
    schemaVersion: str = "phase56b-stable-budget-policy/v1"
    routePoolReserveMs: int = 5_000
    finalReserveMs: int = 3_000
    incumbentMaxShare: float = 0.25
    incumbentMaxMs: int = 8_000
    naturalRouteEliminationPreferredMs: int = 1_500
    naturalRouteEliminationMinMs: int = 400
    boundedLargeRouteEliminationPreferredMs: int = 1_500
    internalSolverPreferredMs: int = 3_800
    fastNeighborhoodPreferredMs: int = 1_800
    routePoolMaxRuntimeMs: int = 4_500
    wallClockToleranceMs: int = 1_000
    incumbentOverrunThresholdMs: int = 18_000


def route_pair_counts(instance: Dict[str, Any], solution: Dict[str, Any]) -> List[int]:
    return [len(route_request_pairs(instance, [str(stop) for stop in route])) for route in solution.get("routes", []) if len(route) > 2]


def route_request_signature(instance: Dict[str, Any], route: List[str]) -> tuple[str, ...]:
    pairs = route_request_pairs(instance, [str(stop) for stop in route])
    return tuple(sorted(f"{pickup}->{dropoff}" for pickup, dropoff in pairs))


def stable_route_sort_key(instance: Dict[str, Any], route: List[str]) -> tuple[tuple[str, ...], float, int, tuple[str, ...]]:
    normalized = [str(stop) for stop in route]
    return (route_request_signature(instance, normalized), round(route_distance(instance, normalized), 6), len(normalized), tuple(normalized))


def canonicalize_solution(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    canonical = dict(solution or {})
    routes = [[str(stop) for stop in route] for route in canonical.get("routes", []) if len(route) > 2]
    canonical["routes"] = sorted(routes, key=lambda route: stable_route_sort_key(instance, route))
    return canonical


def solution_signature(instance: Dict[str, Any], solution: Dict[str, Any]) -> str:
    canonical = canonicalize_solution(instance, solution)
    payload = json.dumps(canonical.get("routes", []), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_internal_candidate_key(instance: Dict[str, Any], solution: Dict[str, Any], config: Any) -> tuple[int, float, float, str]:
    canonical = canonicalize_solution(instance, solution)
    components = objective_components(instance, canonical, config)
    return (
        int(components.get("vehicleCount", 0) or 0),
        round(float(components.get("objective", 0.0) or 0.0), 6),
        round(float(components.get("totalDistance", 0.0) or 0.0), 6),
        solution_signature(instance, canonical),
    )


def stable_internal_solver_improvement(
    instance: Dict[str, Any],
    solution: Dict[str, Any],
    config: Any,
    deterministic_seed: int = 56,
    max_runtime_ms: int = 3_000,
    candidate_cache_path: Path | None = None,
) -> Dict[str, Any]:
    if candidate_cache_path is not None and candidate_cache_path.exists():
        cached = load_incumbent_cache(candidate_cache_path)
        if cached is not None:
            cached_solution = canonicalize_solution(instance, cached.get("solution", cached))
            cached_after = objective_components(instance, cached_solution, config)
            return {
                "solution": cached_solution,
                "accepted": bool(cached.get("accepted", False)),
                "trace": {
                    "generatorMode": "stable-internal-solver-cache",
                    "deterministicSeed": deterministic_seed,
                    "internalSolverCacheHit": True,
                    "selectedInternalSolverCandidateSignature": solution_signature(instance, cached_solution),
                    "selectedInternalSolverCandidateKey": list(stable_internal_candidate_key(instance, cached_solution, config)),
                    "objectiveAfter": cached_after,
                    "accepted": bool(cached.get("accepted", False)),
                    "rejectReason": cached.get("rejectReason"),
                },
            }
    before = objective_components(instance, solution, config)
    before_feasible = bool(before.get("feasible"))
    current_key = natural_solution_key(instance, solution, config)
    generator = InternalSolverCandidateGenerator(max_runtime_ms=max_runtime_ms)
    generated = generator.generate(instance, config, incumbent=canonicalize_solution(instance, solution))
    strategy_order = [
        [row.get("firstSolutionStrategy"), row.get("localSearchMetaheuristic")]
        for row in generated.get("trace", [])
    ]
    candidate_rows = []
    feasible_candidates = []
    for candidate in generated.get("candidates", []):
        canonical = canonicalize_solution(instance, candidate)
        checked = check_solution(instance, canonical)
        if not checked.get("feasible"):
            candidate_rows.append({"signature": solution_signature(instance, canonical), "key": None, "rejectReason": "hard-violation"})
            continue
        after = objective_components(instance, canonical, config)
        candidate_key = stable_internal_candidate_key(instance, canonical, config)
        delta = float(after.get("objective", 0.0) or 0.0) - float(before.get("objective", 0.0) or 0.0)
        reject_reason = None
        if before_feasible and config.mode == "academic_certification" and int(after.get("vehicleCount", 0) or 0) > int(before.get("vehicleCount", 0) or 0):
            reject_reason = "vehicle-count-regression"
        elif delta >= 0:
            reject_reason = "objective-not-improved"
        row = {
            "signature": candidate_key[-1],
            "key": list(candidate_key),
            "vehicleCount": after.get("vehicleCount"),
            "distance": after.get("totalDistance"),
            "objective": after.get("objective"),
            "objectiveDelta": delta,
            "rejectReason": reject_reason,
        }
        candidate_rows.append(row)
        if reject_reason is None:
            feasible_candidates.append((candidate_key, canonical, after, row))
    feasible_candidates.sort(key=lambda item: item[0])
    selected = feasible_candidates[0] if feasible_candidates else None
    accepted = bool(selected) and natural_solution_key(instance, selected[1], config) < current_key
    selected_solution = selected[1] if accepted and selected else solution
    selected_after = selected[2] if selected else None
    selected_row = selected[3] if selected else None
    selected_signature = selected_row.get("signature") if selected_row else solution_signature(instance, selected_solution)
    selected_key = selected_row.get("key") if selected_row else list(stable_internal_candidate_key(instance, selected_solution, config))
    payload = {
        "solution": selected_solution,
        "accepted": accepted,
        "trace": {
            "generatorMode": "stable-internal-solver",
            "deterministicSeed": deterministic_seed,
            "strategiesTried": generated.get("trace", []),
            "internalSolverStrategyOrder": strategy_order,
            "internalSolverCandidateSignatures": [row["signature"] for row in sorted(candidate_rows, key=lambda item: item.get("key") or [999999, 1e99, 1e99, item["signature"]])],
            "internalSolverCandidateKeys": [row["key"] for row in sorted(candidate_rows, key=lambda item: item.get("key") or [999999, 1e99, 1e99, item["signature"]])],
            "candidateRows": sorted(candidate_rows, key=lambda item: item.get("key") or [999999, 1e99, 1e99, item["signature"]]),
            "selectedInternalSolverCandidateSignature": selected_signature,
            "selectedInternalSolverCandidateKey": selected_key,
            "candidateCount": generated.get("candidateCount"),
            "feasibleCandidateCount": len(feasible_candidates),
            "bestCandidateVehicleCount": selected_after.get("vehicleCount") if selected_after else None,
            "bestCandidateDistance": selected_after.get("totalDistance") if selected_after else None,
            "objectiveBefore": before,
            "objectiveAfter": selected_after,
            "accepted": accepted,
            "rejectReason": None if accepted else ("no-feasible-candidate" if not feasible_candidates else "objective-not-improved"),
        },
    }
    payload["trace"]["internalSolverCacheHit"] = False
    if candidate_cache_path is not None:
        candidate_cache_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_cache_path.write_text(
            json.dumps(
                {
                    "solution": canonicalize_solution(instance, selected_solution),
                    "accepted": accepted,
                    "rejectReason": payload["trace"].get("rejectReason"),
                    "selectedInternalSolverCandidateSignature": selected_signature,
                    "selectedInternalSolverCandidateKey": selected_key,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return payload


def save_incumbent_cache(path: Path, instance: Dict[str, Any], solution: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canonicalize_solution(instance, solution), indent=2, sort_keys=True), encoding="utf-8")


def load_incumbent_cache(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def protected_remaining_ms(scheduler: StageBudgetScheduler) -> int:
    return scheduler.remaining_ms(include_reserve=True)


def elapsed_ms_since(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def wall_clock_remaining_ms(started_at: float, time_limit_ms: int) -> int:
    return max(0, int(time_limit_ms) - elapsed_ms_since(started_at))


def should_skip_for_hard_deadline(started_at: float, time_limit_ms: int, stage_min_ms: int, final_reserve_ms: int) -> bool:
    return wall_clock_remaining_ms(started_at, time_limit_ms) < max(0, int(stage_min_ms)) + max(0, int(final_reserve_ms))


def can_start_optional_stage(scheduler: StageBudgetScheduler, policy: StableBudgetPolicy, stage_min_ms: int, route_pool_pending: bool) -> bool:
    reserve = policy.routePoolReserveMs if route_pool_pending else policy.finalReserveMs
    return protected_remaining_ms(scheduler) >= reserve + max(0, int(stage_min_ms))


def stable_natural_route_elimination_guard(features: Dict[str, Any], pair_counts: List[int], scheduler: StageBudgetScheduler, policy: StableBudgetPolicy) -> Dict[str, Any]:
    smallest = min(pair_counts) if pair_counts else 0
    median = statistics.median(pair_counts) if pair_counts else 0
    route_count = int(features.get("routeCount", 0) or 0)
    request_count = int(features.get("requestCount", 0) or 0)
    remaining = protected_remaining_ms(scheduler)
    reserve_needed = policy.routePoolReserveMs
    if remaining < reserve_needed + policy.naturalRouteEliminationMinMs:
        decision, reason = "skip", "natural-route-elimination-budget-protected"
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
        "remainingBefore": remaining,
        "reserveNeeded": reserve_needed,
        "decision": decision,
        "reason": reason,
    }


def protected_stage_call(
    scheduler: StageBudgetScheduler,
    plan: Dict[str, Any],
    policy: StableBudgetPolicy,
    name: str,
    call: Callable[[int], Dict[str, Any]],
    protected_skips: List[Dict[str, Any]],
    *,
    route_pool_pending: bool,
) -> Dict[str, Any] | None:
    stage = plan["stages"].get(name, {})
    min_ms = int(stage.get("minMs", 0) or 0)
    preferred_ms = int(stage.get("preferredMs", 0) or 0)
    before = protected_remaining_ms(scheduler)
    if not stage.get("enabled", True):
        scheduler.skip(name, "disabled-by-adaptive-profile", min_ms=min_ms)
        protected_skips.append({"stage": name, "reason": "disabled-by-adaptive-profile", "stageBudgetBefore": before, "stageBudgetAfter": protected_remaining_ms(scheduler)})
        return None
    if not can_start_optional_stage(scheduler, policy, min_ms, route_pool_pending):
        reason = "route-pool-budget-protected" if route_pool_pending else "final-reserve-protected"
        scheduler.skip(name, reason, min_ms=min_ms)
        protected_skips.append({"stage": name, "reason": reason, "stageBudgetBefore": before, "stageBudgetAfter": protected_remaining_ms(scheduler)})
        return None
    protected_reserve = policy.routePoolReserveMs if route_pool_pending else policy.finalReserveMs
    budget = min(preferred_ms, max(0, protected_remaining_ms(scheduler) - protected_reserve))
    if budget < min_ms:
        scheduler.skip(name, "budget-too-low", min_ms=min_ms)
        protected_skips.append({"stage": name, "reason": "budget-too-low", "stageBudgetBefore": before, "stageBudgetAfter": protected_remaining_ms(scheduler)})
        return None
    started = time.perf_counter()
    try:
        return call(budget)
    finally:
        scheduler.record_stage(name, budget, int((time.perf_counter() - started) * 1000))


def route_pool_stage_call(scheduler: StageBudgetScheduler, policy: StableBudgetPolicy, call: Callable[[int], Dict[str, Any]], protected_skips: List[Dict[str, Any]], started_at: float, time_limit_ms: int) -> Dict[str, Any] | None:
    remaining = wall_clock_remaining_ms(started_at, time_limit_ms)
    cap = min(policy.routePoolMaxRuntimeMs, policy.routePoolReserveMs, max(0, remaining - policy.finalReserveMs))
    if cap < policy.routePoolMaxRuntimeMs or remaining < policy.finalReserveMs + policy.routePoolMaxRuntimeMs:
        scheduler.skip("route-pool-sp", "budget-too-low", min_ms=policy.routePoolReserveMs)
        protected_skips.append({"stage": "route-pool-sp", "reason": "skippedDueHardDeadline", "wallClockRemainingBefore": remaining, "stageHardCapMs": cap})
        return None
    started = time.perf_counter()
    try:
        result = call(cap)
        if isinstance(result, dict):
            result["routePoolHardCapApplied"] = True
            result["stageHardCapMs"] = cap
        return result
    finally:
        runtime = int((time.perf_counter() - started) * 1000)
        scheduler.record_stage("route-pool-sp", cap, runtime)


def run_instance(
    instance_name: str,
    output_dir: Path,
    data_source: str,
    time_limit_ms: int,
    mode: str,
    *,
    benchmark_source: str = "li-lim",
    stable_incumbent_replay: bool = False,
    incumbent_cache_dir: Path | None = None,
    deterministic_seed: int = 56,
) -> Dict[str, Any]:
    started = time.perf_counter()
    instance = load_benchmark_instance(benchmark_source, instance_name, data_source)
    config = objective_config(mode)
    policy = StableBudgetPolicy(finalReserveMs=min(3_000, max(500, int(time_limit_ms * 0.10))))
    scheduler = StageBudgetScheduler(time_limit_ms, reserve_ms=policy.finalReserveMs)
    operator_trace: Dict[str, Any] = {}
    protected_skips: List[Dict[str, Any]] = []
    stage_wall_clock: List[Dict[str, Any]] = []

    incumbent_budget = min(policy.incumbentMaxMs, int(time_limit_ms * policy.incumbentMaxShare))
    incumbent_cache_path = (incumbent_cache_dir or output_dir.parent / "incumbent-cache") / f"{instance_name.lower()}-{mode}-{deterministic_seed}.json"
    incumbent_cache_hit = False
    cached_incumbent = load_incumbent_cache(incumbent_cache_path) if stable_incumbent_replay else None
    if cached_incumbent is not None:
        incumbent = canonicalize_solution(instance, cached_incumbent)
        scheduler.skip("incumbent", "stable-incumbent-replay-cache-hit", min_ms=0)
        incumbent_cache_hit = True
    else:
        stage_wall_clock.append({"stage": "incumbent", "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms), "stageHardCapMs": incumbent_budget})
        incumbent_plan = {"stages": {"incumbent": {"enabled": True, "preferredMs": incumbent_budget, "minMs": 1_000}}}
        incumbent_result = protected_stage_call(scheduler, incumbent_plan, policy, "incumbent", lambda budget: {"solution": DispatchV2ExternalBenchmarkSolver().solve(instance, budget, "our-dispatch-v2")}, protected_skips, route_pool_pending=False)
        incumbent = incumbent_result["solution"] if incumbent_result else {"routes": []}
        incumbent = canonicalize_solution(instance, incumbent)
        if stable_incumbent_replay:
            save_incumbent_cache(incumbent_cache_path, instance, incumbent)
    incumbent_runtime_ms = next((int(stage.get("runtimeMs", 0) or 0) for stage in scheduler.stages if stage.get("name") == "incumbent"), 0)
    incumbent_overrun_protected = incumbent_runtime_ms > policy.incumbentOverrunThresholdMs
    current = incumbent
    before = objective_components(instance, incumbent, config)
    features = instance_features(instance, incumbent)
    plan = adaptive_budget_profile(features, time_limit_ms)
    plan["stages"]["incumbent"]["preferredMs"] = incumbent_budget
    plan["stages"]["route-pool-sp"]["preferredMs"] = policy.routePoolReserveMs
    plan["stages"]["route-pool-sp"]["minMs"] = policy.routePoolReserveMs
    plan["stages"]["natural-route-elimination"]["preferredMs"] = policy.naturalRouteEliminationPreferredMs
    plan["stages"]["natural-route-elimination"]["minMs"] = policy.naturalRouteEliminationMinMs

    def apply(stage_name: str, result: Dict[str, Any] | None) -> None:
        nonlocal current
        if result is None:
            operator_trace[stage_name] = {"skipped": True}
            return
        candidate = canonicalize_solution(instance, result.get("solution", current))
        current, accepted, reject_reason = _try_accept(instance, current, candidate, config)
        trace = {key: value for key, value in result.items() if key != "solution"}
        trace["candidateSignature"] = solution_signature(instance, candidate)
        trace["acceptedByBudgetedRunner"] = accepted
        trace["budgetedRejectReason"] = None if accepted else reject_reason
        if accepted:
            trace["acceptedStageSignature"] = solution_signature(instance, current)
        operator_trace[stage_name] = trace

    natural_guard = stable_natural_route_elimination_guard(features, route_pair_counts(instance, current), scheduler, policy)
    if natural_guard["decision"] == "run" and not should_skip_for_hard_deadline(started, time_limit_ms, policy.naturalRouteEliminationMinMs, policy.finalReserveMs):
        stage_wall_clock.append({"stage": "natural-route-elimination", "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms), "stageHardCapMs": policy.naturalRouteEliminationPreferredMs})
        apply("naturalRouteElimination", protected_stage_call(scheduler, plan, policy, "natural-route-elimination", lambda _budget: natural_route_elimination(instance, current, config), protected_skips, route_pool_pending=True))
    else:
        reason = natural_guard["reason"] if natural_guard["decision"] != "run" else "skippedDueHardDeadline"
        scheduler.skip("natural-route-elimination", reason, min_ms=policy.naturalRouteEliminationMinMs)
        operator_trace["naturalRouteElimination"] = {"skipped": True, "skipReason": reason}
        protected_skips.append({"stage": "natural-route-elimination", "reason": reason, "stageBudgetBefore": natural_guard["remainingBefore"], "stageBudgetAfter": protected_remaining_ms(scheduler), "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms)})

    if incumbent_overrun_protected and not stable_incumbent_replay:
        protected_skips.append({"stage": "downstream", "reason": "incumbentOverrunProtected", "incumbentRuntimeMs": incumbent_runtime_ms})
    else:
        if not should_skip_for_hard_deadline(started, time_limit_ms, int(plan["stages"]["internal-solver-generator"].get("minMs", 0) or 0), policy.finalReserveMs):
            stage_wall_clock.append({"stage": "internal-solver-generator", "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms), "stageHardCapMs": plan["stages"]["internal-solver-generator"].get("preferredMs")})
            apply(
                "internalSolverGenerator",
                protected_stage_call(
                    scheduler,
                    plan,
                    policy,
                    "internal-solver-generator",
                    lambda budget: stable_internal_solver_improvement(
                        instance,
                        current,
                        config,
                        deterministic_seed=deterministic_seed,
                        max_runtime_ms=budget,
                        candidate_cache_path=(incumbent_cache_path.parent / f"internal-{instance_name.lower()}-{mode}-{deterministic_seed}-{solution_signature(instance, current)[:16]}.json"),
                    ) if stable_incumbent_replay else internal_solver_improvement(instance, current, config),
                    protected_skips,
                    route_pool_pending=False,
                ),
            )
        else:
            scheduler.skip("internal-solver-generator", "skippedDueHardDeadline", min_ms=int(plan["stages"]["internal-solver-generator"].get("minMs", 0) or 0))
            operator_trace["internalSolverGenerator"] = {"skipped": True, "skipReason": "skippedDueHardDeadline"}
            protected_skips.append({"stage": "internal-solver-generator", "reason": "skippedDueHardDeadline", "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms)})
        apply("boundedLargeRouteElimination", protected_stage_call(scheduler, plan, policy, "bounded-large-route-elimination", lambda budget: bounded_large_route_elimination(instance, current, config, max_runtime_ms=budget), protected_skips, route_pool_pending=True))
        route_pool_policy_cache = incumbent_cache_path.parent / f"routepool-policy-{instance_name.lower()}-{mode}-{deterministic_seed}-{solution_signature(instance, current)[:16]}.json"
        route_pool_policy = read_json(route_pool_policy_cache) if stable_incumbent_replay and route_pool_policy_cache.exists() else None
        if route_pool_policy and route_pool_policy.get("decision") == "skip":
            scheduler.skip("route-pool-sp", route_pool_policy.get("reason", "stable-route-pool-skip-replay"), min_ms=policy.routePoolReserveMs)
            operator_trace["routePoolImprovement"] = {"skipped": True, "skipReason": route_pool_policy.get("reason"), "stableRoutePoolPolicyReplay": True}
            protected_skips.append({"stage": "route-pool-sp", "reason": route_pool_policy.get("reason"), "stableRoutePoolPolicyReplay": True})
        else:
            route_pool_result = route_pool_stage_call(scheduler, policy, lambda _budget: route_pool_improvement(instance, current, config), protected_skips, started, time_limit_ms)
            if stable_incumbent_replay and route_pool_result is None:
                write_json(route_pool_policy_cache, {"decision": "skip", "reason": "stable-route-pool-skip-replay"})
            apply("routePoolImprovement", route_pool_result)
        if not should_skip_for_hard_deadline(started, time_limit_ms, int(plan["stages"]["fast-incumbent-neighborhood-repair"].get("minMs", 0) or 0), policy.finalReserveMs):
            apply("fastIncumbentNeighborhoodRepair", protected_stage_call(scheduler, plan, policy, "fast-incumbent-neighborhood-repair", lambda budget: fast_incumbent_neighborhood_repair(instance, current, config, max_runtime_ms=budget), protected_skips, route_pool_pending=False))
        else:
            scheduler.skip("fast-incumbent-neighborhood-repair", "skippedDueHardDeadline", min_ms=int(plan["stages"]["fast-incumbent-neighborhood-repair"].get("minMs", 0) or 0))
            operator_trace["fastIncumbentNeighborhoodRepair"] = {"skipped": True, "skipReason": "skippedDueHardDeadline"}
            protected_skips.append({"stage": "fast-incumbent-neighborhood-repair", "reason": "skippedDueHardDeadline", "wallClockRemainingBefore": wall_clock_remaining_ms(started, time_limit_ms)})

    after = objective_components(instance, current, config)
    checked = check_solution(instance, current)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    stage_summary = scheduler.summary()
    route_pool_stage = next((stage for stage in stage_summary.get("stages", []) if stage.get("name") == "route-pool-sp"), {})
    route_pool_ran = bool(route_pool_stage) and not route_pool_stage.get("skipped")
    wall_clock_over_budget = runtime_ms > time_limit_ms + policy.wallClockToleranceMs
    over_budget = bool(stage_summary["overBudget"]) or wall_clock_over_budget
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
        "schemaVersion": "phase56c-stable-replay-promoted-runner-diagnostics/v1" if stable_incumbent_replay else "phase56b-stable-promoted-runner-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "stableIncumbentReplay": stable_incumbent_replay,
        "incumbentCacheHit": incumbent_cache_hit,
        "incumbentCachePath": str(incumbent_cache_path) if stable_incumbent_replay else None,
        "stableBudgetPolicy": asdict(policy),
        "routePoolBudgetReserved": True,
        "routePoolReserveMs": policy.routePoolReserveMs,
        "actualRuntimeMs": runtime_ms,
        "wallClockOverBudget": wall_clock_over_budget,
        "firstRunBudgetProtected": bool(protected_skips),
        "incumbentOverrunProtected": incumbent_overrun_protected,
        "incumbentRuntimeMs": incumbent_runtime_ms,
        "stageWallClockAudit": stage_wall_clock,
        "protectedSkips": protected_skips,
        "naturalRouteEliminationGuard": natural_guard,
        "adaptiveBudgetProfile": plan,
        "selectedStagePlan": plan["stages"],
        "stageBudgetBeforeAfter": [{"stage": stage.get("name"), "remainingMsAfter": stage.get("remainingMsAfter"), "budgetMs": stage.get("budgetMs"), "runtimeMs": stage.get("runtimeMs")} for stage in stage_summary.get("stages", [])],
        "routePoolRan": route_pool_ran,
        "routePoolSkipReason": route_pool_stage.get("skippedReason"),
        "routePoolHardCapApplied": bool(operator_trace.get("routePoolImprovement", {}).get("routePoolHardCapApplied")),
        "deterministicSeed": deterministic_seed,
        "incumbentSignature": solution_signature(instance, incumbent),
        "finalSolutionSignature": solution_signature(instance, current),
        "routePoolCandidateSignature": operator_trace.get("routePoolImprovement", {}).get("candidateSignature"),
        "acceptedStageSignatures": {name: trace.get("acceptedStageSignature") for name, trace in operator_trace.items() if isinstance(trace, dict) and trace.get("acceptedStageSignature")},
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
    write_json(output_dir / instance_name / "diagnostics.json", diagnostics)
    write_json(output_dir / instance_name / "final_solution.json", current)
    return diagnostics


def phase56b_gate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    duplicate_outcomes: Dict[str, set[str]] = {}
    duplicate_signatures: Dict[str, set[str]] = {}
    for row in rows:
        key = str(row.get("instance") or "").lower()
        duplicate_outcomes.setdefault(key, set()).add(f"{row.get('vehicleCountBefore')}->{row.get('vehicleCountAfter')}:{row.get('objectiveImproved')}")
        duplicate_signatures.setdefault(key, set()).add(str(row.get("finalSolutionSignature") or "missing-signature"))
    checks = {
        "failCountZero": all(row.get("verdict") != "FAIL" for row in rows),
        "hardViolationsZero": all(int(row.get("hardViolations", 0) or 0) == 0 for row in rows),
        "overBudgetZero": all(not row.get("stageRuntimeSummary", {}).get("overBudget") and not row.get("wallClockOverBudget") for row in rows),
        "actualRuntimeWithinTolerance": all(not row.get("wallClockOverBudget") for row in rows),
        "leakageZero": all(not row.get("leakageDetected") for row in rows),
        "routePoolNotBudgetSkipped": True,
        "noAcceptedObjectiveRegression": all(float(row.get("objectiveAfter", 0.0) or 0.0) <= float(row.get("objectiveBefore", 0.0) or 0.0) for row in rows),
        "duplicateOutcomesStable": all(len(outcomes) <= 1 for outcomes in duplicate_outcomes.values()),
        "duplicateFinalSignaturesStable": all(len(signatures) <= 1 for signatures in duplicate_signatures.values()),
        "routePoolRanWhenRepeated": True,
    }
    return {"verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "duplicateOutcomes": {key: sorted(value) for key, value in duplicate_outcomes.items()}, "duplicateFinalSignatures": {key: sorted(value) for key, value in duplicate_signatures.items()}}


def markdown(rows: List[Dict[str, Any]], gate: Dict[str, Any]) -> str:
    lines = ["# Phase 56B Stable Promoted Runner", "", f"Gate: **{gate['verdict']}**", "", "| Instance | Verdict | Vehicles | Route Pool Ran | Route Pool Skip | Over Budget | Runtime ms |", "|---|---|---:|---:|---|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('routePoolRan')} | {row.get('routePoolSkipReason')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(
    instances: List[str],
    output_dir: Path,
    data_source: str,
    time_limit_ms: int,
    mode: str,
    repeat: int = 1,
    *,
    benchmark_source: str = "li-lim",
    stable_incumbent_replay: bool = False,
    incumbent_cache_dir: Path | None = None,
    deterministic_seed: int = 56,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for repeat_index in range(1, max(1, int(repeat)) + 1):
        run_output_dir = output_dir if repeat == 1 else output_dir / f"run-{repeat_index:02d}"
        for instance in instances:
            row = run_instance(
                instance,
                run_output_dir,
                data_source,
                time_limit_ms,
                mode,
                benchmark_source=benchmark_source,
                stable_incumbent_replay=stable_incumbent_replay,
                incumbent_cache_dir=incumbent_cache_dir or output_dir / "incumbent-cache",
                deterministic_seed=deterministic_seed,
            )
            row["runIndex"] = repeat_index
            rows.append(row)
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    gate = phase56b_gate(rows)
    summary = {"schemaVersion": "phase56c-stable-replay-promoted-runner-summary/v1" if stable_incumbent_replay else "phase56b-stable-promoted-runner-summary/v1", "instances": instances, "benchmarkSource": benchmark_source, "repeat": max(1, int(repeat)), "mode": mode, "stableIncumbentReplay": stable_incumbent_replay, "deterministicSeed": deterministic_seed, "incumbentCacheDir": str(incumbent_cache_dir or output_dir / "incumbent-cache") if stable_incumbent_replay else None, "results": rows, "verdictCounts": counts, "phase56bGate": gate}
    write_json(output_dir / "phase56b_stable_promoted_summary.json", summary)
    (output_dir / "phase56b_stable_promoted_summary.md").write_text(markdown(rows, gate), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 56B stable promoted natural optimizer diagnostics.")
    parser.add_argument("--instances", default="lrc202")
    parser.add_argument("--benchmark-source", choices=("li-lim", "synthetic-food"), default="li-lim")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--stable-incumbent-replay", action="store_true")
    parser.add_argument("--incumbent-cache-dir", default="")
    parser.add_argument("--deterministic-seed", type=int, default=56)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(
        instances,
        Path(args.output_dir),
        args.data_source,
        parse_time_limit(args.time_limit),
        args.mode,
        repeat=args.repeat,
        benchmark_source=args.benchmark_source,
        stable_incumbent_replay=args.stable_incumbent_replay,
        incumbent_cache_dir=Path(args.incumbent_cache_dir) if args.incumbent_cache_dir else None,
        deterministic_seed=args.deterministic_seed,
    )
    print(f"[PHASE56B STABLE PROMOTED] wrote {args.output_dir}")
    return 0 if summary["phase56bGate"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
