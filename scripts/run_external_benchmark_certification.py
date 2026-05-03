from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, ortools_baseline_solution, verdict
from parse_li_lim_pdptw import parse_li_lim
from parse_solomon_vrptw import parse_solomon

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "external-certification"
PRESETS = {
    "preset:smoke": {
        "solomon": ["C101", "R101", "RC101"],
        "li-lim": ["LC101", "LR101", "LRC101"],
    },
    "preset:core": {
        "solomon": ["C101", "R101", "RC101"],
        "li-lim": ["LC101", "LR101", "LRC101"],
    },
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_time_limit(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(text[:-2])
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    return int(float(text) * 1000)


def instance_path(suite: str, instance: str, data_source: str) -> Path:
    root = REPO_ROOT / "benchmarks" / "external"
    if data_source == "official":
        root = root / "official"
    if suite == "solomon":
        return root / "solomon" / ("fixtures" if data_source == "fixture" else "") / f"{instance}.txt"
    if suite == "li-lim":
        return root / "li-lim-pdptw" / ("fixtures" if data_source == "fixture" else "") / f"{instance}.txt"
    raise ValueError(f"Unsupported suite: {suite}")


def resolve_instance_path(suite: str, instance: str, data_source: str) -> Path:
    if data_source == "auto":
        official = instance_path(suite, instance, "official")
        return official if official.exists() else instance_path(suite, instance, "fixture")
    return instance_path(suite, instance, data_source)


def parse_instance(suite: str, path: Path) -> Dict[str, Any]:
    if suite == "solomon":
        return parse_solomon(path)
    if suite == "li-lim":
        return parse_li_lim(path)
    raise ValueError(f"Unsupported suite: {suite}")


def requested_instances(suite: str, instances: str, preset: str) -> List[str]:
    if instances:
        return [part.strip() for part in instances.split(",") if part.strip()]
    return PRESETS[preset][suite]


def build_solution(normalized: Dict[str, Any], solver: str, time_limit_ms: int) -> Dict[str, Any]:
    if solver == "pyvrp-baseline":
        return {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": solver,
            "routes": [],
            "evidenceGapReason": "pyvrp-baseline-not-installed",
        }
    if solver == "ortools-baseline":
        return ortools_baseline_solution(normalized, time_limit_ms, solver)
    return DispatchV2ExternalBenchmarkSolver().solve(normalized, time_limit_ms, solver)


def solver_implementation(solver: str, solution: Dict[str, Any]) -> str:
    if solver == "ortools-baseline" and not solution.get("evidenceGapReason"):
        return "python-ortools-routing-baseline"
    if solver == "our-dispatch-v2":
        return solution.get("solverImplementation", "external-benchmark-dispatch-adapter-v1")
    return solver


def run_instance(
    suite: str,
    instance: str,
    solver: str,
    output_root: Path,
    gap_limit: float,
    time_limit_ms: int,
    data_source: str = "fixture",
) -> Dict[str, Any]:
    started = time.perf_counter()
    source_path = resolve_instance_path(suite, instance, data_source)
    effective_data_source = "official" if "official" in source_path.parts else "fixture"
    if not source_path.exists():
        return {
            "suite": suite,
            "instance": instance,
            "solver": solver,
            "dataSource": data_source,
            "effectiveDataSource": effective_data_source,
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["instance-data-missing"],
        }
    normalized = parse_instance(suite, source_path)
    normalized_path = output_root / "normalized" / effective_data_source / suite / f"{instance}.json"
    write_json(normalized_path, normalized)
    if solver not in {"our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"}:
        raise ValueError(f"Unsupported solver: {solver}")
    solution = build_solution(normalized, solver, time_limit_ms)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    solver_budget_usage = solution.get("budgetUsage") if isinstance(solution.get("budgetUsage"), dict) else {}
    verdict_runtime_ms = int(solver_budget_usage.get("usedMs") or runtime_ms)
    solution_path = output_root / "solutions" / effective_data_source / solver / suite / f"{instance}.json"
    write_json(solution_path, solution)
    if solution.get("evidenceGapReason"):
        return {
            "suite": suite,
            "instance": instance,
            "problemType": normalized.get("problemType"),
            "solver": solver,
            "solverImplementation": solver_implementation(solver, solution),
            "dataSource": data_source,
            "effectiveDataSource": effective_data_source,
            "feasible": False,
            "runtimeMs": runtime_ms,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": [solution["evidenceGapReason"]],
            "normalizedPath": str(normalized_path),
            "solutionPath": str(solution_path),
        }
    checked = check_solution(normalized, solution)
    cell_verdict, reasons = verdict(checked, gap_limit, verdict_runtime_ms, time_limit_ms)
    best_vehicle_count = normalized.get("bestKnown", {}).get("vehicleCount")
    if cell_verdict == "PASS" and best_vehicle_count is not None and checked["vehicleCount"] > int(best_vehicle_count):
        cell_verdict = "PASS_WITH_LIMITS"
        reasons = ["vehicle-count-above-best-known"]
    return {
        "suite": suite,
        "instance": instance,
        "problemType": normalized.get("problemType"),
        "solver": solver,
        "solverImplementation": solver_implementation(solver, solution),
        "dataSource": data_source,
        "effectiveDataSource": effective_data_source,
        "feasible": checked["feasible"],
        "vehicleCount": checked["vehicleCount"],
        "bestKnownVehicleCount": normalized.get("bestKnown", {}).get("vehicleCount"),
        "totalDistance": checked["totalDistance"],
        "bestKnownDistance": normalized.get("bestKnown", {}).get("objective"),
        "objectiveGapPercent": checked["objectiveGapPercent"],
        "servedRequestCount": checked["servedRequestCount"],
        "unservedRequestCount": checked["unservedRequestCount"],
        "capacityViolationCount": checked["capacityViolationCount"],
        "timeWindowViolationCount": checked["timeWindowViolationCount"],
        "pickupBeforeDropoffViolationCount": checked["pickupBeforeDropoffViolationCount"],
        "vehicleLimitViolationCount": checked.get("vehicleLimitViolationCount", 0),
        "runtimeMs": runtime_ms,
        "verdictRuntimeMs": verdict_runtime_ms,
        "verdict": cell_verdict,
        "verdictReasons": reasons,
        "normalizedPath": str(normalized_path),
        "solutionPath": str(solution_path),
    }


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# External Benchmark Certification Report",
        "",
        "| Suite | Instance | Data | Solver | Implementation | Feasible | Vehicles | Distance | BKS | Gap % | Runtime ms | Verdict |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        gap = row.get("objectiveGapPercent")
        lines.append(
            "| {suite} | {instance} | {data} | {solver} | {implementation} | {feasible} | {vehicles} | {distance:.6f} | {bks} | {gap} | {runtime} | {verdict} |".format(
                suite=row.get("suite"),
                instance=row.get("instance"),
                data=row.get("effectiveDataSource", ""),
                solver=row.get("solver"),
                implementation=row.get("solverImplementation", ""),
                feasible=row.get("feasible"),
                vehicles=row.get("vehicleCount", ""),
                distance=float(row.get("totalDistance", 0.0) or 0.0),
                bks=row.get("bestKnownDistance", ""),
                gap="" if gap is None else f"{float(gap):.3f}",
                runtime=row.get("runtimeMs", ""),
                verdict=row.get("verdict"),
            )
        )
    lines.extend([
        "",
        "## Scope Note",
        "",
        "`official` data may come from vetted raw mirrors when direct SINTEF assets are blocked by browser challenges; inspect `benchmarks/external/official/download_manifest.json` for provenance.",
        "`our-dispatch-v2` uses `ExternalBenchmarkToDispatchCaseAdapter` in benchmark-native mode. It preserves capacity, time-window, pickup/dropoff, and benchmark matrix constraints that the food-delivery Java domain cannot yet express losslessly.",
        "",
        "## Verdict Reasons",
        "",
    ])
    for row in rows:
        lines.append(f"- `{row.get('suite')}/{row.get('instance')}/{row.get('solver')}`: `{row.get('verdict')}` {row.get('verdictReasons')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run External Benchmark Certification Rail.")
    parser.add_argument("--suite", choices=("solomon", "li-lim"), default="li-lim")
    parser.add_argument("--instances", default="")
    parser.add_argument("--preset", choices=tuple(PRESETS.keys()), default="preset:smoke")
    parser.add_argument("--mode", choices=("benchmark-native",), default="benchmark-native")
    parser.add_argument("--solver", choices=("our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"), default="our-dispatch-v2")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="fixture")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--gap-limit", type=float, default=20.0)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()
    output_root = Path(args.output_root)
    time_limit_ms = parse_time_limit(args.time_limit)
    rows = [run_instance(args.suite, instance, args.solver, output_root, args.gap_limit, time_limit_ms, args.data_source)
            for instance in requested_instances(args.suite, args.instances, args.preset)]
    result = {
        "schemaVersion": "external-benchmark-certification/v1",
        "mode": args.mode,
        "suite": args.suite,
        "solver": args.solver,
        "dataSource": args.data_source,
        "results": rows,
        "verdictCounts": {verdict_name: sum(1 for row in rows if row["verdict"] == verdict_name)
                          for verdict_name in ("PASS", "PASS_WITH_LIMITS", "FAIL", "EVIDENCE_GAP")},
    }
    write_json(output_root / "external_benchmark_results.json", result)
    (output_root / "external_benchmark_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[EXTERNAL BENCHMARK JSON] {output_root / 'external_benchmark_results.json'}")
    print(f"[EXTERNAL BENCHMARK REPORT] {output_root / 'external_benchmark_report.md'}")
    return 1 if any(row["verdict"] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
