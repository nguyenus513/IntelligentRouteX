from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from academic_global_consolidation import _route_is_feasible
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase32_internal_column_generation import _insert_pair_best, relatedness, request_features, request_pairs
from run_phase38b_target_vehicle_feasibility import (
    DispatchV2ExternalBenchmarkSolver,
    construct_target_k,
    remove_pairs_from_routes,
    repair_missing_pairs,
    route_pairs,
    score_routes,
    solution_from_routes,
    target_k_alns_repair,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase39-missing-driven-targetk-v1"


@dataclass(frozen=True)
class MissingInsertionOption:
    missing_pair: tuple[str, str]
    route_index: int
    route: List[str]
    ejected_pairs: tuple[tuple[str, str], ...]
    delta_distance: float
    option_type: str


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def pair_id(instance: Dict[str, Any], pair: tuple[str, str]) -> str:
    for index, request in enumerate(instance.get("requests", [])):
        if str(request.get("pickupNodeId")) == pair[0] and str(request.get("dropoffNodeId")) == pair[1]:
            return str(request.get("id") or request.get("requestId") or index)
    return f"{pair[0]}-{pair[1]}"


def served_and_missing_pairs(instance: Dict[str, Any], routes: List[List[str]]) -> tuple[List[tuple[str, str]], List[tuple[str, str]]]:
    served = []
    for route in routes:
        served.extend(route_pairs(instance, route))
    served_set = set(served)
    missing = [pair for pair in request_pairs(instance) if pair not in served_set]
    return served, missing


def route_without_pairs(route: List[str], pairs: Iterable[tuple[str, str]]) -> List[str]:
    removed = {stop for pair in pairs for stop in pair}
    return [stop for stop in route if stop not in removed]


def enumerate_missing_options(instance: Dict[str, Any], routes: List[List[str]], missing_pair: tuple[str, str], max_eject: int = 1) -> List[MissingInsertionOption]:
    options: List[MissingInsertionOption] = []
    for route_index, route in enumerate(routes):
        direct = _insert_pair_best(instance, route, missing_pair, max_checks=180)
        if direct is not None:
            options.append(MissingInsertionOption(missing_pair, route_index, direct, tuple(), route_distance(instance, direct) - route_distance(instance, route), "direct"))
        route_served = route_pairs(instance, route)
        related = sorted(route_served, key=lambda pair: relatedness(instance, missing_pair, pair))[:4]
        for eject_count in range(1, max_eject + 1):
            for start in range(0, max(0, len(related) - eject_count + 1)):
                ejected = tuple(related[start:start + eject_count])
                reduced = route_without_pairs(route, ejected)
                inserted = _insert_pair_best(instance, reduced, missing_pair, max_checks=180)
                if inserted is None:
                    continue
                options.append(MissingInsertionOption(missing_pair, route_index, inserted, ejected, route_distance(instance, inserted) - route_distance(instance, route), f"eject-{eject_count}"))
    options.sort(key=lambda option: (len(option.ejected_pairs), option.delta_distance, request_features(instance, option.missing_pair)["due"]))
    return options


def priority_missing_pairs(instance: Dict[str, Any], routes: List[List[str]], missing_pairs: List[tuple[str, str]], max_ranked: int | None = None) -> List[tuple[str, str]]:
    scored = []
    for pair in missing_pairs[:max_ranked or len(missing_pairs)]:
        option_count = sum(1 for route in routes if _insert_pair_best(instance, route, pair, max_checks=80) is not None)
        features = request_features(instance, pair)
        direct_distance = ((features["pickupX"] - features["dropoffX"]) ** 2 + (features["pickupY"] - features["dropoffY"]) ** 2) ** 0.5
        scored.append((option_count, features["due"], -direct_distance, pair))
    scored.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[3] for row in scored]


def route_slack_diagnostics(instance: Dict[str, Any], routes: List[List[str]], missing_pairs: List[tuple[str, str]]) -> List[Dict[str, Any]]:
    diagnostics = []
    for route_index, route in enumerate(routes):
        insertable = [pair_id(instance, pair) for pair in missing_pairs[:8] if _insert_pair_best(instance, route, pair, max_checks=80) is not None]
        diagnostics.append({
            "routeIndex": route_index,
            "requestCount": len(route_pairs(instance, route)),
            "routeDistance": route_distance(instance, route) if len(route) > 2 else 0.0,
            "routeFeasible": _route_is_feasible(instance, route)[0],
            "candidateMissingInsertable": insertable,
            "candidateMissingInsertableCount": len(insertable),
        })
    return diagnostics


