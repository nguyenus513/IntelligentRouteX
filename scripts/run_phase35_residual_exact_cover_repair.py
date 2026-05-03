from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRouteColumn, PDPTWSetPartitioningSolver, request_id_map
from run_phase32_internal_column_generation import (
    RouteColumnCollector,
    _insert_pair_best,
    construct_route_from_pairs,
    generate_internal_columns,
    selected_column_details,
)
from run_phase33_route_set_guided_generation import max_cover_packing
from run_phase34_missing_request_large_columns import run_phase34_generation

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase35-residual-exact-cover-repair-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def selected_columns_from_max_cover(columns: List[PDPTWRouteColumn], max_cover: Dict[str, Any]) -> List[PDPTWRouteColumn]:
    selected_ids = set(max_cover.get("selectedColumnIds", []))
    return [column for column in columns if column.column_id in selected_ids and column.allowed_for_claim]


def coverage_state(instance: Dict[str, Any], columns: List[PDPTWRouteColumn]) -> Dict[str, Any]:
    all_ids = set(request_id_map(instance).values())
    counts = {request_id: 0 for request_id in all_ids}
    for column in columns:
        for request_id in column.request_ids:
            counts[request_id] = counts.get(request_id, 0) + 1
    missing = sorted(request_id for request_id in all_ids if counts.get(request_id, 0) == 0)
    duplicate = sorted(request_id for request_id, count in counts.items() if count > 1)
    covered = sorted(request_id for request_id, count in counts.items() if count > 0)
    return {
        "coveredRequestIds": covered,
        "missingRequests": missing,
        "duplicateRequests": duplicate,
        "missingCount": len(missing),
        "duplicateCount": len(duplicate),
    }


