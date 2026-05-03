from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from external_benchmark_support import route_distance
from parse_solomon_vrptw import parse_solomon
from run_academic_max_quality import required_customers, route_feasible


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def route_reject_reason(instance: dict[str, Any], route: list[str]) -> str:
    depot = str(instance.get("depotNodeId", "0"))
    if not route or route[0] != depot or route[-1] != depot:
        return "depot-boundary"
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
    capacity = int(instance.get("capacity", 0))
    load = 0
    elapsed = 0.0
    for previous, current in zip(route, route[1:]):
        if previous not in nodes or current not in nodes:
            return "unknown-node"
        elapsed += route_distance(instance, [previous, current])
        node = nodes[current]
        ready = float(node.get("readyTime", 0.0))
        due = float(node.get("dueTime", 1e18))
        if elapsed < ready:
            elapsed = ready
        if elapsed > due + 1e-9:
            return "time-window"
        elapsed += float(node.get("serviceTime", 0.0))
        load += int(float(node.get("demand", 0)))
        if load > capacity:
            return "capacity"
        if load < 0:
            return "negative-load"
    return "feasible" if route_feasible(instance, route) else "unknown-infeasible"


def coverage_stats(instance: dict[str, Any], route_pool: Sequence[dict[str, Any]]) -> dict[str, Any]:
    customers = required_customers(instance)
    counts = Counter({customer: 0 for customer in customers})
    for route in route_pool:
        for customer in route.get("customerSet", []):
            counts[str(customer)] += 1
    values = list(counts.values())
    low_threshold = max(1, int(median(values) if values else 1) // 2)
    low = [customer for customer, count in counts.items() if count <= low_threshold]
    return {
        "customerCount": len(customers),
        "coverageMin": min(values, default=0),
        "coverageMedian": median(values) if values else 0,
        "coverageMax": max(values, default=0),
        "lowCoverageThreshold": low_threshold,
        "lowCoverageCustomers": low[:25],
        "lowCoverageCustomerCount": len(low),
    }


def route_size_histogram(route_pool: Sequence[dict[str, Any]]) -> dict[str, int]:
    histogram: Counter[str] = Counter()
    for route in route_pool:
        histogram[str(len(route.get("customerSet", [])))] += 1
    return dict(sorted(histogram.items(), key=lambda item: int(item[0])))


def merge_diagnostics(instance: dict[str, Any], route_pool: Sequence[dict[str, Any]], max_pairs: int = 200) -> dict[str, Any]:
    ordered = sorted(route_pool, key=lambda route: (len(route.get("customerSet", [])), float(route.get("distance", 1e18))))
    attempts = successes = 0
    reasons: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for left_index, left in enumerate(ordered[:50]):
        for right in ordered[left_index + 1:50]:
            if attempts >= max_pairs:
                break
            left_route = [str(stop) for stop in left.get("sequence", [])]
            right_route = [str(stop) for stop in right.get("sequence", [])]
            if not left_route or not right_route:
                continue
            depot = str(instance.get("depotNodeId", "0"))
            merged = [depot] + [stop for stop in left_route if stop != depot] + [stop for stop in right_route if stop != depot] + [depot]
            attempts += 1
            reason = route_reject_reason(instance, merged)
            if reason == "feasible":
                successes += 1
            else:
                reasons[reason] += 1
                if len(examples) < 10:
                    examples.append({
                        "leftRouteId": left.get("routeId"),
                        "rightRouteId": right.get("routeId"),
                        "leftSize": len(left.get("customerSet", [])),
                        "rightSize": len(right.get("customerSet", [])),
                        "reason": reason,
                    })
        if attempts >= max_pairs:
            break
    return {
        "mergeAttemptCount": attempts,
        "mergeSuccessCount": successes,
        "mergeRejectReasons": dict(reasons.most_common()),
        "mergeRejectExamples": examples,
    }


def analyze(instance: dict[str, Any], solution: dict[str, Any], route_pool: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected_routes = solution.get("routes", []) if isinstance(solution.get("routes"), list) else []
    diagnostics = {
        "schemaVersion": "phase17-route-pool-diagnostics/v1",
        "instance": instance.get("instanceName"),
        "problemType": instance.get("problemType"),
        "routePoolSize": len(route_pool),
        "selectedRouteCount": len([route for route in selected_routes if len(route) > 2]),
        "routeSizeHistogram": route_size_histogram(route_pool),
        "coverage": coverage_stats(instance, route_pool),
        "mergeDiagnostics": merge_diagnostics(instance, route_pool),
    }
    if diagnostics["coverage"]["lowCoverageCustomerCount"] > 0:
        diagnostics["actionableNextStep"] = "expand-low-coverage-customer-route-variants"
    elif diagnostics["mergeDiagnostics"]["mergeRejectReasons"]:
        diagnostics["actionableNextStep"] = "target-top-merge-reject-reason"
    else:
        diagnostics["actionableNextStep"] = "increase-route-pool-diversification"
    return diagnostics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Phase 17 route-pool gaps for a VRPTW instance.")
    parser.add_argument("--instance-path", required=True)
    parser.add_argument("--solution-path", required=True)
    parser.add_argument("--route-pool-path", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    instance = parse_solomon(Path(args.instance_path))
    solution = json.loads(Path(args.solution_path).read_text(encoding="utf-8"))
    route_pool_payload = json.loads(Path(args.route_pool_path).read_text(encoding="utf-8"))
    route_pool = route_pool_payload.get("routes", route_pool_payload if isinstance(route_pool_payload, list) else [])
    report = analyze(instance, solution, route_pool)
    output_dir = Path(args.output_dir)
    write_json(output_dir / "phase17_route_pool_diagnostics.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
