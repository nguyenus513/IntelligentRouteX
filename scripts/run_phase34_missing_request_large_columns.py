from __future__ import annotations

import argparse
import itertools
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRouteColumn, PDPTWSetPartitioningSolver, request_id_map
from run_phase32_internal_column_generation import (
    RouteColumnCollector,
    construct_route_from_pairs,
    generate_internal_columns,
    relatedness,
    request_pairs,
    request_set_diversity_stats,
    selected_column_details,
)
from run_phase33_route_set_guided_generation import (
    column_request_set,
    compatibility_graph_stats,
    compression_column_generator,
    guided_penalty_generation,
    max_cover_packing,
    min_slack_relaxation,
    request_ids_to_pairs,
    target_size_diagnostics,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase34-missing-request-large-columns-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _request_pair_by_id(instance: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    return {request_id: pair for pair, request_id in request_id_map(instance).items()}


def _request_ids_to_pairs(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[tuple[str, str]]:
    inverse = _request_pair_by_id(instance)
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def _request_set_exists(collector: RouteColumnCollector, request_ids: Iterable[str]) -> bool:
    key = tuple(sorted(request_ids))
    return any(tuple(sorted(column.request_ids)) == key for column in collector.pool.columns)


def _collect_constructed_route(
    instance: Dict[str, Any],
    collector: RouteColumnCollector,
    request_ids: List[str],
    stage: str,
    seed: int,
) -> bool:
    if not request_ids or _request_set_exists(collector, request_ids):
        return False
    pairs = _request_ids_to_pairs(instance, request_ids)
    for strategy in ("regret-3", "regret-2", "earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle"):
        route = construct_route_from_pairs(instance, pairs, strategy, seed=seed)
        if route and collector.collect(route, stage, failed_repair=True):
            return True
    return False


def _deadline_hit(started: float | None, max_runtime_ms: int) -> bool:
    return started is not None and int((time.perf_counter() - started) * 1000) >= max_runtime_ms


def _related_request_ids(instance: Dict[str, Any], seed_request_id: str, candidate_ids: List[str]) -> List[str]:
    inverse = _request_pair_by_id(instance)
    seed_pair = inverse.get(seed_request_id)
    if seed_pair is None:
        return candidate_ids
    return sorted(candidate_ids, key=lambda request_id: relatedness(instance, seed_pair, inverse[request_id]))


def missing_request_focused_generator(
    instance: Dict[str, Any],
    collector: RouteColumnCollector,
    missing_request_ids: List[str],
    avg_target_route_size: int,
    max_columns: int = 100,
    seed: int = 34,
    started: float | None = None,
    max_runtime_ms: int = 10_000,
) -> int:
    generated = 0
    all_ids = sorted(request_id_map(instance).values())
    target_sizes = range(max(2, avg_target_route_size - 2), min(len(all_ids), avg_target_route_size + 3) + 1)
    for seed_index, missing_id in enumerate(dict.fromkeys(missing_request_ids)):
        if _deadline_hit(started, max_runtime_ms):
            return generated
        related_ids = _related_request_ids(instance, missing_id, all_ids)
        for size in target_sizes:
            if _deadline_hit(started, max_runtime_ms):
                return generated
            candidate = [missing_id]
            for request_id in related_ids:
                if request_id != missing_id and request_id not in candidate and len(candidate) < size:
                    candidate.append(request_id)
            if _collect_constructed_route(instance, collector, sorted(candidate), "missing-request-focused", seed + seed_index + size):
                generated += 1
                if generated >= max_columns:
                    return generated
            for offset in range(1, min(6, max(1, len(related_ids) - size + 1))):
                if _deadline_hit(started, max_runtime_ms):
                    return generated
                window = [missing_id] + [request_id for request_id in related_ids[offset:offset + size] if request_id != missing_id]
                if len(window) < size:
                    continue
                if _collect_constructed_route(instance, collector, sorted(window[:size]), "missing-request-focused", seed + seed_index + size + offset):
                    generated += 1
                    if generated >= max_columns:
                        return generated
    return generated


def compatible_complement_generator(
    instance: Dict[str, Any],
    collector: RouteColumnCollector,
    max_cover: Dict[str, Any],
    avg_target_route_size: int,
    max_columns: int = 100,
    seed: int = 134,
    started: float | None = None,
    max_runtime_ms: int = 10_000,
) -> int:
    selected_sets = [set(request_set) for request_set in max_cover.get("selectedColumnRequestSets", [])]
    if not selected_sets:
        return 0
    generated = 0
    all_ids = set(request_id_map(instance).values())
    for selected_count in range(len(selected_sets), -1, -1):
        if _deadline_hit(started, max_runtime_ms):
            return generated
        for selected_indexes in itertools.combinations(range(len(selected_sets)), selected_count):
            if _deadline_hit(started, max_runtime_ms):
                return generated
            used = set().union(*(selected_sets[index] for index in selected_indexes)) if selected_indexes else set()
            complement = sorted(all_ids - used)
            if not complement or len(complement) > avg_target_route_size + 3:
                continue
            if _collect_constructed_route(instance, collector, complement, "compatible-complement", seed + selected_count + generated):
                generated += 1
                if generated >= max_columns:
                    return generated
            for missing_id in max_cover.get("uncoveredRequestsInBestPacking", []):
                if _deadline_hit(started, max_runtime_ms):
                    return generated
                if missing_id not in complement:
                    continue
                related = [request_id for request_id in _related_request_ids(instance, missing_id, complement) if request_id in complement]
                for size in range(max(2, min(len(related), avg_target_route_size - 2)), min(len(related), avg_target_route_size + 3) + 1):
                    candidate = sorted(related[:size])
                    if _collect_constructed_route(instance, collector, candidate, "compatible-complement", seed + size + generated):
                        generated += 1
                        if generated >= max_columns:
                            return generated
    return generated


def large_route_compression_generator(
    instance: Dict[str, Any],
    collector: RouteColumnCollector,
    avg_target_route_size: int,
    max_columns: int = 120,
    max_source_columns: int = 140,
    started: float | None = None,
    max_runtime_ms: int = 10_000,
) -> int:
    generated = 0
    columns = sorted(collector.pool.columns, key=lambda column: (-len(column.request_ids), column.distance))[:max_source_columns]
    min_size = max(2, avg_target_route_size - 2)
    max_size = avg_target_route_size + 3
    for left_index in range(len(columns)):
        if _deadline_hit(started, max_runtime_ms):
            return generated
        left_set = column_request_set(columns[left_index])
        for right_index in range(left_index + 1, len(columns)):
            if _deadline_hit(started, max_runtime_ms):
                return generated
            union = sorted(left_set | column_request_set(columns[right_index]))
            if len(union) < min_size or len(union) > max_size:
                continue
            if _collect_constructed_route(instance, collector, union, "large-route-compression", 234 + left_index + right_index):
                generated += 1
                if generated >= max_columns:
                    return generated
    return generated


def large_compatible_column_stats(columns: List[PDPTWRouteColumn], avg_target_route_size: int) -> Dict[str, Any]:
    graph = compatibility_graph_stats(columns)
    request_sets = [column_request_set(column) for column in columns]
    large_indexes = [index for index, request_set in enumerate(request_sets) if avg_target_route_size - 2 <= len(request_set) <= avg_target_route_size + 3]
    compatible_large = 0
    for index in large_indexes:
        if any(index != other and not (request_sets[index] & request_sets[other]) for other in range(len(request_sets))):
            compatible_large += 1
    return {
        "largeColumnCount": len(large_indexes),
        "largeCompatibleColumnCount": compatible_large,
        "compatibleEdgeCount": graph.get("compatibleEdgeCount"),
        "averageCompatibleDegree": graph.get("averageCompatibleDegree"),
        "isolatedColumnCount": graph.get("isolatedColumnCount"),
    }


def run_phase34_generation(instance: Dict[str, Any], collector: RouteColumnCollector, target_vehicle_count: int) -> Dict[str, Any]:
    started = time.perf_counter()
    sp_solver = PDPTWSetPartitioningSolver(time_limit_ms=2_000)
    exact_before = sp_solver.solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    max_cover_before = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    relaxation_before = min_slack_relaxation(instance, collector.pool.columns, target_vehicle_count)
    total_requests = len(request_id_map(instance))
    avg_target = (total_requests + target_vehicle_count - 1) // max(1, target_vehicle_count)
    size_before = target_size_diagnostics(total_requests, target_vehicle_count, collector.pool.columns, max_cover_before)
    large_stats_before = large_compatible_column_stats(collector.pool.columns, avg_target)
    missing = list(dict.fromkeys(max_cover_before.get("uncoveredRequestsInBestPacking", []) + relaxation_before.get("missingRequests", [])))
    missing_count = missing_request_focused_generator(instance, collector, missing, avg_target, max_columns=80, started=started, max_runtime_ms=12_000)
    complement_count = compatible_complement_generator(instance, collector, max_cover_before, avg_target, max_columns=80, started=started, max_runtime_ms=18_000)
    compression_count = large_route_compression_generator(instance, collector, avg_target, max_columns=80, max_source_columns=100, started=started, max_runtime_ms=26_000)
    guided_count = 0 if _deadline_hit(started, 28_000) else guided_penalty_generation(instance, collector, relaxation_before, max_columns=40)
    baseline_compression_count = 0 if _deadline_hit(started, 30_000) else compression_column_generator(instance, collector, max_columns=20)
    exact_after = sp_solver.solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    max_cover_after = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    size_after = target_size_diagnostics(total_requests, target_vehicle_count, collector.pool.columns, max_cover_after)
    large_stats_after = large_compatible_column_stats(collector.pool.columns, avg_target)
    return {
        "exactBefore": exact_before,
        "exactAfter": exact_after,
        "maxCoverBefore": max_cover_before,
        "maxCoverAfter": max_cover_after,
        "minSlackRelaxationBefore": relaxation_before,
        "targetSizeBefore": size_before,
        "targetSizeAfter": size_after,
        "largeCompatibleBefore": large_stats_before,
        "largeCompatibleAfter": large_stats_after,
        "missingRequestFocusedColumnsGenerated": missing_count,
        "compatibleComplementColumnsGenerated": complement_count,
        "largeRouteCompressionColumnsGenerated": compression_count,
        "guidedColumnsGenerated": guided_count,
        "baselineCompressionColumnsGenerated": baseline_compression_count,
    }


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    collector, phase32_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    incumbent_vehicle_count = len([route for route in solution.get("routes", []) if len(route) > 2])
    target_vehicle_count = max(1, incumbent_vehicle_count - 1)
    before_stats = collector.pool.stats()
    before_diversity = request_set_diversity_stats(collector.pool)
    generation = run_phase34_generation(instance, collector, target_vehicle_count)
    after_stats = collector.pool.stats()
    after_diversity = request_set_diversity_stats(collector.pool)
    exact_before = generation["exactBefore"]
    exact_after = generation["exactAfter"]
    max_cover_before = generation["maxCoverBefore"]
    max_cover_after = generation["maxCoverAfter"]
    selected_solution = exact_after.get("solution") if exact_after.get("feasible") else None
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    selected_details = selected_column_details(collector.pool, exact_after)
    max_cover_improved = int(max_cover_after.get("maxCoveredRequestCount", 0)) > int(max_cover_before.get("maxCoveredRequestCount", 0))
    missing_reduced = len(max_cover_after.get("uncoveredRequestsInBestPacking", [])) < len(max_cover_before.get("uncoveredRequestsInBestPacking", []))
    large_improved = generation["largeCompatibleAfter"].get("largeCompatibleColumnCount", 0) > generation["largeCompatibleBefore"].get("largeCompatibleColumnCount", 0)
    if leakage or hard_violations or after_stats.get("uncoveredRequests"):
        verdict = "FAIL"
    elif exact_after.get("feasible"):
        verdict = "PASS"
    elif max_cover_improved or missing_reduced or large_improved:
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "PASS_WITH_LIMITS"
    diagnostics = {
        "schemaVersion": "phase34-missing-request-large-columns-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "targetVehicleCount": target_vehicle_count,
        "internalColumnCountBefore": before_stats.get("columnCount"),
        "internalColumnCountAfter": after_stats.get("columnCount"),
        "uniqueRequestSetCountBefore": before_diversity.get("uniqueRequestSetCount"),
        "uniqueRequestSetCountAfter": after_diversity.get("uniqueRequestSetCount"),
        "requestCoverageMinAfter": after_stats.get("requestCoverageMin"),
        "requestCoverageMedianAfter": after_stats.get("requestCoverageMedian"),
        "requestCoverageMaxAfter": after_stats.get("requestCoverageMax"),
        "exactTargetFeasibleBefore": bool(exact_before.get("feasible")),
        "exactTargetFeasibleAfter": bool(exact_after.get("feasible")),
        "maxCoveredRequestCountBefore": max_cover_before.get("maxCoveredRequestCount"),
        "maxCoveredRequestCountAfter": max_cover_after.get("maxCoveredRequestCount"),
        "uncoveredRequestsInBestPackingBefore": max_cover_before.get("uncoveredRequestsInBestPacking"),
        "uncoveredRequestsInBestPackingAfter": max_cover_after.get("uncoveredRequestsInBestPacking"),
        "targetSizeDiagnosticsBefore": generation.get("targetSizeBefore"),
        "targetSizeDiagnosticsAfter": generation.get("targetSizeAfter"),
        "largeCompatibleColumnStatsBefore": generation.get("largeCompatibleBefore"),
        "largeCompatibleColumnStatsAfter": generation.get("largeCompatibleAfter"),
        "missingRequestFocusedColumnsGenerated": generation.get("missingRequestFocusedColumnsGenerated"),
        "compatibleComplementColumnsGenerated": generation.get("compatibleComplementColumnsGenerated"),
        "largeRouteCompressionColumnsGenerated": generation.get("largeRouteCompressionColumnsGenerated"),
        "guidedColumnsGenerated": generation.get("guidedColumnsGenerated"),
        "baselineCompressionColumnsGenerated": generation.get("baselineCompressionColumnsGenerated"),
        "selectedSolutionFeasible": bool(selected_solution) and hard_violations == 0,
        "selectedColumnSources": selected_details.get("selectedColumnSources"),
        "selectedColumnStages": selected_details.get("selectedColumnStages"),
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    write_json(instance_dir / "sp_diagnostics.json", generation)
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    write_json(instance_dir / "diagnostics.json", diagnostics)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 34 Missing-Request Large Columns", "", "| Instance | Verdict | Columns Before | Columns After | MaxCover Before | MaxCover After | Large Compatible Before | Large Compatible After | Exact After | Runtime ms |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        before_large = (row.get("largeCompatibleColumnStatsBefore") or {}).get("largeCompatibleColumnCount")
        after_large = (row.get("largeCompatibleColumnStatsAfter") or {}).get("largeCompatibleColumnCount")
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('internalColumnCountBefore')} | {row.get('internalColumnCountAfter')} | {row.get('maxCoveredRequestCountBefore')} | {row.get('maxCoveredRequestCountAfter')} | {before_large} | {after_large} | {row.get('exactTargetFeasibleAfter')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase34-missing-request-large-columns-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase34_missing_request_large_columns_summary.json", summary)
    (output_dir / "phase34_missing_request_large_columns_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 34 missing-request focused PDPTW column generation.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE34 MISSING REQUEST LARGE COLUMNS] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
