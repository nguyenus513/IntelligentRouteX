from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase40_natural_pdptw_optimizer import natural_solution_key, objective_components, objective_config, write_json
from run_phase56b_stable_promoted_runner import canonicalize_solution, run as run_stable_promoted, solution_signature


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAP_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase59-vroom-gap-analyzer-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase60a-bounded-distance-polish-v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def request_pairs(instance: Dict[str, Any]) -> List[Tuple[str, str]]:
    return sorted((str(request.get("pickupNodeId")), str(request.get("dropoffNodeId"))) for request in instance.get("requests", []))


def route_pairs(instance: Dict[str, Any], route: List[str]) -> List[Tuple[str, str]]:
    normalized = [str(stop) for stop in route]
    pairs = []
    for pickup, dropoff in request_pairs(instance):
        if pickup in normalized and dropoff in normalized and normalized.index(pickup) < normalized.index(dropoff):
            pairs.append((pickup, dropoff))
    return sorted(pairs)


def exact_pair_coverage(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    missing = []
    duplicate = []
    incomplete = []
    for pickup, dropoff in request_pairs(instance):
        count = 0
        for route in routes:
            has_pickup = pickup in route
            has_dropoff = dropoff in route
            if has_pickup or has_dropoff:
                if has_pickup and has_dropoff and route.index(pickup) < route.index(dropoff):
                    count += 1
                else:
                    incomplete.append((pickup, dropoff))
        if count == 0:
            missing.append((pickup, dropoff))
        if count > 1:
            duplicate.append((pickup, dropoff))
    return {"valid": not missing and not duplicate and not incomplete, "missing": missing, "duplicate": duplicate, "incomplete": incomplete}


def stable_candidate_key(instance: Dict[str, Any], solution: Dict[str, Any], config: Any) -> Tuple[int, float, float, str]:
    components = objective_components(instance, solution, config)
    return (
        int(components.get("vehicleCount", 0) or 0),
        round(float(components.get("objective", 0.0) or 0.0), 6),
        round(float(components.get("totalDistance", 0.0) or 0.0), 6),
        solution_signature(instance, solution),
    )


def without_pair(route: List[str], pair: Tuple[str, str]) -> List[str]:
    pickup, dropoff = pair
    return [stop for stop in route if stop not in {pickup, dropoff}]


def insert_pair(route: List[str], pair: Tuple[str, str], pickup_index: int, dropoff_index: int) -> List[str]:
    pickup, dropoff = pair
    candidate = list(route)
    candidate.insert(pickup_index, pickup)
    candidate.insert(dropoff_index, dropoff)
    return candidate


def route_insertions(route: List[str], pair: Tuple[str, str], max_positions: int) -> List[List[str]]:
    insertions = []
    inner_limit = max(1, len(route))
    for pickup_index in range(1, max(1, inner_limit)):
        for dropoff_index in range(pickup_index + 1, min(len(route) + 1, pickup_index + 2 + max_positions)):
            insertions.append(insert_pair(route, pair, pickup_index, dropoff_index))
            if len(insertions) >= max_positions:
                return insertions
    return insertions


def validate_candidate(instance: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, str]:
    coverage = exact_pair_coverage(instance, candidate)
    if not coverage.get("valid"):
        return False, "coverage-invalid"
    checked = check_solution(instance, candidate)
    if not checked.get("feasible"):
        return False, "hard-violation"
    return True, "ok"


def try_candidate(
    instance: Dict[str, Any],
    config: Any,
    current: Dict[str, Any],
    candidate: Dict[str, Any],
    current_key: Tuple[int, float, float, str],
    reject_reasons: Dict[str, int],
) -> Tuple[Dict[str, Any] | None, Tuple[int, float, float, str] | None, str]:
    candidate = canonicalize_solution(instance, candidate)
    valid, reason = validate_candidate(instance, candidate)
    if not valid:
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
        return None, None, reason
    key = stable_candidate_key(instance, candidate, config)
    if key[0] > current_key[0]:
        reject_reasons["vehicle-count-regression"] = reject_reasons.get("vehicle-count-regression", 0) + 1
        return None, None, "vehicle-count-regression"
    if natural_solution_key(instance, candidate, config) >= natural_solution_key(instance, current, config):
        reject_reasons["objective-not-improved"] = reject_reasons.get("objective-not-improved", 0) + 1
        return None, None, "objective-not-improved"
    return candidate, key, "accepted"


def bounded_distance_polish(
    instance: Dict[str, Any],
    solution: Dict[str, Any],
    mode: str,
    max_runtime_ms: int = 2_000,
    max_candidate_checks: int = 500,
    max_routes_considered: int = 8,
    max_pairs_per_route: int = 10,
    deterministic_seed: int = 60,
) -> Dict[str, Any]:
    started = time.perf_counter()
    config = objective_config(mode)
    current = canonicalize_solution(instance, solution)
    current_key = stable_candidate_key(instance, current, config)
    best = current
    best_key = current_key
    before_components = objective_components(instance, current, config)
    reject_reasons: Dict[str, int] = {}
    candidate_checks = 0
    feasible_candidates = 0

    def time_remaining() -> bool:
        return (time.perf_counter() - started) * 1000 < max_runtime_ms

    def consider(candidate_routes: List[List[str]]) -> None:
        nonlocal candidate_checks, feasible_candidates, best, best_key
        if candidate_checks >= max_candidate_checks or not time_remaining():
            return
        candidate_checks += 1
        candidate = {"schemaVersion": current.get("schemaVersion", "external-benchmark-solution/v1"), "solver": "phase60a-bounded-distance-polish", "routes": candidate_routes}
        accepted, key, reason = try_candidate(instance, config, current, candidate, current_key, reject_reasons)
        if reason not in {"coverage-invalid", "hard-violation"}:
            feasible_candidates += 1
        if accepted is not None and key is not None and key < best_key:
            best = accepted
            best_key = key

    routes = [[str(stop) for stop in route] for route in current.get("routes", []) if len(route) > 2]
    ordered_route_indexes = sorted(range(len(routes)), key=lambda index: (route_distance(instance, routes[index]), tuple(routes[index])))[:max_routes_considered]

    for route_index in ordered_route_indexes:
        route = routes[route_index]
        for start in range(1, max(1, len(route) - 2)):
            for end in range(start + 1, len(route) - 1):
                if candidate_checks >= max_candidate_checks or not time_remaining():
                    break
                candidate_routes = [list(candidate_route) for candidate_route in routes]
                candidate_routes[route_index] = route[:start] + list(reversed(route[start : end + 1])) + route[end + 1 :]
                consider(candidate_routes)

    for source_index in ordered_route_indexes:
        pairs = route_pairs(instance, routes[source_index])[:max_pairs_per_route]
        for pair in pairs:
            stripped_source = without_pair(routes[source_index], pair)
            for target_index in ordered_route_indexes:
                if candidate_checks >= max_candidate_checks or not time_remaining():
                    break
                base_target = stripped_source if target_index == source_index else routes[target_index]
                for inserted_target in route_insertions(base_target, pair, max_pairs_per_route):
                    candidate_routes = [list(candidate_route) for candidate_route in routes]
                    candidate_routes[source_index] = stripped_source
                    candidate_routes[target_index] = inserted_target
                    candidate_routes = [route for route in candidate_routes if len(route) > 2]
                    consider(candidate_routes)

    for left_index in ordered_route_indexes:
        for right_index in ordered_route_indexes:
            if right_index <= left_index:
                continue
            left_pairs = route_pairs(instance, routes[left_index])[:max_pairs_per_route]
            right_pairs = route_pairs(instance, routes[right_index])[:max_pairs_per_route]
            for left_pair in left_pairs:
                for right_pair in right_pairs:
                    if candidate_checks >= max_candidate_checks or not time_remaining():
                        break
                    left_base = without_pair(routes[left_index], left_pair)
                    right_base = without_pair(routes[right_index], right_pair)
                    for left_inserted in route_insertions(left_base, right_pair, 2):
                        for right_inserted in route_insertions(right_base, left_pair, 2):
                            candidate_routes = [list(candidate_route) for candidate_route in routes]
                            candidate_routes[left_index] = left_inserted
                            candidate_routes[right_index] = right_inserted
                            consider(candidate_routes)

    after_components = objective_components(instance, best, config)
    accepted = solution_signature(instance, best) != solution_signature(instance, current)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    return {
        "solution": best,
        "diagnostics": {
            "distancePolishAttempted": True,
            "deterministicSeed": deterministic_seed,
            "candidateChecks": candidate_checks,
            "feasibleCandidates": feasible_candidates,
            "acceptedCandidates": 1 if accepted else 0,
            "bestDistanceDelta": float(after_components.get("totalDistance", 0.0) or 0.0) - float(before_components.get("totalDistance", 0.0) or 0.0),
            "bestObjectiveDelta": float(after_components.get("objective", 0.0) or 0.0) - float(before_components.get("objective", 0.0) or 0.0),
            "rejectReasons": reject_reasons,
            "runtimeMs": runtime_ms,
            "initialSignature": solution_signature(instance, current),
            "finalSignature": solution_signature(instance, best),
        },
    }


def gap_instances(gap_dir: Path) -> List[str]:
    summary = read_json(gap_dir / "phase59_vroom_gap_summary.json")
    return [str(row.get("instance")) for row in summary.get("rows", []) if row.get("gapClassification") == "vroom-quality-win-distance"]


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()] if args.instances else gap_instances(Path(args.gap_artifact_dir))
    stable_dir = output_dir / "phase56f_base"
    stable_summary = run_stable_promoted(instances, stable_dir, args.data_source, parse_time_limit(args.time_limit), args.mode, repeat=args.repeat, stable_incumbent_replay=True, deterministic_seed=args.deterministic_seed)
    rows = []
    for instance_name in instances:
        instance = parse_instance("li-lim", resolve_instance_path("li-lim", instance_name, args.data_source))
        base_solution_path = stable_dir / instance_name / "final_solution.json"
        base_solution = read_json(base_solution_path)
        polish = bounded_distance_polish(instance, base_solution, args.mode, args.max_runtime_ms, args.max_candidate_checks, args.max_routes_considered, args.max_pairs_per_route, args.deterministic_seed)
        final_solution = polish["solution"]
        final_checked = check_solution(instance, final_solution)
        base_components = objective_components(instance, base_solution, objective_config(args.mode))
        final_components = objective_components(instance, final_solution, objective_config(args.mode))
        row = {
            "instance": instance.get("instanceName", instance_name),
            "baseVehicleCount": base_components.get("vehicleCount"),
            "finalVehicleCount": final_components.get("vehicleCount"),
            "baseDistance": base_components.get("totalDistance"),
            "finalDistance": final_components.get("totalDistance"),
            "baseObjective": base_components.get("objective"),
            "finalObjective": final_components.get("objective"),
            "hardViolations": 0 if final_checked.get("feasible") else len(final_checked.get("violations", [])),
            "overBudget": False,
            "objectiveRegressionAccepted": float(final_components.get("objective", 0.0) or 0.0) > float(base_components.get("objective", 0.0) or 0.0),
            "distanceImproved": float(final_components.get("totalDistance", 0.0) or 0.0) < float(base_components.get("totalDistance", 0.0) or 0.0),
            "diagnostics": polish["diagnostics"],
        }
        write_json(output_dir / instance_name / "final_solution.json", final_solution)
        write_json(output_dir / instance_name / "diagnostics.json", row)
        rows.append(row)
    gate = phase60a_gate(rows, stable_summary)
    summary = {"schemaVersion": "phase60a-bounded-distance-polish/v1", "instances": instances, "baseRunner": "phase56f-stable-certification", "rows": rows, "gate": gate}
    write_json(output_dir / "phase60a_bounded_distance_polish_summary.json", summary)
    (output_dir / "phase60a_bounded_distance_polish_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def phase60a_gate(rows: List[Dict[str, Any]], stable_summary: Dict[str, Any]) -> Dict[str, Any]:
    safety_clean = all(int(row.get("hardViolations", 0) or 0) == 0 and not row.get("overBudget") and not row.get("objectiveRegressionAccepted") for row in rows)
    stable_clean = stable_summary.get("phase56bGate", {}).get("verdict") == "PASS"
    any_distance_improved = any(row.get("distanceImproved") for row in rows)
    verdict = "FAIL"
    if safety_clean and stable_clean and any_distance_improved:
        verdict = "PASS_STRONG"
    elif safety_clean and stable_clean:
        verdict = "PASS"
    return {"verdict": verdict, "safetyClean": safety_clean, "stableBaseGate": stable_summary.get("phase56bGate", {}).get("verdict"), "anyDistanceImproved": any_distance_improved}


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 60A Bounded Distance Polish", "", f"Gate: **{summary['gate']['verdict']}**", "", "| Instance | Vehicles | Distance | Objective | Accepted | Checks |", "|---|---:|---:|---:|---:|---:|"]
    for row in summary.get("rows", []):
        diagnostics = row.get("diagnostics", {})
        lines.append(f"| {row['instance']} | {row['baseVehicleCount']} -> {row['finalVehicleCount']} | {row['baseDistance']} -> {row['finalDistance']} | {row['baseObjective']} -> {row['finalObjective']} | {diagnostics.get('acceptedCandidates')} | {diagnostics.get('candidateChecks')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded distance polish on Phase 56F stable solutions for VROOM distance-gap cases.")
    parser.add_argument("--instances", default="")
    parser.add_argument("--gap-artifact-dir", default=str(DEFAULT_GAP_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-runtime-ms", type=int, default=2_000)
    parser.add_argument("--max-candidate-checks", type=int, default=500)
    parser.add_argument("--max-routes-considered", type=int, default=8)
    parser.add_argument("--max-pairs-per-route", type=int, default=10)
    parser.add_argument("--deterministic-seed", type=int, default=60)
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE60A BOUNDED DISTANCE POLISH] wrote {args.output_dir}")
    return 0 if summary["gate"]["verdict"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
