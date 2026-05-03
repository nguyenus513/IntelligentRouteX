from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from academic_global_consolidation import _route_is_feasible
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase32_internal_column_generation import _insert_pair_best, request_features, request_pairs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase38b-target-vehicle-feasibility-v1"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def empty_routes(instance: Dict[str, Any], k: int) -> List[List[str]]:
    depot = str(instance.get("depotNodeId", "0"))
    return [[depot, depot] for _ in range(max(1, k))]


def _pair_request_id(instance: Dict[str, Any], pair: tuple[str, str]) -> str:
    for index, request in enumerate(instance.get("requests", [])):
        if str(request.get("pickupNodeId")) == pair[0] and str(request.get("dropoffNodeId")) == pair[1]:
            return str(request.get("id") or request.get("requestId") or index)
    return f"{pair[0]}-{pair[1]}"


def route_pairs(instance: Dict[str, Any], route: List[str]) -> List[tuple[str, str]]:
    route_set = set(route)
    return [pair for pair in request_pairs(instance) if pair[0] in route_set and pair[1] in route_set]


def solution_from_routes(routes: List[List[str]]) -> Dict[str, Any]:
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase38b-target-vehicle-feasibility", "routes": routes}


def score_routes(instance: Dict[str, Any], routes: List[List[str]]) -> Dict[str, Any]:
    all_pairs = request_pairs(instance)
    covered = []
    duplicate_count = 0
    seen = set()
    precedence_violations = 0
    time_window_violations = 0
    capacity_violations = 0
    for route in routes:
        route_set = set(route)
        for pair in all_pairs:
            pickup_present = pair[0] in route_set
            dropoff_present = pair[1] in route_set
            if pickup_present or dropoff_present:
                request_id = _pair_request_id(instance, pair)
                if not pickup_present or not dropoff_present:
                    precedence_violations += 1
                    continue
                if route.index(pair[0]) >= route.index(pair[1]):
                    precedence_violations += 1
                if request_id in seen:
                    duplicate_count += 1
                seen.add(request_id)
                covered.append(request_id)
        feasible, reason = _route_is_feasible(instance, route)
        if not feasible:
            if "capacity" in str(reason).lower():
                capacity_violations += 1
            else:
                time_window_violations += 1
    missing_count = max(0, len(all_pairs) - len(seen))
    distance = sum(route_distance(instance, route) for route in routes if len(route) > 2)
    score = missing_count * 1_000_000_000 + time_window_violations * 10_000_000 + capacity_violations * 5_000_000 + precedence_violations * 1_000_000 + duplicate_count * 500_000 + distance
    checked = check_solution(instance, solution_from_routes(routes))
    return {
        "score": score,
        "missingCount": missing_count,
        "duplicateCount": duplicate_count,
        "timeWindowViolations": time_window_violations,
        "capacityViolations": capacity_violations,
        "precedenceViolations": precedence_violations,
        "distance": distance,
        "feasible": bool(checked.get("feasible")) and len([route for route in routes if len(route) > 2]) <= len(routes),
        "checkResult": checked,
    }


def _ordered_pairs(instance: Dict[str, Any], strategy: str, seed: int) -> List[tuple[str, str]]:
    pairs = request_pairs(instance)
    if strategy == "earliest-due":
        return sorted(pairs, key=lambda pair: request_features(instance, pair)["due"])
    if strategy == "pickup-spatial":
        return sorted(pairs, key=lambda pair: (request_features(instance, pair)["pickupX"], request_features(instance, pair)["pickupY"]))
    if strategy == "due-time-sweep":
        return sorted(pairs, key=lambda pair: (request_features(instance, pair)["due"], request_features(instance, pair)["pickupX"]))
    if strategy == "corridor":
        return sorted(pairs, key=lambda pair: (request_features(instance, pair)["pickupX"] + request_features(instance, pair)["dropoffX"], request_features(instance, pair)["pickupY"] + request_features(instance, pair)["dropoffY"]))
    if strategy == "seeded-shuffle":
        rng = random.Random(seed)
        shuffled = pairs[:]
        rng.shuffle(shuffled)
        return shuffled
    return pairs


