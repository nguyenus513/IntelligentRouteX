from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from academic_global_consolidation import _route_is_feasible
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, ortools_baseline_solution, route_distance
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase31c-pdptw-route-pool-v1"


@dataclass(frozen=True)
class PDPTWRouteColumn:
    column_id: str
    route: List[str]
    request_ids: frozenset[str]
    distance: float
    source: str
    source_solver: str
    source_run_id: str
    provenance: str
    allowed_for_claim: bool
    feasible: bool
    check_result: Dict[str, Any]


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def request_id_map(instance: Dict[str, Any]) -> Dict[tuple[str, str], str]:
    mapping: Dict[tuple[str, str], str] = {}
    for index, request in enumerate(instance.get("requests", [])):
        request_id = str(request.get("id") or request.get("requestId") or index)
        mapping[(str(request["pickupNodeId"]), str(request["dropoffNodeId"]))] = request_id
    return mapping


def route_request_ids(instance: Dict[str, Any], route: List[str]) -> frozenset[str]:
    route_set = set(route)
    ids = []
    for pair, request_id in request_id_map(instance).items():
        pickup, dropoff = pair
        if pickup in route_set or dropoff in route_set:
            if pickup not in route_set or dropoff not in route_set or route.index(pickup) >= route.index(dropoff):
                return frozenset()
            ids.append(request_id)
    return frozenset(ids)


def build_column(instance: Dict[str, Any], route: List[str], source: str, column_id: str, source_solver: str = "unknown", source_run_id: str = "default", provenance: str = "diagnostic", allowed_for_claim: bool = False) -> PDPTWRouteColumn | None:
    normalized_route = [str(stop) for stop in route]
    check_result = check_solution(instance, {"routes": [normalized_route]})
    request_ids = route_request_ids(instance, normalized_route)
    route_hard_feasible = _route_is_feasible(instance, normalized_route)[0]
    feasible = route_hard_feasible and bool(request_ids)
    if not feasible:
        return None
    return PDPTWRouteColumn(
        column_id=column_id,
        route=normalized_route,
        request_ids=request_ids,
        distance=route_distance(instance, normalized_route),
        source=source,
        source_solver=source_solver,
        source_run_id=source_run_id,
        provenance=provenance,
        allowed_for_claim=allowed_for_claim,
        feasible=True,
        check_result=check_result,
    )


