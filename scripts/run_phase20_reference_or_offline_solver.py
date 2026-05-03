from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution, ortools_baseline_solution
from parse_solomon_vrptw import parse_solomon
from reference_solution_loader import find_reference_solution
from run_academic_max_quality import (
    FIRST_SOLUTION_STRATEGIES,
    LOCAL_SEARCH_METAHEURISTICS,
    append_route_to_pool,
    parse_duration_ms,
    set_partitioning_solution,
    solution_key,
    vehicle_fixed_cost,
    write_json,
)
from run_phase13_hgs_route_pool_targets import instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase20-reference-offline-v1"
DEFAULT_SEED_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase18-time-window-restructuring-v1"
FIXED_COST_MULTIPLIERS = (100_000, 1_000_000, 10_000_000)


def load_seed(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_dir = seed_dir / "solomon" / "RC101"
    solution = json.loads((case_dir / "solution.json").read_text(encoding="utf-8"))
    route_pool = json.loads((case_dir / "route_pool.json").read_text(encoding="utf-8")).get("routes", [])
    metrics = json.loads((case_dir / "metrics.json").read_text(encoding="utf-8"))
    return solution, list(route_pool), metrics


def evaluate_candidate(instance: dict[str, Any], solution: dict[str, Any], label: str) -> dict[str, Any]:
    checked = check_solution(instance, solution)
    return {
        "label": label,
        "solution": solution,
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "checked": checked,
    }


def import_solution_routes(instance: dict[str, Any], route_pool: list[dict[str, Any]], solution: dict[str, Any], source: str) -> int:
    imported = 0
    for route in solution.get("routes", []):
        if append_route_to_pool(instance, route_pool, [str(stop) for stop in route], source):
            imported += 1
    return imported


def run_offline_multistart(instance: dict[str, Any], route_pool: list[dict[str, Any]], time_limit_ms: int, max_runs: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    runs: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    imported_routes = 0
    strategy_pairs = [(first, local) for first in FIRST_SOLUTION_STRATEGIES for local in LOCAL_SEARCH_METAHEURISTICS]
    per_run_ms = max(500, min(5_000, time_limit_ms // max(1, max_runs)))
    run_index = 0
    for multiplier in FIXED_COST_MULTIPLIERS:
        fixed_cost = vehicle_fixed_cost(instance, multiplier)
        for first, local in strategy_pairs:
            if run_index >= max_runs:
                return candidates, runs, imported_routes
            run_index += 1
            started = time.perf_counter()
            solution = ortools_baseline_solution(
                instance,
                per_run_ms,
                f"phase20-offline-{run_index}",
                vehicle_fixed_cost=fixed_cost,
                first_solution_strategy=first,
                local_search_metaheuristic=local,
            )
            runtime_ms = int((time.perf_counter() - started) * 1000)
            if solution.get("evidenceGapReason"):
                runs.append({
                    "run": run_index,
                    "fixedCostMultiplier": multiplier,
                    "firstSolutionStrategy": first,
                    "localSearchMetaheuristic": local,
                    "runtimeMs": runtime_ms,
                    "evidenceGapReason": solution.get("evidenceGapReason"),
                })
                continue
            evaluated = evaluate_candidate(instance, solution, f"phase20-offline-{run_index}:{first}+{local}+{multiplier}")
            candidates.append(evaluated)
            imported = import_solution_routes(instance, route_pool, solution, evaluated["label"])
            imported_routes += imported
            runs.append({
                "run": run_index,
                "fixedCostMultiplier": multiplier,
                "firstSolutionStrategy": first,
                "localSearchMetaheuristic": local,
                "runtimeMs": runtime_ms,
                "feasible": evaluated["feasible"],
                "vehicleCount": evaluated["vehicleCount"],
                "totalDistance": evaluated["totalDistance"],
                "importedRoutes": imported,
            })
    return candidates, runs, imported_routes


def run_phase20(output_dir: Path, seed_dir: Path, time_limit_ms: int, data_source: str, max_runs: int) -> dict[str, Any]:
    started = time.perf_counter()
    suite = "solomon"
    instance_name = "RC101"
    instance = parse_solomon(instance_path(suite, instance_name, data_source))
    seed_solution, route_pool, seed_metrics = load_seed(seed_dir)
    route_pool_before = len(route_pool)
    candidates = [evaluate_candidate(instance, seed_solution, "phase20-seed-incumbent")]

    reference = find_reference_solution(instance_name, REPO_ROOT, str(instance.get("depotNodeId", "0")))
    reference_checked = check_solution(instance, reference) if reference is not None else None
    reference_imported = 0
    if reference is not None:
        reference_eval = evaluate_candidate(instance, reference, "phase20-reference-route")
        candidates.append(reference_eval)
        if reference_eval["feasible"]:
            reference_imported = import_solution_routes(instance, route_pool, reference, "phase20-reference-route")

    offline_budget_ms = max(1_000, int(time_limit_ms * 0.70))
    offline_candidates, offline_runs, offline_imported = run_offline_multistart(instance, route_pool, offline_budget_ms, max_runs)
    candidates.extend(offline_candidates)

    sp_solution = set_partitioning_solution(instance, route_pool, max(1_000, min(10_000, int(time_limit_ms * 0.20)))) if route_pool else None
    if sp_solution is not None:
        candidates.append(evaluate_candidate(instance, sp_solution, "phase20-set-partitioning-reference-offline-pool"))

    best = min(candidates, key=solution_key)
    checked = best["checked"]
    bks = instance.get("bestKnown", {})
    best_offline = min(offline_candidates, key=solution_key) if offline_candidates else None
    row = {
        "suite": suite,
        "instance": instance_name,
        "status": "PASS" if checked.get("feasible") else "FAIL",
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "bestKnownVehicleCount": bks.get("vehicleCount"),
        "vehicleGap": max(0, int(checked.get("vehicleCount", 0)) - int(bks.get("vehicleCount", checked.get("vehicleCount", 0)) or checked.get("vehicleCount", 0))),
        "seedVehicleGap": seed_metrics.get("vehicleGap"),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "referenceRouteAvailable": reference is not None,
        "referenceRouteFeasible": bool(reference_checked and reference_checked.get("feasible")),
        "referenceVehicleCount": None if reference_checked is None else reference_checked.get("vehicleCount"),
        "referenceDistance": None if reference_checked is None else reference_checked.get("totalDistance"),
        "referenceImportCount": reference_imported,
        "offlineRunCount": len(offline_runs),
        "offlineFeasibleRunCount": sum(1 for run in offline_runs if run.get("feasible")),
        "bestOfflineVehicleCount": None if best_offline is None else best_offline.get("vehicleCount"),
        "bestOfflineDistance": None if best_offline is None else best_offline.get("totalDistance"),
        "offlineImportedRoutes": offline_imported,
        "routePoolSizeBefore": route_pool_before,
        "routePoolSizeAfter": len(route_pool),
        "setPartitioningProducedSolution": sp_solution is not None,
        "bestLabel": best["label"],
        "runSummaries": offline_runs,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
    }
    result = {"schemaVersion": "phase20-reference-offline-results/v1", "results": [row]}
    case_dir = output_dir / suite / instance_name
    write_json(case_dir / "solution.json", best["solution"])
    write_json(case_dir / "route_pool.json", {"routes": route_pool})
    write_json(case_dir / "metrics.json", row)
    write_json(output_dir / "phase20_reference_offline_results.json", result)
    (output_dir / "phase20_reference_offline_report.md").write_text(markdown([row]), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 20 Reference / Offline Solver Report",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Ref | Offline Runs | Best Offline | Pool Before/After | SP | Best Label | Runtime |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedVehicleGap')}/{row.get('vehicleGap')} | "
            f"{row.get('referenceRouteAvailable')}/{row.get('referenceRouteFeasible')} | {row.get('offlineRunCount')} | "
            f"{row.get('bestOfflineVehicleCount')} | {row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | "
            f"{row.get('setPartitioningProducedSolution')} | {row.get('bestLabel')} | {row.get('runtimeMs')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 20 reference import and offline solver search.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR))
    parser.add_argument("--time-limit", default="60s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--max-runs", type=int, default=12)
    args = parser.parse_args(argv)
    result = run_phase20(Path(args.output_dir), Path(args.seed_dir), parse_duration_ms(args.time_limit), args.data_source, args.max_runs)
    print(f"[PHASE20 REFERENCE OFFLINE] wrote {args.output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