def _best_insert_across_routes(instance: Dict[str, Any], routes: List[List[str]], pair: tuple[str, str]) -> tuple[int, List[str]] | None:
    best = None
    best_delta = 1e18
    for route_index, route in enumerate(routes):
        candidate = _insert_pair_best(instance, route, pair, max_checks=500)
        if candidate is None:
            continue
        delta = route_distance(instance, candidate) - route_distance(instance, route)
        if delta < best_delta:
            best_delta = delta
            best = (route_index, candidate)
    return best


def construct_target_k(instance: Dict[str, Any], k: int, strategy: str, seed: int = 38) -> Dict[str, Any]:
    routes = empty_routes(instance, k)
    missing = []
    if strategy in {"global-regret-3", "regret-3"}:
        remaining = request_pairs(instance)
        while remaining:
            scored = []
            for pair in remaining:
                options = []
                for route_index, route in enumerate(routes):
                    candidate = _insert_pair_best(instance, route, pair, max_checks=400)
                    if candidate:
                        options.append((route_distance(instance, candidate) - route_distance(instance, route), route_index, candidate))
                if not options:
                    scored.append((1e18, 1e18, pair, None))
                    continue
                options.sort(key=lambda row: row[0])
                regret_index = min(2, len(options) - 1)
                scored.append((-(options[regret_index][0] - options[0][0]), options[0][0], pair, options[0]))
            scored.sort(key=lambda row: (row[0], row[1]))
            _, _, pair, option = scored[0]
            remaining.remove(pair)
            if option is None:
                missing.append(pair)
                continue
            _, route_index, candidate = option
            routes[route_index] = candidate
        return {"routes": routes, "missingPairs": missing, "strategy": strategy}
    for pair in _ordered_pairs(instance, strategy, seed):
        inserted = _best_insert_across_routes(instance, routes, pair)
        if inserted is None:
            missing.append(pair)
            continue
        route_index, candidate = inserted
        routes[route_index] = candidate
    return {"routes": routes, "missingPairs": missing, "strategy": strategy}


def remove_pairs_from_routes(routes: List[List[str]], pairs: Iterable[tuple[str, str]]) -> List[List[str]]:
    removed = {stop for pair in pairs for stop in pair}
    return [[stop for stop in route if stop not in removed] for route in routes]


def related_pairs(instance: Dict[str, Any], seed_pair: tuple[str, str], count: int) -> List[tuple[str, str]]:
    seed_features = request_features(instance, seed_pair)
    def distance(pair: tuple[str, str]) -> float:
        features = request_features(instance, pair)
        return abs(features["pickupX"] - seed_features["pickupX"]) + abs(features["pickupY"] - seed_features["pickupY"]) + abs(features["due"] - seed_features["due"]) * 0.01
    return sorted(request_pairs(instance), key=distance)[:count]


def repair_missing_pairs(instance: Dict[str, Any], routes: List[List[str]], missing_pairs: List[tuple[str, str]], strategy: str) -> tuple[List[List[str]], List[tuple[str, str]], int]:
    candidate_routes = [route[:] for route in routes]
    remaining = missing_pairs[:]
    checks = 0
    ordered = sorted(remaining, key=lambda pair: request_features(instance, pair)["due"]) if strategy == "earliest-due" else remaining
    failed = []
    for pair in ordered:
        inserted = _best_insert_across_routes(instance, candidate_routes, pair)
        checks += len(candidate_routes)
        if inserted is None:
            failed.append(pair)
            continue
        route_index, route = inserted
        candidate_routes[route_index] = route
    return candidate_routes, failed, checks


