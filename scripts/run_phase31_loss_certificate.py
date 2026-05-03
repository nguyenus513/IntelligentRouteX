from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from academic_global_consolidation import PairInsertionIndex
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase31-loss-certificate-v1"
DEFAULT_TARGETS = ["lrc202", "lrc206"]


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def active_routes(solution: Dict[str, Any]) -> List[List[str]]:
    return [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]


def request_pairs(instance: Dict[str, Any]) -> List[tuple[str, str]]:
    return [(str(request["pickupNodeId"]), str(request["dropoffNodeId"])) for request in instance.get("requests", [])]


def pairs_in_route(route: List[str], pairs: List[tuple[str, str]]) -> List[tuple[str, str]]:
    route_set = set(route)
    return [(pickup, dropoff) for pickup, dropoff in pairs if pickup in route_set and dropoff in route_set]


def select_weak_route(instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]]) -> int:
    candidates = [index for index, route in enumerate(routes) if pairs_in_route(route, pairs)]
    if not candidates:
        return -1
    return min(candidates, key=lambda index: (len(pairs_in_route(routes[index], pairs)), route_distance(instance, routes[index])))


def pair_direct_distance(instance: Dict[str, Any], pair: tuple[str, str]) -> float:
    return route_distance(instance, [pair[0], pair[1]])


def related_pairs(instance: Dict[str, Any], routes: List[List[str]], weak_route_index: int, base_pairs: List[tuple[str, str]], pairs: List[tuple[str, str]], limit: int) -> List[tuple[str, str]]:
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}

    def euclidean(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        return ((float(left.get("x", 0.0)) - float(right.get("x", 0.0))) ** 2 + (float(left.get("y", 0.0)) - float(right.get("y", 0.0))) ** 2) ** 0.5

    def score(pair: tuple[str, str]) -> float:
        pickup = nodes.get(pair[0], {})
        dropoff = nodes.get(pair[1], {})
        best = 1e18
        for base_pickup_id, base_dropoff_id in base_pairs:
            base_pickup = nodes.get(base_pickup_id, {})
            base_dropoff = nodes.get(base_dropoff_id, {})
            proximity = euclidean(pickup, base_pickup) + euclidean(dropoff, base_dropoff)
            ready_gap = abs(float(pickup.get("readyTime", 0.0)) - float(base_pickup.get("readyTime", 0.0)))
            due_gap = abs(float(dropoff.get("dueTime", 0.0)) - float(base_dropoff.get("dueTime", 0.0)))
            best = min(best, proximity + 0.01 * ready_gap + 0.01 * due_gap)
        return best

    base_set = set(base_pairs)
    candidates: List[tuple[float, tuple[str, str]]] = []
    for route_index, route in enumerate(routes):
        if route_index == weak_route_index:
            continue
        for pair in pairs_in_route(route, pairs):
            if pair not in base_set:
                candidates.append((score(pair), pair))
    candidates.sort(key=lambda item: item[0])
    return [pair for _, pair in candidates[:limit]]


def partial_routes_after_removal(instance: Dict[str, Any], routes: List[List[str]], removed_pairs: List[tuple[str, str]], target_vehicle_count: int) -> List[List[str]]:
    removed_stops = {stop for pair in removed_pairs for stop in pair}
    partial_routes = []
    for route in routes:
        reduced = [stop for stop in route if stop not in removed_stops]
        if len(reduced) > 2:
            partial_routes.append(reduced)
    depot = str(instance.get("depotNodeId", "0"))
    while len(partial_routes) < max(1, target_vehicle_count):
        partial_routes.append([depot, depot])
    return partial_routes[: max(1, target_vehicle_count)]


def pair_option_stats(instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]], route_shortlist: int, max_candidate_checks: int) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    feasible_route_counts: Dict[str, int] = {}
    candidate_checks = 0
    candidate_cap_hit = False
    measured_pairs: List[str] = []
    unmeasured_pairs_due_to_cap: List[str] = []
    for index_in_pairs, pair in enumerate(pairs):
        if candidate_checks >= max_candidate_checks:
            candidate_cap_hit = True
            unmeasured_pairs_due_to_cap.extend(f"{pickup}->{dropoff}" for pickup, dropoff in pairs[index_in_pairs:])
            break
        remaining_checks = max_candidate_checks - candidate_checks
        index = PairInsertionIndex.build(instance, routes, max_candidate_checks=remaining_checks, max_routes=route_shortlist, max_positions_per_route=96)
        options = index.options_for_pair(pair, top_k=128)
        candidate_checks += index.candidate_checks
        pair_key = f"{pair[0]}->{pair[1]}"
        measured_pairs.append(pair_key)
        counts[pair_key] = len(options)
        feasible_route_counts[pair_key] = len({option.route_index for option in options})
        if candidate_checks >= max_candidate_checks:
            candidate_cap_hit = True
            unmeasured_pairs_due_to_cap.extend(f"{pickup}->{dropoff}" for pickup, dropoff in pairs[index_in_pairs + 1:])
            break
    values = list(counts.values())
    zero_option_pairs = [pair for pair, count in counts.items() if count == 0]
    measured_pair_count = len(measured_pairs)
    total_pair_count = len(pairs)
    return {
        "routeShortlist": route_shortlist,
        "pairOptionCounts": counts,
        "feasibleRouteCounts": feasible_route_counts,
        "measuredPairs": measured_pairs,
        "measuredPairCount": measured_pair_count,
        "totalPairCount": total_pair_count,
        "unmeasuredPairsDueToCap": unmeasured_pairs_due_to_cap,
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
        "zeroOptionPairs": zero_option_pairs,
        "zeroOptionPairCount": len(zero_option_pairs),
        "candidateChecks": candidate_checks,
        "candidateCapHit": candidate_cap_hit,
        "measurementComplete": measured_pair_count == total_pair_count and not candidate_cap_hit,
    }


