from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution
from parse_solomon_vrptw import parse_solomon
from reference_solution_loader import find_reference_solution, load_reference_solution
from run_academic_max_quality import append_route_to_pool, set_partitioning_solution, solution_key, write_json
from run_phase13_hgs_route_pool_targets import instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase23-reference-import-v1"
DEFAULT_SEED_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase20-reference-offline-v1"


def load_seed(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_dir = seed_dir / "solomon" / "RC101"
    solution = json.loads((case_dir / "solution.json").read_text(encoding="utf-8"))
    route_pool = json.loads((case_dir / "route_pool.json").read_text(encoding="utf-8")).get("routes", [])
    metrics = json.loads((case_dir / "metrics.json").read_text(encoding="utf-8"))
    return solution, list(route_pool), metrics


def normalize_routes(solution: dict[str, Any], depot: str = "0") -> dict[str, Any]:
    routes = []
    for route in solution.get("routes", []):
        stops = [str(stop) for stop in route]
        if not stops:
            continue
        if stops[0] != depot:
            stops = [depot] + stops
        if stops[-1] != depot:
            stops = stops + [depot]
        if len(stops) > 2:
            routes.append(stops)
    normalized = dict(solution)
    normalized["routes"] = routes
    return normalized


def customer_diagnostics(instance: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    required = {str(node["id"]) for node in instance.get("nodes", []) if str(node["id"]) != depot}
    visits = [str(stop) for route in solution.get("routes", []) for stop in route if str(stop) != depot]
    visit_counts: dict[str, int] = {}
    for stop in visits:
        visit_counts[stop] = visit_counts.get(stop, 0) + 1
    missing = sorted(required - set(visits), key=lambda value: int(value) if value.isdigit() else value)
    duplicate = sorted([customer for customer, count in visit_counts.items() if count > 1], key=lambda value: int(value) if value.isdigit() else value)
    unknown = sorted(set(visits) - required, key=lambda value: int(value) if value.isdigit() else value)
    return {
        "requiredCustomerCount": len(required),
        "visitedCustomerCount": len(set(visits) & required),
        "missingCustomerCount": len(missing),
        "duplicateCustomerCount": len(duplicate),
        "unknownCustomerCount": len(unknown),
        "missingCustomers": missing[:25],
        "duplicateCustomers": duplicate[:25],
        "unknownCustomers": unknown[:25],
    }


def evaluate_solution(instance: dict[str, Any], solution: dict[str, Any], label: str) -> dict[str, Any]:
    checked = check_solution(instance, solution)
    return {
        "label": label,
        "solution": solution,
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "checked": checked,
    }


def import_routes(instance: dict[str, Any], route_pool: list[dict[str, Any]], solution: dict[str, Any], source: str) -> int:
    imported = 0
    for route in solution.get("routes", []):
        if append_route_to_pool(instance, route_pool, [str(stop) for stop in route], source):
            imported += 1
    return imported


def resolve_reference(instance_name: str, explicit_reference: str | None) -> dict[str, Any] | None:
    if explicit_reference:
        path = Path(explicit_reference)
        if path.exists():
            return load_reference_solution(path)
        return None
    return find_reference_solution(instance_name, REPO_ROOT)


def run_phase23(instance_name: str, data_source: str, reference: str | None, seed_dir: Path, output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    instance = parse_solomon(instance_path("solomon", instance_name, data_source))
    seed_solution, route_pool, seed_metrics = load_seed(seed_dir)
    route_pool_before = len(route_pool)
    candidates = [evaluate_solution(instance, seed_solution, "phase23-seed-incumbent")]
    reference_solution = resolve_reference(instance_name, reference)
    reference_available = reference_solution is not None
    reference_import_count = 0
    reference_eval = None
    reference_customer_diagnostics = None
    if reference_solution is not None:
        reference_solution = normalize_routes(reference_solution, str(instance.get("depotNodeId", "0")))
        reference_customer_diagnostics = customer_diagnostics(instance, reference_solution)
        reference_eval = evaluate_solution(instance, reference_solution, "phase23-reference-route")
        candidates.append(reference_eval)
        if reference_eval["feasible"]:
            reference_import_count = import_routes(instance, route_pool, reference_solution, "phase23-reference-route")
    sp_solution = set_partitioning_solution(instance, route_pool, 5_000) if route_pool else None
    if sp_solution is not None:
        candidates.append(evaluate_solution(instance, sp_solution, "phase23-set-partitioning-reference-pool"))
    best = min(candidates, key=solution_key)
    checked = best["checked"]
    bks = instance.get("bestKnown", {})
    row = {
        "suite": "solomon",
        "instance": instance_name,
        "status": "PASS" if checked.get("feasible") else "FAIL",
        "feasible": checked.get("feasible"),
        "vehicleCount": checked.get("vehicleCount"),
        "bestKnownVehicleCount": bks.get("vehicleCount"),
        "vehicleGap": max(0, int(checked.get("vehicleCount", 0)) - int(bks.get("vehicleCount", checked.get("vehicleCount", 0)) or checked.get("vehicleCount", 0))),
        "seedVehicleGap": seed_metrics.get("vehicleGap"),
        "totalDistance": checked.get("totalDistance"),
        "hardViolationCount": len(checked.get("violations", [])),
        "referenceRouteAvailable": reference_available,
        "referenceRouteFeasible": bool(reference_eval and reference_eval.get("feasible")),
        "referenceVehicleCount": None if reference_eval is None else reference_eval.get("vehicleCount"),
        "referenceDistance": None if reference_eval is None else reference_eval.get("totalDistance"),
        "referenceHardViolationCount": None if reference_eval is None else reference_eval.get("hardViolationCount"),
        "referenceCustomerDiagnostics": reference_customer_diagnostics,
        "referenceImportCount": reference_import_count,
        "routePoolSizeBefore": route_pool_before,
        "routePoolSizeAfter": len(route_pool),
        "setPartitioningProducedSolution": sp_solution is not None,
        "bestLabel": best["label"],
        "runtimeMs": int((time.perf_counter() - started) * 1000),
    }
    result = {"schemaVersion": "phase23-reference-import-results/v1", "results": [row]}
    case_dir = output_dir / "solomon" / instance_name
    write_json(case_dir / "solution.json", best["solution"])
    write_json(case_dir / "route_pool.json", {"routes": route_pool})
    write_json(case_dir / "metrics.json", row)
    write_json(output_dir / "phase23_reference_import_results.json", result)
    (output_dir / "phase23_reference_import_report.md").write_text(markdown([row]), encoding="utf-8")
    return result


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Phase 23 Reference Import Report",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Ref Available/Feasible | Ref Vehicles | Pool Before/After | SP | Best Label | Runtime |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedVehicleGap')}/{row.get('vehicleGap')} | "
            f"{row.get('referenceRouteAvailable')}/{row.get('referenceRouteFeasible')} | {row.get('referenceVehicleCount')} | "
            f"{row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | {row.get('setPartitioningProducedSolution')} | "
            f"{row.get('bestLabel')} | {row.get('runtimeMs')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import and validate Phase 23 reference solution.")
    parser.add_argument("--instance", default="RC101")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--reference", default="")
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    result = run_phase23(args.instance, args.data_source, args.reference or None, Path(args.seed_dir), Path(args.output_dir))
    print(f"[PHASE23 REFERENCE IMPORT] wrote {args.output_dir}")
    return 1 if any(row.get("status") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