class PDPTWRoutePool:
    def __init__(self, instance: Dict[str, Any]) -> None:
        self._instance = instance
        self._columns: List[PDPTWRouteColumn] = []
        self._route_keys: set[tuple[str, ...]] = set()
        self.duplicate_route_count = 0
        self.rejected_infeasible_count = 0

    @property
    def columns(self) -> List[PDPTWRouteColumn]:
        return self._columns[:]

    def add_route(self, route: List[str], source: str, source_solver: str = "unknown", source_run_id: str = "default", provenance: str = "diagnostic", allowed_for_claim: bool | None = None) -> bool:
        key = tuple(str(stop) for stop in route)
        if key in self._route_keys:
            self.duplicate_route_count += 1
            return False
        if allowed_for_claim is None:
            allowed_for_claim = provenance == "internal"
        column = build_column(self._instance, list(key), source, f"c{len(self._columns)}", source_solver, source_run_id, provenance, allowed_for_claim)
        if column is None:
            self.rejected_infeasible_count += 1
            return False
        self._route_keys.add(key)
        self._columns.append(column)
        return True

    def add_solution(self, solution: Dict[str, Any], source: str, source_solver: str = "unknown", source_run_id: str = "default", provenance: str = "diagnostic", allowed_for_claim: bool | None = None) -> None:
        for route in solution.get("routes", []):
            if len(route) > 2:
                self.add_route([str(stop) for stop in route], source, source_solver, source_run_id, provenance, allowed_for_claim)

    def filtered(self, allowed_for_claim: bool | None = None) -> "PDPTWRoutePool":
        pool = PDPTWRoutePool(self._instance)
        for column in self._columns:
            if allowed_for_claim is not None and column.allowed_for_claim != allowed_for_claim:
                continue
            pool._route_keys.add(tuple(column.route))
            pool._columns.append(column)
        return pool

    def stats(self) -> Dict[str, Any]:
        all_request_ids = sorted(request_id_map(self._instance).values())
        coverage_counts = {request_id: 0 for request_id in all_request_ids}
        source_counts: Dict[str, int] = {}
        provenance_counts: Dict[str, int] = {}
        allowed_counts = {"allowed": 0, "disallowed": 0}
        for column in self._columns:
            source_counts[column.source] = source_counts.get(column.source, 0) + 1
            provenance_counts[column.provenance] = provenance_counts.get(column.provenance, 0) + 1
            allowed_counts["allowed" if column.allowed_for_claim else "disallowed"] += 1
            for request_id in column.request_ids:
                coverage_counts[request_id] = coverage_counts.get(request_id, 0) + 1
        values = list(coverage_counts.values())
        uncovered = [request_id for request_id, count in coverage_counts.items() if count == 0]
        return {
            "columnCount": len(self._columns),
            "sourceCounts": source_counts,
            "provenanceCounts": provenance_counts,
            "allowedForClaimCounts": allowed_counts,
            "requestCoverageMin": min(values) if values else None,
            "requestCoverageMedian": statistics.median(values) if values else None,
            "requestCoverageMax": max(values) if values else None,
            "uncoveredRequests": uncovered,
            "duplicateRouteCount": self.duplicate_route_count,
            "rejectedInfeasibleCount": self.rejected_infeasible_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": "phase31b-pdptw-route-pool/v1",
            "stats": self.stats(),
            "columns": [
                {
                    "columnId": column.column_id,
                    "route": column.route,
                    "requestIds": sorted(column.request_ids),
                    "distance": column.distance,
                    "source": column.source,
                    "sourceSolver": column.source_solver,
                    "sourceRunId": column.source_run_id,
                    "provenance": column.provenance,
                    "allowedForClaim": column.allowed_for_claim,
                    "feasible": column.feasible,
                }
                for column in self._columns
            ],
        }


class PDPTWSetPartitioningSolver:
    def __init__(self, time_limit_ms: int = 2_000) -> None:
        self._time_limit_ms = time_limit_ms

    def solve(self, instance: Dict[str, Any], columns: List[PDPTWRouteColumn], target_vehicle_count: int | None = None) -> Dict[str, Any]:
        try:
            from ortools.sat.python import cp_model
        except Exception as exception:
            return {"status": "unavailable", "reason": f"ortools-cp-sat-unavailable:{exception}", "feasible": False}
        all_request_ids = sorted(request_id_map(instance).values())
        if not columns:
            return {"status": "infeasible", "reason": "empty-route-pool", "feasible": False}
        model = cp_model.CpModel()
        variables = [model.NewBoolVar(column.column_id) for column in columns]
        for request_id in all_request_ids:
            covering = [variables[index] for index, column in enumerate(columns) if request_id in column.request_ids]
            if not covering:
                return {"status": "infeasible", "reason": "uncovered-request", "uncoveredRequests": [request_id], "feasible": False}
            model.Add(sum(covering) == 1)
        if target_vehicle_count is not None:
            model.Add(sum(variables) <= target_vehicle_count)
        max_total_distance = max(1, int(sum(max(1.0, column.distance) for column in columns) * 1000) + 1)
        big_m = max_total_distance + 1
        model.Minimize(big_m * sum(variables) + sum(int(round(column.distance * 1000)) * variables[index] for index, column in enumerate(columns)))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.001, self._time_limit_ms / 1000.0)
        status = solver.Solve(model)
        status_name = solver.StatusName(status).lower()
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            return {"status": status_name, "feasible": False, "targetVehicleCount": target_vehicle_count}
        selected = [columns[index] for index, variable in enumerate(variables) if solver.Value(variable) == 1]
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase31b-pdptw-route-pool-sp", "routes": [column.route for column in selected]}
        checked = check_solution(instance, solution)
        return {
            "status": status_name,
            "feasible": bool(checked.get("feasible")),
            "targetVehicleCount": target_vehicle_count,
            "selectedColumnIds": [column.column_id for column in selected],
            "selectedRouteCount": len(selected),
            "selectedDistance": checked.get("totalDistance"),
            "checkResult": checked,
            "solution": solution,
        }


