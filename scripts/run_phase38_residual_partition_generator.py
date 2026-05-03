from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRouteColumn, request_id_map
from run_phase32_internal_column_generation import RouteColumnCollector, construct_route_from_pairs, generate_internal_columns, request_features
from run_phase33_route_set_guided_generation import max_cover_packing
from run_phase34_missing_request_large_columns import run_phase34_generation
from run_phase35_residual_exact_cover_repair import coverage_state, residual_exact_cover_local_search, selected_columns_from_max_cover
from run_phase37_conflict_guided_replacement import columns_by_ids, conflict_analysis, solve_residual_subproblem

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase38-residual-partition-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _request_pair_by_id(instance: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    return {request_id: pair for pair, request_id in request_id_map(instance).items()}


def _pairs_for_ids(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[tuple[str, str]]:
    inverse = _request_pair_by_id(instance)
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def _sort_key(instance: Dict[str, Any], request_id: str, strategy: str) -> tuple[float, float]:
    pair = _request_pair_by_id(instance)[request_id]
    features = request_features(instance, pair)
    if strategy == "pickup-spatial":
        return (features["pickupX"], features["pickupY"])
    if strategy == "dropoff-spatial":
        return (features["dropoffX"], features["dropoffY"])
    if strategy == "due-time":
        return (features["due"], features["ready"])
    if strategy == "ready-time":
        return (features["ready"], features["due"])
    if strategy == "corridor":
        return (features["pickupX"] + features["dropoffX"], features["pickupY"] + features["dropoffY"])
    return (features["pickupX"] - features["dropoffX"], features["pickupY"] - features["dropoffY"])


def balanced_partition(request_ids: List[str], slots: int) -> List[List[str]]:
    groups = [[] for _ in range(max(1, slots))]
    for index, request_id in enumerate(request_ids):
        groups[index % len(groups)].append(request_id)
    return [group for group in groups if group]


def residual_partitions(instance: Dict[str, Any], residual_ids: List[str], slots: int, missing_ids: List[str], seed: int = 38) -> List[Dict[str, Any]]:
    if slots <= 0:
        return []
    partitions: List[Dict[str, Any]] = []
    for strategy in ("due-time", "pickup-spatial", "corridor"):
        ordered = sorted(residual_ids, key=lambda request_id: _sort_key(instance, request_id, strategy))
        partitions.append({"strategy": strategy, "groups": balanced_partition(ordered, slots)})
    rng = random.Random(seed)
    for shuffle_index in range(1):
        ordered = residual_ids[:]
        rng.shuffle(ordered)
        partitions.append({"strategy": f"seeded-random-{shuffle_index}", "groups": balanced_partition(ordered, slots)})
    if missing_ids:
        groups = [[] for _ in range(max(1, slots))]
        for index, request_id in enumerate(missing_ids):
            if request_id in residual_ids:
                groups[index % len(groups)].append(request_id)
        remaining = [request_id for request_id in residual_ids if request_id not in set(missing_ids)]
        for request_id in remaining:
            groups.sort(key=len)
            groups[0].append(request_id)
        partitions.append({"strategy": "mixed-missing-forced", "groups": [group for group in groups if group]})
    return partitions


def construct_partition_columns(instance: Dict[str, Any], collector: RouteColumnCollector, groups: List[List[str]], stage: str) -> tuple[List[PDPTWRouteColumn], int]:
    columns: List[PDPTWRouteColumn] = []
    repairs = 0
    for group in groups:
        route = construct_group_route(instance, group)
        if route is None:
            route, repair_count = repair_group_route(instance, groups, group)
            repairs += repair_count
        if route is None:
            return [], repairs
        before = len(collector.pool.columns)
        if not collector.collect(route, stage, failed_repair=True):
            return [], repairs
        after = collector.pool.columns
        if len(after) <= before:
            return [], repairs
        columns.append(after[-1])
    return columns, repairs


def construct_group_route(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[str] | None:
    pairs = _pairs_for_ids(instance, request_ids)
    if not pairs:
        return None
    strategies = ("earliest-due", "ready-time", "nearest-pickup") if len(pairs) > 8 else ("regret-2", "earliest-due", "ready-time", "nearest-pickup")
    for strategy in strategies:
        route = construct_route_from_pairs(instance, pairs, strategy, seed=38 + len(pairs))
        if route:
            return route
    return None


def repair_group_route(instance: Dict[str, Any], groups: List[List[str]], failed_group: List[str], max_repairs: int = 8) -> tuple[List[str] | None, int]:
    attempts = 0
    for request_id in list(failed_group):
        if attempts >= max_repairs:
            break
        attempts += 1
        for target_group in groups:
            if target_group is failed_group:
                continue
            candidate_group = [item for item in failed_group if item != request_id]
            target_candidate = target_group + [request_id]
            if construct_group_route(instance, target_candidate) and candidate_group and construct_group_route(instance, candidate_group):
                failed_group[:] = candidate_group
                target_group[:] = target_candidate
                return construct_group_route(instance, failed_group), attempts
    return None, attempts


def phase37_residual_attempts(instance: Dict[str, Any], selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_attempts: int = 12) -> List[Dict[str, Any]]:
    all_ids = set(request_id_map(instance).values())
    attempts = []
    for analysis in conflict_analysis(selected, selected + [], missing_ids):
        pass
    analyses = conflict_analysis(selected, selected, missing_ids)
    if not analyses:
        analyses = conflict_analysis(selected, selected, missing_ids)
    return attempts


def conflict_residual_attempts(selected: List[PDPTWRouteColumn], pool_columns: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_attempts: int = 20) -> List[Dict[str, Any]]:
    all_ids: Set[str] = set().union(*(set(column.request_ids) for column in pool_columns)) if pool_columns else set()
    attempts = []
    for analysis in conflict_analysis(selected, pool_columns, missing_ids)[:max_attempts]:
        blocker_ids = set(analysis["blockingSelectedColumnIds"])
        fixed = [column for column in selected if column.column_id not in blocker_ids]
        fixed_used = set().union(*(set(column.request_ids) for column in fixed)) if fixed else set()
        residual_ids = sorted(all_ids - fixed_used)
        route_slots = target_vehicle_count - len(fixed)
        attempts.append({
            "candidateColumnId": analysis["candidateColumnId"],
            "blockingSelectedColumnIds": sorted(blocker_ids),
            "fixedColumns": fixed,
            "residualRequestIds": residual_ids,
            "routeSlotsRemaining": route_slots,
            "missingRequestIds": [request_id for request_id in missing_ids if request_id in residual_ids],
        })
    return attempts


def run_residual_partition_attempt(instance: Dict[str, Any], collector: RouteColumnCollector, attempt: Dict[str, Any], started: float | None = None, max_runtime_ms: int = 40_000) -> Dict[str, Any]:
    fixed = attempt["fixedColumns"]
    residual_ids = attempt["residualRequestIds"]
    route_slots = attempt["routeSlotsRemaining"]
    missing_ids = attempt.get("missingRequestIds", [])
    generated = 0
    feasible_partitions = 0
    group_repairs = 0
    strategies = []
    for partition in residual_partitions(instance, residual_ids, route_slots, missing_ids):
        if started is not None and int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
            break
        strategies.append(partition["strategy"])
        columns, repairs = construct_partition_columns(instance, collector, partition["groups"], "phase38-residual-partition")
        group_repairs += repairs
        generated += len(columns)
        if columns and len(columns) == route_slots:
            feasible_partitions += 1
            selected = fixed + columns
            state = coverage_state(instance, selected)
            if state["missingCount"] == 0 and state["duplicateCount"] == 0:
                solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase38-residual-partition", "routes": [column.route for column in selected]}
                checked = check_solution(instance, solution)
                if checked.get("feasible"):
                    return {"feasible": True, "solution": solution, "selectedColumns": selected, "generated": generated, "feasiblePartitions": feasible_partitions, "groupRepairs": group_repairs, "strategies": strategies, "cpSatStatus": "not-needed"}
    candidates = [column for column in collector.pool.columns if set(column.request_ids) & set(residual_ids)]
    cp_sat = {"status": "skipped", "reason": "runtime-cap"} if started is not None and int((time.perf_counter() - started) * 1000) >= max_runtime_ms else solve_residual_subproblem(instance, fixed, candidates, residual_ids, route_slots)
    if cp_sat.get("feasible"):
        selected = fixed + cp_sat["selectedColumns"]
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase38-residual-partition-cpsat", "routes": [column.route for column in selected]}
        checked = check_solution(instance, solution)
        if checked.get("feasible"):
            return {"feasible": True, "solution": solution, "selectedColumns": selected, "generated": generated, "feasiblePartitions": feasible_partitions, "groupRepairs": group_repairs, "strategies": strategies, "cpSatStatus": cp_sat.get("status")}
    return {"feasible": False, "solution": None, "selectedColumns": [], "generated": generated, "feasiblePartitions": feasible_partitions, "groupRepairs": group_repairs, "strategies": strategies, "cpSatStatus": cp_sat.get("status"), "cpSatReason": cp_sat.get("reason")}


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    collector, phase32_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    target_vehicle_count = max(1, len([route for route in solution.get("routes", []) if len(route) > 2]) - 1)
    phase34 = run_phase34_generation(instance, collector, target_vehicle_count)
    seed_selected = selected_columns_from_max_cover(collector.pool.columns, max_cover_packing(instance, collector.pool.columns, target_vehicle_count))
    phase35_seed = residual_exact_cover_local_search(instance, collector, seed_selected, target_vehicle_count, max_runtime_ms=20_000) if seed_selected else {}
    selected = columns_by_ids(collector.pool.columns, phase35_seed.get("bestSelectedColumnIds", [])) or seed_selected
    missing_ids = coverage_state(instance, selected).get("missingRequests", [])
    attempts = conflict_residual_attempts(selected, collector.pool.columns, missing_ids, target_vehicle_count, max_attempts=4)
    attempt_results = []
    selected_solution = None
    for attempt in attempts:
        if int((time.perf_counter() - started) * 1000) >= 150_000:
            break
        result = run_residual_partition_attempt(instance, collector, attempt, started=started, max_runtime_ms=150_000)
        attempt_results.append({key: value for key, value in result.items() if key not in {"solution", "selectedColumns"}} | {
            "residualRequestCount": len(attempt["residualRequestIds"]),
            "routeSlotsRemaining": attempt["routeSlotsRemaining"],
            "blockingSelectedColumnIds": attempt["blockingSelectedColumnIds"],
        })
        if result.get("feasible"):
            selected_solution = result.get("solution")
            break
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    exact_after = bool(selected_solution) and hard_violations == 0
    generated = sum(result.get("generated", 0) for result in attempt_results)
    feasible_partitions = sum(result.get("feasiblePartitions", 0) for result in attempt_results)
    cp_statuses = [result.get("cpSatStatus") for result in attempt_results]
    if leakage or hard_violations:
        verdict = "FAIL"
    elif exact_after:
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    blocker = "candidate-pool-missing"
    if generated == 0:
        blocker = "route-construction-time-window-block"
    elif all(status in {"infeasible", "model_invalid"} for status in cp_statuses if status):
        blocker = "residual-subproblem-infeasible"
    diagnostics = {
        "schemaVersion": "phase38-residual-partition-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "residualAttemptCount": len(attempts),
        "residualRequestCounts": [len(attempt["residualRequestIds"]) for attempt in attempts],
        "routeSlotsRemaining": [attempt["routeSlotsRemaining"] for attempt in attempts],
        "partitionStrategiesTried": sorted({strategy for result in attempt_results for strategy in result.get("strategies", [])}),
        "partitionColumnsGenerated": generated,
        "feasiblePartitionCount": feasible_partitions,
        "groupRepairAttempts": sum(result.get("groupRepairs", 0) for result in attempt_results),
        "groupRepairSuccesses": feasible_partitions,
        "residualCpSatStatus": cp_statuses,
        "bestResidualMissingCount": len(missing_ids),
        "exactTargetFeasibleAfter": exact_after,
        "selectedSolutionFeasible": exact_after,
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "blockerAfter": blocker,
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "phase34ExactTargetFeasibleAfter": phase34.get("exactAfter", {}).get("feasible"),
        "phase35SeedMissingCountAfter": phase35_seed.get("bestMissingCountAfter"),
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "phase38_residual_diagnostics.json", diagnostics)
    write_json(instance_dir / "phase38_partition_attempts.json", {"attempts": attempt_results})
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 38 Residual Partition Generator", "", "| Instance | Verdict | Attempts | Generated | Feasible Partitions | Exact After | Blocker | Runtime ms |", "|---|---|---:|---:|---:|---:|---|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('residualAttemptCount')} | {row.get('partitionColumnsGenerated')} | {row.get('feasiblePartitionCount')} | {row.get('exactTargetFeasibleAfter')} | {row.get('blockerAfter')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase38-residual-partition-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase38_residual_partition_summary.json", summary)
    (output_dir / "phase38_residual_partition_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 38 residual partition generator diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE38 RESIDUAL PARTITION GENERATOR] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
