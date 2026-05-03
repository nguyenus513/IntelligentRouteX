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
from run_phase32_internal_column_generation import RouteColumnCollector, _insert_pair_best, construct_route_from_pairs, generate_internal_columns, selected_column_details
from run_phase34_missing_request_large_columns import run_phase34_generation
from run_phase35_residual_exact_cover_repair import coverage_state, residual_exact_cover_local_search, selected_columns_from_max_cover
from run_phase33_route_set_guided_generation import max_cover_packing

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase36-residual-focused-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _request_pair_by_id(instance: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    return {request_id: pair for pair, request_id in request_id_map(instance).items()}


def _pairs_for_ids(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[tuple[str, str]]:
    inverse = _request_pair_by_id(instance)
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def _construct_route(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[str] | None:
    pairs = _pairs_for_ids(instance, request_ids)
    if not pairs:
        return None
    for strategy in ("regret-3", "regret-2", "earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle"):
        route = construct_route_from_pairs(instance, pairs, strategy, seed=36 + len(pairs))
        if route:
            return route
    return None


def _collect(collector: RouteColumnCollector, route: List[str], stage: str) -> PDPTWRouteColumn | None:
    before = len(collector.pool.columns)
    if not collector.collect(route, stage, failed_repair=True):
        return None
    columns = collector.pool.columns
    return columns[-1] if len(columns) > before else None


def _exact(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int) -> bool:
    state = coverage_state(instance, columns)
    return len(columns) <= target_vehicle_count and state["missingCount"] == 0 and state["duplicateCount"] == 0


def _score(instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int) -> tuple[int, int, int, float]:
    state = coverage_state(instance, columns)
    return (state["missingCount"], state["duplicateCount"], max(0, len(columns) - target_vehicle_count), sum(column.distance for column in columns))


def columns_by_ids(columns: List[PDPTWRouteColumn], column_ids: Iterable[str]) -> List[PDPTWRouteColumn]:
    wanted = set(column_ids)
    return [column for column in columns if column.column_id in wanted and column.allowed_for_claim]


def residual_context(instance: Dict[str, Any], selected: List[PDPTWRouteColumn], pool_columns: List[PDPTWRouteColumn]) -> Dict[str, Any]:
    state = coverage_state(instance, selected)
    missing = state["missingRequests"]
    containing = {request_id: [column.column_id for column in pool_columns if request_id in column.request_ids and column.allowed_for_claim] for request_id in missing}
    selected_sets = [set(column.request_ids) for column in selected]
    compatible_containing: Dict[str, List[str]] = {}
    conflicting: Dict[str, List[str]] = {}
    for request_id in missing:
        compatible_containing[request_id] = []
        conflicting[request_id] = []
        for column in pool_columns:
            if request_id not in column.request_ids or not column.allowed_for_claim:
                continue
            overlaps = [selected[index].column_id for index, request_set in enumerate(selected_sets) if request_set & set(column.request_ids)]
            if overlaps:
                conflicting[request_id].extend(overlaps)
            else:
                compatible_containing[request_id].append(column.column_id)
    return {
        "missingRequestIds": missing,
        "selectedColumnIds": [column.column_id for column in selected],
        "selectedColumnRequestSets": [sorted(column.request_ids) for column in selected],
        "candidateColumnsContainingEachMissingRequest": containing,
        "compatibleCandidateColumnsContainingMissingRequests": compatible_containing,
        "conflictingSelectedColumns": {request_id: sorted(set(values)) for request_id, values in conflicting.items()},
    }


def insert_missing_pair_set(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best = selected[:]
    pairs = _pairs_for_ids(instance, missing_ids)
    for index, column in enumerate(selected):
        route = column.route
        attempts += 1
        candidate_route = route[:]
        for pair in pairs:
            inserted = _insert_pair_best(instance, candidate_route, pair, max_checks=600)
            if inserted is None:
                candidate_route = []
                break
            candidate_route = inserted
        if not candidate_route:
            continue
        new_column = _collect(collector, candidate_route, "phase36-insert-missing-set")
        if new_column is None:
            continue
        candidate = selected[:index] + [new_column] + selected[index + 1:]
        successes += 1
        if _score(instance, candidate, target_vehicle_count) < _score(instance, best, target_vehicle_count):
            best = candidate
        if _exact(instance, candidate, target_vehicle_count):
            return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
    return {"attempts": attempts, "successes": successes, "columns": best, "exact": _exact(instance, best, target_vehicle_count)}


def _deadline_hit(started: float | None, max_runtime_ms: int) -> bool:
    return started is not None and int((time.perf_counter() - started) * 1000) >= max_runtime_ms


def replace_one_with_two(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_partitions: int = 16, started: float | None = None, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best = selected[:]
    for index, removed in enumerate(selected):
        if _deadline_hit(started, max_runtime_ms):
            break
        remaining = selected[:index] + selected[index + 1:]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = sorted((set(removed.request_ids) | set(missing_ids)) - used)
        if len(residual) < 2:
            continue
        tried = 0
        for split_size in range(1, len(residual)):
            for left_ids in itertools.combinations(residual, split_size):
                if _deadline_hit(started, max_runtime_ms):
                    break
                if tried >= max_partitions:
                    break
                tried += 1
                right_ids = [request_id for request_id in residual if request_id not in set(left_ids)]
                attempts += 1
                left_route = _construct_route(instance, left_ids)
                right_route = _construct_route(instance, right_ids)
                if not left_route or not right_route:
                    continue
                left_column = _collect(collector, left_route, "phase36-one-to-two")
                right_column = _collect(collector, right_route, "phase36-one-to-two")
                if not left_column or not right_column or set(left_column.request_ids) & set(right_column.request_ids):
                    continue
                candidate = remaining + [left_column, right_column]
                successes += 1
                if _score(instance, candidate, target_vehicle_count) < _score(instance, best, target_vehicle_count):
                    best = candidate
                if _exact(instance, candidate, target_vehicle_count):
                    return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
            if tried >= max_partitions:
                break
    return {"attempts": attempts, "successes": successes, "columns": best, "exact": _exact(instance, best, target_vehicle_count)}


def replace_two_with_two(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_partitions: int = 20, started: float | None = None, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best = selected[:]
    for left_index, right_index in itertools.combinations(range(len(selected)), 2):
        if _deadline_hit(started, max_runtime_ms):
            break
        remaining = [column for index, column in enumerate(selected) if index not in {left_index, right_index}]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = sorted((set(selected[left_index].request_ids) | set(selected[right_index].request_ids) | set(missing_ids)) - used)
        if len(residual) < 2:
            continue
        midpoint = len(residual) // 2
        split_sizes = sorted(set([max(1, midpoint - 1), midpoint, min(len(residual) - 1, midpoint + 1)]))
        tried = 0
        for split_size in split_sizes:
            for left_ids in itertools.combinations(residual, split_size):
                if _deadline_hit(started, max_runtime_ms):
                    break
                if tried >= max_partitions:
                    break
                tried += 1
                right_ids = [request_id for request_id in residual if request_id not in set(left_ids)]
                attempts += 1
                left_route = _construct_route(instance, left_ids)
                right_route = _construct_route(instance, right_ids)
                if not left_route or not right_route:
                    continue
                left_column = _collect(collector, left_route, "phase36-two-to-two")
                right_column = _collect(collector, right_route, "phase36-two-to-two")
                if not left_column or not right_column or set(left_column.request_ids) & set(right_column.request_ids):
                    continue
                candidate = remaining + [left_column, right_column]
                successes += 1
                if _score(instance, candidate, target_vehicle_count) < _score(instance, best, target_vehicle_count):
                    best = candidate
                if _exact(instance, candidate, target_vehicle_count):
                    return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
            if tried >= max_partitions:
                break
    return {"attempts": attempts, "successes": successes, "columns": best, "exact": _exact(instance, best, target_vehicle_count)}


def replace_two_with_one(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, started: float | None = None, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best = selected[:]
    for left_index, right_index in itertools.combinations(range(len(selected)), 2):
        if _deadline_hit(started, max_runtime_ms):
            break
        remaining = [column for index, column in enumerate(selected) if index not in {left_index, right_index}]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = sorted((set(selected[left_index].request_ids) | set(selected[right_index].request_ids) | set(missing_ids)) - used)
        attempts += 1
        route = _construct_route(instance, residual)
        if not route:
            continue
        column = _collect(collector, route, "phase36-two-to-one")
        if column is None or set(column.request_ids) & used:
            continue
        candidate = remaining + [column]
        successes += 1
        if _score(instance, candidate, target_vehicle_count) < _score(instance, best, target_vehicle_count):
            best = candidate
        if _exact(instance, candidate, target_vehicle_count):
            return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
    return {"attempts": attempts, "successes": successes, "columns": best, "exact": _exact(instance, best, target_vehicle_count)}


def replace_three_with_two(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_partitions: int = 16, started: float | None = None, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    attempts = 0
    successes = 0
    best = selected[:]
    for indexes in itertools.combinations(range(len(selected)), 3):
        if _deadline_hit(started, max_runtime_ms):
            break
        remaining = [column for index, column in enumerate(selected) if index not in set(indexes)]
        used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        residual = sorted((set().union(*(set(selected[index].request_ids) for index in indexes)) | set(missing_ids)) - used)
        if len(residual) < 2:
            continue
        tried = 0
        midpoint = len(residual) // 2
        for split_size in sorted(set([max(1, midpoint - 1), midpoint, min(len(residual) - 1, midpoint + 1)])):
            for left_ids in itertools.combinations(residual, split_size):
                if _deadline_hit(started, max_runtime_ms):
                    break
                if tried >= max_partitions:
                    break
                tried += 1
                right_ids = [request_id for request_id in residual if request_id not in set(left_ids)]
                attempts += 1
                left_route = _construct_route(instance, left_ids)
                right_route = _construct_route(instance, right_ids)
                if not left_route or not right_route:
                    continue
                left_column = _collect(collector, left_route, "phase36-three-to-two")
                right_column = _collect(collector, right_route, "phase36-three-to-two")
                if not left_column or not right_column or set(left_column.request_ids) & set(right_column.request_ids):
                    continue
                candidate = remaining + [left_column, right_column]
                successes += 1
                if _score(instance, candidate, target_vehicle_count) < _score(instance, best, target_vehicle_count):
                    best = candidate
                if _exact(instance, candidate, target_vehicle_count):
                    return {"attempts": attempts, "successes": successes, "columns": candidate, "exact": True}
            if tried >= max_partitions:
                break
    return {"attempts": attempts, "successes": successes, "columns": best, "exact": _exact(instance, best, target_vehicle_count)}


def focused_local_search(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], target_vehicle_count: int, max_runtime_ms: int = 24_000) -> Dict[str, Any]:
    started = time.perf_counter()
    best = selected[:]
    attempts: Dict[str, Dict[str, Any]] = {}
    missing_ids = coverage_state(instance, best)["missingRequests"]
    for name, move in [
        ("insertBothMissing", lambda: insert_missing_pair_set(instance, collector, best, missing_ids, target_vehicle_count)),
        ("oneToTwo", lambda: replace_one_with_two(instance, collector, best, missing_ids, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)),
        ("twoToTwo", lambda: replace_two_with_two(instance, collector, best, missing_ids, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)),
        ("twoToOne", lambda: replace_two_with_one(instance, collector, best, missing_ids, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)),
        ("threeToTwo", lambda: replace_three_with_two(instance, collector, best, missing_ids, target_vehicle_count, started=started, max_runtime_ms=max_runtime_ms)),
    ]:
        if _deadline_hit(started, max_runtime_ms):
            break
        result = move()
        attempts[name] = {key: result.get(key) for key in ("attempts", "successes", "exact")}
        if _score(instance, result["columns"], target_vehicle_count) < _score(instance, best, target_vehicle_count):
            best = result["columns"]
            missing_ids = coverage_state(instance, best)["missingRequests"]
        if result.get("exact"):
            best = result["columns"]
            break
    state = coverage_state(instance, best)
    exact = _exact(instance, best, target_vehicle_count)
    solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase36-residual-focused-repair", "routes": [column.route for column in best]} if exact else None
    checked = check_solution(instance, solution) if solution else {"feasible": False, "violations": []}
    return {
        "attempts": attempts,
        "bestMissingCountAfter": state["missingCount"],
        "bestDuplicateCountAfter": state["duplicateCount"],
        "exactTargetFeasibleAfter": exact and bool(checked.get("feasible")),
        "selectedSolutionFeasible": bool(checked.get("feasible")) if solution else False,
        "selectedColumnIds": [column.column_id for column in best],
        "solution": solution,
        "checkResult": checked,
    }


def hard_residual_certificate(instance: Dict[str, Any], selected: List[PDPTWRouteColumn], pool_columns: List[PDPTWRouteColumn]) -> Dict[str, Any]:
    context = residual_context(instance, selected, pool_columns)
    classifications: Dict[str, str] = {}
    for request_id in context["missingRequestIds"]:
        if not context["candidateColumnsContainingEachMissingRequest"].get(request_id):
            classifications[request_id] = "no-column-containing-missing"
        elif not context["compatibleCandidateColumnsContainingMissingRequests"].get(request_id):
            classifications[request_id] = "no-compatible-column"
        else:
            classifications[request_id] = "search-cap"
    return {**context, "blockerClassificationByRequest": classifications, "primaryBlocker": next(iter(classifications.values()), "none")}


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
    max_cover_selected = selected_columns_from_max_cover(collector.pool.columns, max_cover)
    phase35_seed = residual_exact_cover_local_search(instance, collector, max_cover_selected, target_vehicle_count, max_runtime_ms=24_000) if max_cover_selected else {}
    selected = columns_by_ids(collector.pool.columns, phase35_seed.get("bestSelectedColumnIds", [])) or max_cover_selected
    before_state = coverage_state(instance, selected)
    context = residual_context(instance, selected, collector.pool.columns)
    repair = focused_local_search(instance, collector, selected, target_vehicle_count, max_runtime_ms=14_000) if selected else {"exactTargetFeasibleAfter": False, "bestMissingCountAfter": before_state.get("missingCount"), "bestDuplicateCountAfter": before_state.get("duplicateCount"), "attempts": {}}
    exact_sp_after = PDPTWSetPartitioningSolver(time_limit_ms=2_000).solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    certificate = hard_residual_certificate(instance, selected, collector.pool.columns)
    selected_solution = repair.get("solution") or (exact_sp_after.get("solution") if exact_sp_after.get("feasible") else None)
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    if leakage or hard_violations:
        verdict = "FAIL"
    elif repair.get("exactTargetFeasibleAfter") or exact_sp_after.get("feasible"):
        verdict = "PASS"
    elif repair.get("bestMissingCountAfter", 999) < before_state.get("missingCount", 999) or certificate.get("primaryBlocker") != "none":
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "PASS_WITH_LIMITS"
    details = selected_column_details(collector.pool, exact_sp_after)
    diagnostics = {
        "schemaVersion": "phase36-residual-focused-repair-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "routeCountTarget": target_vehicle_count,
        "missingRequestIds": before_state.get("missingRequests"),
        "missingCountBefore": before_state.get("missingCount"),
        "bestMissingCountAfter": repair.get("bestMissingCountAfter"),
        "bestDuplicateCountAfter": repair.get("bestDuplicateCountAfter"),
        "exactTargetFeasibleAfter": bool(repair.get("exactTargetFeasibleAfter") or exact_sp_after.get("feasible")),
        "selectedSolutionFeasible": bool(selected_solution) and hard_violations == 0,
        "candidateColumnsContainingEachMissingRequest": context.get("candidateColumnsContainingEachMissingRequest"),
        "compatibleCandidateColumnsContainingMissingRequests": context.get("compatibleCandidateColumnsContainingMissingRequests"),
        "conflictingSelectedColumns": context.get("conflictingSelectedColumns"),
        "repairAttempts": repair.get("attempts"),
        "selectedColumnSources": details.get("selectedColumnSources"),
        "selectedColumnStages": details.get("selectedColumnStages"),
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "phase34ExactTargetFeasibleAfter": phase34.get("exactAfter", {}).get("feasible"),
        "phase35SeedMissingCountAfter": phase35_seed.get("bestMissingCountAfter"),
        "phase35SeedExactTargetFeasibleAfter": phase35_seed.get("exactTargetFeasibleAfter"),
        "hardResidualPrimaryBlocker": certificate.get("primaryBlocker"),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "phase36_residual_diagnostics.json", diagnostics)
    write_json(instance_dir / "phase36_repair_attempts.json", repair)
    write_json(instance_dir / "hard_residual_certificate.json", certificate)
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 36 Residual Focused Repair", "", "| Instance | Verdict | Missing Before | Missing After | Exact After | Blocker | Runtime ms |", "|---|---|---:|---:|---:|---|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('missingCountBefore')} | {row.get('bestMissingCountAfter')} | {row.get('exactTargetFeasibleAfter')} | {row.get('hardResidualPrimaryBlocker')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase36-residual-focused-repair-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase36_residual_focused_summary.json", summary)
    (output_dir / "phase36_residual_focused_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 36 residual focused repair diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE36 RESIDUAL FOCUSED REPAIR] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
