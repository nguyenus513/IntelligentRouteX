from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from academic_global_consolidation import _route_is_feasible
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRoutePool, PDPTWSetPartitioningSolver, request_id_map

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase32-internal-column-generation-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def request_pairs(instance: Dict[str, Any]) -> List[tuple[str, str]]:
    return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]


def pairs_in_route(route: List[str], pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
    route_set = set(route)
    return [(pickup, dropoff) for pickup, dropoff in pairs if pickup in route_set and dropoff in route_set]


def route_without_pairs(route: List[str], pairs: List[tuple[str, str]]) -> List[str]:
    removed = {stop for pair in pairs for stop in pair}
    return [stop for stop in route if stop not in removed]


def request_set_key(route: List[str], instance: Dict[str, Any]) -> tuple[str, ...]:
    route_set = set(route)
    ids = []
    for pair, request_id in request_id_map(instance).items():
        if pair[0] in route_set and pair[1] in route_set:
            ids.append(request_id)
    return tuple(sorted(ids))


def request_set_diversity_stats(pool: PDPTWRoutePool) -> Dict[str, Any]:
    keys = [tuple(sorted(column.request_ids)) for column in pool.columns]
    unique_keys = set(keys)
    histogram: Dict[str, int] = {}
    for key in keys:
        size = str(len(key))
        histogram[size] = histogram.get(size, 0) + 1
    jaccards = []
    for left_index in range(len(keys)):
        left = set(keys[left_index])
        for right_index in range(left_index + 1, len(keys)):
            right = set(keys[right_index])
            union = left | right
            if union:
                jaccards.append(len(left & right) / len(union))
    return {
        "uniqueRequestSetCount": len(unique_keys),
        "duplicateRequestSetCount": len(keys) - len(unique_keys),
        "requestSetSizeHistogram": histogram,
        "pairwiseJaccardMedian": statistics.median(jaccards) if jaccards else None,
    }


def request_features(instance: Dict[str, Any], pair: tuple[str, str]) -> Dict[str, float]:
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
    pickup = nodes[pair[0]]
    dropoff = nodes[pair[1]]
    return {
        "pickupX": float(pickup.get("x", 0.0)),
        "pickupY": float(pickup.get("y", 0.0)),
        "dropoffX": float(dropoff.get("x", 0.0)),
        "dropoffY": float(dropoff.get("y", 0.0)),
        "ready": float(pickup.get("readyTime", 0.0)),
        "due": float(dropoff.get("dueTime", 0.0)),
    }


def relatedness(instance: Dict[str, Any], left: tuple[str, str], right: tuple[str, str]) -> float:
    a = request_features(instance, left)
    b = request_features(instance, right)
    pickup_distance = ((a["pickupX"] - b["pickupX"]) ** 2 + (a["pickupY"] - b["pickupY"]) ** 2) ** 0.5
    dropoff_distance = ((a["dropoffX"] - b["dropoffX"]) ** 2 + (a["dropoffY"] - b["dropoffY"]) ** 2) ** 0.5
    time_gap = 0.01 * (abs(a["ready"] - b["ready"]) + abs(a["due"] - b["due"]))
    return pickup_distance + dropoff_distance + time_gap


class RouteColumnCollector:
    def __init__(self, instance: Dict[str, Any], source_run_id: str = "phase32-internal") -> None:
        self.pool = PDPTWRoutePool(instance)
        self._instance = instance
        self._source_run_id = source_run_id
        self.stage_counts: Dict[str, int] = {}
        self.harvested_from_failed_repairs = 0

    def collect(self, route: List[str], stage: str, source: str | None = None, failed_repair: bool = False) -> bool:
        source = source or stage
        accepted = self.pool.add_route(
            [str(stop) for stop in route],
            source=source,
            source_solver="our-dispatch-v2",
            source_run_id=self._source_run_id,
            provenance="internal",
            allowed_for_claim=True,
        )
        if accepted:
            self.stage_counts[stage] = self.stage_counts.get(stage, 0) + 1
            if failed_repair:
                self.harvested_from_failed_repairs += 1
        return accepted

    def collect_solution(self, solution: Dict[str, Any], stage: str) -> None:
        for route in solution.get("routes", []):
            if len(route) > 2:
                self.collect([str(stop) for stop in route], stage)


def _insert_pair_best(instance: Dict[str, Any], route: List[str], pair: tuple[str, str], max_checks: int) -> List[str] | None:
    pickup, dropoff = pair
    best_route = None
    best_distance = 1e18
    checks = 0
    for pickup_pos in range(1, len(route)):
        for dropoff_pos in range(pickup_pos, len(route)):
            if checks >= max_checks:
                return best_route
            candidate = route[:pickup_pos] + [pickup] + route[pickup_pos:dropoff_pos] + [dropoff] + route[dropoff_pos:]
            checks += 1
            if not _route_is_feasible(instance, candidate)[0]:
                continue
            distance = route_distance(instance, candidate)
            if distance < best_distance:
                best_distance = distance
                best_route = candidate
    return best_route


def route_variants(instance: Dict[str, Any], route: List[str], max_variants: int = 80) -> List[List[str]]:
    variants: List[List[str]] = []
    pairs = pairs_in_route(route, request_pairs(instance))
    for pair in pairs:
        reduced = route_without_pairs(route, [pair])
        candidate = _insert_pair_best(instance, reduced, pair, max_checks=120)
        if candidate and candidate != route:
            variants.append(candidate)
        if len(variants) >= max_variants:
            return variants
    for left_index in range(len(pairs)):
        for right_index in range(left_index + 1, len(pairs)):
            pair_a = pairs[left_index]
            pair_b = pairs[right_index]
            swapped = route[:]
            positions = {stop: swapped.index(stop) for stop in [*pair_a, *pair_b] if stop in swapped}
            if len(positions) != 4:
                continue
            for stop_a, stop_b in [(pair_a[0], pair_b[0]), (pair_a[1], pair_b[1])]:
                swapped[positions[stop_a]], swapped[positions[stop_b]] = swapped[positions[stop_b]], swapped[positions[stop_a]]
            if _route_is_feasible(instance, swapped)[0]:
                variants.append(swapped)
            if len(variants) >= max_variants:
                return variants
    return variants


def split_merge_variants(instance: Dict[str, Any], route_a: List[str], route_b: List[str], max_pairs: int = 3) -> List[List[str]]:
    variants: List[List[str]] = []
    pairs_a = pairs_in_route(route_a, request_pairs(instance))[:max_pairs]
    pairs_b = pairs_in_route(route_b, request_pairs(instance))[:max_pairs]
    for moved_pairs, source_route, target_route in [(pairs_a, route_a, route_b), (pairs_b, route_b, route_a)]:
        for pair in moved_pairs:
            reduced = route_without_pairs(source_route, [pair])
            expanded = _insert_pair_best(instance, target_route, pair, max_checks=160)
            if len(reduced) > 2 and _route_is_feasible(instance, reduced)[0]:
                variants.append(reduced)
            if expanded and _route_is_feasible(instance, expanded)[0]:
                variants.append(expanded)
    return variants


def subset_route_columns(instance: Dict[str, Any], route: List[str], max_columns: int = 80, max_pairs_per_route: int = 14) -> List[List[str]]:
    variants: List[List[str]] = []
    pairs = pairs_in_route(route, request_pairs(instance))
    if len(pairs) < 2:
        return variants
    for size in range(2, min(max_pairs_per_route, len(pairs)) + 1):
        for offset in range(0, len(pairs) - size + 1):
            selected = set(pairs[offset:offset + size])
            selected_stops = {stop for pair in selected for stop in pair}
            candidate = [stop for stop in route if stop == route[0] or stop == route[-1] or stop in selected_stops]
            if len(candidate) > 2 and _route_is_feasible(instance, candidate)[0]:
                variants.append(candidate)
                if len(variants) >= max_columns:
                    return variants
    return variants


def construct_route_from_pairs(instance: Dict[str, Any], pairs: List[tuple[str, str]], strategy: str, seed: int = 31) -> List[str] | None:
    depot = str(instance.get("depotNodeId", "0"))
    ordered = pairs[:]
    if strategy in {"regret-2", "regret-3"}:
        route = [depot, depot]
        remaining = ordered[:]
        while remaining:
            scored = []
            for pair in remaining:
                options = []
                pickup, dropoff = pair
                checks = 0
                for pickup_pos in range(1, len(route)):
                    for dropoff_pos in range(pickup_pos, len(route)):
                        if checks >= 300:
                            break
                        candidate = route[:pickup_pos] + [pickup] + route[pickup_pos:dropoff_pos] + [dropoff] + route[dropoff_pos:]
                        checks += 1
                        if _route_is_feasible(instance, candidate)[0]:
                            options.append((route_distance(instance, candidate), candidate))
                    if checks >= 300:
                        break
                if not options:
                    return None
                options.sort(key=lambda row: row[0])
                regret_index = min(len(options) - 1, 1 if strategy == "regret-2" else 2)
                regret = options[regret_index][0] - options[0][0]
                scored.append((-regret, options[0][0], pair, options[0][1]))
            scored.sort(key=lambda row: (row[0], row[1]))
            _, _, selected_pair, route = scored[0]
            remaining.remove(selected_pair)
        return route if _route_is_feasible(instance, route)[0] else None
    if strategy == "earliest-due":
        ordered.sort(key=lambda pair: request_features(instance, pair)["due"])
    elif strategy == "ready-time":
        ordered.sort(key=lambda pair: request_features(instance, pair)["ready"])
    elif strategy == "nearest-pickup":
        ordered.sort(key=lambda pair: (request_features(instance, pair)["pickupX"], request_features(instance, pair)["pickupY"]))
    elif strategy == "seeded-shuffle":
        rng = random.Random(seed)
        rng.shuffle(ordered)
    route = [depot, depot]
    for pair in ordered:
        inserted = _insert_pair_best(instance, route, pair, max_checks=300)
        if inserted is None:
            return None
        route = inserted
    return route if _route_is_feasible(instance, route)[0] else None


def cluster_route_columns(instance: Dict[str, Any], collector: RouteColumnCollector, max_columns: int = 160, max_pairs_per_route: int = 14, related_k: int = 28, seed: int = 31, started: float | None = None, max_runtime_ms: int = 8_000) -> int:
    started = started or time.perf_counter()
    generated = 0
    pairs = request_pairs(instance)
    existing_sets = {tuple(sorted(column.request_ids)) for column in collector.pool.columns}
    strategies = ["earliest-due", "ready-time", "nearest-pickup", "seeded-shuffle"]
    for seed_index, seed_pair in enumerate(pairs):
        if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
            return generated
        related = sorted(pairs, key=lambda pair: relatedness(instance, seed_pair, pair))[:related_k]
        for size in range(2, min(max_pairs_per_route, len(related)) + 1):
            if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
                return generated
            candidate_pairs = related[:size]
            for strategy in strategies:
                if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
                    return generated
                route = construct_route_from_pairs(instance, candidate_pairs, strategy, seed + seed_index + size)
                if route is None:
                    continue
                key = request_set_key(route, instance)
                if key in existing_sets:
                    continue
                if collector.collect(route, "cluster-route"):
                    existing_sets.add(key)
                    generated += 1
                    if generated >= max_columns:
                        return generated
    return generated


def weak_route_replacement_columns(instance: Dict[str, Any], solution: Dict[str, Any], collector: RouteColumnCollector, target_vehicle_count: int, max_columns: int = 80, started: float | None = None, max_runtime_ms: int = 8_000) -> int:
    started = started or time.perf_counter()
    generated = 0
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    all_pairs = request_pairs(instance)
    total_requests = len(all_pairs)
    target_size = max(2, min(16, (total_requests + max(1, target_vehicle_count) - 1) // max(1, target_vehicle_count)))
    existing_sets = {tuple(sorted(column.request_ids)) for column in collector.pool.columns}
    for route in sorted(routes, key=lambda candidate: len(pairs_in_route(candidate, all_pairs))):
        if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
            return generated
        route_pairs = pairs_in_route(route, all_pairs)
        if not route_pairs:
            continue
        neighbors = sorted(all_pairs, key=lambda pair: min(relatedness(instance, pair, base) for base in route_pairs))
        for size in range(max(2, target_size - 2), min(len(neighbors), target_size + 3) + 1):
            if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
                return generated
            for offset in range(0, min(8, len(neighbors) - size + 1)):
                if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
                    return generated
                candidate_pairs = neighbors[offset:offset + size]
                route_candidate = construct_route_from_pairs(instance, candidate_pairs, "earliest-due") or construct_route_from_pairs(instance, candidate_pairs, "ready-time")
                if route_candidate is None:
                    continue
                key = request_set_key(route_candidate, instance)
                if key in existing_sets:
                    continue
                if collector.collect(route_candidate, "weak-route-replacement", failed_repair=True):
                    existing_sets.add(key)
                    generated += 1
                    if generated >= max_columns:
                        return generated
    return generated


def generate_internal_columns(instance: Dict[str, Any], solution: Dict[str, Any], budget_ms: int = 8_000, max_variants_per_route: int = 80) -> tuple[RouteColumnCollector, Dict[str, Any]]:
    started = time.perf_counter()
    collector = RouteColumnCollector(instance)
    collector.collect_solution(solution, "incumbent")
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    for route in routes:
        if int((time.perf_counter() - started) * 1000) >= budget_ms:
            break
        for variant in route_variants(instance, route, max_variants=max_variants_per_route):
            collector.collect(variant, "route-variant")
        for variant in subset_route_columns(instance, route, max_columns=120, max_pairs_per_route=14):
            collector.collect(variant, "request-subset")
    for left_index in range(len(routes)):
        if int((time.perf_counter() - started) * 1000) >= budget_ms:
            break
        for right_index in range(left_index + 1, min(len(routes), left_index + 5)):
            for variant in split_merge_variants(instance, routes[left_index], routes[right_index]):
                collector.collect(variant, "neighbor-split-merge", failed_repair=True)
    cluster_generated = 0
    weak_replacement_generated = 0
    if int((time.perf_counter() - started) * 1000) < budget_ms:
        cluster_generated = cluster_route_columns(instance, collector, max_columns=160, max_pairs_per_route=14, related_k=28, started=started, max_runtime_ms=budget_ms)
    if int((time.perf_counter() - started) * 1000) < budget_ms:
        target_vehicle_count = max(1, len(routes) - 1)
        weak_replacement_generated = weak_route_replacement_columns(instance, solution, collector, target_vehicle_count, started=started, max_runtime_ms=budget_ms)
    diagnostics = {
        "columnGenerationRuntimeMs": int((time.perf_counter() - started) * 1000),
        "stageCounts": collector.stage_counts,
        "harvestedFromFailedRepairs": collector.harvested_from_failed_repairs,
        "clusterColumnsGenerated": cluster_generated,
        "weakRouteReplacementColumnsGenerated": weak_replacement_generated,
    }
    return collector, diagnostics


def selected_column_details(pool: PDPTWRoutePool, result: Dict[str, Any]) -> Dict[str, Any]:
    selected = set(result.get("selectedColumnIds", []))
    columns = [column for column in pool.columns if column.column_id in selected]
    return {
        "selectedColumnSources": [column.source for column in columns],
        "selectedColumnStages": [column.source for column in columns],
        "selectedAllowedForClaim": [column.allowed_for_claim for column in columns],
    }


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    before_collector = RouteColumnCollector(instance, "phase32-before")
    before_collector.collect_solution(solution, "incumbent")
    before_stats = before_collector.pool.stats()
    before_diversity = request_set_diversity_stats(before_collector.pool)
    incumbent_vehicle_count = len([route for route in solution.get("routes", []) if len(route) > 2])
    target_vehicle_count = max(1, incumbent_vehicle_count - 1)
    solver = PDPTWSetPartitioningSolver(time_limit_ms=2_000)
    before_sp = solver.solve(instance, before_collector.pool.columns, target_vehicle_count=target_vehicle_count)
    collector, generation_diag = generate_internal_columns(instance, solution, budget_ms=8_000)
    after_stats = collector.pool.stats()
    after_diversity = request_set_diversity_stats(collector.pool)
    after_sp = solver.solve(instance, collector.pool.columns, target_vehicle_count=target_vehicle_count)
    selected_solution = after_sp.get("solution") if after_sp.get("feasible") else None
    hard_violations = len(check_solution(instance, selected_solution).get("violations", [])) if selected_solution else 0
    leakage = any(not column.allowed_for_claim for column in collector.pool.columns)
    if leakage or after_stats.get("uncoveredRequests"):
        verdict = "FAIL"
    elif after_sp.get("feasible") and hard_violations == 0:
        verdict = "PASS"
    elif after_stats.get("columnCount", 0) >= 100 and after_diversity.get("uniqueRequestSetCount", 0) > before_diversity.get("uniqueRequestSetCount", 0) and hard_violations == 0:
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "FAIL"
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "internal_route_pool.json", collector.pool.to_dict())
    write_json(instance_dir / "sp_result.json", {"before": before_sp, "after": after_sp})
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    details = selected_column_details(collector.pool, after_sp)
    diagnostics = {
        "schemaVersion": "phase32-internal-column-generation-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "internalColumnCountBefore": before_stats.get("columnCount"),
        "internalColumnCountAfter": after_stats.get("columnCount"),
        "sourceCounts": after_stats.get("sourceCounts"),
        "stageCounts": generation_diag.get("stageCounts"),
        "uniqueRequestSetCountBefore": before_diversity.get("uniqueRequestSetCount"),
        "uniqueRequestSetCountAfter": after_diversity.get("uniqueRequestSetCount"),
        "duplicateRequestSetCountAfter": after_diversity.get("duplicateRequestSetCount"),
        "requestSetSizeHistogramAfter": after_diversity.get("requestSetSizeHistogram"),
        "pairwiseJaccardMedianAfter": after_diversity.get("pairwiseJaccardMedian"),
        "requestCoverageMinBefore": before_stats.get("requestCoverageMin"),
        "requestCoverageMedianBefore": before_stats.get("requestCoverageMedian"),
        "requestCoverageMaxBefore": before_stats.get("requestCoverageMax"),
        "requestCoverageMinAfter": after_stats.get("requestCoverageMin"),
        "requestCoverageMedianAfter": after_stats.get("requestCoverageMedian"),
        "requestCoverageMaxAfter": after_stats.get("requestCoverageMax"),
        "uncoveredRequests": after_stats.get("uncoveredRequests"),
        "duplicateRouteCount": after_stats.get("duplicateRouteCount"),
        "harvestedFromFailedRepairs": generation_diag.get("harvestedFromFailedRepairs"),
        "clusterColumnsGenerated": generation_diag.get("clusterColumnsGenerated"),
        "weakRouteReplacementColumnsGenerated": generation_diag.get("weakRouteReplacementColumnsGenerated"),
        "spTargetFeasibleBefore": bool(before_sp.get("feasible")),
        "spTargetFeasibleAfter": bool(after_sp.get("feasible")),
        "selectedColumnSources": details.get("selectedColumnSources"),
        "selectedColumnStages": details.get("selectedColumnStages"),
        "hardViolationCount": hard_violations,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "columnGenerationRuntimeMs": generation_diag.get("columnGenerationRuntimeMs"),
        "targetVehicleCount": target_vehicle_count,
        "verdict": verdict,
    }
    write_json(instance_dir / "diagnostics.json", diagnostics)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 32 Internal Column Generation", "", "| Instance | Verdict | Columns Before | Columns After | Unique Sets | Coverage Min | SP Target After | Runtime ms |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('internalColumnCountBefore')} | {row.get('internalColumnCountAfter')} | {row.get('uniqueRequestSetCountAfter')} | {row.get('requestCoverageMinAfter')} | {row.get('spTargetFeasibleAfter')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase32-internal-column-generation-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase32_internal_column_generation_summary.json", summary)
    (output_dir / "phase32_internal_column_generation_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 32 internal PDPTW column generation.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE32 INTERNAL COLUMN GENERATION] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
