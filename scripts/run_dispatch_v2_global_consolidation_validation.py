from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Sequence

from academic_global_consolidation import GlobalRouteConsolidator
from external_benchmark_dispatch_adapter import DispatchV2ExternalBenchmarkSolver
from external_benchmark_support import check_solution, ortools_baseline_solution
from parse_solomon_vrptw import parse_solomon
from run_dispatch_benchmark_certification_suite import HOMBERGER_BEST_KNOWN, REPO_ROOT, homberger_time_limit_ms
from run_external_benchmark_certification import parse_time_limit


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "global-consolidation"
DEFAULT_INSTANCES = ("C1_10_1", "R1_10_1", "RC1_10_1")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_homberger_instance(instance: str) -> Dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt"
    normalized = parse_solomon(path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    return normalized


def evaluate_instance(instance_name: str, time_limit_ms: int, output_root: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    instance = load_homberger_instance(instance_name)
    benchmark_time_limit_ms = homberger_time_limit_ms(instance_name, time_limit_ms)
    baseline_solution = ortools_baseline_solution(instance, benchmark_time_limit_ms, "ortools-before-consolidation")
    before = check_solution(instance, baseline_solution)
    consolidated = GlobalRouteConsolidator().consolidate(instance, baseline_solution)
    after = consolidated.after_metrics
    dispatch_solution = DispatchV2ExternalBenchmarkSolver().solve(instance, benchmark_time_limit_ms, "our-dispatch-v2")
    dispatch_metrics = check_solution(instance, dispatch_solution)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    row = {
        "instance": instance_name,
        "requestedTimeLimitMs": time_limit_ms,
        "benchmarkTimeLimitMs": benchmark_time_limit_ms,
        "beforeVehicleCount": before.get("vehicleCount"),
        "afterVehicleCount": after.get("vehicleCount"),
        "dispatchVehicleCount": dispatch_metrics.get("vehicleCount"),
        "bestKnownVehicleCount": instance.get("bestKnown", {}).get("vehicleCount"),
        "beforeDistance": before.get("totalDistance"),
        "afterDistance": after.get("totalDistance"),
        "dispatchDistance": dispatch_metrics.get("totalDistance"),
        "beforeGap": before.get("objectiveGapPercent"),
        "afterGap": after.get("objectiveGapPercent"),
        "dispatchGap": dispatch_metrics.get("objectiveGapPercent"),
        "vehicleReduction": int(before.get("vehicleCount", 0)) - int(after.get("vehicleCount", 0)),
        "dispatchVehicleDelta": int(before.get("vehicleCount", 0)) - int(dispatch_metrics.get("vehicleCount", 0)),
        "hardViolationCount": len(after.get("violations", [])) + len(dispatch_metrics.get("violations", [])),
        "operatorAttempts": consolidated.trace.operator_attempts,
        "acceptedMoves": consolidated.trace.accepted_moves,
        "rejectedMoves": consolidated.trace.rejected_moves,
        "topRejectReasons": consolidated.trace.to_dict()["topRejectReasons"],
        "runtimeMs": runtime_ms,
    }
    case_root = output_root / instance_name
    write_json(case_root / "before_solution.json", baseline_solution)
    write_json(case_root / "after_solution.json", consolidated.solution)
    write_json(case_root / "dispatch_solution.json", dispatch_solution)
    write_json(case_root / "metrics.json", row)
    return row


def markdown(rows: Sequence[Dict[str, Any]]) -> str:
    lines = ["# Academic Global Consolidation Report", ""]
    lines.append("| Case | Before vehicles | After vehicles | Dispatch vehicles | BKS vehicles | Gap before | Gap after | Dispatch gap | Accepted moves | Hard violations |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        lines.append(
            "| {instance} | {beforeVehicleCount} | {afterVehicleCount} | {dispatchVehicleCount} | {bestKnownVehicleCount} | {beforeGap:.2f}% | {afterGap:.2f}% | {dispatchGap:.2f}% | {acceptedMoves} | {hardViolationCount} |".format(
                **row
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run focused Academic Global Consolidation validation.")
    parser.add_argument("--instances", default=",".join(DEFAULT_INSTANCES))
    parser.add_argument("--time-limit", default="60s")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [evaluate_instance(instance, parse_time_limit(args.time_limit), output_root) for instance in instances]
    result = {"schemaVersion": "academic-global-consolidation/v1", "results": rows}
    write_json(output_root / "global_consolidation_results.json", result)
    (output_root / "global_consolidation_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[GLOBAL CONSOLIDATION JSON] {output_root / 'global_consolidation_results.json'}")
    print(f"[GLOBAL CONSOLIDATION REPORT] {output_root / 'global_consolidation_report.md'}")
    return 1 if any(row["hardViolationCount"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