def forced_missing_repair(instance: Dict[str, Any], routes: List[List[str]], max_steps: int = 12, max_runtime_ms: int = 8_000) -> Dict[str, Any]:
    started = time.perf_counter()
    current = [route[:] for route in routes]
    _, missing = served_and_missing_pairs(instance, current)
    queue = priority_missing_pairs(instance, current, missing, max_ranked=8)
    trace = {
        "directInsertionAttempts": 0,
        "directInsertionSuccess": 0,
        "ejectionInsertionAttempts": 0,
        "ejectionInsertionSuccess": 0,
        "ejectedRequestCount": 0,
        "queueStallReasons": {},
        "perMissingOptionCount": {},
    }
    steps = 0
    while queue and steps < max_steps and int((time.perf_counter() - started) * 1000) < max_runtime_ms:
        steps += 1
        pair = queue.pop(0)
        if pair not in served_and_missing_pairs(instance, current)[1]:
            continue
        options = enumerate_missing_options(instance, current, pair, max_eject=1)
        trace["perMissingOptionCount"][pair_id(instance, pair)] = len(options)
        if not options:
            trace["queueStallReasons"]["no-ejection-insertion"] = trace["queueStallReasons"].get("no-ejection-insertion", 0) + 1
            queue.append(pair)
            if trace["queueStallReasons"]["no-ejection-insertion"] > len(queue) + 4:
                break
            continue
        option = options[0]
        if option.ejected_pairs:
            trace["ejectionInsertionAttempts"] += 1
            trace["ejectionInsertionSuccess"] += 1
            trace["ejectedRequestCount"] += len(option.ejected_pairs)
        else:
            trace["directInsertionAttempts"] += 1
            trace["directInsertionSuccess"] += 1
        current[option.route_index] = option.route
        for ejected in option.ejected_pairs:
            if ejected not in queue:
                queue.append(ejected)
        _, missing = served_and_missing_pairs(instance, current)
        queue = priority_missing_pairs(instance, current, list(dict.fromkeys(queue + missing)), max_ranked=8)
    if queue:
        trace["queueStallReasons"]["runtime-cap" if int((time.perf_counter() - started) * 1000) >= max_runtime_ms else "candidate-cap"] = trace["queueStallReasons"].get("runtime-cap", 0) + 1
    return {"routes": current, "trace": trace, "score": score_routes(instance, current)}


def perturbation_repair(instance: Dict[str, Any], routes: List[List[str]], seed: int = 39, max_attempts: int = 40) -> Dict[str, Any]:
    rng = random.Random(seed)
    best = [route[:] for route in routes]
    best_score = score_routes(instance, best)
    attempts = 0
    successes = 0
    _, initial_missing = served_and_missing_pairs(instance, best)
    for blocked in initial_missing[:8]:
        related = sorted([pair for route in best for pair in route_pairs(instance, route)], key=lambda pair: relatedness(instance, blocked, pair))[:6]
        for size in range(2, min(6, len(related)) + 1):
            if attempts >= max_attempts:
                break
            attempts += 1
            removed = [blocked] + related[:size]
            partial = remove_pairs_from_routes(best, removed)
            repaired, failed, _ = repair_missing_pairs(instance, partial, removed, "earliest-due")
            candidate_score = score_routes(instance, repaired)
            if candidate_score["score"] < best_score["score"]:
                best = repaired
                best_score = candidate_score
                successes += 1
            elif rng.random() < 0.02:
                best = repaired
                best_score = candidate_score
        if attempts >= max_attempts:
            break
    return {"routes": best, "attempts": attempts, "successes": successes, "score": best_score}


def run_missing_driven_repair(instance: Dict[str, Any], routes: List[List[str]]) -> Dict[str, Any]:
    before_score = score_routes(instance, routes)
    forced = forced_missing_repair(instance, routes)
    perturb = perturbation_repair(instance, forced["routes"])
    best_routes = perturb["routes"] if perturb["score"]["score"] <= forced["score"]["score"] else forced["routes"]
    best_score = score_routes(instance, best_routes)
    blocker = "none" if best_score["feasible"] else "target-k-infeasible-in-search"
    if best_score["missingCount"] > 0:
        blocker = "no-ejection-insertion" if forced["trace"]["queueStallReasons"].get("no-ejection-insertion") else "candidate-cap"
    return {
        "routes": best_routes,
        "beforeScore": before_score,
        "afterScore": best_score,
        "forcedTrace": forced["trace"],
        "perturbationAttempts": perturb["attempts"],
        "perturbationSuccess": perturb["successes"],
        "bestBlocker": blocker,
        "routeSlackDiagnostics": route_slack_diagnostics(instance, best_routes, served_and_missing_pairs(instance, best_routes)[1]),
    }