def collect_pool(instance: Dict[str, Any], time_limit_ms: int) -> tuple[PDPTWRoutePool, Dict[str, Any]]:
    pool = PDPTWRoutePool(instance)
    diagnostics: Dict[str, Any] = {"candidateSources": []}
    ortools_solution = ortools_baseline_solution(instance, max(1, time_limit_ms), "phase31b-ortools-incumbent")
    pool.add_solution(ortools_solution, "ortools-incumbent", source_solver="ortools-baseline", source_run_id="comparator", provenance="comparator", allowed_for_claim=False)
    diagnostics["candidateSources"].append({"source": "ortools-incumbent", "routes": len(ortools_solution.get("routes", []))})
    dispatch_solution = DispatchV2ExternalBenchmarkSolver().solve(instance, max(1, time_limit_ms), "our-dispatch-v2")
    pool.add_solution(dispatch_solution, "our-dispatch-v2", source_solver="our-dispatch-v2", source_run_id="internal-main", provenance="internal", allowed_for_claim=True)
    diagnostics["candidateSources"].append({"source": "our-dispatch-v2", "routes": len(dispatch_solution.get("routes", []))})
    return pool, diagnostics


def run_instance(instance_name: str, output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    source_path = resolve_instance_path("li-lim", instance_name, data_source)
    instance = parse_instance("li-lim", source_path)
    started = time.perf_counter()
    pool, diagnostics = collect_pool(instance, time_limit_ms)
    oracle_pool = pool
    internal_pool = pool.filtered(allowed_for_claim=True)
    oracle_stats = oracle_pool.stats()
    internal_stats = internal_pool.stats()
    incumbent_vehicle_count = min((len(solution_routes) for solution_routes in [[column.route for column in pool.columns if column.source == "our-dispatch-v2"]] if solution_routes), default=0)
    if incumbent_vehicle_count <= 0:
        incumbent_vehicle_count = max(1, int(instance.get("vehicleCount", 1)))
    target_vehicle_count = max(1, incumbent_vehicle_count - 1)
    solver = PDPTWSetPartitioningSolver(time_limit_ms=2_000)
    internal_feasibility_result = solver.solve(instance, internal_pool.columns, target_vehicle_count=target_vehicle_count)
    internal_quality_result = solver.solve(instance, internal_pool.columns, target_vehicle_count=None)
    oracle_feasibility_result = solver.solve(instance, oracle_pool.columns, target_vehicle_count=target_vehicle_count)
    oracle_quality_result = solver.solve(instance, oracle_pool.columns, target_vehicle_count=None)
    selected_solution = internal_feasibility_result.get("solution") if internal_feasibility_result.get("feasible") else oracle_feasibility_result.get("solution") if oracle_feasibility_result.get("feasible") else None
    hard_violations = 0
    if selected_solution:
        hard_violations = len(check_solution(instance, selected_solution).get("violations", []))
    comparator_used_by_oracle = _oracle_uses_disallowed_columns(oracle_pool.columns, oracle_feasibility_result)
    if internal_stats.get("uncoveredRequests"):
        verdict = "FAIL"
    elif internal_feasibility_result.get("feasible") and hard_violations == 0:
        verdict = "PASS"
    elif oracle_feasibility_result.get("feasible") and hard_violations == 0:
        verdict = "PASS_WITH_LIMITS"
    else:
        verdict = "FAIL"
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "internal_route_pool.json", internal_pool.to_dict())
    write_json(instance_dir / "oracle_route_pool.json", oracle_pool.to_dict())
    write_json(instance_dir / "internal_sp_result.json", {"feasibilityMode": internal_feasibility_result, "qualityMode": internal_quality_result})
    write_json(instance_dir / "oracle_sp_result.json", {"feasibilityMode": oracle_feasibility_result, "qualityMode": oracle_quality_result})
    write_json(instance_dir / "provenance_summary.json", provenance_summary(internal_pool, oracle_pool, internal_feasibility_result, oracle_feasibility_result))
    if selected_solution:
        write_json(instance_dir / "selected_solution.json", selected_solution)
    diagnostics.update({
        "instance": instance.get("instanceName"),
        "poolStats": oracle_stats,
        "internalPoolStats": internal_stats,
        "oraclePoolStats": oracle_stats,
        "targetVehicleCount": target_vehicle_count,
        "internalTargetFeasible": bool(internal_feasibility_result.get("feasible")),
        "oracleTargetFeasible": bool(oracle_feasibility_result.get("feasible")),
        "comparatorColumnUsedByOracleSolution": comparator_used_by_oracle,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "hardViolationCount": hard_violations,
        "verdict": verdict,
    })
    write_json(instance_dir / "diagnostics.json", diagnostics)
    return diagnostics


