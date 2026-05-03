from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from academic_global_consolidation import GlobalRouteConsolidator, PairAwareRouteEliminationOperator, PairEjectionChainOperator
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, ortools_baseline_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase31_pdptw_route_pool_sp import PDPTWRoutePool, PDPTWSetPartitioningSolver
from run_phase32_internal_column_generation import RouteColumnCollector, _insert_pair_best, generate_internal_columns, request_features, request_pairs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase40-natural-pdptw-optimizer-v1"


@dataclass(frozen=True)
class NaturalPDPTWObjectiveConfig:
    mode: str
    hard_infeasibility_penalty: float
    vehicle_fixed_cost: float
    distance_weight: float
    slack_penalty_weight: float
    route_duration_penalty_weight: float
    load_risk_penalty_weight: float
    tail_penalty_weight: float


def objective_config(mode: str) -> NaturalPDPTWObjectiveConfig:
    if mode == "production_food_dispatch":
        return NaturalPDPTWObjectiveConfig(mode, 1_000_000_000.0, 1_500.0, 1.0, 4.0, 2.5, 20.0, 30.0)
    return NaturalPDPTWObjectiveConfig(mode, 1_000_000_000.0, 10_000_000.0, 1.0, 0.2, 0.1, 5.0, 0.0)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def route_request_pairs(instance: Dict[str, Any], route: List[str]) -> List[tuple[str, str]]:
    route_set = set(route)
    return [pair for pair in request_pairs(instance) if pair[0] in route_set and pair[1] in route_set]


def evaluate_route_state(instance: Dict[str, Any], route: List[str]) -> Dict[str, Any]:
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    capacity = float(instance.get("vehicleCapacity", instance.get("capacity", 10_000)))
    time = 0.0
    load = 0.0
    min_slack = 1e18
    max_load_ratio = 0.0
    feasible = True
    previous = None
    for stop in route:
        node = nodes.get(str(stop), {})
        if previous is not None:
            prev = nodes.get(str(previous), {})
            time += ((float(prev.get("x", 0.0)) - float(node.get("x", 0.0))) ** 2 + (float(prev.get("y", 0.0)) - float(node.get("y", 0.0))) ** 2) ** 0.5
        ready = float(node.get("readyTime", 0.0))
        due = float(node.get("dueTime", 1e9))
        if time < ready:
            time = ready
        slack = due - time
        min_slack = min(min_slack, slack)
        if slack < 0:
            feasible = False
        load += float(node.get("demand", 0.0))
        if load < -1e-9 or load - capacity > 1e-9:
            feasible = False
        max_load_ratio = max(max_load_ratio, load / max(1.0, capacity))
        time += float(node.get("serviceTime", 0.0))
        previous = stop
    return {
        "feasible": feasible,
        "requestCount": len(route_request_pairs(instance, route)),
        "distance": route_distance(instance, route) if len(route) > 2 else 0.0,
        "routeDuration": time,
        "minSlack": min_slack if min_slack < 1e18 else 0.0,
        "slackRisk": max(0.0, -min_slack) + max(0.0, 30.0 - min_slack) * 0.01,
        "loadRisk": max_load_ratio,
    }


