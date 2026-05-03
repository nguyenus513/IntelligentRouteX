from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution
from parse_solomon_vrptw import parse_solomon
from run_academic_max_quality import append_route_to_pool, parse_duration_ms, set_partitioning_solution, write_json
from run_phase13_hgs_route_pool_targets import instance_path
from time_window_giant_split import split_candidates

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase18-time-window-restructuring-v1"
DEFAULT_SEED_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase17-route-pool-quality-v1"


def load_seed(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_dir = seed_dir / "solomon" / "RC101"
    solution = json.loads((case_dir / "solution.json").read_text(encoding="utf-8"))
    route_pool = json.loads((case_dir / "route_pool.json").read_text(encoding="utf-8")).get("routes", [])
    metrics = json.loads((case_dir / "metrics.json").read_text(encoding="utf-8"))
    return solution, list(route_pool), metrics


def solution_key(instance: dict[str, Any], solution: dict[str, Any]) -> tuple[int, int, float]:
    checked = check_solution(instance, solution)
    return 0 if checked.get("feasible") else 1, int(checked.get("vehicleCount", 10**9)), float(checked.get("totalDistance", 1e18))


def run_rc101(output_dir: Path, seed_dir: Path, time_limit_ms: int, data_source: str) -> dict[str, Any]:
    started = time.perf_counter()
    suite = "solomon"
    instance_name = "RC101"
    instance = parse_solomon(instance_path(suite, instance_name, data_source))
    seed_solution, route_pool, seed_metrics = load_seed(seed_dir)
    before_size = len(route_pool)
    splits = split_candidates(instance, route_pool)
    imported_routes = 0
    split_solutions = []
    for split in splits:
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": f"phase18-giant-split:{split['strategy']}", "routes": split["routes"]}
        split_solutions.append(solution)
        for route in split["routes"]:
            if append_route_to_pool(instance, route_pool, route, f"phase18-giant-split:{split['strategy']}"):
                imported_routes += 1
    sp_solution = set_partitioning_solution(instance, route_pool, max(1_000, min(5_000, time_limit_ms // 3))) if route_pool else None
    candidates = [seed_solution] + split_solutions
    if sp_solution is not None:
        candidates.append(sp_solution)
    best_solution = min(candidates, key=lambda solution: solution_key(instance, solution))
    checked = check_solution(instance, best_solution)
    bks = instance.get("bestKnown", {})
    best_split = splits[0] if splits else None
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
        "routePoolSizeBefore": before_size,
        "routePoolSizeAfter": len(route_pool),
        "setPartitioningProducedSolution": sp_solution is not None,
        "giantTourCount": len(splits),
        "splitCandidateCount": len(splits),
        "splitFeasibleCount": len(splits),
        "bestSplitStrategy": None if best_split is None else best_split.get("strategy"),
        "bestSplitVehicleCount": None if best_split is None else best_split.get("vehicleCount"),
        "bestSplitDistance": None if best_split is None else best_split.get("totalDistance"),
        "splitDiagnostics": splits[:10],
        "importedSplitRoutes": imported_routes,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
    }
    case_dir = output_dir / suite / instance_name
    write_json(case_dir / "solution.json", best_solution)
    write_json(case_dir / "route_pool.json", {"routes": route_pool})
    write_json(case_dir / "metrics.json", row)
    return row


def run_phase18(output_dir: Path, seed_dir: Path, time_limit_ms: int, data_source: str) -> dict[str, Any]:
    row = run_rc101(output_dir, seed_dir, time_limit_ms, data_source)
    result = {"schemaVersion": "phase18-time-window-restructuring-results/v1", "results": [row]}
    write_json(output_dir / "phase18_time_window_restructuring_results.json", result)
    (output_dir / "phase18_time_window_restructuring_report.md").write_text(markdown([row]), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 18 Time-Window Restructuring Report",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Pool Before/After | Splits | Best Split | SP | Runtime |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedVehicleGap')}/{row.get('vehicleGap')} | "
            f"{row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | {row.get('splitCandidateCount')} | "
            f"{row.get('bestSplitVehicleCount')} | {row.get('setPartitioningProducedSolution')} | {row.get('runtimeMs')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 18 time-window-aware restructuring.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR))
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    args = parser.parse_args(argv)
    result = run_phase18(Path(args.output_dir), Path(args.seed_dir), parse_duration_ms(args.time_limit), args.data_source)
    print(f"[PHASE18 TIME WINDOW RESTRUCTURING] wrote {args.output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
