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
from run_phase32_internal_column_generation import RouteColumnCollector, construct_route_from_pairs, generate_internal_columns, request_features, selected_column_details
from run_phase33_route_set_guided_generation import max_cover_packing
from run_phase34_missing_request_large_columns import run_phase34_generation
from run_phase35_residual_exact_cover_repair import coverage_state, residual_exact_cover_local_search, selected_columns_from_max_cover
from run_phase36_residual_focused_repair import hard_residual_certificate

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase37-conflict-guided-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _request_pair_by_id(instance: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    return {request_id: pair for pair, request_id in request_id_map(instance).items()}


def _pairs_for_ids(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[tuple[str, str]]:
    inverse = _request_pair_by_id(instance)
    return [inverse[request_id] for request_id in request_ids if request_id in inverse]


def _collect(collector: RouteColumnCollector, route: List[str], stage: str) -> PDPTWRouteColumn | None:
    before = len(collector.pool.columns)
    if not collector.collect(route, stage, failed_repair=True):
        return None
    columns = collector.pool.columns
    return columns[-1] if len(columns) > before else None


def columns_by_ids(columns: List[PDPTWRouteColumn], column_ids: Iterable[str]) -> List[PDPTWRouteColumn]:
    wanted = set(column_ids)
    return [column for column in columns if column.column_id in wanted and column.allowed_for_claim]


def conflict_analysis(selected: List[PDPTWRouteColumn], pool_columns: List[PDPTWRouteColumn], missing_ids: List[str]) -> List[Dict[str, Any]]:
    selected_sets = {column.column_id: set(column.request_ids) for column in selected}
    analyses: List[Dict[str, Any]] = []
    for candidate in pool_columns:
        if not candidate.allowed_for_claim or not (set(candidate.request_ids) & set(missing_ids)):
            continue
        blockers = []
        conflict_size = 0
        for selected_column in selected:
            overlap = set(candidate.request_ids) & selected_sets[selected_column.column_id]
            if overlap:
                blockers.append({"columnId": selected_column.column_id, "overlap": sorted(overlap), "overlapSize": len(overlap)})
                conflict_size += len(overlap)
        remaining = [column for column in selected if column.column_id not in {blocker["columnId"] for blocker in blockers}]
        remaining_used = set().union(*(set(column.request_ids) for column in remaining)) if remaining else set()
        analyses.append({
            "candidateColumnId": candidate.column_id,
            "candidateRequestIds": sorted(candidate.request_ids),
            "missingCovered": sorted(set(candidate.request_ids) & set(missing_ids)),
            "blockingSelectedColumns": blockers,
            "blockingSelectedColumnIds": [blocker["columnId"] for blocker in blockers],
            "conflictSize": conflict_size,
            "newCoverageGain": len(set(candidate.request_ids) & set(missing_ids)),
            "compatibilityWithRemaining": not (set(candidate.request_ids) & remaining_used),
        })
    analyses.sort(key=lambda row: (-row["newCoverageGain"], row["conflictSize"], len(row["blockingSelectedColumnIds"])))
    return analyses


def _construct_route(instance: Dict[str, Any], request_ids: Iterable[str]) -> List[str] | None:
    pairs = _pairs_for_ids(instance, request_ids)
    if not pairs:
        return None
    for strategy in ("regret-3", "regret-2", "earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle"):
        route = construct_route_from_pairs(instance, pairs, strategy, seed=37 + len(pairs))
        if route:
            return route
    return None


def _feature_sort_key(instance: Dict[str, Any], request_id: str, mode: str) -> tuple[float, float]:
    pair = _request_pair_by_id(instance)[request_id]
    features = request_features(instance, pair)
    if mode == "due-time":
        return (features["due"], features["ready"])
    if mode == "pickup-x":
        return (features["pickupX"], features["pickupY"])
    if mode == "corridor":
        return (features["pickupX"] + features["dropoffX"], features["pickupY"] + features["dropoffY"])
    return (features["ready"], features["due"])


def generate_replacement_columns(instance: Dict[str, Any], collector: RouteColumnCollector, residual_ids: List[str], route_slots: int, max_columns: int = 80) -> int:
    generated = 0
    if route_slots <= 0 or not residual_ids:
        return 0
    if route_slots == 1:
        route = _construct_route(instance, residual_ids)
        return 1 if route and _collect(collector, route, "phase37-generated-replacement") else 0
    for mode in ("due-time", "pickup-x", "corridor", "ready"):
        ordered = sorted(residual_ids, key=lambda request_id: _feature_sort_key(instance, request_id, mode))
        chunk_size = max(1, (len(ordered) + route_slots - 1) // route_slots)
        chunks = [ordered[index:index + chunk_size] for index in range(0, len(ordered), chunk_size)]
        if len(chunks) > route_slots:
            chunks[route_slots - 1:] = [sum(chunks[route_slots - 1:], [])]
        for chunk in chunks[:route_slots]:
            route = _construct_route(instance, chunk)
            if route and _collect(collector, route, "phase37-generated-replacement"):
                generated += 1
                if generated >= max_columns:
                    return generated
    midpoint = len(residual_ids) // 2
    balanced_sizes = sorted(set([max(1, midpoint - 1), midpoint, min(len(residual_ids) - 1, midpoint + 1)]))
    for split_size in balanced_sizes:
        for left_ids in itertools.combinations(residual_ids, split_size):
            right_ids = [request_id for request_id in residual_ids if request_id not in set(left_ids)]
            for chunk in (list(left_ids), right_ids):
                route = _construct_route(instance, chunk)
                if route and _collect(collector, route, "phase37-generated-replacement"):
                    generated += 1
                    if generated >= max_columns:
                        return generated
            break
    return generated


def solve_residual_subproblem(instance: Dict[str, Any], fixed_columns: List[PDPTWRouteColumn], candidate_columns: List[PDPTWRouteColumn], residual_ids: List[str], route_slots: int, time_limit_ms: int = 2_000) -> Dict[str, Any]:
    try:
        from ortools.sat.python import cp_model
    except Exception as exception:
        return {"status": "unavailable", "reason": f"ortools-cp-sat-unavailable:{exception}", "feasible": False}
    fixed_used = set().union(*(set(column.request_ids) for column in fixed_columns)) if fixed_columns else set()
    residual_set = set(residual_ids)
    eligible = []
    seen = set()
    for column in candidate_columns:
        column_set = set(column.request_ids)
        if not column.allowed_for_claim or column_set & fixed_used or not column_set <= residual_set or not column_set:
            continue
        key = tuple(sorted(column.request_ids))
        if key in seen:
            continue
        seen.add(key)
        eligible.append(column)
    if route_slots <= 0 or not residual_ids:
        return {"status": "infeasible", "reason": "empty-residual-or-no-slots", "feasible": False, "eligibleColumnCount": len(eligible)}
    if not eligible:
        return {"status": "infeasible", "reason": "candidate-pool-missing", "feasible": False, "eligibleColumnCount": 0}
    model = cp_model.CpModel()
    x = [model.NewBoolVar(column.column_id) for column in eligible]
    for request_id in sorted(residual_set):
        covering = [x[index] for index, column in enumerate(eligible) if request_id in column.request_ids]
        if not covering:
            return {"status": "infeasible", "reason": "candidate-pool-missing", "missingResidualRequest": request_id, "feasible": False, "eligibleColumnCount": len(eligible)}
        model.Add(sum(covering) == 1)
    model.Add(sum(x) == route_slots)
    distance_terms = [int(round(column.distance * 1000)) * x[index] for index, column in enumerate(eligible)]
    balance_terms = [abs(len(column.request_ids) - max(1, len(residual_ids) // route_slots)) * x[index] for index, column in enumerate(eligible)]
    model.Minimize(sum(distance_terms) + 1000 * sum(balance_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, time_limit_ms / 1000.0)
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return {"status": solver.StatusName(status).lower(), "reason": "residual-subproblem-infeasible", "feasible": False, "eligibleColumnCount": len(eligible)}
    selected = [eligible[index] for index, var in enumerate(x) if solver.Value(var) == 1]
    return {"status": solver.StatusName(status).lower(), "feasible": True, "selectedColumnIds": [column.column_id for column in selected], "selectedColumns": selected, "eligibleColumnCount": len(eligible)}


def blocking_set_replacement_search(instance: Dict[str, Any], collector: RouteColumnCollector, selected: List[PDPTWRouteColumn], missing_ids: List[str], target_vehicle_count: int, max_attempts: int = 20) -> Dict[str, Any]:
    analyses = conflict_analysis(selected, collector.pool.columns, missing_ids)
    all_ids = set(request_id_map(instance).values())
    attempts = []
    generated_total = 0
    for analysis in analyses[:max_attempts]:
        blocker_ids = set(analysis["blockingSelectedColumnIds"])
        fixed = [column for column in selected if column.column_id not in blocker_ids]
        fixed_used = set().union(*(set(column.request_ids) for column in fixed)) if fixed else set()
        residual_ids = sorted(all_ids - fixed_used)
        route_slots = target_vehicle_count - len(fixed)
        generated = generate_replacement_columns(instance, collector, residual_ids, route_slots, max_columns=40)
        generated_total += generated
        candidate_columns = [column for column in collector.pool.columns if set(column.request_ids) & set(residual_ids)]
        result = solve_residual_subproblem(instance, fixed, candidate_columns, residual_ids, route_slots)
        attempts.append({
            "candidateColumnId": analysis["candidateColumnId"],
            "blockingSelectedColumnIds": sorted(blocker_ids),
            "blockingSetSize": len(blocker_ids),
            "residualRequestCount": len(residual_ids),
            "routeSlotsRemaining": route_slots,
            "generatedReplacementColumns": generated,
            "localSubproblemStatus": result.get("status"),
            "localSubproblemReason": result.get("reason"),
            "eligibleColumnCount": result.get("eligibleColumnCount"),
        })
        if result.get("feasible"):
            replacement = result["selectedColumns"]
            solution_columns = fixed + replacement
            solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase37-conflict-guided-replacement", "routes": [column.route for column in solution_columns]}
            checked = check_solution(instance, solution)
            if checked.get("feasible") and coverage_state(instance, solution_columns)["missingCount"] == 0 and coverage_state(instance, solution_columns)["duplicateCount"] == 0:
                return {"feasible": True, "attempts": attempts, "generatedReplacementColumns": generated_total, "solutionColumns": solution_columns, "solution": solution, "checkResult": checked, "blockerAfter": "none"}
    blocker = "candidate-pool-missing"
    if attempts and all(attempt.get("localSubproblemReason") == "residual-subproblem-infeasible" for attempt in attempts if attempt.get("localSubproblemReason")):
        blocker = "residual-subproblem-infeasible"
    elif generated_total == 0:
        blocker = "route-construction-time-window-block"
    return {"feasible": False, "attempts": attempts, "generatedReplacementColumns": generated_total, "solutionColumns": [], "solution": None, "checkResult": {"feasible": False}, "blockerAfter": blocker}


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    collector, phase32_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    target_vehicle_count = max(1, len([route for route in solution.get("routes", []) if len(route) > 2]) - 1)
    phase34 = run_phase34_generation(instance, collector, target_vehicle_count)
    max_cover = max_cover_packing(instance, collector.pool.columns, target_vehicle_count)
    seed_selected = selected_columns_from_max_cover(collector.pool.columns, max_cover)
    phase35_seed = residual_exact_cover_local_search(instance, collector, seed_selected, target_vehicle_count, max_runtime_ms=24_000) if seed_selected else {}
    selected = columns_by_ids(collector.pool.columns, phase35_seed.get("bestSelectedColumnIds", [])) or seed_selected
    before_state = coverage_state(instance, selected)
    certificate = hard_residual_certificate(instance, selected, collector.pool.columns)
    exact_before = PDPTWSetPartitioningSolver(time_limit_ms=2_000).solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    replacement = blocking_set_replacement_search(instance, collector, selected, before_state.get("missingRequests", []), target_vehicle_count)
    exact_after = PDPTWSetPartitioningSolver(time_limit_ms=2_000).solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    selected_solution = replacement.get("solution") or (exact_after.get("solution") if exact_after.get("feasible") else None)
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    if leakage or hard_violations:
        verdict = "FAIL"
    elif replacement.get("feasible") or exact_after.get("feasible"):
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    details = selected_column_details(collector.pool, exact_after)
    diagnostics = {
        "schemaVersion": "phase37-conflict-guided-replacement-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "routeCountTarget": target_vehicle_count,
        "missingRequestIds": before_state.get("missingRequests"),
        "candidateColumnsContainingMissing": certificate.get("candidateColumnsContainingEachMissingRequest"),
        "conflictColumnsByMissingRequest": certificate.get("conflictingSelectedColumns"),
        "blockingSetAttempts": len(replacement.get("attempts", [])),
        "blockingSetSizes": [attempt.get("blockingSetSize") for attempt in replacement.get("attempts", [])],
        "residualRequestCounts": [attempt.get("residualRequestCount") for attempt in replacement.get("attempts", [])],
        "routeSlotsRemaining": [attempt.get("routeSlotsRemaining") for attempt in replacement.get("attempts", [])],
        "generatedReplacementColumns": replacement.get("generatedReplacementColumns"),
        "localSubproblemStatus": [attempt.get("localSubproblemStatus") for attempt in replacement.get("attempts", [])],
        "exactTargetFeasibleBefore": bool(exact_before.get("feasible")),
        "exactTargetFeasibleAfter": bool(replacement.get("feasible") or exact_after.get("feasible")),
        "selectedSolutionFeasible": bool(selected_solution) and hard_violations == 0,
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "blockerBefore": certificate.get("primaryBlocker"),
        "blockerAfter": replacement.get("blockerAfter"),
        "phase32StageCounts": phase32_diag.get("stageCounts"),
        "phase34ExactTargetFeasibleAfter": phase34.get("exactAfter", {}).get("feasible"),
        "phase35SeedMissingCountAfter": phase35_seed.get("bestMissingCountAfter"),
        "selectedColumnSources": details.get("selectedColumnSources"),
        "selectedColumnStages": details.get("selectedColumnStages"),
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "phase37_conflict_diagnostics.json", diagnostics)
    write_json(instance_dir / "phase37_replacement_attempts.json", replacement)
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 37 Conflict-Guided Replacement", "", "| Instance | Verdict | Exact Before | Exact After | Blocker Before | Blocker After | Attempts | Runtime ms |", "|---|---|---:|---:|---|---|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('exactTargetFeasibleBefore')} | {row.get('exactTargetFeasibleAfter')} | {row.get('blockerBefore')} | {row.get('blockerAfter')} | {row.get('blockingSetAttempts')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase37-conflict-guided-replacement-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase37_conflict_guided_summary.json", summary)
    (output_dir / "phase37_conflict_guided_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 37 conflict-guided residual replacement diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE37 CONFLICT GUIDED REPLACEMENT] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
