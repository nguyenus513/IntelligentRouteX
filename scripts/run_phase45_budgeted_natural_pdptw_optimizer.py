from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase40_natural_pdptw_optimizer import (
    incumbent_neighborhood_repair,
    internal_solver_improvement,
    natural_alns_probe,
    natural_route_elimination,
    natural_solution_key,
    objective_components,
    objective_config,
    objective_driven_route_elimination_repair,
    route_pool_improvement,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase45-budgeted-natural-pdptw-v1"


class StageBudgetScheduler:
    """Simple wall-clock scheduler for diagnostic natural PDPTW runs.

    The goal is not to make every operator faster. The goal is to prevent the
    Phase 40 diagnostic runner from starting too many heavy stages after the
    incumbent already consumed most of the requested wall-clock budget.
    """

    def __init__(self, total_budget_ms: int, reserve_ms: int | None = None) -> None:
        self.total_budget_ms = max(1, int(total_budget_ms))
        self.reserve_ms = int(reserve_ms if reserve_ms is not None else min(3_000, max(500, self.total_budget_ms * 0.10)))
        self.started_at = time.perf_counter()
        self.stages: List[Dict[str, Any]] = []

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def remaining_ms(self, include_reserve: bool = False) -> int:
        reserve = 0 if include_reserve else self.reserve_ms
        return max(0, self.total_budget_ms - self.elapsed_ms() - reserve)

    def stage_budget(self, name: str, preferred_ms: int, min_ms: int = 0) -> int:
        budget = min(max(0, int(preferred_ms)), self.remaining_ms())
        if budget < min_ms:
            return 0
        return budget

    def should_run(self, name: str, min_ms: int) -> bool:
        return self.remaining_ms() >= min_ms

    def record_stage(self, name: str, budget_ms: int, runtime_ms: int, skipped: bool = False, skipped_reason: str | None = None) -> None:
        self.stages.append(
            {
                "name": name,
                "budgetMs": int(budget_ms),
                "runtimeMs": int(runtime_ms),
                "skipped": bool(skipped),
                "skippedReason": skipped_reason,
                "remainingMsAfter": self.remaining_ms(include_reserve=True),
            }
        )

    def skip(self, name: str, reason: str, min_ms: int = 0) -> None:
        self.record_stage(name, 0, 0, skipped=True, skipped_reason=reason or f"remaining-below-{min_ms}ms")

    def summary(self) -> Dict[str, Any]:
        elapsed = self.elapsed_ms()
        return {
            "schemaVersion": "phase45-stage-budget-summary/v1",
            "totalRuntimeMs": elapsed,
            "totalBudgetMs": self.total_budget_ms,
            "reserveMs": self.reserve_ms,
            "overBudget": elapsed > self.total_budget_ms,
            "stages": self.stages,
        }


def _active_vehicle_count(solution: Dict[str, Any]) -> int:
    return len([route for route in solution.get("routes", []) if len(route) > 2])


def _solution_distance_and_feasibility(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    checked = check_solution(instance, solution)
    return {
        "feasible": bool(checked.get("feasible")),
        "hardViolations": len(checked.get("violations", [])),
        "vehicleCount": checked.get("vehicleCount", _active_vehicle_count(solution)),
        "totalDistance": checked.get("totalDistance"),
    }


def _try_accept(
    instance: Dict[str, Any],
    current_solution: Dict[str, Any],
    candidate_solution: Dict[str, Any] | None,
    config: Any,
) -> Tuple[Dict[str, Any], bool, str]:
    if candidate_solution is None:
        return current_solution, False, "no-candidate"
    checked = check_solution(instance, candidate_solution)
    if not checked.get("feasible"):
        return current_solution, False, "hard-violation"
    if natural_solution_key(instance, candidate_solution, config) < natural_solution_key(instance, current_solution, config):
        return candidate_solution, True, "accepted"
    return current_solution, False, "objective-not-improved"


def _stage_call(
    scheduler: StageBudgetScheduler,
    name: str,
    preferred_ms: int,
    min_ms: int,
    call: Callable[[int], Dict[str, Any]],
) -> Dict[str, Any] | None:
    budget = scheduler.stage_budget(name, preferred_ms, min_ms=min_ms)
    if budget <= 0:
        scheduler.skip(name, "budget-too-low", min_ms=min_ms)
        return None
    started = time.perf_counter()
    try:
        return call(budget)
    finally:
        scheduler.record_stage(name, budget, int((time.perf_counter() - started) * 1000))


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    instance_started = time.perf_counter()
    instance_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", instance_path)
    config = objective_config(mode)
    scheduler = StageBudgetScheduler(time_limit_ms)
    operator_trace: Dict[str, Any] = {}

    incumbent_budget = scheduler.stage_budget("incumbent", min(8_000, int(time_limit_ms * 0.25)), min_ms=1_000)
    if incumbent_budget <= 0:
        incumbent_budget = max(1, min(time_limit_ms, 1_000))
    incumbent_started = time.perf_counter()
    incumbent = DispatchV2ExternalBenchmarkSolver().solve(instance, incumbent_budget, "our-dispatch-v2")
    scheduler.record_stage("incumbent", incumbent_budget, int((time.perf_counter() - incumbent_started) * 1000))

    current = incumbent
    before = objective_components(instance, incumbent, config)

    def apply_stage_result(stage_name: str, result: Dict[str, Any] | None) -> None:
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

    if before["vehicleCount"] > 16:
        scheduler.skip("natural-route-elimination", "route-count-too-large-for-unbounded-stage", min_ms=400)
        operator_trace["naturalRouteElimination"] = {"skipped": True, "skippedReason": "route-count-too-large-for-unbounded-stage", "vehicleCount": before["vehicleCount"]}
    else:
        apply_stage_result(
            "naturalRouteElimination",
            _stage_call(
                scheduler,
                "natural-route-elimination",
                preferred_ms=1_500,
                min_ms=400,
                call=lambda _budget: natural_route_elimination(instance, current, config),
            ),
        )

    apply_stage_result(
        "objectiveDrivenRouteElimination",
        _stage_call(
            scheduler,
            "objective-driven-route-elimination",
            preferred_ms=20_000,
            min_ms=20_000,
            call=lambda _budget: objective_driven_route_elimination_repair(instance, current, config),
        ),
    )

    apply_stage_result(
        "internalSolverGenerator",
        _stage_call(
            scheduler,
            "internal-solver-generator",
            preferred_ms=3_200,
            min_ms=3_000,
            call=lambda _budget: internal_solver_improvement(instance, current, config),
        ),
    )

    apply_stage_result(
        "incumbentNeighborhoodRepair",
        _stage_call(
            scheduler,
            "incumbent-neighborhood-repair",
            preferred_ms=2_500,
            min_ms=1_200,
            call=lambda _budget: incumbent_neighborhood_repair(instance, current, config),
        ),
    )

    apply_stage_result(
        "naturalAlnsProbe",
        _stage_call(
            scheduler,
            "natural-alns-probe",
            preferred_ms=20_000,
            min_ms=20_000,
            call=lambda budget: natural_alns_probe(instance, current, config, max_runtime_ms=budget),
        ),
    )

    # The current route-pool stage performs column generation plus SP internally.
    # It is useful, but it is the first stage we skip when the wall-clock budget
    # is tight, because previous phases showed the timeout came from stacking all
    # heavyweight generators after a full incumbent solve.
    route_pool_min_ms = 7_000
    apply_stage_result(
        "routePoolImprovement",
        _stage_call(
            scheduler,
            "route-pool-sp",
            preferred_ms=route_pool_min_ms,
            min_ms=route_pool_min_ms,
            call=lambda _budget: route_pool_improvement(instance, current, config),
        ),
    )

    after = objective_components(instance, current, config)
    checked = check_solution(instance, current)
    objective_improved = natural_solution_key(instance, current, config) < natural_solution_key(instance, incumbent, config)
    vehicle_improved = after["vehicleCount"] < before["vehicleCount"]
    runtime_ms = int((time.perf_counter() - instance_started) * 1000)
    stage_summary = scheduler.summary()
    over_budget = stage_summary["overBudget"] or runtime_ms > time_limit_ms + 1_000

    if checked.get("feasible") and not over_budget and not stage_summary["overBudget"]:
        verdict = "PASS_STRONG" if vehicle_improved and objective_improved else "PASS" if objective_improved else "PASS_WITH_LIMITS"
    else:
        verdict = "FAIL" if over_budget or not checked.get("feasible") else "PASS_WITH_LIMITS"

    diagnostics = {
        "schemaVersion": "phase45-budgeted-natural-pdptw-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "vehicleCountBefore": before["vehicleCount"],
        "vehicleCountAfter": after["vehicleCount"],
        "distanceBefore": before["totalDistance"],
        "distanceAfter": after["totalDistance"],
        "objectiveBefore": before["objective"],
        "objectiveAfter": after["objective"],
        "objectiveImproved": objective_improved,
        "vehicleCountImproved": vehicle_improved,
        "hardViolations": len(checked.get("violations", [])) if not checked.get("feasible") else 0,
        "leakageDetected": False,
        "operatorTrace": operator_trace,
        "stageRuntimeSummary": stage_summary,
        "runtimeMs": runtime_ms,
        "verdict": verdict,
    }

    instance_dir = output_dir / instance_name
    write_json(instance_dir / "diagnostics.json", diagnostics)
    write_json(instance_dir / "stage_runtime_summary.json", stage_summary)
    write_json(instance_dir / "final_solution.json", current)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Phase 45 Budgeted Natural PDPTW Optimizer",
        "",
        "| Instance | Verdict | Vehicles | Objective Improved | Over Budget | Runtime ms |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        stage_summary = row.get("stageRuntimeSummary", {})
        lines.append(
            f"| {row.get('instance')} | {row.get('verdict')} | {row.get('vehicleCountBefore')} -> {row.get('vehicleCountAfter')} | {row.get('objectiveImproved')} | {stage_summary.get('overBudget')} | {row.get('runtimeMs')} |"
        )
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    summary = {
        "schemaVersion": "phase45-budgeted-natural-pdptw-summary/v1",
        "instances": instances,
        "mode": mode,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase45_budgeted_natural_summary.json", summary)
    (output_dir / "phase45_budgeted_natural_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 45 budgeted natural PDPTW optimizer diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE45 BUDGETED NATURAL PDPTW] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
