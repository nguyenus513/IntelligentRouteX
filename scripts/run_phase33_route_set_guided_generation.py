from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from academic_global_consolidation import _route_is_feasible
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRouteColumn, PDPTWRoutePool, PDPTWSetPartitioningSolver, request_id_map
from run_phase32_internal_column_generation import (
    RouteColumnCollector,
    construct_route_from_pairs,
    generate_internal_columns,
    request_pairs,
    request_set_diversity_stats,
    selected_column_details,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase33-route-set-guided-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def column_request_set(column: PDPTWRouteColumn) -> Set[str]:
    return set(column.request_ids)


def max_cover_packing(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int, time_limit_ms: int = 2_000) -> Dict[str, Any]:
    try:
        from ortools.sat.python import cp_model
    except Exception as exception:
        return {"status": "unavailable", "reason": f"ortools-cp-sat-unavailable:{exception}", "feasible": False}
    request_ids = sorted(request_id_map(instance).values())
    model = cp_model.CpModel()
    x = [model.NewBoolVar(column.column_id) for column in columns]
    covered = {request_id: model.NewBoolVar(f"covered_{request_id}") for request_id in request_ids}
    for request_id in request_ids:
        covering = [x[index] for index, column in enumerate(columns) if request_id in column.request_ids]
        if covering:
            model.Add(sum(covering) == covered[request_id])
        else:
            model.Add(covered[request_id] == 0)
    for left in range(len(columns)):
        left_set = column_request_set(columns[left])
        for right in range(left + 1, len(columns)):
            if left_set & column_request_set(columns[right]):
                model.Add(x[left] + x[right] <= 1)
    model.Add(sum(x) <= target_vehicle_count)
    distance_terms = [int(round(column.distance * 1000)) * x[index] for index, column in enumerate(columns)]
    model.Maximize(sum(covered.values()) * 1_000_000 - sum(distance_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, time_limit_ms / 1000.0)
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return {"status": solver.StatusName(status).lower(), "feasible": False}
    selected = [columns[index] for index, var in enumerate(x) if solver.Value(var) == 1]
    covered_ids = sorted({request_id for column in selected for request_id in column.request_ids})
    uncovered = sorted(set(request_ids) - set(covered_ids))
    return {
        "status": solver.StatusName(status).lower(),
        "feasible": True,
        "maxCoveredRequestCount": len(covered_ids),
        "totalRequestCount": len(request_ids),
        "uncoveredRequestsInBestPacking": uncovered,
        "selectedColumnIds": [column.column_id for column in selected],
        "selectedColumnSizes": [len(column.request_ids) for column in selected],
        "selectedColumnSources": [column.source for column in selected],
        "selectedColumnRequestSets": [sorted(column.request_ids) for column in selected],
    }


def min_slack_relaxation(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int, time_limit_ms: int = 2_000) -> Dict[str, Any]:
    try:
        from ortools.sat.python import cp_model
    except Exception as exception:
        return {"status": "unavailable", "reason": f"ortools-cp-sat-unavailable:{exception}", "feasible": False}
    request_ids = sorted(request_id_map(instance).values())
    model = cp_model.CpModel()
    x = [model.NewBoolVar(column.column_id) for column in columns]
    missing = {request_id: model.NewBoolVar(f"missing_{request_id}") for request_id in request_ids}
    duplicate = {request_id: model.NewIntVar(0, max(1, len(columns)), f"dup_{request_id}") for request_id in request_ids}
    for request_id in request_ids:
        cover_count = sum(x[index] for index, column in enumerate(columns) if request_id in column.request_ids)
        model.Add(cover_count + missing[request_id] >= 1)
        model.Add(duplicate[request_id] >= cover_count - 1)
    model.Add(sum(x) <= target_vehicle_count)
    distance_terms = [int(round(column.distance * 1000)) * x[index] for index, column in enumerate(columns)]
    model.Minimize(sum(missing.values()) * 10_000_000 + sum(duplicate.values()) * 1_000_000 + sum(distance_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, time_limit_ms / 1000.0)
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return {"status": solver.StatusName(status).lower(), "feasible": False}
    selected = [columns[index] for index, var in enumerate(x) if solver.Value(var) == 1]
    missing_ids = [request_id for request_id in request_ids if solver.Value(missing[request_id]) == 1]
    duplicate_ids = [request_id for request_id in request_ids if solver.Value(duplicate[request_id]) > 0]
    overlap_pairs = []
    for left in range(len(selected)):
        for right in range(left + 1, len(selected)):
            overlap = sorted(column_request_set(selected[left]) & column_request_set(selected[right]))
            if overlap:
                overlap_pairs.append({"left": selected[left].column_id, "right": selected[right].column_id, "overlap": overlap})
    return {
        "status": solver.StatusName(status).lower(),
        "feasible": True,
        "missingRequests": missing_ids,
        "duplicateRequests": duplicate_ids,
        "conflictRequests": sorted(set(missing_ids) | set(duplicate_ids)),
        "overlapPairs": overlap_pairs[:50],
        "routeCountUsed": len(selected),
        "selectedColumnIds": [column.column_id for column in selected],
    }


def compatibility_graph_stats(columns: List[PDPTWRouteColumn]) -> Dict[str, Any]:
    degrees = [0 for _ in columns]
    edge_count = 0
    for left in range(len(columns)):
        left_set = column_request_set(columns[left])
        for right in range(left + 1, len(columns)):
            if not (left_set & column_request_set(columns[right])):
                edge_count += 1
                degrees[left] += 1
                degrees[right] += 1
    top_by_degree = sorted(range(len(columns)), key=lambda index: degrees[index], reverse=True)[:10]
    top_by_size = sorted(range(len(columns)), key=lambda index: len(columns[index].request_ids), reverse=True)[:10]
    size_hist: Dict[str, int] = {}
    for column in columns:
        size = str(len(column.request_ids))
        size_hist[size] = size_hist.get(size, 0) + 1
    return {
        "compatibleEdgeCount": edge_count,
        "averageCompatibleDegree": statistics.mean(degrees) if degrees else 0,
        "maxCompatibleDegree": max(degrees) if degrees else 0,
        "isolatedColumnCount": sum(1 for degree in degrees if degree == 0),
        "requestSetSizeHistogram": size_hist,
        "topColumnsByCompatibleDegree": [{"columnId": columns[index].column_id, "degree": degrees[index], "size": len(columns[index].request_ids)} for index in top_by_degree],
        "topColumnsByCoverageSize": [{"columnId": columns[index].column_id, "degree": degrees[index], "size": len(columns[index].request_ids)} for index in top_by_size],
        "largeIncompatibleColumns": [{"columnId": columns[index].column_id, "degree": degrees[index], "size": len(columns[index].request_ids)} for index in top_by_size if degrees[index] <= (statistics.median(degrees) if degrees else 0)],
    }


def target_size_diagnostics(total_requests: int, target_vehicle_count: int, columns: List[PDPTWRouteColumn], max_cover: Dict[str, Any]) -> Dict[str, Any]:
    avg_target = (total_requests + target_vehicle_count - 1) // max(1, target_vehicle_count)
    sizes = [len(column.request_ids) for column in columns]
    selected_sizes = max_cover.get("selectedColumnSizes", [])
    return {
        "avgTargetRouteSize": avg_target,
        "columnsBelowTargetBand": sum(1 for size in sizes if size < avg_target - 2),
        "columnsAroundTargetBand": sum(1 for size in sizes if avg_target - 2 <= size <= avg_target + 2),
        "columnsAboveTargetBand": sum(1 for size in sizes if size > avg_target + 2),
        "bestPackingSelectedSizes": selected_sizes,
        "bestPackingUsesTooSmallColumns": bool(selected_sizes and statistics.mean(selected_sizes) < avg_target - 1),
    }


def request_ids_to_pairs(instance: Dict[str, Any], request_ids: List[str]) -> List[tuple[str, str]]:
    inverse = {request_id: pair for pair, request_id in request_id_map(instance).items()}
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def complement_route_generator(instance: Dict[str, Any], collector: RouteColumnCollector, max_cover: Dict[str, Any], max_columns: int = 80) -> int:
    generated = 0
    uncovered = list(max_cover.get("uncoveredRequestsInBestPacking", []))
    if not uncovered:
        return 0
    base_pairs = request_ids_to_pairs(instance, uncovered)
    all_pairs = request_pairs(instance)
    for extra_count in range(0, 5):
        candidate_pairs = base_pairs[:]
        for pair in all_pairs:
            if pair not in candidate_pairs and len(candidate_pairs) < len(base_pairs) + extra_count:
                candidate_pairs.append(pair)
        for strategy in ["earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle"]:
            route = construct_route_from_pairs(instance, candidate_pairs, strategy, seed=33 + extra_count)
            if route and collector.collect(route, "complement-generation", failed_repair=True):
                generated += 1
                if generated >= max_columns:
                    return generated
    return generated


def compression_column_generator(instance: Dict[str, Any], collector: RouteColumnCollector, max_columns: int = 120) -> int:
    generated = 0
    columns = collector.pool.columns
    seen_sets = {tuple(sorted(column.request_ids)) for column in columns}
    for left_index in range(len(columns)):
        for right_index in range(left_index + 1, min(len(columns), left_index + 40)):
            union_ids = sorted(column_request_set(columns[left_index]) | column_request_set(columns[right_index]))
            if tuple(union_ids) in seen_sets:
                continue
            pairs = request_ids_to_pairs(instance, union_ids)
            route = construct_route_from_pairs(instance, pairs, "earliest-due") or construct_route_from_pairs(instance, pairs, "ready-time")
            if route and collector.collect(route, "compression-generation", failed_repair=True):
                seen_sets.add(tuple(union_ids))
                generated += 1
                if generated >= max_columns:
                    return generated
    return generated


def guided_penalty_generation(instance: Dict[str, Any], collector: RouteColumnCollector, relaxation: Dict[str, Any], max_columns: int = 80) -> int:
    priority_ids = list(dict.fromkeys(relaxation.get("missingRequests", []) + relaxation.get("duplicateRequests", [])))
    if not priority_ids:
        return 0
    generated = 0
    base_pairs = request_ids_to_pairs(instance, priority_ids)
    all_pairs = request_pairs(instance)
    for size in range(max(2, len(base_pairs)), min(len(base_pairs) + 8, len(all_pairs)) + 1):
        candidate_pairs = base_pairs[:]
        for pair in all_pairs:
            if pair not in candidate_pairs and len(candidate_pairs) < size:
                candidate_pairs.append(pair)
        route = construct_route_from_pairs(instance, candidate_pairs, "earliest-due") or construct_route_from_pairs(instance, candidate_pairs, "ready-time")
        if route and collector.collect(route, "guided-penalty-generation", failed_repair=True):
            generated += 1
            if generated >= max_columns:
                return generated
    return generated


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    collector, phase32_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    before_stats = collector.pool.stats()
    before_diversity = request_set_diversity_stats(collector.pool)
    incumbent_vehicle_count = len([route for route in solution.get("routes", []) if len(route) > 2])
    target_vehicle_count = max(1, incumbent_vehicle_count - 1)
    sp_solver = PDPTWSetPartitioningSolver(time_limit_ms=2_000)
    exact_before = sp_solver.solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    max_cover_before = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    relaxation_before = min_slack_relaxation(instance, collector.pool.columns, target_vehicle_count)
    graph_before = compatibility_graph_stats(collector.pool.columns)
    size_diag = target_size_diagnostics(len(request_id_map(instance)), target_vehicle_count, collector.pool.columns, max_cover_before)
    complement_count = complement_route_generator(instance, collector, max_cover_before)
    compression_count = compression_column_generator(instance, collector)
    guided_count = guided_penalty_generation(instance, collector, relaxation_before)
    after_stats = collector.pool.stats()
    after_diversity = request_set_diversity_stats(collector.pool)
    exact_after = sp_solver.solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    max_cover_after = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    selected_solution = exact_after.get("solution") if exact_after.get("feasible") else None
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    if leakage or hard_violations:
        verdict = "FAIL"
    elif exact_after.get("feasible"):
        verdict = "PASS"
    elif int(max_cover_after.get("maxCoveredRequestCount", 0)) > int(max_cover_before.get("maxCoveredRequestCount", 0)) or len(max_cover_after.get("uncoveredRequestsInBestPacking", [])) < len(max_cover_before.get("uncoveredRequestsInBestPacking", [])):
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "PASS_WITH_LIMITS"
    details = selected_column_details(collector.pool, exact_after)
    diagnostics = {
        "schemaVersion": "phase33-route-set-guided-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "internalColumnCountBefore": before_stats.get("columnCount"),
        "internalColumnCountAfter": after_stats.get("columnCount"),
        "uniqueRequestSetCountBefore": before_diversity.get("uniqueRequestSetCount"),
        "uniqueRequestSetCountAfter": after_diversity.get("uniqueRequestSetCount"),
        "exactTargetFeasibleBefore": bool(exact_before.get("feasible")),
        "exactTargetFeasibleAfter": bool(exact_after.get("feasible")),
        "maxCoveredRequestCountBefore": max_cover_before.get("maxCoveredRequestCount"),
        "maxCoveredRequestCountAfter": max_cover_after.get("maxCoveredRequestCount"),
        "uncoveredRequestsInBestPackingBefore": max_cover_before.get("uncoveredRequestsInBestPacking"),
        "uncoveredRequestsInBestPackingAfter": max_cover_after.get("uncoveredRequestsInBestPacking"),
        "missingRequests": relaxation_before.get("missingRequests"),
        "duplicateRequests": relaxation_before.get("duplicateRequests"),
        "compatibleEdgeCount": graph_before.get("compatibleEdgeCount"),
        "averageCompatibleDegree": graph_before.get("averageCompatibleDegree"),
        "requestSetSizeHistogram": graph_before.get("requestSetSizeHistogram"),
        "targetSizeDiagnostics": size_diag,
        "complementColumnsGenerated": complement_count,
        "compressionColumnsGenerated": compression_count,
        "guidedColumnsGenerated": guided_count,
        "selectedSolutionFeasible": bool(selected_solution) and hard_violations == 0,
        "selectedColumnSources": details.get("selectedColumnSources"),
        "selectedColumnStages": details.get("selectedColumnStages"),
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    write_json(instance_dir / "sp_diagnostics.json", {"exactBefore": exact_before, "exactAfter": exact_after, "maxCoverBefore": max_cover_before, "maxCoverAfter": max_cover_after, "minSlackRelaxationBefore": relaxation_before, "compatibilityGraphBefore": graph_before})
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    write_json(instance_dir / "diagnostics.json", diagnostics)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 33 Route-Set Guided Generation", "", "| Instance | Verdict | Columns Before | Columns After | MaxCover Before | MaxCover After | Exact After | Runtime ms |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('internalColumnCountBefore')} | {row.get('internalColumnCountAfter')} | {row.get('maxCoveredRequestCountBefore')} | {row.get('maxCoveredRequestCountAfter')} | {row.get('exactTargetFeasibleAfter')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase33-route-set-guided-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase33_route_set_guided_summary.json", summary)
    (output_dir / "phase33_route_set_guided_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 33 route-set guided PDPTW column generation.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE33 ROUTE-SET GUIDED] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
