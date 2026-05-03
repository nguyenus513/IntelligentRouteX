from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution, ortools_baseline_solution
from parse_li_lim_pdptw import parse_li_lim
from parse_solomon_vrptw import parse_solomon
from pyvrp_vrptw_bridge import PyvrpModelConfig, solve_vrptw
from run_academic_max_quality import (
    FIRST_SOLUTION_STRATEGIES,
    LOCAL_SEARCH_METAHEURISTICS,
    collect_route_pool,
    evaluate_solution,
    generate_cross_exchange_candidates,
    generate_route_elimination_candidates,
    generate_route_merge_candidates,
    parse_duration_ms,
    set_partitioning_solution,
    solution_key,
    vehicle_fixed_cost,
    write_json,
)
from run_phase13_hgs_route_pool_targets import TARGETS, append_hgs_route, instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase14-pyvrp-calibration-v1"


def parse_instance(suite: str, path: Path) -> dict[str, Any]:
    if suite == "solomon":
        return parse_solomon(path)
    return parse_li_lim(path)


def calibration_variants() -> list[PyvrpModelConfig]:
    return [
        PyvrpModelConfig(name="duration-service-scale1000", scale=1000, fixed_cost=1_000_000_000, duration_includes_service=True, demand_mode="delivery"),
        PyvrpModelConfig(name="travel-only-scale1000", scale=1000, fixed_cost=1_000_000_000, duration_includes_service=False, demand_mode="delivery"),
        PyvrpModelConfig(name="travel-only-scale100", scale=100, fixed_cost=100_000_000, duration_includes_service=False, demand_mode="delivery"),
        PyvrpModelConfig(name="travel-only-scale10", scale=10, fixed_cost=10_000_000, duration_includes_service=False, demand_mode="delivery"),
        PyvrpModelConfig(name="pickup-demand-scale1000", scale=1000, fixed_cost=1_000_000_000, duration_includes_service=False, demand_mode="pickup"),
    ]