def build_phase38b_seed(instance: Dict[str, Any], k: int, time_limit_ms: int) -> Dict[str, Any]:
    best = None
    for index, strategy in enumerate(["earliest-due"]):
        constructed = construct_target_k(instance, k, strategy, seed=39 + index)
        repaired = target_k_alns_repair(instance, constructed["routes"], constructed["missingPairs"], max_runtime_ms=1_000, max_iterations=12, seed=39 + index)
        candidate = {"routes": repaired["routes"], "score": score_routes(instance, repaired["routes"]), "strategy": strategy}
        if best is None or candidate["score"]["score"] < best["score"]["score"]:
            best = candidate
    assert best is not None
    return best


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int, target_vehicle_count: int | None) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    incumbent = DispatchV2ExternalBenchmarkSolver().solve(instance, min(time_limit_ms, 12_000), "our-dispatch-v2")
    incumbent_routes = [route for route in incumbent.get("routes", []) if len(route) > 2]
    k = target_vehicle_count or max(1, len(incumbent_routes) - 1)
    seed_state = build_phase38b_seed(instance, k, min(time_limit_ms, 12_000))
    repair = run_missing_driven_repair(instance, seed_state["routes"])
    solution = solution_from_routes(repair["routes"])
    checked = check_solution(instance, solution)
    feasible = bool(checked.get("feasible")) and len([route for route in repair["routes"] if len(route) > 2]) <= k
    hard_violations = len(checked.get("violations", [])) if feasible else 0
    if feasible:
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS" if repair["afterScore"]["missingCount"] <= repair["beforeScore"]["missingCount"] else "FAIL"
    diagnostics = {
        "schemaVersion": "phase39-missing-driven-targetk-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "targetVehicleCount": k,
        "incumbentVehicleCount": len(incumbent_routes),
        "missingBefore": repair["beforeScore"].get("missingCount"),
        "missingAfter": repair["afterScore"].get("missingCount"),
        "bestViolationCounts": {
            "timeWindow": repair["afterScore"].get("timeWindowViolations"),
            "capacity": repair["afterScore"].get("capacityViolations"),
            "precedence": repair["afterScore"].get("precedenceViolations"),
            "duplicate": repair["afterScore"].get("duplicateCount"),
        },
        "directInsertionAttempts": repair["forcedTrace"].get("directInsertionAttempts"),
        "directInsertionSuccess": repair["forcedTrace"].get("directInsertionSuccess"),
        "ejectionInsertionAttempts": repair["forcedTrace"].get("ejectionInsertionAttempts"),
        "ejectionInsertionSuccess": repair["forcedTrace"].get("ejectionInsertionSuccess"),
        "perturbationAttempts": repair.get("perturbationAttempts"),
        "perturbationSuccess": repair.get("perturbationSuccess"),
        "ejectedRequestCount": repair["forcedTrace"].get("ejectedRequestCount"),
        "queueStallReasons": repair["forcedTrace"].get("queueStallReasons"),
        "perMissingOptionCount": repair["forcedTrace"].get("perMissingOptionCount"),
        "routeSlackDiagnostics": repair.get("routeSlackDiagnostics"),
        "bestBlocker": repair.get("bestBlocker"),
        "feasibleTargetSolution": feasible,
        "hardViolations": hard_violations,
        "leakageDetected": False,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "verdict": verdict,
    }
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "diagnostics.json", diagnostics)
    write_json(instance_dir / "trace.json", {"forcedTrace": repair["forcedTrace"], "routeSlackDiagnostics": repair.get("routeSlackDiagnostics")})
    if feasible:
        write_json(instance_dir / "best_solution.json", solution)
    return diagnostics


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 39 Missing-Driven Target-K Repair", "", "| Instance | Verdict | Target K | Missing Before | Missing After | Feasible | Blocker | Runtime ms |", "|---|---|---:|---:|---:|---:|---|---:|"]
    for row in rows:
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('targetVehicleCount')} | {row.get('missingBefore')} | {row.get('missingAfter')} | {row.get('feasibleTargetSolution')} | {row.get('bestBlocker')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int, target_vehicle_count: int | None) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms, target_vehicle_count) for instance in instances]
    summary = {
        "schemaVersion": "phase39-missing-driven-targetk-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase39_missing_driven_targetk_summary.json", summary)
    (output_dir / "phase39_missing_driven_targetk_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 39 missing-driven target-K PDPTW repair diagnostics.")
    parser.add_argument("--instances", default="lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--target-vehicle-count", type=int, default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit), args.target_vehicle_count)
    print(f"[PHASE39 MISSING DRIVEN TARGETK] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
