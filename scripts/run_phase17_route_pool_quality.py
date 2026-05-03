from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from analyze_phase17_route_pool_gaps import analyze, route_reject_reason
from external_benchmark_support import check_solution, route_distance
from parse_solomon_vrptw import parse_solomon
from run_academic_max_quality import append_route_to_pool, parse_duration_ms, route_feasible, set_partitioning_solution, write_json
from run_phase13_hgs_route_pool_targets import instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase17-route-pool-quality-v1"
DEFAULT_SEED_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase14-pyvrp-calibration-v1"


def load_seed_artifacts(seed_dir: Path, suite: str, instance_name: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_dir = seed_dir / suite / instance_name
    solution = json.loads((case_dir / "solution.json").read_text(encoding="utf-8"))
    route_pool_payload = json.loads((case_dir / "route_pool.json").read_text(encoding="utf-8"))
    metrics = json.loads((case_dir / "metrics.json").read_text(encoding="utf-8"))
    return solution, list(route_pool_payload.get("routes", [])), metrics


def two_opt_variants(instance: dict[str, Any], route_pool: list[dict[str, Any]], max_routes: int = 80, max_segment: int = 5) -> dict[str, int]:
    attempts = successes = 0
    for route_entry in sorted(route_pool[:], key=lambda route: -len(route.get("customerSet", [])))[:max_routes]:
        route = [str(stop) for stop in route_entry.get("sequence", [])]
        if len(route) <= 5:
            continue
        for left in range(1, min(len(route) - 2, max_segment + 1)):
            for right in range(left + 1, min(len(route) - 1, left + max_segment + 1)):
                attempts += 1
                candidate = route[:left] + list(reversed(route[left:right + 1])) + route[right + 1:]
                if route_feasible(instance, candidate) and route_distance(instance, candidate) + 1e-9 < route_distance(instance, route):
                    if append_route_to_pool(instance, route_pool, candidate, "phase17-two-opt-slack-variant"):
                        successes += 1
    return {"twoOptAttempts": attempts, "twoOptSuccesses": successes}


def low_coverage_relocation_variants(instance: dict[str, Any], route_pool: list[dict[str, Any]], low_customers: Sequence[str], max_attempts: int = 500) -> dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    attempts = successes = 0
    reject_reasons: dict[str, int] = {}
    source_routes = sorted(route_pool[:], key=lambda route: float(route.get("distance", 1e18)))[:100]
    for customer in low_customers[:20]:
        for route_entry in source_routes:
            if attempts >= max_attempts:
                break
            route = [str(stop) for stop in route_entry.get("sequence", [])]
            if customer in route:
                continue
            for position in range(1, len(route)):
                attempts += 1
                candidate = route[:position] + [str(customer)] + route[position:]
                reason = route_reject_reason(instance, candidate)
                if reason == "feasible":
                    if append_route_to_pool(instance, route_pool, candidate, "phase17-low-coverage-insertion"):
                        successes += 1
                    break
                reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
                if attempts >= max_attempts:
                    break
        if attempts >= max_attempts:
            break
    return {"lowCoverageInsertionAttempts": attempts, "lowCoverageInsertionSuccesses": successes, "lowCoverageRejectReasons": reject_reasons}


def run_rc101(output_dir: Path, seed_dir: Path, time_limit_ms: int, data_source: str) -> dict[str, Any]:
    started = time.perf_counter()
    suite = "solomon"
    instance_name = "RC101"
    instance = parse_solomon(instance_path(suite, instance_name, data_source))
    seed_solution, route_pool, seed_metrics = load_seed_artifacts(seed_dir, suite, instance_name)
    before_pool_size = len(route_pool)
    before_diagnostics = analyze(instance, seed_solution, route_pool)
    expansion_counts: dict[str, Any] = {}
    expansion_counts.update(two_opt_variants(instance, route_pool))
    low_customers = before_diagnostics.get("coverage", {}).get("lowCoverageCustomers", [])
    expansion_counts.update(low_coverage_relocation_variants(instance, route_pool, low_customers))
    sp_solution = set_partitioning_solution(instance, route_pool, max(1_000, min(5_000, time_limit_ms // 3)))
    candidates = [seed_solution]
    if sp_solution is not None:
        candidates.append(sp_solution)
    best_solution = min(candidates, key=lambda solution: (0 if check_solution(instance, solution).get("feasible") else 1, int(check_solution(instance, solution).get("vehicleCount", 10**9)), float(check_solution(instance, solution).get("totalDistance", 1e18))))
    checked = check_solution(instance, best_solution)
    after_diagnostics = analyze(instance, best_solution, route_pool)
    bks = instance.get("bestKnown", {})
    row = {
        "suite": suite,
        "instance": instance_name,
        "status": "PASS" if checked.get("feasible") else "FAIL",
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "bestKnownVehicleCount": bks.get("vehicleCount"),
        "vehicleGap": max(0, int(checked.get("vehicleCount", 0)) - int(bks.get("vehicleCount", checked.get("vehicleCount", 0)) or checked.get("vehicleCount", 0))),
        "seedVehicleGap": seed_metrics.get("vehicleGap"),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "routePoolSizeBefore": before_pool_size,
        "routePoolSizeAfter": len(route_pool),
        "setPartitioningProducedSolution": sp_solution is not None,
        "expansionCounts": expansion_counts,
        "diagnosticsBefore": before_diagnostics,
        "diagnosticsAfter": after_diagnostics,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
    }
    case_dir = output_dir / suite / instance_name
    write_json(case_dir / "solution.json", best_solution)
    write_json(case_dir / "route_pool.json", {"routes": route_pool})
    write_json(case_dir / "metrics.json", row)
    return row


def run_phase17(output_dir: Path, seed_dir: Path, time_limit_ms: int, data_source: str) -> dict[str, Any]:
    row = run_rc101(output_dir, seed_dir, time_limit_ms, data_source)
    result = {"schemaVersion": "phase17-route-pool-quality-results/v1", "results": [row]}
    write_json(output_dir / "phase17_route_pool_quality_results.json", result)
    (output_dir / "phase17_route_pool_quality_report.md").write_text(markdown([row]), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 17 Route Pool Quality Report",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Pool Before/After | SP | Runtime | Expansion | Action |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedVehicleGap')}/{row.get('vehicleGap')} | "
            f"{row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | {row.get('setPartitioningProducedSolution')} | {row.get('runtimeMs')} | "
            f"{row.get('expansionCounts')} | {row.get('diagnosticsAfter', {}).get('actionableNextStep')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 17 route-pool quality diagnostics and expansion.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR))
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    args = parser.parse_args(argv)
    result = run_phase17(Path(args.output_dir), Path(args.seed_dir), parse_duration_ms(args.time_limit), args.data_source)
    print(f"[PHASE17 ROUTE POOL QUALITY] wrote {args.output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