def run_ortools_seed_pool(instance: dict[str, Any], time_limit_ms: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    per_run_ms = max(500, min(1_800, time_limit_ms // 10))
    fixed_cost = vehicle_fixed_cost(instance, 1_000_000)
    candidates: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    strategies = [(first, local) for first in FIRST_SOLUTION_STRATEGIES[:2] for local in LOCAL_SEARCH_METAHEURISTICS[:1]][:2]
    for run_index, (first, local) in enumerate(strategies, start=1):
        solution = ortools_baseline_solution(
            instance,
            per_run_ms,
            f"phase14-calibration-ortools-{run_index}",
            vehicle_fixed_cost=fixed_cost,
            first_solution_strategy=first,
            local_search_metaheuristic=local,
        )
        if solution.get("evidenceGapReason"):
            run_rows.append({"run": run_index, "evidenceGapReason": solution["evidenceGapReason"]})
            continue
        evaluated = evaluate_solution(instance, solution, f"phase14-{first}+{local}")
        candidates.append(evaluated)
        run_rows.append({
            "run": run_index,
            "firstSolutionStrategy": first,
            "localSearchMetaheuristic": local,
            "feasible": evaluated["feasible"],
            "vehicleCount": evaluated["vehicleCount"],
            "totalDistance": evaluated["totalDistance"],
        })
    route_pool = collect_route_pool(instance, candidates)
    operator_counts = {
        "routeEliminationAttempts": 0,
        "routeEliminationSuccesses": 0,
        "routeEliminationGeneratedRoutes": 0,
        "ejectionChainAttempts": 0,
        "ejectionChainSuccesses": 0,
        "crossExchangeAttempts": 0,
        "crossExchangeSuccesses": 0,
        "crossExchangeGeneratedRoutes": 0,
        "routeMergeAttempts": 0,
        "routeMergeSuccesses": 0,
        "routeMergeGeneratedRoutes": 0,
    }
    for seed in sorted(candidates, key=solution_key)[:2]:
        route_count = len(seed["solution"].get("routes", []))
        for key, value in generate_route_elimination_candidates(instance, seed["solution"], route_pool, max_attempts=min(4, route_count)).items():
            operator_counts[key] += value
        for key, value in generate_cross_exchange_candidates(instance, seed["solution"], route_pool, max_route_pairs=min(10, route_count * max(1, route_count - 1) // 2), max_segment_size=2).items():
            operator_counts[key] += value
        for key, value in generate_route_merge_candidates(instance, seed["solution"], route_pool, max_pairs=10, max_combined_customers=14).items():
            operator_counts[key] += value
    return candidates, route_pool, run_rows, operator_counts


def hgs_diagnostic(instance: dict[str, Any], solution: dict[str, Any], variant: PyvrpModelConfig) -> dict[str, Any]:
    checked = solution.get("checked") if isinstance(solution.get("checked"), dict) else check_solution(instance, solution)
    bks = instance.get("bestKnown", {})
    return {
        "variant": variant.name,
        "status": solution.get("status"),
        "pyvrpAvailable": solution.get("pyvrpAvailable", False),
        "pyvrpFeasible": solution.get("pyvrpFeasible"),
        "pyvrpCost": solution.get("pyvrpCost"),
        "vehicleCount": checked.get("vehicleCount"),
        "bestKnownVehicleCount": bks.get("vehicleCount"),
        "vehicleGap": None if checked.get("vehicleCount") is None or bks.get("vehicleCount") is None else max(0, int(checked["vehicleCount"]) - int(bks["vehicleCount"])),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "runtimeMs": solution.get("runtimeMs"),
        "evidenceGapReason": solution.get("evidenceGapReason"),
        "config": variant.__dict__,
    }


def run_vrptw_calibration(instance: dict[str, Any], time_limit_ms: int, output_dir: Path, suite: str, instance_name: str, hgs_time_limit_ms: int) -> dict[str, Any]:
    started = time.perf_counter()
    candidates, route_pool, ortools_runs, operator_counts = run_ortools_seed_pool(instance, time_limit_ms)
    route_pool_size_before_hgs = len(route_pool)
    hgs_rows: list[dict[str, Any]] = []
    hgs_solutions: list[dict[str, Any]] = []
    per_variant_ms = max(500, hgs_time_limit_ms // max(1, len(calibration_variants())))
    for index, variant in enumerate(calibration_variants(), start=1):
        solution = solve_vrptw(instance, per_variant_ms, seed=14000 + index, config=variant)
        diagnostic = hgs_diagnostic(instance, solution, variant)
        hgs_rows.append(diagnostic)
        if solution.get("status") == "PASS":
            hgs_solutions.append(solution)
            candidates.append(evaluate_solution(instance, solution, f"pyvrp-hgs-calibrated:{variant.name}"))
            for route in solution.get("routes", []):
                append_hgs_route(instance, route_pool, [str(stop) for stop in route])
    route_pool_size_after_hgs = len(route_pool)
    best_hgs = min((row for row in hgs_rows if row.get("status") == "PASS"), key=lambda row: (int(row.get("vehicleCount") or 10**9), float(row.get("totalDistance") or 1e18)), default=None)
    sp_solution = set_partitioning_solution(instance, route_pool, max(500, time_limit_ms // 5)) if route_pool else None
    if sp_solution is not None:
        candidates.append(evaluate_solution(instance, sp_solution, "phase14-set-partitioning-calibrated-route-pool"))
    best = min(candidates, key=solution_key) if candidates else None
    runtime_ms = int((time.perf_counter() - started) * 1000)
    if best is None:
        return {
            "suite": suite,
            "instance": instance_name,
            "problemType": instance.get("problemType"),
            "status": "EVIDENCE_GAP",
            "reasons": ["phase14-no-candidate-solution"],
            "runtimeMs": runtime_ms,
            "hgsDiagnostics": hgs_rows,
        }
    checked = check_solution(instance, best["solution"])
    bks = instance.get("bestKnown", {})
    row = {
        "suite": suite,
        "instance": instance_name,
        "problemType": instance.get("problemType"),
        "status": "PASS" if checked.get("feasible") else "FAIL",
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "bestKnownVehicleCount": bks.get("vehicleCount"),
        "vehicleGap": max(0, int(checked.get("vehicleCount", 0)) - int(bks.get("vehicleCount", checked.get("vehicleCount", 0)) or checked.get("vehicleCount", 0))),
        "totalDistance": checked.get("totalDistance"),
        "bestKnownDistance": bks.get("objective"),
        "objectiveGapPercent": checked.get("objectiveGapPercent"),
        "hardViolationCount": len(checked.get("violations", [])),
        "routePoolSize": len(route_pool),
        "routePoolSizeBeforeHgs": route_pool_size_before_hgs,
        "routePoolSizeAfterHgs": route_pool_size_after_hgs,
        "hgsVariantCount": len(hgs_rows),
        "hgsPassCount": sum(1 for row in hgs_rows if row.get("status") == "PASS"),
        "bestHgsVariant": None if best_hgs is None else best_hgs.get("variant"),
        "bestHgsVehicleCount": None if best_hgs is None else best_hgs.get("vehicleCount"),
        "bestHgsDistance": None if best_hgs is None else best_hgs.get("totalDistance"),
        "hgsDiagnostics": hgs_rows,
        "setPartitioningProducedSolution": sp_solution is not None,
        "bestLabel": best["label"],
        "operatorCounts": operator_counts,
        "runs": ortools_runs,
        "runtimeMs": runtime_ms,
    }
    case_dir = output_dir / suite / instance_name
    write_json(case_dir / "solution.json", best["solution"])
    write_json(case_dir / "route_pool.json", {"routes": route_pool})
    write_json(case_dir / "metrics.json", row)
    return row


def run_pdptw_skip(instance: dict[str, Any], suite: str, instance_name: str) -> dict[str, Any]:
    return {
        "suite": suite,
        "instance": instance_name,
        "problemType": instance.get("problemType"),
        "status": "SKIPPED",
        "vehicleGap": None,
        "runtimeMs": 0,
        "reasons": ["phase14-pdptw-hgs-calibration-deferred-until-pair-route-pool-model"],
    }


def run_targets(output_dir: Path, time_limit_ms: int, data_source: str, hgs_time_limit_ms: int) -> dict[str, Any]:
    rows = []
    for suite, instance_name in TARGETS:
        instance = parse_instance(suite, instance_path(suite, instance_name, data_source))
        if instance.get("problemType") == "VRPTW":
            rows.append(run_vrptw_calibration(instance, time_limit_ms, output_dir, suite, instance_name, hgs_time_limit_ms))
        else:
            row = run_pdptw_skip(instance, suite, instance_name)
            write_json(output_dir / suite / instance_name / "metrics.json", row)
            rows.append(row)
    result = {"schemaVersion": "phase14-pyvrp-calibration-targets/v1", "results": rows}
    write_json(output_dir / "phase14_pyvrp_calibration_results.json", result)
    (output_dir / "phase14_pyvrp_calibration_report.md").write_text(markdown(rows), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 14 PyVRP Calibration Report",
        "",
        "| Suite | Instance | Status | Vehicles | BKS | Gap | Best HGS | HGS Vehicles | Pool | SP | Runtime ms | Reasons |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('vehicleCount')} | "
            f"{row.get('bestKnownVehicleCount')} | {row.get('vehicleGap')} | {row.get('bestHgsVariant')} | "
            f"{row.get('bestHgsVehicleCount')} | {row.get('routePoolSize')} | {row.get('setPartitioningProducedSolution')} | "
            f"{row.get('runtimeMs')} | {row.get('reasons', [])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 14 PyVRP/HGS calibration on known gap targets.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--hgs-time-limit", default="8s")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    result = run_targets(output_dir, parse_duration_ms(args.time_limit), args.data_source, parse_duration_ms(args.hgs_time_limit))
    print(f"[PHASE14 PYVRP CALIBRATION] wrote {output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