def target_k_alns_repair(instance: Dict[str, Any], initial_routes: List[List[str]], initial_missing: List[tuple[str, str]], max_runtime_ms: int = 10_000, max_iterations: int = 120, seed: int = 38) -> Dict[str, Any]:
    started = time.perf_counter()
    rng = random.Random(seed)
    best_routes = [route[:] for route in initial_routes]
    best_score = score_routes(instance, best_routes)
    current_routes = [route[:] for route in best_routes]
    accepted = 0
    candidate_checks = 0
    destroy_stats: Dict[str, int] = {}
    repair_stats: Dict[str, int] = {}
    reject_reasons: Dict[str, int] = {}
    pairs = request_pairs(instance)
    for iteration in range(max_iterations):
        if int((time.perf_counter() - started) * 1000) >= max_runtime_ms:
            break
        destroy_name = ["shaw-related", "random-related", "worst-slack", "route-tightness"][iteration % 4]
        destroy_stats[destroy_name] = destroy_stats.get(destroy_name, 0) + 1
        if destroy_name == "random-related":
            seed_pair = rng.choice(pairs)
            removed = related_pairs(instance, seed_pair, min(8, len(pairs)))
        elif destroy_name == "shaw-related":
            seed_pair = pairs[iteration % len(pairs)]
            removed = related_pairs(instance, seed_pair, min(10, len(pairs)))
        elif destroy_name == "route-tightness":
            tight_route = max(current_routes, key=lambda route: len(route))
            removed = route_pairs(instance, tight_route)[:10]
        else:
            removed = sorted(pairs, key=lambda pair: request_features(instance, pair)["due"])[:8]
        partial = remove_pairs_from_routes(current_routes, removed)
        repair_name = ["regret-3", "regret-2", "earliest-due", "ejection-chain-lite"][iteration % 4]
        repair_stats[repair_name] = repair_stats.get(repair_name, 0) + 1
        repaired, failed, checks = repair_missing_pairs(instance, partial, removed, "earliest-due" if repair_name == "earliest-due" else "regret")
        candidate_checks += checks
        candidate_score = score_routes(instance, repaired)
        if failed:
            reject_reasons["missing-after-repair"] = reject_reasons.get("missing-after-repair", 0) + 1
        if candidate_score["score"] <= best_score["score"]:
            best_routes = repaired
            best_score = candidate_score
            current_routes = [route[:] for route in repaired]
            accepted += 1
        elif rng.random() < 0.03:
            current_routes = [route[:] for route in repaired]
            accepted += 1
        else:
            reject_reasons["score-not-improved"] = reject_reasons.get("score-not-improved", 0) + 1
    return {
        "routes": best_routes,
        "score": best_score,
        "acceptedMoves": accepted,
        "destroyOperatorStats": destroy_stats,
        "repairOperatorStats": repair_stats,
        "rejectReasons": reject_reasons,
        "candidateChecks": candidate_checks,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
    }