def _oracle_uses_disallowed_columns(columns: List[PDPTWRouteColumn], result: Dict[str, Any]) -> bool:
    selected = set(result.get("selectedColumnIds", []))
    return any(column.column_id in selected and not column.allowed_for_claim for column in columns)


def provenance_summary(internal_pool: PDPTWRoutePool, oracle_pool: PDPTWRoutePool, internal_result: Dict[str, Any], oracle_result: Dict[str, Any]) -> Dict[str, Any]:
    oracle_columns = oracle_pool.columns
    return {
        "schemaVersion": "phase31c-provenance-summary/v1",
        "internalColumnCount": len(internal_pool.columns),
        "oracleColumnCount": len(oracle_columns),
        "sourceCounts": oracle_pool.stats().get("sourceCounts", {}),
        "allowedForClaimCounts": oracle_pool.stats().get("allowedForClaimCounts", {}),
        "internalCoverageMin": internal_pool.stats().get("requestCoverageMin"),
        "internalCoverageMedian": internal_pool.stats().get("requestCoverageMedian"),
        "internalCoverageMax": internal_pool.stats().get("requestCoverageMax"),
        "oracleCoverageMin": oracle_pool.stats().get("requestCoverageMin"),
        "oracleCoverageMedian": oracle_pool.stats().get("requestCoverageMedian"),
        "oracleCoverageMax": oracle_pool.stats().get("requestCoverageMax"),
        "internalTargetFeasible": bool(internal_result.get("feasible")),
        "oracleTargetFeasible": bool(oracle_result.get("feasible")),
        "comparatorColumnUsedByOracleSolution": _oracle_uses_disallowed_columns(oracle_columns, oracle_result),
    }


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 31C PDPTW Provenance-Safe Route Pool SP", "", "| Instance | Verdict | Internal Target | Oracle Target | Internal Columns | Oracle Columns | Target | Runtime ms |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        internal_stats = row.get("internalPoolStats", {})
        oracle_stats = row.get("oraclePoolStats", {})
        lines.append(f"| {row.get('instance')} | {row.get('verdict')} | {row.get('internalTargetFeasible')} | {row.get('oracleTargetFeasible')} | {internal_stats.get('columnCount')} | {oracle_stats.get('columnCount')} | {row.get('targetVehicleCount')} | {row.get('runtimeMs')} |")
    return "\n".join(lines) + "\n"


def run(instances: List[str], output_dir: Path, data_source: str, time_limit_ms: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_instance(instance, output_dir, data_source, time_limit_ms) for instance in instances]
    summary = {
        "schemaVersion": "phase31b-pdptw-route-pool-summary/v1",
        "instances": instances,
        "results": rows,
        "verdictCounts": {verdict: sum(1 for row in rows if row.get("verdict") == verdict) for verdict in ("PASS", "PASS_WITH_LIMITS", "FAIL")},
    }
    write_json(output_dir / "phase31b_route_pool_summary.json", summary)
    (output_dir / "phase31b_route_pool_summary.md").write_text(markdown(rows), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 31B PDPTW route-pool set partitioning diagnostics.")
    parser.add_argument("--instances", default="lrc202,lrc206")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    summary = run(instances, Path(args.output_dir), args.data_source, parse_time_limit(args.time_limit))
    print(f"[PHASE31B ROUTE POOL SP] wrote {args.output_dir}")
    return 1 if summary["verdictCounts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