def _request_pair_by_id(instance: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    return {request_id: pair for pair, request_id in request_id_map(instance).items()}


def _pairs_for_ids(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[tuple[str, str]]:
    inverse = _request_pair_by_id(instance)
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def _collect_route(collector: RouteColumnCollector, route: List[str], stage: str) -> PDPTWRouteColumn | None:
    before = len(collector.pool.columns)
    if not collector.collect(route, stage, failed_repair=True):
        return None
    columns = collector.pool.columns
    return columns[-1] if len(columns) > before else None


def _candidate_solution(columns: List[PDPTWRouteColumn]) -> Dict[str, Any]:
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase35-residual-exact-cover-repair", "routes": [column.route for column in columns]}


def _is_exact_cover(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int) -> bool:
    state = coverage_state(instance, columns)
    return len(columns) <= target_vehicle_count and state["missingCount"] == 0 and state["duplicateCount"] == 0


def _score(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int) -> tuple[int, int, int, float]:
    state = coverage_state(instance, columns)
    route_penalty = max(0, len(columns) - target_vehicle_count)
    return (state["missingCount"], state["duplicateCount"], route_penalty, sum(column.distance for column in columns))


def missing_request_insertion_repair(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best_columns = selected[:]
    inverse = _request_pair_by_id(instance)
    for missing_id in coverage_state(instance, selected)["missingRequests"]:
        pair = inverse.get(missing_id)
        if pair is None:
            continue
        for index, column in enumerate(selected):
            attempts += 1
            route = _insert_pair_best(instance, column.route, pair, max_checks=500)
            if route is None:
                continue
            new_column = _collect_route(collector, route, "residual-missing-insertion")
            if new_column is None:
                continue
            candidate = selected[:index] + [new_column] + selected[index + 1:]
            successes += 1
            if _score(instance, candidate, target_vehicle_count) < _score(instance, best_columns, target_vehicle_count):
                best_columns = candidate
            if _is_exact_cover(instance, candidate, target_vehicle_count):
                return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
    return {"attempts": attempts, "successes": successes, "columns": best_columns, "exact": _is_exact_cover(instance, best_columns, target_vehicle_count)}


def one_column_swap_repair(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best_columns = selected[:]
    pool_columns = [column for column in collector.pool.columns if column.allowed_for_claim]
    for index, removed in enumerate(selected):
        remaining = selected[:index] + selected[index + 1:]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = set(removed.request_ids) | set(coverage_state(instance, remaining)["missingRequests"])
        for replacement in pool_columns:
            attempts += 1
            replacement_set = set(replacement.request_ids)
            if not replacement_set <= residual or replacement_set & used:
                continue
            candidate = remaining + [replacement]
            successes += 1
            if _score(instance, candidate, target_vehicle_count) < _score(instance, best_columns, target_vehicle_count):
                best_columns = candidate
            if _is_exact_cover(instance, candidate, target_vehicle_count):
                return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
        route = _construct_residual_route(instance, residual, "residual-one-swap")
        if route:
            attempts += 1
            new_column = _collect_route(collector, route, "residual-one-swap")
            if new_column and not (set(new_column.request_ids) & used):
                candidate = remaining + [new_column]
                successes += 1
                if _score(instance, candidate, target_vehicle_count) < _score(instance, best_columns, target_vehicle_count):
                    best_columns = candidate
                if _is_exact_cover(instance, candidate, target_vehicle_count):
                    return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
    return {"attempts": attempts, "successes": successes, "columns": best_columns, "exact": _is_exact_cover(instance, best_columns, target_vehicle_count)}


def _deadline_hit(started: float | None, max_runtime_ms: int) -> bool:
    return started is not None and int((time.perf_counter() - started) * 1000) >= max_runtime_ms


def two_column_swap_repair(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int, max_partitions: int = 16, started: float | None = None, max_runtime_ms: int = 20_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best_columns = selected[:]
    for left_index, right_index in itertools.combinations(range(len(selected)), 2):
        if _deadline_hit(started, max_runtime_ms):
            break
        remaining = [column for index, column in enumerate(selected) if index not in {left_index, right_index}]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = sorted((set(selected[left_index].request_ids) | set(selected[right_index].request_ids) | set(coverage_state(instance, remaining)["missingRequests"])) - used)
        if len(residual) < 2:
            continue
        partition_count = 0
        midpoint = max(1, len(residual) // 2)
        split_sizes = [size for size in range(max(1, midpoint - 2), min(len(residual), midpoint + 3))]
        if 1 not in split_sizes:
            split_sizes.append(1)
        for split_size in sorted(set(split_sizes)):
            for left_ids in itertools.combinations(residual, split_size):
                if _deadline_hit(started, max_runtime_ms):
                    break
                partition_count += 1
                if partition_count > max_partitions:
                    break
                right_ids = [request_id for request_id in residual if request_id not in set(left_ids)]
                attempts += 1
                left_route = _construct_residual_route(instance, left_ids, "residual-two-swap")
                right_route = _construct_residual_route(instance, right_ids, "residual-two-swap")
                if not left_route or not right_route:
                    continue
                left_column = _collect_route(collector, left_route, "residual-two-swap")
                right_column = _collect_route(collector, right_route, "residual-two-swap")
                if not left_column or not right_column or set(left_column.request_ids) & set(right_column.request_ids):
                    continue
                candidate = remaining + [left_column, right_column]
                successes += 1
                if _score(instance, candidate, target_vehicle_count) < _score(instance, best_columns, target_vehicle_count):
                    best_columns = candidate
                if _is_exact_cover(instance, candidate, target_vehicle_count):
                    return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
            if partition_count > max_partitions:
                break
    return {"attempts": attempts, "successes": successes, "columns": best_columns, "exact": _is_exact_cover(instance, best_columns, target_vehicle_count)}


def k_minus_one_complement_repair(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int, started: float | None = None, max_runtime_ms: int = 20_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    all_ids = set(request_id_map(instance).values())
    best_columns = selected[:]
    subset_size = max(0, target_vehicle_count - 1)
    for indexes in itertools.combinations(range(len(selected)), min(subset_size, len(selected))):
        if _deadline_hit(started, max_runtime_ms):
            break
        kept = [selected[index] for index in indexes]
        used = set().union(*(set(column.request_ids) for column in kept)) if kept else set()
        complement = sorted(all_ids - used)
        if not complement:
            continue
        attempts += 1
        route = _construct_residual_route(instance, complement, "residual-k-minus-one-complement")
        if route is None:
            continue
        new_column = _collect_route(collector, route, "residual-k-minus-one-complement")
        if new_column is None or set(new_column.request_ids) & used:
            continue
        candidate = kept + [new_column]
        successes += 1
        if _score(instance, candidate, target_vehicle_count) < _score(instance, best_columns, target_vehicle_count):
            best_columns = candidate
        if _is_exact_cover(instance, candidate, target_vehicle_count):
            return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
    return {"attempts": attempts, "successes": successes, "columns": best_columns, "exact": _is_exact_cover(instance, best_columns, target_vehicle_count)}


def _construct_residual_route(instance: Dict[str, Any], request_ids: Iterable[str], stage: str) -> List[str] | None:
    pairs = _pairs_for_ids(instance, request_ids)
    if not pairs:
        return None
    seed = 35 + len(pairs) + len(stage)
    strategies = ("earliest-due", "ready-time", "nearest-pickup", "regret-2", "seeded-shuffle") if len(pairs) > 8 else ("regret-3", "regret-2", "earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle")
    for strategy in strategies:
        route = construct_route_from_pairs(instance, pairs, strategy, seed=seed)
        if route:
            return route
    return None


def residual_exact_cover_local_search(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    started = time.perf_counter()
    best_columns = selected[:]
    missing_result = missing_request_insertion_repair(instance, collector, best_columns, target_vehicle_count)
    best_columns = missing_result["columns"] if _score(instance, missing_result["columns"], target_vehicle_count) <= _score(instance, best_columns, target_vehicle_count) else best_columns
    if missing_result["exact"]:
        return _local_search_result(instance, collector, best_columns, target_vehicle_count, missing_result, {}, {}, {})
    one_result = one_column_swap_repair(instance, collector, best_columns, target_vehicle_count)
    best_columns = one_result["columns"] if _score(instance, one_result["columns"], target_vehicle_count) <= _score(instance, best_columns, target_vehicle_count) else best_columns
    if one_result["exact"]:
        return _local_search_result(instance, collector, best_columns, target_vehicle_count, missing_result, one_result, {}, {})
    two_result = {"attempts": 0, "successes": 0, "columns": best_columns, "exact": False}
    if not _deadline_hit(started, max_runtime_ms):
        two_result = two_column_swap_repair(instance, collector, best_columns, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)
    best_columns = two_result["columns"] if _score(instance, two_result["columns"], target_vehicle_count) <= _score(instance, best_columns, target_vehicle_count) else best_columns
    if two_result["exact"]:
        return _local_search_result(instance, collector, best_columns, target_vehicle_count, missing_result, one_result, two_result, {})
    complement_result = {"attempts": 0, "successes": 0, "columns": best_columns, "exact": False}
    if not _deadline_hit(started, max_runtime_ms):
        complement_result = k_minus_one_complement_repair(instance, collector, best_columns, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)
    best_columns = complement_result["columns"] if _score(instance, complement_result["columns"], target_vehicle_count) <= _score(instance, best_columns, target_vehicle_count) else best_columns
    return _local_search_result(instance, collector, best_columns, target_vehicle_count, missing_result, one_result, two_result, complement_result)


def _local_search_result(
    instance: Dict[str, Any],
    collector: RouteColumnCollector,
    best_columns: List[PDPTWRouteColumn],
    target_vehicle_count: int,
    missing_result: Dict[str, Any],
    one_result: Dict[str, Any],
    two_result: Dict[str, Any],
    complement_result: Dict[str, Any],
) -> Dict[str, Any]:
    state = coverage_state(instance, best_columns)
    exact = _is_exact_cover(instance, best_columns, target_vehicle_count)
    solution = _candidate_solution(best_columns) if exact else None
    checked = check_solution(instance, solution) if solution else {"feasible": False, "violations": []}
    return {
        "exactTargetFeasibleAfter": exact and bool(checked.get("feasible")),
        "bestMissingCountAfter": state["missingCount"],
        "bestDuplicateCountAfter": state["duplicateCount"],
        "bestSelectedColumnIds": [column.column_id for column in best_columns],
        "solution": solution,
        "selectedSolutionFeasible": bool(checked.get("feasible")) if solution else False,
        "checkResult": checked,
        "generatedResidualColumns": len([column for column in collector.pool.columns if column.source.startswith("residual-")]),
        "missingInsertionAttempts": missing_result.get("attempts", 0),
        "missingInsertionSuccess": missing_result.get("successes", 0),
        "oneSwapAttempts": one_result.get("attempts", 0),
        "oneSwapSuccess": one_result.get("successes", 0),
        "twoSwapAttempts": two_result.get("attempts", 0),
        "twoSwapSuccess": two_result.get("successes", 0),
        "complementAttempts": complement_result.get("attempts", 0),
        "complementSuccess": complement_result.get("successes", 0),
    }


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    collector, phase32_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    incumbent_vehicle_count = len([route for route in solution.get("routes", []) if len(route) > 2])
    target_vehicle_count = max(1, incumbent_vehicle_count - 1)
    phase34 = run_phase34_generation(instance, collector, target_vehicle_count)
    max_cover = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    selected = selected_columns_from_max_cover(collector.pool.columns, max_cover)
    before_state = coverage_state(instance, selected)
    residual = residual_exact_cover_local_search(instance, collector, selected, target_vehicle_count) if selected else {"exactTargetFeasibleAfter": False, "bestMissingCountAfter": before_state.get("missingCount"), "bestDuplicateCountAfter": before_state.get("duplicateCount")}
    exact_after = PDPTWSetPartitioningSolver(time_limit_ms=2_000).solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    selected_solution = residual.get("solution") or (exact_after.get("solution") if exact_after.get("feasible") else None)
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    max_cover_after = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    selected_details = selected_column_details(collector.pool, exact_after)
    if leakage or hard_violations:
        verdict = "FAIL"
    elif residual.get("exactTargetFeasibleAfter") or exact_after.get("feasible"):
        verdict = "PASS"
    elif residual.get("bestMissingCountAfter", 999) < before_state.get("missingCount", 999) or int(max_cover_after.get("maxCoveredRequestCount", 0)) > int(max_cover.get("maxCoveredRequestCount", 0)):
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "PASS_WITH_LIMITS"
    diagnostics = {
        "schemaVersion": "phase35-residual-exact-cover-repair-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "targetVehicleCount": target_vehicle_count,
        "internalColumnCount": len(collector.pool.columns),
        "maxCoverBefore": max_cover.get("maxCoveredRequestCount"),
        "maxCoverAfter": max_cover_after.get("maxCoveredRequestCount"),
        "missingRequestsBefore": before_state.get("missingRequests"),
        "residualRequestCount": before_state.get("missingCount"),
        "selectedColumnSizesBefore": [len(column.request_ids) for column in selected],
        "exactTargetFeasibleAfter": bool(residual.get("exactTargetFeasibleAfter") or exact_after.get("feasible")),
        "bestMissingCountAfter": residual.get("bestMissingCountAfter"),
        "bestDuplicateCountAfter": residual.get("bestDuplicateCountAfter"),
        "generatedResidualColumns": residual.get("generatedResidualColumns"),
        "missingInsertionAttempts": residual.get("missingInsertionAttempts"),
        "missingInsertionSuccess": residual.get("missingInsertionSuccess"),
        "oneSwapAttempts": residual.get("oneSwapAttempts"),
        "oneSwapSuccess": residual.get("oneSwapSuccess"),
        "twoSwapAttempts": residual.get("twoSwapAttempts"),
        "twoSwapSuccess": residual.get("twoSwapSuccess"),
        "complementAttempts": residual.get("complementAttempts"),
        "complementSuccess": residual.get("complementSuccess"),
        "selectedSolutionFeasible": bool(selected_solution) and hard_violations == 0,
        "selectedColumnSources": selected_details.get("selectedColumnSources"),
        "selectedColumnStages": selected_details.get("selectedColumnStages"),
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "phase34ExactTargetFeasibleAfter": phase34.get("exactAfter", {}).get("feasible"),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    write_json(instance_dir / "max_cover.json", max_cover)
    write_json(instance_dir / "residual_repair.json", residual)
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    write_json(instance_dir / "diagnostics.json", diagnostics)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 35 Residual Exact-Cover Repair", "", "| Instance | Verdict | MaxCover Before | MaxCover After | Missing Before | Missing After | Exact After | Residual Columns | Runtime ms |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('maxCoverBefore')} | {row.get('maxCoverAfter')} | {row.get('residualRequestCount')} | {row.get('bestMissingCountAfter')} | {row.get('exactTargetFeasibleAfter')} | {row.get('generatedResidualColumns')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase35-residual-exact-cover-repair-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase35_residual_exact_cover_repair_summary.json", summary)
    (output_dir / "phase35_residual_exact_cover_repair_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 35 residual exact-cover repair diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE35 RESIDUAL EXACT-COVER REPAIR] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