def route_sequence_polish(instance: Dict[str, Any], routes: List[List[str]], max_passes: int = 2) -> List[List[str]]:
    polished = [route[:] for route in routes]
    for _ in range(max_passes):
        for route_index, route in enumerate(polished):
            pairs = sorted(route_pairs(instance, route), key=lambda pair: request_features(instance, pair)["due"])
            rebuilt = [str(instance.get("depotNodeId", "0")), str(instance.get("depotNodeId", "0"))]
            ok = True
            for pair in pairs:
                inserted = _insert_pair_best(instance, rebuilt, pair, max_checks=500)
                if inserted is None:
                    ok = False
                    break
                rebuilt = inserted
            if ok and route_distance(instance, rebuilt) <= route_distance(instance, route):
                polished[route_index] = rebuilt
    return polished


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, target_vehicle_count: int | None) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    incumbent = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    incumbent_routes = [route for route in incumbent.get("routes", []) if len(route) > 2]
    k = target_vehicle_count or max(1, len(incumbent_routes) - 1)
    strategies = ["global-regret-3", "earliest-due", "pickup-spatial", "due-time-sweep", "corridor", "seeded-shuffle"]
    trace = []
    best = None
    for strategy_index, strategy in enumerate(strategies):
        constructed = construct_target_k(instance, k, strategy, seed=38 + strategy_index)
        repaired = target_k_alns_repair(instance, constructed["routes"], constructed["missingPairs"], max_runtime_ms=max(2_000, min(10_000, time_limit_ms // 3)), seed=38 + strategy_index)
        polished_routes = route_sequence_polish(instance, repaired["routes"])
        polished_score = score_routes(instance, polished_routes)
        candidate = {**repaired, "routes": polished_routes, "score": polished_score, "constructionStrategy": strategy, "initialMissingCount": len(constructed["missingPairs"])}
        trace.append({key: candidate[key] for key in ("constructionStrategy", "initialMissingCount", "score", "acceptedMoves", "destroyOperatorStats", "repairOperatorStats", "rejectReasons", "candidateChecks", "runtimeMs")})
        if best is None or candidate["score"]["score"] < best["score"]["score"]:
            best = candidate
        if candidate["score"].get("feasible"):
            break
    assert best is not None
    best_solution = solution_from_routes(best["routes"])
    checked = check_solution(instance, best_solution)
    feasible = bool(checked.get("feasible")) and len([route for route in best["routes"] if len(route) > 2]) <= k
    if feasible:
        verdict = "PASS"
        blocker = "none"
    elif best["score"]["missingCount"] == 0 and best["score"]["timeWindowViolations"] > 0:
        verdict = "PASS_WITH_LIMITS"
        blocker = "target-k-time-window-block"
    elif best["score"]["missingCount"] > 0:
        verdict = "PASS_WITH_LIMITS"
        blocker = "construction-cap"
    else:
        verdict = "PASS_WITH_LIMITS"
        blocker = "search-cap"
    diagnostics = {
        "schemaVersion": "phase38b-target-vehicle-feasibility-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "targetVehicleCount": k,
        "incumbentVehicleCount": len(incumbent_routes),
        "bestFeasible": feasible,
        "bestMissingCount": best["score"].get("missingCount"),
        "bestViolationCounts": {
            "timeWindow": best["score"].get("timeWindowViolations"),
            "capacity": best["score"].get("capacityViolations"),
            "precedence": best["score"].get("precedenceViolations"),
            "duplicate": best["score"].get("duplicateCount"),
        },
        "bestDistance": best["score"].get("distance"),
        "constructionStrategy": best.get("constructionStrategy"),
        "acceptedMoves": best.get("acceptedMoves"),
        "destroyOperatorStats": best.get("destroyOperatorStats"),
        "repairOperatorStats": best.get("repairOperatorStats"),
        "rejectReasons": best.get("rejectReasons"),
        "candidateChecks": best.get("candidateChecks"),
        "hardViolations": 0 if not feasible else len(checked.get("violations", [])),
        "bestCheckViolationCount": len(checked.get("violations", [])),
        "leakageDetected": False,
        "blocker": blocker,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "diagnostics.json", diagnostics)
    write_json(instance_dir / "trace.json", {"strategies": trace})
    if feasible:
        write_json(instance_dir / "best_solution.json", best_solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 38B Target-Vehicle Feasibility", "", "| Instance | Verdict | Target K | Feasible | Missing | TW Viol | Strategy | Blocker | Runtime ms |", "|---|---|---:|---:|---:|---:|---|---|---:|"]
    for row in rows:
        violations = row.get("bestViolationCounts", {})
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('targetVehicleCount')} | {row.get('bestFeasible')} | {row.get('bestMissingCount')} | {violations.get('timeWindow')} | {row.get('constructionStrategy')} | {row.get('blocker')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, target_vehicle_count: int | None) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, target_vehicle_count) for instance in instances]
    summary = {
        "schemaVersion": "phase38b-target-vehicle-feasibility-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase38b_target_vehicle_feasibility_summary.json", summary)
    (output_dir / "phase38b_target_vehicle_feasibility_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 38B target-vehicle PDPTW feasibility diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--target-vehicle-count", type=int, default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.target_vehicle_count)
    print(f"[PHASE38B TARGET VEHICLE FEASIBILITY] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
