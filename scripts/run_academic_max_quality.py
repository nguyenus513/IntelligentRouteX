from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from external_benchmark_support import check_solution, route_distance, ortools_baseline_solution
from parse_solomon_vrptw import parse_solomon
from run_dispatch_benchmark_certification_suite import HOMBERGER_BEST_KNOWN, REPO_ROOT


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "academic-max-quality"
DEFAULT_INSTANCES = ("C1_10_1", "R1_10_1", "RC1_10_1")
FIRST_SOLUTION_STRATEGIES = (
    "PARALLEL_CHEAPEST_INSERTION",
    "PATH_CHEAPEST_ARC",
    "SAVINGS",
    "GLOBAL_CHEAPEST_ARC",
)
LOCAL_SEARCH_METAHEURISTICS = (
    "GUIDED_LOCAL_SEARCH",
    "TABU_SEARCH",
    "SIMULATED_ANNEALING",
)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_duration_ms(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(float(text[:-2]))
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 60_000)
    if text.endswith("h"):
        return int(float(text[:-1]) * 3_600_000)
    return int(float(text) * 1000)


def load_homberger(instance: str) -> Dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt"
    normalized = parse_solomon(path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    return normalized


def vehicle_fixed_cost(instance: Dict[str, Any], multiplier: int) -> int:
    values = [float(value) for row in instance.get("distanceMatrix", []) for value in row]
    max_arc = max(values, default=1.0)
    node_count = max(1, len(instance.get("nodes", [])))
    return max(1_000_000, int(round(max_arc * node_count * multiplier)))


def solution_key(metrics: Dict[str, Any]) -> tuple[int, int, float]:
    feasible_penalty = 0 if metrics.get("feasible") else 1
    return feasible_penalty, int(metrics.get("vehicleCount", 10**9)), float(metrics.get("totalDistance", 1e18))


def evaluate_solution(instance: Dict[str, Any], solution: Dict[str, Any], label: str) -> Dict[str, Any]:
    metrics = check_solution(instance, solution)
    return {
        "label": label,
        "feasible": metrics["feasible"],
        "vehicleCount": metrics["vehicleCount"],
        "totalDistance": metrics["totalDistance"],
        "objectiveGapPercent": metrics["objectiveGapPercent"],
        "hardViolationCount": len(metrics.get("violations", [])),
        "violations": metrics.get("violations", []),
        "solution": solution,
    }


def required_customers(instance: Dict[str, Any]) -> List[str]:
    depot = str(instance.get("depotNodeId", "0"))
    return [str(node["id"]) for node in instance.get("nodes", []) if str(node["id"]) != depot]


def route_feasible(instance: Dict[str, Any], route: List[str]) -> bool:
    depot = str(instance.get("depotNodeId", "0"))
    if not route or route[0] != depot or route[-1] != depot:
        return False
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
    capacity = int(instance.get("capacity", 0))
    load = 0
    elapsed = 0.0
    for previous, current in zip(route, route[1:]):
        if previous not in nodes or current not in nodes:
            return False
        elapsed += route_distance(instance, [previous, current])
        node = nodes[current]
        ready = float(node.get("readyTime", 0.0))
        due = float(node.get("dueTime", 1e18))
        if elapsed < ready:
            elapsed = ready
        if elapsed > due + 1e-9:
            return False
        elapsed += float(node.get("serviceTime", 0.0))
        load += int(float(node.get("demand", 0)))
        if load > capacity or load < 0:
            return False
    return True


def collect_route_pool(instance: Dict[str, Any], candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pool_by_key: Dict[tuple[str, ...], Dict[str, Any]] = {}
    depot = str(instance.get("depotNodeId", "0"))
    for candidate in candidates:
        for route_index, raw_route in enumerate(candidate["solution"].get("routes", [])):
            route = [str(stop) for stop in raw_route]
            customers = tuple(stop for stop in route if stop != depot)
            if not customers or not route_feasible(instance, route):
                continue
            distance = route_distance(instance, route)
            key = tuple(route)
            existing = pool_by_key.get(key)
            if existing is None or distance < existing["distance"]:
                pool_by_key[key] = {
                    "routeId": f"route-{len(pool_by_key) + 1}",
                    "customerSet": sorted(customers, key=lambda value: int(value) if value.isdigit() else value),
                    "sequence": route,
                    "distance": distance,
                    "vehicleCount": 1,
                    "capacityFeasible": True,
                    "timeWindowFeasible": True,
                    "sourceRun": candidate["label"],
                    "sourceRouteIndex": route_index,
                }
    return list(pool_by_key.values())


def route_pool_source_counts(route_pool: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for route in route_pool:
        source = str(route.get("sourceRun", "unknown"))
        family = source.split("+")[0] if "+" in source else source
        counts[family] = counts.get(family, 0) + 1
    return counts


def append_route_to_pool(instance: Dict[str, Any], route_pool: List[Dict[str, Any]], route: List[str], source: str) -> bool:
    depot = str(instance.get("depotNodeId", "0"))
    route = [str(stop) for stop in route]
    customers = tuple(stop for stop in route if stop != depot)
    if not customers or not route_feasible(instance, route):
        return False
    key = tuple(route)
    if any(tuple(existing["sequence"]) == key for existing in route_pool):
        return False
    route_pool.append({
        "routeId": f"route-{len(route_pool) + 1}",
        "customerSet": sorted(customers, key=lambda value: int(value) if value.isdigit() else value),
        "sequence": route,
        "distance": route_distance(instance, route),
        "vehicleCount": 1,
        "capacityFeasible": True,
        "timeWindowFeasible": True,
        "sourceRun": source,
        "sourceRouteIndex": -1,
    })
    return True


def best_insert_position(instance: Dict[str, Any], route: List[str], customer: str) -> tuple[float, List[str]] | None:
    best: tuple[float, List[str]] | None = None
    base_distance = route_distance(instance, route)
    for position in range(1, len(route)):
        candidate = route[:position] + [customer] + route[position:]
        if not route_feasible(instance, candidate):
            continue
        delta = route_distance(instance, candidate) - base_distance
        if best is None or delta < best[0]:
            best = (delta, candidate)
    return best


def regret_ordered_insertions(instance: Dict[str, Any], routes: List[List[str]], customers: List[str]) -> tuple[List[List[str]], bool]:
    remaining = [str(customer) for customer in customers]
    candidate_routes = [route[:] for route in routes]
    while remaining:
        ranked: List[tuple[float, float, str, int, List[str]]] = []
        for customer in remaining:
            insertions: List[tuple[float, int, List[str]]] = []
            for route_index, route in enumerate(candidate_routes):
                inserted = best_insert_position(instance, route, customer)
                if inserted is not None:
                    insertions.append((inserted[0], route_index, inserted[1]))
            if not insertions:
                return candidate_routes, False
            insertions.sort(key=lambda item: item[0])
            regret = insertions[1][0] - insertions[0][0] if len(insertions) > 1 else 1_000_000.0
            ranked.append((-regret, insertions[0][0], customer, insertions[0][1], insertions[0][2]))
        ranked.sort(key=lambda item: (item[0], item[1]))
        _, _, selected_customer, selected_route_index, selected_route = ranked[0]
        candidate_routes[selected_route_index] = selected_route
        remaining.remove(selected_customer)
    return candidate_routes, True


def generate_route_elimination_candidates(
    instance: Dict[str, Any],
    seed_solution: Dict[str, Any],
    route_pool: List[Dict[str, Any]],
    max_attempts: int,
) -> Dict[str, int]:
    routes = [[str(stop) for stop in route] for route in seed_solution.get("routes", []) if len(route) > 2]
    depot = str(instance.get("depotNodeId", "0"))
    attempts = 0
    successes = 0
    generated_routes = 0
    priorities = sorted(
        range(len(routes)),
        key=lambda index: (
            len([stop for stop in routes[index] if stop != depot]),
            route_distance(instance, routes[index]) / max(1, len(routes[index]) - 2),
        ),
    )
    for route_index in priorities[:max_attempts]:
        removed_customers = [stop for stop in routes[route_index] if stop != depot]
        remaining_routes = [route[:] for index, route in enumerate(routes) if index != route_index]
        attempts += 1
        repaired_routes, feasible = regret_ordered_insertions(instance, remaining_routes, removed_customers)
        if not feasible:
            continue
        candidate_solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "route-elimination-v3", "routes": repaired_routes}
        checked = check_solution(instance, candidate_solution)
        if not checked.get("feasible") or int(checked.get("vehicleCount", len(routes))) >= len(routes):
            continue
        successes += 1
        for repaired in repaired_routes:
            if append_route_to_pool(instance, route_pool, repaired, "route-elimination-v3"):
                generated_routes += 1
    return {"routeEliminationAttempts": attempts, "routeEliminationSuccesses": successes, "routeEliminationGeneratedRoutes": generated_routes}


def set_partitioning_solution(instance: Dict[str, Any], route_pool: Sequence[Dict[str, Any]], time_limit_ms: int) -> Dict[str, Any] | None:
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return None
    customers = required_customers(instance)
    routes_by_customer: Dict[str, List[int]] = {customer: [] for customer in customers}
    for route_index, route in enumerate(route_pool):
        for customer in route["customerSet"]:
            if customer in routes_by_customer:
                routes_by_customer[customer].append(route_index)
    if any(not indexes for indexes in routes_by_customer.values()):
        return None
    model = cp_model.CpModel()
    selected = [model.NewBoolVar(f"route_{index}") for index in range(len(route_pool))]
    for customer in customers:
        model.Add(sum(selected[index] for index in routes_by_customer[customer]) == 1)
    max_distance = max((float(route["distance"]) for route in route_pool), default=1.0)
    big_m = int(max(1_000_000_000, round(max_distance * len(customers) * 1000)))
    model.Minimize(
        sum(selected[index] * (big_m + int(round(float(route_pool[index]["distance"]) * 1000))) for index in range(len(route_pool)))
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, time_limit_ms / 1000)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return None
    routes = [route_pool[index]["sequence"] for index, variable in enumerate(selected) if solver.Value(variable)]
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "academic-max-quality-set-partitioning", "routes": routes}


def run_instance(instance_name: str, time_limit_ms: int, output_root: Path, max_runs: int, fixed_cost_multiplier: int) -> Dict[str, Any]:
    started = time.perf_counter()
    instance = load_homberger(instance_name)
    bks = instance.get("bestKnown", {})
    per_run_ms = max(1, time_limit_ms // max(1, max_runs))
    fixed_cost = vehicle_fixed_cost(instance, fixed_cost_multiplier)
    candidates: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    strategy_pairs = [
        (first, local)
        for first in FIRST_SOLUTION_STRATEGIES
        for local in LOCAL_SEARCH_METAHEURISTICS
    ][:max_runs]
    for index, (first_strategy, local_strategy) in enumerate(strategy_pairs, start=1):
        run_started = time.perf_counter()
        solution = ortools_baseline_solution(
            instance,
            per_run_ms,
            f"academic-max-quality-run-{index}",
            vehicle_fixed_cost=fixed_cost,
            first_solution_strategy=first_strategy,
            local_search_metaheuristic=local_strategy,
        )
        runtime_ms = int((time.perf_counter() - run_started) * 1000)
        if solution.get("evidenceGapReason"):
            runs.append({
                "run": index,
                "firstSolutionStrategy": first_strategy,
                "localSearchMetaheuristic": local_strategy,
                "runtimeMs": runtime_ms,
                "evidenceGapReason": solution["evidenceGapReason"],
            })
            continue
        evaluated = evaluate_solution(instance, solution, f"{first_strategy}+{local_strategy}")
        candidates.append(evaluated)
        runs.append({
            "run": index,
            "firstSolutionStrategy": first_strategy,
            "localSearchMetaheuristic": local_strategy,
            "runtimeMs": runtime_ms,
            "feasible": evaluated["feasible"],
            "vehicleCount": evaluated["vehicleCount"],
            "totalDistance": evaluated["totalDistance"],
            "objectiveGapPercent": evaluated["objectiveGapPercent"],
        })
    route_pool = collect_route_pool(instance, candidates)
    best_seed = min(candidates, key=lambda item: solution_key(item)) if candidates else None
    operator_counts = {"routeEliminationAttempts": 0, "routeEliminationSuccesses": 0, "routeEliminationGeneratedRoutes": 0}
    if best_seed is not None:
        operator_counts = generate_route_elimination_candidates(
            instance,
            best_seed["solution"],
            route_pool,
            max_attempts=max(10, min(80, len(best_seed["solution"].get("routes", [])) // 2)),
        )
    set_partitioning_runtime_ms = 0
    set_partitioning_solution_candidate = None
    if route_pool:
        partition_started = time.perf_counter()
        set_partitioning_solution_candidate = set_partitioning_solution(instance, route_pool, max(1, min(300_000, time_limit_ms // 6)))
        set_partitioning_runtime_ms = int((time.perf_counter() - partition_started) * 1000)
        if set_partitioning_solution_candidate is not None:
            candidates.append(evaluate_solution(instance, set_partitioning_solution_candidate, "set-partitioning-route-pool"))
    if not candidates:
        row = {
            "instance": instance_name,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["no-candidate-solution"],
            "runs": runs,
        }
        write_json(output_root / instance_name / "metrics.json", row)
        return row
    best = min(candidates, key=lambda item: solution_key(item))
    runtime_ms = int((time.perf_counter() - started) * 1000)
    final_vehicle_count = int(best["vehicleCount"])
    bks_vehicles = int(bks.get("vehicleCount", final_vehicle_count) or final_vehicle_count)
    distance_gap = best["objectiveGapPercent"]
    hard_violations = int(best["hardViolationCount"])
    if hard_violations:
        verdict = "FAIL"
        reasons = best["violations"]
    elif final_vehicle_count <= bks_vehicles and distance_gap is not None and float(distance_gap) <= 20.0:
        verdict = "PASS"
        reasons = ["academic-max-quality-within-target"]
    else:
        verdict = "PASS_WITH_LIMITS"
        reasons = []
        if final_vehicle_count > bks_vehicles:
            reasons.append("vehicle-count-above-best-known")
        if distance_gap is None:
            reasons.append("best-known-objective-missing")
        elif float(distance_gap) > 20.0:
            reasons.append("objective-gap-above-pass-threshold")
    row = {
        "schemaVersion": "academic-objective-quality-v2/v1",
        "instance": instance_name,
        "profile": "academic-max-quality",
        "usedBksInSolver": False,
        "caseSpecificRuleUsed": False,
        "instanceNameBranchCount": 0,
        "setPartitioningEnabled": True,
        "setPartitioningProducedSolution": set_partitioning_solution_candidate is not None,
        "setPartitioningRuntimeMs": set_partitioning_runtime_ms,
        "routePoolSize": len(route_pool),
        "validRoutePoolSize": len(route_pool),
        "setPartitioningSelectedRoutes": final_vehicle_count if best["label"] == "set-partitioning-route-pool" else None,
        "routePoolSourceCounts": route_pool_source_counts(route_pool),
        "operatorSuccessCounts": {
            "route-elimination-v3": operator_counts["routeEliminationSuccesses"],
            "cp-sat-set-partitioning": 1 if set_partitioning_solution_candidate is not None else 0,
        },
        "objectiveMode": "vehicle-first-lexicographic",
        "solverSawBestKnown": False,
        "localSearchOperatorsUsed": ["or-tools-multi-start", "route-elimination-v3", "regret-insertion", "cp-sat-set-partitioning"],
        "routeEliminationAttempts": operator_counts["routeEliminationAttempts"],
        "routeEliminationSuccesses": operator_counts["routeEliminationSuccesses"],
        "routeEliminationGeneratedRoutes": operator_counts["routeEliminationGeneratedRoutes"],
        "ejectionChainAttempts": 0,
        "ejectionChainSuccesses": 0,
        "orToolsRuns": len(runs),
        "perRunTimeLimitMs": per_run_ms,
        "runtimeMs": runtime_ms,
        "runtimeMinutes": runtime_ms / 60_000,
        "vehicleFixedCost": fixed_cost,
        "initialVehicles": runs[0].get("vehicleCount") if runs else None,
        "finalVehicles": final_vehicle_count,
        "bksVehicles": bks.get("vehicleCount"),
        "vehicleGap": final_vehicle_count - bks_vehicles,
        "initialDistance": runs[0].get("totalDistance") if runs else None,
        "finalDistance": best["totalDistance"],
        "bksDistance": bks.get("objective"),
        "distanceGap": distance_gap,
        "hardViolationCount": hard_violations,
        "bestRunLabel": best["label"],
        "runs": runs,
        "verdict": verdict,
        "verdictReasons": reasons,
    }
    case_root = output_root / instance_name
    write_json(case_root / "solution.json", best["solution"])
    write_json(case_root / "route_pool.json", {"routes": route_pool})
    write_json(case_root / "metrics.json", row)
    return row


def markdown(rows: Sequence[Dict[str, Any]]) -> str:
    lines = ["# Academic Max Quality Report", ""]
    lines.append("| Case | Final vehicles | BKS vehicles | Vehicle gap | Distance gap | Route pool | SP selected | Runtime min | Verdict | Reasons |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |")
    for row in rows:
        distance_gap = row.get("distanceGap")
        gap_text = "n/a" if distance_gap is None else f"{float(distance_gap):.2f}%"
        lines.append(
            "| {instance} | {finalVehicles} | {bksVehicles} | {vehicleGap} | {gap} | {routePoolSize} | {setPartitioningProducedSolution} | {runtimeMinutes:.2f} | {verdict} | {reasons} |".format(
                gap=gap_text,
                reasons=", ".join(row.get("verdictReasons", [])),
                **row,
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run academic max-quality Homberger optimization.")
    parser.add_argument("--instances", default=",".join(DEFAULT_INSTANCES))
    parser.add_argument("--time-limit", default="30m")
    parser.add_argument("--or-tools-runs", type=int, default=6)
    parser.add_argument("--fixed-cost-multiplier", type=int, default=1_000_000)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [
        run_instance(instance, parse_duration_ms(args.time_limit), output_root, args.or_tools_runs, args.fixed_cost_multiplier)
        for instance in instances
    ]
    result = {"schemaVersion": "academic-max-quality/v1", "results": rows}
    write_json(output_root / "academic_max_quality_results.json", result)
    (output_root / "academic_max_quality_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[ACADEMIC MAX QUALITY JSON] {output_root / 'academic_max_quality_results.json'}")
    print(f"[ACADEMIC MAX QUALITY REPORT] {output_root / 'academic_max_quality_report.md'}")
    return 1 if any(row["verdict"] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