def rejection_probe(instance: Dict[str, Any], routes: List[List[str]], pairs: List[tuple[str, str]], max_candidate_checks: int = 300) -> Dict[str, int]:
    reasons = {"time-window": 0, "capacity": 0, "precedence": 0, "candidate-cap": 0, "feasible": 0}
    checks = 0
    for pair in pairs:
        pickup, dropoff = pair
        for route in routes:
            baseline_checks = checks
            for pickup_pos in range(1, len(route)):
                for dropoff_pos in range(pickup_pos, len(route)):
                    if checks >= max_candidate_checks:
                        reasons["candidate-cap"] += 1
                        return reasons
                    candidate = route[:pickup_pos] + [pickup] + route[pickup_pos:dropoff_pos] + [dropoff] + route[dropoff_pos:]
                    checked = check_solution(instance, {"routes": [candidate]})
                    checks += 1
                    if checked.get("feasible"):
                        reasons["feasible"] += 1
                    elif checked.get("timeWindowViolationCount", 0) > 0:
                        reasons["time-window"] += 1
                    elif checked.get("capacityViolationCount", 0) > 0:
                        reasons["capacity"] += 1
                    elif checked.get("pickupBeforeDropoffViolationCount", 0) > 0:
                        reasons["precedence"] += 1
            if checks - baseline_checks >= max_candidate_checks:
                break
    return reasons


def classify_blocker(shortlist_sensitivity: List[Dict[str, Any]], reject_reasons: Dict[str, int], state_cap_hit: bool, runtime_cap_hit: bool) -> str:
    if runtime_cap_hit and state_cap_hit:
        return "search-budget-cap"
    if runtime_cap_hit:
        return "runtime-cap"
    if state_cap_hit:
        return "state-cap"
    current_zero = int(shortlist_sensitivity[0].get("zeroOptionPairCount", 0)) if shortlist_sensitivity else 0
    all_zero = int(shortlist_sensitivity[-1].get("zeroOptionPairCount", 0)) if shortlist_sensitivity else current_zero
    if current_zero > all_zero:
        return "over-pruning"
    if all_zero > 0 and reject_reasons.get("capacity", 0) > reject_reasons.get("time-window", 0):
        return "capacity-block"
    if all_zero > 0 and reject_reasons.get("time-window", 0) > 0:
        return "true-time-window-block"
    if all_zero > 0:
        return "pool-missing"
    if reject_reasons.get("candidate-cap", 0) > 0:
        return "state-cap"
    return "pool-missing"


def secondary_blockers(primary_blocker: str, state_cap_hit: bool, runtime_cap_hit: bool) -> List[str]:
    blockers = []
    if runtime_cap_hit and primary_blocker != "runtime-cap":
        blockers.append("runtime-cap")
    if state_cap_hit and primary_blocker != "state-cap":
        blockers.append("state-cap")
    return blockers


