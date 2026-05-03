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
from external_benchmark_support import check_solution, route_distance
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
    alns = natural_alns_probe(instance, route_elimination["solution"], config, max_runtime_ms=min(3_000, max(500, time_limit_ms // 8)))
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
        "operatorTrace": {"routeElimination": route_elimination["attempts"], "alnsAccepted": alns["accepted"], "routePoolAccepted": pool["accepted"]},
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
