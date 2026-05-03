from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution, ortools_baseline_solution
from parse_li_lim_pdptw import parse_li_lim
from parse_solomon_vrptw import parse_solomon
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

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase12-route-pool-v1"
TARGETS = (("solomon", "RC101"), ("li-lim", "LR101"), ("li-lim", "LRC101"))


def instance_path(suite: str, instance: str, data_source: str) -> Path:
    official_root = REPO_ROOT / "benchmarks" / "external" / "official"
    fixture_root = REPO_ROOT / "benchmarks" / "external"
    if suite == "solomon":
        official = official_root / "solomon" / f"{instance}.txt"
        fixture = fixture_root / "solomon" / "fixtures" / f"{instance}.txt"
    elif suite == "li-lim":
        official = official_root / "li-lim-pdptw" / f"{instance}.txt"
        fixture = fixture_root / "li-lim-pdptw" / "fixtures" / f"{instance}.txt"
    else:
        raise ValueError(f"Unsupported suite: {suite}")
    if data_source == "official":
        return official
    return official if official.exists() else fixture


def parse_instance(suite: str, path: Path) -> dict[str, Any]:
    if suite == "solomon":
        return parse_solomon(path)
    return parse_li_lim(path)


def run_vrptw_route_pool(instance: dict[str, Any], time_limit_ms: int, output_dir: Path, suite: str, instance_name: str) -> dict[str, Any]:
    started = time.perf_counter()
    per_run_ms = max(500, min(2_500, time_limit_ms // 6))
    fixed_cost = vehicle_fixed_cost(instance, 1_000_000)
    candidates: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    strategies = [(first, local) for first in FIRST_SOLUTION_STRATEGIES[:3] for local in LOCAL_SEARCH_METAHEURISTICS[:1]][:3]
    for run_index, (first, local) in enumerate(strategies, start=1):
        solution = ortools_baseline_solution(
            instance,
            per_run_ms,
            f"phase12-route-pool-run-{run_index}",
            vehicle_fixed_cost=fixed_cost,
            first_solution_strategy=first,
            local_search_metaheuristic=local,
        )
        if solution.get("evidenceGapReason"):
            run_rows.append({"run": run_index, "evidenceGapReason": solution["evidenceGapReason"]})
            continue
        evaluated = evaluate_solution(instance, solution, f"{first}+{local}")
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
        for key, value in generate_route_elimination_candidates(instance, seed["solution"], route_pool, max_attempts=min(6, route_count)).items():
            operator_counts[key] += value
        for key, value in generate_cross_exchange_candidates(instance, seed["solution"], route_pool, max_route_pairs=min(18, route_count * max(1, route_count - 1) // 2), max_segment_size=2).items():
            operator_counts[key] += value
        for key, value in generate_route_merge_candidates(instance, seed["solution"], route_pool, max_pairs=18, max_combined_customers=16).items():
            operator_counts[key] += value
    sp_solution = set_partitioning_solution(instance, route_pool, max(500, time_limit_ms // 5)) if route_pool else None
    if sp_solution is not None:
        candidates.append(evaluate_solution(instance, sp_solution, "phase12-set-partitioning-route-pool"))
    best = min(candidates, key=solution_key) if candidates else None
    runtime_ms = int((time.perf_counter() - started) * 1000)
    if best is None:
        return {
            "suite": suite,
            "instance": instance_name,
            "problemType": instance.get("problemType"),
            "status": "EVIDENCE_GAP",
            "reasons": ["phase12-no-candidate-solution"],
            "runtimeMs": runtime_ms,
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
        "setPartitioningProducedSolution": sp_solution is not None,
        "bestLabel": best["label"],
        "operatorCounts": operator_counts,
        "runs": run_rows,
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
        "feasible": None,
        "vehicleCount": None,
        "bestKnownVehicleCount": instance.get("bestKnown", {}).get("vehicleCount"),
        "vehicleGap": None,
        "routePoolSize": 0,
        "setPartitioningProducedSolution": False,
        "runtimeMs": 0,
        "reasons": ["phase12-pdptw-route-pool-seeding-deferred-until-pair-route-pool-model"],
    }


def run_targets(output_dir: Path, time_limit_ms: int, data_source: str) -> dict[str, Any]:
    rows = []
    for suite, instance_name in TARGETS:
        instance = parse_instance(suite, instance_path(suite, instance_name, data_source))
        if instance.get("problemType") == "VRPTW":
            rows.append(run_vrptw_route_pool(instance, time_limit_ms, output_dir, suite, instance_name))
        else:
            row = run_pdptw_skip(instance, suite, instance_name)
            case_dir = output_dir / suite / instance_name
            write_json(case_dir / "metrics.json", row)
            rows.append(row)
    result = {"schemaVersion": "phase12-route-pool-targets/v1", "results": rows}
    write_json(output_dir / "phase12_route_pool_results.json", result)
    (output_dir / "phase12_route_pool_report.md").write_text(markdown(rows), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 12 Route Pool Seeding Report",
        "",
        "| Suite | Instance | Status | Vehicles | BKS | Gap | Route Pool | SP | Runtime ms | Reasons |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('vehicleCount')} | "
            f"{row.get('bestKnownVehicleCount')} | {row.get('vehicleGap')} | {row.get('routePoolSize')} | "
            f"{row.get('setPartitioningProducedSolution')} | {row.get('runtimeMs')} | {row.get('reasons', [])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 12 route-pool seeding on known gap targets.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    result = run_targets(output_dir, parse_duration_ms(args.time_limit), args.data_source)
    print(f"[PHASE12 ROUTE POOL] wrote {output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

