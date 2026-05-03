from __future__ import annotations

import argparse
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase40_natural_pdptw_optimizer import (
    IncumbentNeighborhoodRepairGenerator,
    internal_solver_improvement,
    natural_route_elimination,
    natural_solution_key,
    objective_components,
    objective_config,
    route_pool_improvement,
    write_json,
)
from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler, _try_accept
from run_phase47_adaptive_budget_natural_optimizer import adaptive_budget_profile, bounded_large_route_elimination, instance_features


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase51-fast-neighborhood-profile-v1"


@dataclass(frozen=True)
class FastNeighborhoodCapProfile:
    name: str
    max_runtime_ms: int
    max_neighborhoods: int
    max_ortools_pairs: int
    max_affected_request_count: int
    max_route_pool_variants: int
    max_candidate_checks: int


CONSERVATIVE_PROFILE = FastNeighborhoodCapProfile("conservative", 1_400, 3, 8, 8, 8, 900)
EXPANDED_PROFILE = FastNeighborhoodCapProfile("expanded", 2_200, 5, 12, 12, 12, 1_500)
LARGE_SAFE_PROFILE = FastNeighborhoodCapProfile("large_safe", 1_800, 6, 10, 10, 8, 900)


def select_fast_neighborhood_profile(features: Dict[str, Any], remaining_ms: int) -> tuple[FastNeighborhoodCapProfile, str]:
    route_count = int(features.get("routeCount", 0) or 0)
    request_count = int(features.get("requestCount", 0) or 0)
    tightness = float(features.get("timeWindowTightness", 0.0) or 0.0)
    mixedness = float(features.get("mixedness", 0.0) or 0.0)
    incumbent_feasible = bool(features.get("incumbentFeasible", False))
    if remaining_ms < 2_200 or not incumbent_feasible:
        return CONSERVATIVE_PROFILE, "low-budget-or-infeasible-incumbent"
    if route_count > 16 or request_count > 120:
        return LARGE_SAFE_PROFILE, "large-route-or-request-count"
    if tightness > 0.015 or mixedness > 40.0:
        return EXPANDED_PROFILE, "tight-or-mixed-instance"
    return CONSERVATIVE_PROFILE, "default-conservative"


class ProfiledIncumbentNeighborhoodRepairGenerator(IncumbentNeighborhoodRepairGenerator):
    def __init__(self, profile: FastNeighborhoodCapProfile) -> None:
        super().__init__(max_runtime_ms=profile.max_runtime_ms, max_neighborhoods=profile.max_neighborhoods, max_ortools_pairs=profile.max_ortools_pairs)
        self._profile = profile
        self._skipped_by_affected_cap = 0
        self._candidate_cap_hit = False

    def extract_neighborhoods(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = super().extract_neighborhoods(instance, solution)
        filtered = []
        for neighborhood in raw:
            if int(neighborhood.get("affectedRequestCount", 0) or 0) > self._profile.max_affected_request_count:
                self._skipped_by_affected_cap += 1
                self._candidate_cap_hit = True
                continue
            filtered.append(neighborhood)
        return filtered

    def repair(self, instance: Dict[str, Any], solution: Dict[str, Any], config: Any) -> Dict[str, Any]:
        result = super().repair(instance, solution, config)
        trace = result.get("trace", [])
        self._candidate_cap_hit = self._candidate_cap_hit or any(row.get("rejectReason") == "candidate-cap" for row in trace if isinstance(row, dict))
        feasible_subproblem = sum(int(row.get("feasibleSubproblemCandidates", 0) or 0) for row in trace if isinstance(row, dict))
        recombined_feasible = sum(int(row.get("recombinedFeasibleCandidates", 0) or 0) for row in trace if isinstance(row, dict))
        result.update(
            {
                "profile": asdict(self._profile),
                "neighborhoodsGenerated": len(trace),
                "neighborhoodsSkippedByAffectedCap": self._skipped_by_affected_cap,
                "candidateCapHit": self._candidate_cap_hit,
                "feasibleSubproblemCandidates": feasible_subproblem,
                "recombinedFeasibleCandidates": recombined_feasible,
                "rejectReason": None if result.get("accepted") else ("candidate-cap" if self._candidate_cap_hit else "objective-not-improved" if recombined_feasible else "no-feasible-subproblem"),
            }
        )
        return result


def fast_incumbent_neighborhood_repair_with_profile(instance: Dict[str, Any], solution: Dict[str, Any], config: Any, profile: FastNeighborhoodCapProfile, max_runtime_ms: int) -> Dict[str, Any]:
    effective_profile = FastNeighborhoodCapProfile(
        profile.name,
        min(profile.max_runtime_ms, max_runtime_ms),
        profile.max_neighborhoods,
        profile.max_ortools_pairs,
        profile.max_affected_request_count,
        profile.max_route_pool_variants,
        profile.max_candidate_checks,
    )
    generator = ProfiledIncumbentNeighborhoodRepairGenerator(effective_profile)
    result = generator.repair(instance, solution, config)
    result["fastMode"] = True
    return result


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
    remaining_for_profile = scheduler.remaining_ms()
    profile, profile_reason = select_fast_neighborhood_profile(features, remaining_for_profile)
    plan["stages"]["fast-incumbent-neighborhood-repair"]["preferredMs"] = profile.max_runtime_ms
    plan["stages"]["fast-incumbent-neighborhood-repair"]["minMs"] = min(700, profile.max_runtime_ms)

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
        "schemaVersion": "phase51-fast-neighborhood-profile-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "adaptiveBudgetProfile": plan,
        "selectedFastNeighborhoodProfile": profile.name,
        "profileReason": profile_reason,
        "maxNeighborhoods": profile.max_neighborhoods,
        "maxOrtoolsPairs": profile.max_ortools_pairs,
        "maxAffectedRequestCount": profile.max_affected_request_count,
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


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 51 Fast Neighborhood Profile", "", "| Instance | Verdict | Vehicles | Profile | Obj Improved | Over Budget | Runtime ms |", "|---|---|---:|---|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('selectedFastNeighborhoodProfile')} | {row.get('objectiveImproved')} | {row.get('stageRuntimeSummary', {}).get('overBudget')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    counts = {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")}
    candidate_cap_hit_count = sum(1 for row in rows if row.get("operatorTrace", {}).get("fastIncumbentNeighborhoodRepair", {}).get("candidateCapHit"))
    total_vehicle_reduction = sum(max(0, int(row.get("vehicleCountBefore", 0) or 0) - int(row.get("vehicleCountAfter", 0) or 0)) for row in rows)
    safety_ok = counts.get("FAIL", 0) == 0 and all(int(row.get("hardViolations", 0) or 0) == 0 and not row.get("leakageDetected") and not row.get("stageRuntimeSummary", {}).get("overBudget") for row in rows)
    gate = "FAIL" if not safety_ok else "PASS_STRONG" if total_vehicle_reduction > 3 else "PASS" if candidate_cap_hit_count < 5 else "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase51-fast-neighborhood-profile-summary/v1", "instances": instances, "mode": mode, "results": rows, "verdictCounts": counts, "candidateCapHitCount": candidate_cap_hit_count, "totalVehicleReduction": total_vehicle_reduction, "phase51Gate": gate}
    write_json(output_dir / "phase51_fast_neighborhood_profile_summary.json", summary)
    (output_dir / "phase51_fast_neighborhood_profile_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 51 feature-driven fast-neighborhood cap profile diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE51 FAST NEIGHBORHOOD PROFILE] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