def build_loss_certificate(instance: Dict[str, Any], solution: Dict[str, Any], current_route_shortlist: int = 4, max_removed_pairs: int = 12, max_candidate_checks: int = 2_000, runtime_cap_ms: int = 2_000) -> Dict[str, Any]:
    started = time.perf_counter()
    checked = check_solution(instance, solution)
    routes = active_routes(solution)
    pairs = request_pairs(instance)
    weak_route_index = select_weak_route(instance, routes, pairs)
    if weak_route_index < 0:
        return {
            "schemaVersion": "phase31-loss-certificate/v1",
            "instance": instance.get("instanceName"),
            "blocker": "pool-missing",
            "reason": "no-weak-route-with-pairs",
        }
    base_pairs = pairs_in_route(routes[weak_route_index], pairs)
    related = related_pairs(instance, routes, weak_route_index, base_pairs, pairs, max(0, max_removed_pairs - len(base_pairs)))
    removed_pairs = (base_pairs + related)[:max_removed_pairs]
    target_vehicle_count = max(1, int(checked.get("vehicleCount", len(routes))) - 1)
    partial_routes = partial_routes_after_removal(instance, routes, removed_pairs, target_vehicle_count)
    all_shortlist = max(1, len(partial_routes))
    shortlist_values = []
    for value in [current_route_shortlist, 12, 32, all_shortlist]:
        if value not in shortlist_values:
            shortlist_values.append(value)
    shortlist_sensitivity = [pair_option_stats(instance, partial_routes, removed_pairs, min(value, all_shortlist), max_candidate_checks) for value in shortlist_values]
    reject_reasons = rejection_probe(instance, partial_routes, removed_pairs, max_candidate_checks=min(500, max_candidate_checks))
    destroy_sensitivity = []
    neighbor_pairs = related_pairs(instance, routes, weak_route_index, base_pairs, pairs, 32)
    for neighbor_count in range(0, 4):
        probe_pairs = (base_pairs + neighbor_pairs[:neighbor_count])[:max_removed_pairs]
        probe_routes = partial_routes_after_removal(instance, routes, probe_pairs, target_vehicle_count)
        stats = pair_option_stats(instance, probe_routes, probe_pairs, min(all_shortlist, 32), max_candidate_checks)
        destroy_sensitivity.append({
            "destroyedNeighborRoutesApprox": neighbor_count,
            "removedPairCount": len(probe_pairs),
            "zeroOptionPairCount": stats["zeroOptionPairCount"],
            "minOptionCount": stats["min"],
            "hasPerPairInsertionCoverage": stats["zeroOptionPairCount"] == 0,
        })
    state_cap_hit = any(stats.get("candidateCapHit") for stats in shortlist_sensitivity)
    runtime_cap_hit = int((time.perf_counter() - started) * 1000) >= runtime_cap_ms
    blocker = classify_blocker(shortlist_sensitivity, reject_reasons, state_cap_hit, runtime_cap_hit)
    secondary = secondary_blockers(blocker, state_cap_hit, runtime_cap_hit)
    return {
        "schemaVersion": "phase31-loss-certificate/v1",
        "instance": instance.get("instanceName"),
        "incumbentVehicleCount": int(checked.get("vehicleCount", len(routes))),
        "targetVehicleCount": target_vehicle_count,
        "weakRouteIndex": weak_route_index,
        "removedPairs": [f"{pickup}->{dropoff}" for pickup, dropoff in removed_pairs],
        "relatedPairs": [f"{pickup}->{dropoff}" for pickup, dropoff in related],
        "pairOptionStats": shortlist_sensitivity[0],
        "rejectReasons": reject_reasons,
        "shortlistSensitivity": shortlist_sensitivity,
        "destroySensitivity": destroy_sensitivity,
        "stateCapHit": state_cap_hit,
        "runtimeCapHit": runtime_cap_hit,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "blocker": blocker,
        "primaryBlocker": blocker,
        "secondaryBlockers": secondary,
    }


def markdown(certificates: List[Dict[str, Any]]) -> str:
    lines = [
        "# Phase 31 Loss Certificate Summary",
        "",
        "| Instance | Incumbent | Target | Weak Route | Removed Pairs | Blocker | Secondary | Complete | Runtime ms |",
        "|---|---:|---:|---:|---:|---|---|---:|---:|",
    ]
    for certificate in certificates:
        pair_stats = certificate.get("pairOptionStats", {}) if isinstance(certificate.get("pairOptionStats"), dict) else {}
        lines.append(
            f"| {certificate.get('instance')} | {certificate.get('incumbentVehicleCount')} | {certificate.get('targetVehicleCount')} | {certificate.get('weakRouteIndex')} | {len(certificate.get('removedPairs', []))} | {certificate.get('primaryBlocker', certificate.get('blocker'))} | {certificate.get('secondaryBlockers', [])} | {pair_stats.get('measurementComplete')} | {certificate.get('runtimeMs')} |"
        )
    lines.extend(["", "## Notes", "", "This diagnostic rail does not affect solver output or benchmark claims."])
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    certificates = []
    for instance_name in instances:
        source_path = resolve_instance_path("li-lim", instance_name, data_source)
        instance = parse_instance("li-lim", source_path)
        solution = DispatchV2ExternalBenchmarkSolver().solve(instance, time_limit_ms, "our-dispatch-v2")
        certificate = build_loss_certificate(instance, solution)
        certificates.append(certificate)
        write_json(output_dir / f"{instance_name}_loss_certificate.json", certificate)
    summary = {
        "schemaVersion": "phase31-loss-certificate-summary/v1",
        "instances": instances,
        "certificates": certificates,
        "blockerCounts": {blocker: sum(1 for certificate in certificates if certificate.get("primaryBlocker", certificate.get("blocker")) == blocker) for blocker in sorted({str(certificate.get("primaryBlocker", certificate.get("blocker"))) for certificate in certificates})},
        "pass": all(certificate.get("primaryBlocker", certificate.get("blocker")) in {"over-pruning", "true-time-window-block", "capacity-block", "state-cap", "runtime-cap", "search-budget-cap", "pool-missing"} for certificate in certificates),
    }
    write_json(output_dir / "phase31_loss_certificate_summary.json", summary)
    (output_dir / "phase31_loss_certificate_summary.md").write_text(markdown(certificates), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 31A PDPTW loss certificate diagnostics.")
    parser.add_argument("--instances", default=",".join(DEFAULT_TARGETS))
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE31 LOSS CERTIFICATE] wrote {args.output_dir}")
    return 0 if summary.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