def objective_components(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
    checked = check_solution(instance, solution)
    routes = [route for route in solution.get("routes", []) if len(route) > 2]
    states = [evaluate_route_state(instance, [str(stop) for stop in route]) for route in routes]
    hard_violation_count = len(checked.get("violations", [])) if not checked.get("feasible") else 0
    total_distance = float(checked.get("totalDistance", sum(state["distance"] for state in states)) or 0.0)
    durations = [state["routeDuration"] for state in states]
    tail = max(durations) if durations else 0.0
    components = {
        "hardInfeasibility": hard_violation_count * config.hard_infeasibility_penalty,
        "vehicleFixed": len(routes) * config.vehicle_fixed_cost,
        "distance": total_distance * config.distance_weight,
        "slackPenalty": sum(state["slackRisk"] for state in states) * config.slack_penalty_weight,
        "routeDurationPenalty": sum(durations) * config.route_duration_penalty_weight,
        "loadRiskPenalty": sum(state["loadRisk"] for state in states) * config.load_risk_penalty_weight,
        "tailPenalty": tail * config.tail_penalty_weight,
        "vehicleCount": len(routes),
        "totalDistance": total_distance,
        "hardViolationCount": hard_violation_count,
        "feasible": bool(checked.get("feasible")),
    }
    components["objective"] = sum(value for key, value in components.items() if key not in {"vehicleCount", "totalDistance", "hardViolationCount", "feasible"})
    return components


def natural_solution_key(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> tuple[float, float, float, float]:
    components = objective_components(instance, solution, config)
    return (components["hardInfeasibility"], components["vehicleFixed"], components["objective"], components["distance"])


def solution_from_routes(routes: List[List[str]]) -> Dict[str, Any]:
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase40-natural-pdptw-optimizer", "routes": routes}


def _exact_pair_coverage(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    pairs = [(str(pickup), str(dropoff)) for pickup, dropoff in request_pairs(instance)]
    stop_counts: Dict[str, int] = {stop: 0 for pair in pairs for stop in pair}
    pair_counts: Dict[str, int] = {f"{pickup}->{dropoff}": 0 for pickup, dropoff in pairs}
    partial_pairs = []
    precedence_violations = []
    for route in solution.get("routes", []):
        route_stops = [str(stop) for stop in route]
        positions: Dict[str, List[int]] = {}
        for index, stop in enumerate(route_stops):
            if stop in stop_counts:
                stop_counts[stop] += 1
                positions.setdefault(stop, []).append(index)
        route_set = set(route_stops)
        for pickup, dropoff in pairs:
            has_pickup = pickup in route_set
            has_dropoff = dropoff in route_set
            if has_pickup and has_dropoff:
                pair_counts[f"{pickup}->{dropoff}"] += 1
                if min(positions.get(pickup, [10**9])) > min(positions.get(dropoff, [-1])):
                    precedence_violations.append(f"{pickup}->{dropoff}")
            elif has_pickup or has_dropoff:
                partial_pairs.append(f"{pickup}->{dropoff}")
    duplicate_stops = [stop for stop, count in stop_counts.items() if count > 1]
    missing_stops = [stop for stop, count in stop_counts.items() if count == 0]
    duplicate_pairs = [pair for pair, count in pair_counts.items() if count > 1]
    missing_pairs = [pair for pair, count in pair_counts.items() if count == 0]
    return {
        "valid": not duplicate_stops and not missing_stops and not duplicate_pairs and not missing_pairs and not partial_pairs and not precedence_violations,
        "duplicateStops": duplicate_stops,
        "missingStops": missing_stops,
        "duplicatePairs": duplicate_pairs,
        "missingPairs": missing_pairs,
        "partialPairs": partial_pairs,
        "precedenceViolations": precedence_violations,
    }


def remove_route_and_repair(instance: Dict[str, Any], routes: List[List[str]], remove_index: int, max_checks: int = 4_000) -> Dict[str, Any] | None:
    removed_route = routes[remove_index]
    removed_pairs = route_request_pairs(instance, removed_route)
    remaining = [route[:] for index, route in enumerate(routes) if index != remove_index]
    checks = 0
    for pair in sorted(removed_pairs, key=lambda item: request_features(instance, item)["due"]):
        best = None
        best_delta = 1e18
        for route_index, route in enumerate(remaining):
            if checks >= max_checks:
                return None
            checks += 1
            candidate = _insert_pair_best(instance, route, pair, max_checks=300)
            if candidate is None:
                continue
            delta = route_distance(instance, candidate) - route_distance(instance, route)
            if delta < best_delta:
                best = (route_index, candidate)
                best_delta = delta
        if best is None:
            return None
        route_index, candidate = best
        remaining[route_index] = candidate
    return {"solution": solution_from_routes(remaining), "candidateChecks": checks, "removedPairCount": len(removed_pairs)}


def _route_without_pairs(route: List[str], pairs: Iterable[tuple[str, str]]) -> List[str]:
    removed = {stop for pair in pairs for stop in pair}
    return [stop for stop in route if stop not in removed]


def _pair_relatedness(instance: Dict[str, Any], left: tuple[str, str], right: tuple[str, str]) -> float:
    left_features = request_features(instance, left)
    right_features = request_features(instance, right)
    return abs(left_features["pickupX"] - right_features["pickupX"]) + abs(left_features["pickupY"] - right_features["pickupY"]) + abs(left_features["due"] - right_features["due"]) * 0.01


def _insert_with_ejection(instance: Dict[str, Any], routes: List[List[str]], pair: tuple[str, str], max_eject: int = 2) -> tuple[List[List[str]] | None, List[tuple[str, str]], int]:
    checks = 0
    best_routes = None
    best_ejected: List[tuple[str, str]] = []
    best_delta = 1e18
    for route_index, route in enumerate(routes):
        direct = _insert_pair_best(instance, route, pair, max_checks=240)
        checks += 1
        if direct is not None:
            delta = route_distance(instance, direct) - route_distance(instance, route)
            if delta < best_delta:
                candidate_routes = [candidate[:] for candidate in routes]
                candidate_routes[route_index] = direct
                best_routes = candidate_routes
                best_ejected = []
                best_delta = delta
        route_pairs = sorted(route_request_pairs(instance, route), key=lambda candidate_pair: _pair_relatedness(instance, pair, candidate_pair))[:6]
        for eject_count in range(1, max_eject + 1):
            for offset in range(0, max(0, len(route_pairs) - eject_count + 1)):
                ejected = route_pairs[offset:offset + eject_count]
                reduced = _route_without_pairs(route, ejected)
                inserted = _insert_pair_best(instance, reduced, pair, max_checks=240)
                checks += 1
                if inserted is None:
                    continue
                delta = route_distance(instance, inserted) - route_distance(instance, route)
                if delta < best_delta:
                    candidate_routes = [candidate[:] for candidate in routes]
                    candidate_routes[route_index] = inserted
                    best_routes = candidate_routes
                    best_ejected = ejected
                    best_delta = delta
    return best_routes, best_ejected, checks


def objective_aware_ejection_repair(instance: Dict[str, Any], routes: List[List[str]], removed_pairs: List[tuple[str, str]], config: NaturalPDPTWObjectiveConfig, max_steps: int = 36) -> Dict[str, Any]:
    queue = sorted(removed_pairs, key=lambda pair: request_features(instance, pair)["due"])
    current = [route[:] for route in routes]
    checks = 0
    direct_success = 0
    ejection_success = 0
    ejected_count = 0
    steps = 0
    while queue and steps < max_steps:
        steps += 1
        pair = queue.pop(0)
        candidate_routes, ejected, used_checks = _insert_with_ejection(instance, current, pair, max_eject=1)
        checks += used_checks
        if candidate_routes is None:
            queue.append(pair)
            if steps > len(removed_pairs) + 12:
                return {"solution": None, "missingAfterRepair": len(queue), "candidateChecks": checks, "directInsertionSuccess": direct_success, "ejectionInsertionSuccess": ejection_success, "ejectedRequestCount": ejected_count, "rejectReason": "no-feasible-repair"}
            continue
        current = candidate_routes
        if ejected:
            ejection_success += 1
            ejected_count += len(ejected)
            queue.extend(ejected)
        else:
            direct_success += 1
    if queue:
        return {"solution": None, "missingAfterRepair": len(queue), "candidateChecks": checks, "directInsertionSuccess": direct_success, "ejectionInsertionSuccess": ejection_success, "ejectedRequestCount": ejected_count, "rejectReason": "candidate-cap"}
    solution = solution_from_routes(current)
    components = objective_components(instance, solution, config)
    if not components["feasible"]:
        return {"solution": None, "missingAfterRepair": 0, "candidateChecks": checks, "directInsertionSuccess": direct_success, "ejectionInsertionSuccess": ejection_success, "ejectedRequestCount": ejected_count, "rejectReason": "invalid-repair"}
    return {"solution": solution, "missingAfterRepair": 0, "candidateChecks": checks, "directInsertionSuccess": direct_success, "ejectionInsertionSuccess": ejection_success, "ejectedRequestCount": ejected_count, "rejectReason": None}


def affected_route_pool_repair(instance: Dict[str, Any], fixed_routes: List[List[str]], affected_pairs: List[tuple[str, str]], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
    collector = RouteColumnCollector(instance, source_run_id="phase41-affected")
    base_route = [str(instance.get("depotNodeId", "0")), str(instance.get("depotNodeId", "0"))]
    for pair in affected_pairs:
        inserted = _insert_pair_best(instance, base_route, pair, max_checks=300)
        if inserted is not None:
            collector.collect(inserted, "phase41-singleton")
    route = [str(instance.get("depotNodeId", "0")), str(instance.get("depotNodeId", "0"))]
    for pair in sorted(affected_pairs, key=lambda item: request_features(instance, item)["due"]):
        inserted = _insert_pair_best(instance, route, pair, max_checks=300)
        if inserted is None:
            break
        route = inserted
        collector.collect(route, "phase41-prefix")
    pool = collector.pool
    sp_result = PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, [column for column in pool.columns if column.allowed_for_claim])
    if not sp_result.get("feasible"):
        return {"solution": None, "spStatus": sp_result.get("status"), "rejectReason": "sp-infeasible", "poolStats": pool.stats()}
    solution = {"routes": fixed_routes + sp_result["solution"].get("routes", [])}
    components = objective_components(instance, solution, config)
    if not components["feasible"]:
        return {"solution": None, "spStatus": sp_result.get("status"), "rejectReason": "invalid-repair", "poolStats": pool.stats()}
    return {"solution": solution, "spStatus": sp_result.get("status"), "rejectReason": None, "poolStats": pool.stats()}


def objective_driven_route_elimination_repair(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig, max_routes: int = 3) -> Dict[str, Any]:
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    before_components = objective_components(instance, solution, config)
    best_solution = solution
    best_key = natural_solution_key(instance, solution, config)
    trace = []
    candidate_indexes = sorted(range(len(routes)), key=lambda index: (len(route_request_pairs(instance, routes[index])), evaluate_route_state(instance, routes[index])["slackRisk"]))[:max_routes]
    for route_index in candidate_indexes:
        removed_pairs = route_request_pairs(instance, routes[route_index])
        fixed_routes = [route[:] for index, route in enumerate(routes) if index != route_index]
        repair = objective_aware_ejection_repair(instance, fixed_routes, removed_pairs, config)
        candidate_solution = repair.get("solution")
        affected_sp_status = None
        if candidate_solution is None:
            sp_repair = {"solution": None, "spStatus": "skipped", "rejectReason": "no-feasible-repair"}
            candidate_solution = sp_repair.get("solution")
            affected_sp_status = sp_repair.get("spStatus")
            if candidate_solution is None:
                trace.append({"eliminatedRouteIndex": route_index, "eliminatedRequestCount": len(removed_pairs), "directInsertionSuccess": repair.get("directInsertionSuccess"), "ejectionInsertionSuccess": repair.get("ejectionInsertionSuccess"), "relatedDestroyCount": 0, "affectedSpStatus": affected_sp_status, "missingAfterRepair": repair.get("missingAfterRepair"), "objectiveBefore": before_components["objective"], "objectiveAfter": None, "vehicleCountBefore": before_components["vehicleCount"], "vehicleCountAfter": None, "rejectReason": sp_repair.get("rejectReason")})
                continue
        after_components = objective_components(instance, candidate_solution, config)
        candidate_key = natural_solution_key(instance, candidate_solution, config)
        accepted = candidate_key < best_key
        trace.append({"eliminatedRouteIndex": route_index, "eliminatedRequestCount": len(removed_pairs), "directInsertionSuccess": repair.get("directInsertionSuccess"), "ejectionInsertionSuccess": repair.get("ejectionInsertionSuccess"), "relatedDestroyCount": repair.get("ejectedRequestCount"), "affectedSpStatus": affected_sp_status, "missingAfterRepair": repair.get("missingAfterRepair"), "objectiveBefore": before_components["objective"], "objectiveAfter": after_components["objective"], "vehicleCountBefore": before_components["vehicleCount"], "vehicleCountAfter": after_components["vehicleCount"], "rejectReason": None if accepted else "objective-not-improved"})
        if accepted:
            best_solution = candidate_solution
            best_key = candidate_key
            break
    return {"solution": best_solution, "trace": trace, "accepted": best_solution is not solution}


def natural_route_elimination(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
    routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
    best_solution = solution
    best_key = natural_solution_key(instance, best_solution, config)
    attempts = []
    for route_index in sorted(range(len(routes)), key=lambda index: len(route_request_pairs(instance, routes[index]))):
        candidate = remove_route_and_repair(instance, routes, route_index)
        if candidate is None:
            attempts.append({"routeIndex": route_index, "accepted": False, "reason": "repair-failed"})
            continue
        candidate_key = natural_solution_key(instance, candidate["solution"], config)
        accepted = candidate_key < best_key
        attempts.append({"routeIndex": route_index, "accepted": accepted, "candidateChecks": candidate["candidateChecks"], "removedPairCount": candidate["removedPairCount"]})
        if accepted:
            best_solution = candidate["solution"]
            best_key = candidate_key
            routes = [[str(stop) for stop in route] for route in best_solution.get("routes", []) if len(route) > 2]
            break
    return {"solution": best_solution, "attempts": attempts}


def collect_internal_pool(instance: Dict[str, Any], solution: Dict[str, Any]) -> tuple[PDPTWRoutePool, Dict[str, Any]]:
    collector, diagnostics = generate_internal_columns(instance, solution, budget_ms=5_000, max_variants_per_route=40)
    return collector.pool, diagnostics


def route_pool_improvement(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
    pool, diagnostics = collect_internal_pool(instance, solution)
    solver = PDPTWSetPartitioningSolver(time_limit_ms=2_000)
    sp_result = solver.solve(instance, [column for column in pool.columns if column.allowed_for_claim])
    if not sp_result.get("feasible"):
        return {"solution": solution, "poolStats": pool.stats(), "spStatus": sp_result.get("status"), "accepted": False, "generationDiagnostics": diagnostics}
    candidate = sp_result["solution"]
    accepted = natural_solution_key(instance, candidate, config) < natural_solution_key(instance, solution, config)
    return {"solution": candidate if accepted else solution, "poolStats": pool.stats(), "spStatus": sp_result.get("status"), "accepted": accepted, "generationDiagnostics": diagnostics}


class InternalSolverCandidateGenerator:
    def __init__(self, max_runtime_ms: int = 3_000) -> None:
        self._max_runtime_ms = max_runtime_ms

    def generate(self, instance: Dict[str, Any], config: NaturalPDPTWObjectiveConfig, incumbent: Dict[str, Any] | None = None) -> Dict[str, Any]:
        strategies = [
            ("PARALLEL_CHEAPEST_INSERTION", "GUIDED_LOCAL_SEARCH"),
            ("PATH_CHEAPEST_ARC", "TABU_SEARCH"),
            ("SAVINGS", "SIMULATED_ANNEALING"),
        ]
        candidates = []
        trace = []
        if incumbent is not None and check_solution(instance, incumbent).get("feasible"):
            warm = dict(incumbent)
            warm["solver"] = "our-dispatch-v2-internal-generator-warm-start"
            candidates.append(warm)
            checked = check_solution(instance, warm)
            trace.append({
                "firstSolutionStrategy": "INCUMBENT_WARM_START",
                "localSearchMetaheuristic": "PRESERVE_INCUMBENT",
                "status": "feasible",
                "warmStartUsed": True,
                "sameRouteArcBiasUsed": True,
                "fixedCostUsed": int(config.vehicle_fixed_cost),
                "vehicleCount": checked.get("vehicleCount"),
                "distance": checked.get("totalDistance"),
            })
        per_candidate_ms = max(300, self._max_runtime_ms // max(1, len(strategies)))
        for first_strategy, local_strategy in strategies:
            try:
                candidate = ortools_baseline_solution(
                    instance,
                    per_candidate_ms,
                    "our-dispatch-v2-internal-generator",
                    vehicle_fixed_cost=int(config.vehicle_fixed_cost),
                    first_solution_strategy=first_strategy,
                    local_search_metaheuristic=local_strategy,
                )
            except Exception as exception:
                trace.append({"firstSolutionStrategy": first_strategy, "localSearchMetaheuristic": local_strategy, "status": "model-build-failed", "reason": str(exception)})
                continue
            checked = check_solution(instance, candidate)
            feasible = bool(checked.get("feasible"))
            if feasible:
                candidates.append(candidate)
            trace.append({
                "firstSolutionStrategy": first_strategy,
                "localSearchMetaheuristic": local_strategy,
                "status": "feasible" if feasible else candidate.get("evidenceGapReason", "hard-violation"),
                "warmStartUsed": False,
                "sameRouteArcBiasUsed": False,
                "fixedCostUsed": int(config.vehicle_fixed_cost),
                "vehicleCount": checked.get("vehicleCount"),
                "distance": checked.get("totalDistance"),
            })
        return {"candidates": candidates, "trace": trace, "candidateCount": len(trace), "feasibleCandidateCount": len(candidates)}

    def affected_subproblem(self, instance: Dict[str, Any], fixed_routes: List[List[str]], affected_pairs: List[tuple[str, str]], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
        affected_nodes = {stop for pair in affected_pairs for stop in pair}
        if not affected_nodes:
            return {"solution": None, "trace": {"status": "empty-affected-set"}}
        depot = str(instance.get("depotNodeId", "0"))
        sub_nodes = [node for node in instance.get("nodes", []) if str(node.get("id")) == depot or str(node.get("id")) in affected_nodes]
        sub_requests = [request for request in instance.get("requests", []) if (str(request.get("pickupNodeId")), str(request.get("dropoffNodeId"))) in set(affected_pairs)]
        sub_instance = dict(instance)
        sub_instance["nodes"] = sub_nodes
        sub_instance["requests"] = sub_requests
        sub_instance["vehicleCount"] = max(1, len(affected_pairs))
        generated = self.generate(sub_instance, config)
        if not generated["candidates"]:
            return {"solution": None, "trace": {"status": "no-feasible-candidate", "generatorTrace": generated["trace"]}}
        replacement = min(generated["candidates"], key=lambda candidate: objective_components(sub_instance, candidate, config)["objective"])
        full_solution = {"routes": fixed_routes + replacement.get("routes", [])}
        checked = check_solution(instance, full_solution)
        if not checked.get("feasible"):
            return {"solution": None, "trace": {"status": "hard-violation", "generatorTrace": generated["trace"]}}
        return {"solution": full_solution, "trace": {"status": "feasible", "generatorTrace": generated["trace"]}}


def _route_neighborhood_features(instance: Dict[str, Any], route: List[str]) -> Dict[str, float]:
    pairs = route_request_pairs(instance, route)
    if not pairs:
        return {"x": 0.0, "y": 0.0, "ready": 0.0, "due": 0.0, "slackRisk": evaluate_route_state(instance, route)["slackRisk"]}
    features = [request_features(instance, pair) for pair in pairs]
    return {
        "x": sum((row["pickupX"] + row.get("dropoffX", row["pickupX"])) * 0.5 for row in features) / len(features),
        "y": sum((row["pickupY"] + row.get("dropoffY", row["pickupY"])) * 0.5 for row in features) / len(features),
        "ready": sum(row.get("ready", 0.0) for row in features) / len(features),
        "due": sum(row.get("due", 0.0) for row in features) / len(features),
        "slackRisk": evaluate_route_state(instance, route)["slackRisk"],
    }


def _neighborhood_distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    return abs(left["x"] - right["x"]) + abs(left["y"] - right["y"]) + abs(left["ready"] - right["ready"]) * 0.005 + abs(left["due"] - right["due"]) * 0.005 + abs(left["slackRisk"] - right["slackRisk"])


def _sub_instance_for_pairs(instance: Dict[str, Any], pairs: List[tuple[str, str]], slots: int) -> Dict[str, Any]:
    affected_nodes = {stop for pair in pairs for stop in pair}
    depot = str(instance.get("depotNodeId", "0"))
    pair_set = set(pairs)
    sub_instance = dict(instance)
    sub_instance["nodes"] = [node for node in instance.get("nodes", []) if str(node.get("id")) == depot or str(node.get("id")) in affected_nodes]
    sub_instance["requests"] = [request for request in instance.get("requests", []) if (str(request.get("pickupNodeId")), str(request.get("dropoffNodeId"))) in pair_set]
    sub_instance["vehicleCount"] = max(1, slots)
    return sub_instance


def _construct_routes_for_pairs(instance: Dict[str, Any], pairs: List[tuple[str, str]], slots: int) -> List[List[str]] | None:
    depot = str(instance.get("depotNodeId", "0"))
    routes = [[depot, depot] for _ in range(max(1, slots))]
    for pair in sorted(pairs, key=lambda item: (request_features(instance, item)["due"], request_features(instance, item)["ready"])):
        best_index = None
        best_route = None
        best_delta = 1e18
        for route_index, route in enumerate(routes):
            candidate = _insert_pair_best(instance, route, pair, max_checks=420)
            if candidate is None:
                continue
            delta = route_distance(instance, candidate) - route_distance(instance, route)
            if delta < best_delta:
                best_index = route_index
                best_route = candidate
                best_delta = delta
        if best_index is None or best_route is None:
            return None
        routes[best_index] = best_route
    return [route for route in routes if len(route) > 2]


class IncumbentNeighborhoodRepairGenerator:
    def __init__(self, max_runtime_ms: int = 2_000, max_neighborhoods: int = 4, max_ortools_pairs: int = 12) -> None:
        self._max_runtime_ms = max_runtime_ms
        self._max_neighborhoods = max_neighborhoods
        self._max_ortools_pairs = max_ortools_pairs

    def extract_neighborhoods(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> List[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
        features = [_route_neighborhood_features(instance, route) for route in routes]
        route_order = sorted(range(len(routes)), key=lambda index: (len(route_request_pairs(instance, routes[index])), features[index]["slackRisk"], index))
        neighborhoods = []
        seen = set()
        for route_index in route_order:
            neighbors = sorted([index for index in range(len(routes)) if index != route_index], key=lambda index: (_neighborhood_distance(features[route_index], features[index]), index))
            for neighbor_count in range(1, min(3, len(neighbors)) + 1):
                affected_indexes = tuple(sorted([route_index] + neighbors[:neighbor_count]))
                if affected_indexes in seen:
                    continue
                seen.add(affected_indexes)
                affected_pairs = sorted({pair for index in affected_indexes for pair in route_request_pairs(instance, routes[index])}, key=lambda pair: request_features(instance, pair)["due"])
                neighborhoods.append({
                    "affectedRouteIndexes": list(affected_indexes),
                    "affectedRequests": affected_pairs,
                    "affectedRequestCount": len(affected_pairs),
                    "availableSlots": len(affected_indexes),
                    "compressionSlots": max(0, len(affected_indexes) - 1),
                    "unaffectedRoutes": [route[:] for index, route in enumerate(routes) if index not in affected_indexes],
                    "affectedRoutes": [routes[index][:] for index in affected_indexes],
                })
                if len(neighborhoods) >= self._max_neighborhoods:
                    return neighborhoods
        return neighborhoods

    def _subproblem_candidates(self, instance: Dict[str, Any], neighborhood: Dict[str, Any], slots: int, mode: str, config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
        candidates = []
        trace = []
        pairs = neighborhood["affectedRequests"]
        sub_instance = _sub_instance_for_pairs(instance, pairs, slots)
        if slots <= 0:
            return {"candidates": [], "trace": [{"mode": mode, "status": "insufficient-slots"}], "candidateCap": False}
        if mode == "same-slot-polish" and slots == len(neighborhood["affectedRoutes"]):
            incumbent = solution_from_routes(neighborhood["affectedRoutes"])
        else:
            incumbent = None
        constructed = _construct_routes_for_pairs(instance, pairs, slots)
        if constructed is not None:
            candidate = solution_from_routes(constructed)
            if _exact_pair_coverage(sub_instance, candidate)["valid"] and check_solution(sub_instance, candidate).get("feasible"):
                candidates.append(candidate)
                trace.append({"mode": mode, "strategy": "regret-construct", "status": "feasible", "vehicleCount": len(constructed), "distance": route_distance(sub_instance, constructed[0]) if len(constructed) == 1 else objective_components(sub_instance, candidate, config)["totalDistance"]})
            else:
                trace.append({"mode": mode, "strategy": "regret-construct", "status": "hard-violation"})
        else:
            trace.append({"mode": mode, "strategy": "regret-construct", "status": "no-feasible-candidate"})
        if len(pairs) > self._max_ortools_pairs:
            trace.append({"mode": mode, "strategy": "internal-ortools", "status": "candidate-cap", "affectedRequestCount": len(pairs), "maxOrtoolsPairs": self._max_ortools_pairs})
            return {"candidates": candidates, "trace": trace, "candidateCap": True}
        generator = InternalSolverCandidateGenerator(max_runtime_ms=max(600, self._max_runtime_ms // 4))
        generated = generator.generate(sub_instance, config, incumbent=incumbent)
        for candidate in generated["candidates"]:
            if _exact_pair_coverage(sub_instance, candidate)["valid"] and check_solution(sub_instance, candidate).get("feasible"):
                candidates.append(candidate)
        trace.append({"mode": mode, "strategy": "internal-ortools", "status": "complete", "candidateCount": generated["candidateCount"], "feasibleCandidateCount": generated["feasibleCandidateCount"], "generatorTrace": generated["trace"]})
        return {"candidates": candidates, "trace": trace, "candidateCap": False}

    def repair(self, instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
        started = time.perf_counter()
        before = objective_components(instance, solution, config)
        best_solution = solution
        best_key = natural_solution_key(instance, solution, config)
        attempts = []
        for neighborhood in self.extract_neighborhoods(instance, solution):
            if int((time.perf_counter() - started) * 1000) > self._max_runtime_ms:
                attempts.append({"affectedRouteIndexes": neighborhood["affectedRouteIndexes"], "rejectReason": "runtime-cap"})
                break
            modes = [("same-slot-polish", neighborhood["availableSlots"])]
            if neighborhood["compressionSlots"] >= 1:
                modes.append(("compression-candidate", neighborhood["compressionSlots"]))
            feasible_subproblem = 0
            recombined_feasible = 0
            solver_modes = []
            candidate_cap = False
            best_attempt_after = None
            best_attempt_delta = None
            best_attempt_solution = None
            reject_reason = "no-feasible-subproblem"
            for mode, slots in modes:
                if int((time.perf_counter() - started) * 1000) > self._max_runtime_ms:
                    reject_reason = "runtime-cap"
                    break
                solved = self._subproblem_candidates(instance, neighborhood, slots, mode, config)
                solver_modes.extend([row.get("strategy", mode) for row in solved["trace"]])
                feasible_subproblem += len(solved["candidates"])
                candidate_cap = candidate_cap or bool(solved.get("candidateCap"))
                for replacement in solved["candidates"]:
                    replacement_routes = [[str(stop) for stop in route] for route in replacement.get("routes", []) if len(route) > 2]
                    candidate = solution_from_routes(neighborhood["unaffectedRoutes"] + replacement_routes)
                    coverage = _exact_pair_coverage(instance, candidate)
                    checked = check_solution(instance, candidate)
                    if not coverage["valid"]:
                        reject_reason = "recombination-invalid"
                        continue
                    if not checked.get("feasible"):
                        reject_reason = "hard-violation"
                        continue
                    recombined_feasible += 1
                    after = objective_components(instance, candidate, config)
                    delta = after["objective"] - before["objective"]
                    if best_attempt_after is None or after["objective"] < best_attempt_after["objective"]:
                        best_attempt_after = after
                        best_attempt_delta = delta
                        best_attempt_solution = candidate
                    reject_reason = "objective-not-improved"
            if candidate_cap and recombined_feasible == 0 and reject_reason == "no-feasible-subproblem":
                reject_reason = "candidate-cap"
            accepted = best_attempt_solution is not None and natural_solution_key(instance, best_attempt_solution, config) < best_key
            attempts.append({
                "affectedRouteIndexes": neighborhood["affectedRouteIndexes"],
                "affectedRequestCount": neighborhood["affectedRequestCount"],
                "availableSlots": neighborhood["availableSlots"],
                "compressionSlots": neighborhood["compressionSlots"],
                "solverModesTried": sorted(set(solver_modes)),
                "feasibleSubproblemCandidates": feasible_subproblem,
                "recombinedFeasibleCandidates": recombined_feasible,
                "bestCandidateVehicleCount": best_attempt_after.get("vehicleCount") if best_attempt_after else None,
                "bestCandidateDistance": best_attempt_after.get("totalDistance") if best_attempt_after else None,
                "objectiveBefore": before["objective"],
                "objectiveAfter": best_attempt_after.get("objective") if best_attempt_after else None,
                "objectiveDelta": best_attempt_delta,
                "accepted": accepted,
                "rejectReason": None if accepted else reject_reason,
            })
            if accepted:
                best_solution = best_attempt_solution
                best_key = natural_solution_key(instance, best_solution, config)
                break
        return {"solution": best_solution, "accepted": best_solution is not solution, "trace": attempts, "runtimeMs": int((time.perf_counter() - started) * 1000)}


def incumbent_neighborhood_repair(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig) -> Dict[str, Any]:
    return IncumbentNeighborhoodRepairGenerator(max_runtime_ms=2_000, max_neighborhoods=4).repair(instance, solution, config)


def internal_solver_improvement(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig, mode: str = "natural") -> Dict[str, Any]:
    before = objective_components(instance, solution, config)
    before_feasible = bool(before["feasible"])
    generator = InternalSolverCandidateGenerator(max_runtime_ms=3_000)
    generated = generator.generate(instance, config, incumbent=solution)
    best_candidate = None
    best_after = None
    candidate_summaries = []
    for candidate in generated["candidates"]:
        after = objective_components(instance, candidate, config)
        delta = after["objective"] - before["objective"]
        reason = None
        if before_feasible and config.mode == "academic_certification" and after["vehicleCount"] > before["vehicleCount"]:
            reason = "vehicle-count-regression"
        elif not after["feasible"]:
            reason = "hard-violation"
        elif delta >= 0:
            reason = "objective-not-improved"
        candidate_summaries.append({"vehicleCount": after["vehicleCount"], "distance": after["totalDistance"], "objectiveDelta": delta, "rejectReason": reason})
        if not after["feasible"]:
            continue
        if before_feasible and config.mode == "academic_certification" and after["vehicleCount"] > before["vehicleCount"]:
            continue
        if best_after is None or after["objective"] < best_after["objective"]:
            best_candidate = candidate
            best_after = after
    accepted = best_candidate is not None and best_after is not None and natural_solution_key(instance, best_candidate, config) < natural_solution_key(instance, solution, config)
    reject_reason = None if accepted else ("no-feasible-candidate" if not generated["candidates"] else "objective-not-improved")
    return {
        "solution": best_candidate if accepted else solution,
        "accepted": accepted,
        "trace": {
            "generatorMode": mode,
            "strategiesTried": generated["trace"],
            "warmStartUsed": any(row.get("warmStartUsed") for row in generated["trace"]),
            "sameRouteArcBiasUsed": any(row.get("sameRouteArcBiasUsed") for row in generated["trace"]),
            "fixedCostUsed": int(config.vehicle_fixed_cost),
            "candidateCount": generated["candidateCount"],
            "feasibleCandidateCount": generated["feasibleCandidateCount"],
            "candidateVehicleCounts": [row["vehicleCount"] for row in candidate_summaries],
            "candidateDistances": [row["distance"] for row in candidate_summaries],
            "candidateObjectiveDeltas": [row["objectiveDelta"] for row in candidate_summaries],
            "bestCandidateVehicleCount": best_after.get("vehicleCount") if best_after else None,
            "bestCandidateDistance": best_after.get("totalDistance") if best_after else None,
            "bestCandidateComparedToIncumbent": candidate_summaries[0] if candidate_summaries else None,
            "objectiveBefore": before,
            "objectiveAfter": best_after,
            "accepted": accepted,
            "rejectReason": reject_reason,
            "bestRejectedReason": next((row["rejectReason"] for row in candidate_summaries if row.get("rejectReason")), reject_reason),
        },
    }


def natural_alns_probe(instance: Dict[str, Any], solution: Dict[str, Any], config: NaturalPDPTWObjectiveConfig, max_runtime_ms: int = 3_000) -> Dict[str, Any]:
    started = time.perf_counter()
    consolidator = GlobalRouteConsolidator(
        max_nodes=1_000,
        alns_repair_max_runtime_ms=max_runtime_ms,
        operators=[PairAwareRouteEliminationOperator(max_removed_pairs=8, max_attempts=8, route_shortlist=6, beam_width=4), PairEjectionChainOperator(max_removed_pairs=8, max_runtime_ms=max_runtime_ms, max_depth=2, beam_width=8, max_states=200)],
    )
    result = consolidator.consolidate(instance, solution)
    candidate = result.solution
    accepted = natural_solution_key(instance, candidate, config) < natural_solution_key(instance, solution, config)
    return {"solution": candidate if accepted else solution, "accepted": accepted, "runtimeMs": int((time.perf_counter() - started) * 1000)}


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    config = objective_config(mode)
    incumbent = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
    before = objective_components(instance, incumbent, config)
    route_elimination = natural_route_elimination(instance, incumbent, config)
    objective_elimination = objective_driven_route_elimination_repair(instance, route_elimination["solution"], config)
    internal_generator = internal_solver_improvement(instance, objective_elimination["solution"], config)
    neighborhood = incumbent_neighborhood_repair(instance, internal_generator["solution"], config)
    alns = natural_alns_probe(instance, neighborhood["solution"], config, max_runtime_ms=min(3_000, max(500, time_limit_ms // 8)))
    pool = route_pool_improvement(instance, alns["solution"], config)
    final_solution = pool["solution"]
    after = objective_components(instance, final_solution, config)
    leakage = any(not column.allowed_for_claim for column in collect_internal_pool(instance, final_solution)[0].columns)
    hard_violations = after["hardViolationCount"]
    objective_improved = after["objective"] < before["objective"]
    vehicle_improved = after["vehicleCount"] < before["vehicleCount"]
    if hard_violations or leakage:
        verdict = "FAIL"
    elif vehicle_improved and objective_improved:
        verdict = "PASS_STRONG"
    elif objective_improved:
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    diagnostics = {
        "schemaVersion": "phase40-natural-pdptw-optimizer-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "mode": mode,
        "beforeVehicleCount": before["vehicleCount"],
        "afterVehicleCount": after["vehicleCount"],
        "beforeDistance": before["totalDistance"],
        "afterDistance": after["totalDistance"],
        "beforeObjective": before,
        "afterObjective": after,
        "objectiveImproved": objective_improved,
        "vehicleCountImproved": vehicle_improved,
        "hardViolations": hard_violations,
        "leakageDetected": leakage,
        "operatorTrace": {"routeElimination": route_elimination["attempts"], "objectiveDrivenRouteElimination": objective_elimination["trace"], "objectiveDrivenAccepted": objective_elimination["accepted"], "internalSolverGenerator": internal_generator["trace"], "incumbentNeighborhoodRepair": neighborhood["trace"], "incumbentNeighborhoodAccepted": neighborhood["accepted"], "alnsAccepted": alns["accepted"], "routePoolAccepted": pool["accepted"]},
        "routePoolStats": pool.get("poolStats"),
        "routePoolSpStatus": pool.get("spStatus"),
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "diagnostics.json", diagnostics)
    write_json(instance_dir / "best_solution.json", final_solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 40 Natural PDPTW Optimizer", "", "| Instance | Mode | Verdict | Vehicles Before | Vehicles After | Obj Improved | Hard Viol | Runtime ms |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('mode')} | {row.get('verdict')} | {row.get('beforeVehicleCount')} | {row.get('afterVehicleCount')} | {row.get('objectiveImproved')} | {row.get('hardViolations')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, mode: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, mode) for instance in instances]
    summary = {
        "schemaVersion": "phase40-natural-pdptw-optimizer-summary/v1",
        "instances": instances,
        "mode": mode,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS_STRONG", "PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase40_natural_pdptw_optimizer_summary.json", summary)
    (output_dir / "phase40_natural_pdptw_optimizer_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 40 natural-objective PDPTW optimizer diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.mode)
    print(f"[PHASE40 NATURAL PDPTW OPTIMIZER] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
