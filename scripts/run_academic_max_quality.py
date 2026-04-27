from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from external_benchmark_support import check_solution, ortools_baseline_solution
from parse_solomon_vrptw import parse_solomon
from run_dispatch_benchmark_certification_suite import HOMBERGER_BEST_KNOWN, REPO_ROOT


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "academic-max-quality"
DEFAULT_INSTANCES = ("C1_10_1", "R1_10_1", "RC1_10_1")
FIRST_SOLUTION_STRATEGIES = (
    "PARALLEL_CHEAPEST_INSERTION",
    "PATH_CHEAPEST_ARC",
    "SAVINGS",
    "GLOBAL_CHEAPEST_ARC",
)
LOCAL_SEARCH_METAHEURISTICS = (
    "GUIDED_LOCAL_SEARCH",
    "TABU_SEARCH",
    "SIMULATED_ANNEALING",
)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_duration_ms(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(float(text[:-2]))
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 60_000)
    if text.endswith("h"):
        return int(float(text[:-1]) * 3_600_000)
    return int(float(text) * 1000)


def load_homberger(instance: str) -> Dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt"
    normalized = parse_solomon(path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    return normalized


def vehicle_fixed_cost(instance: Dict[str, Any], multiplier: int) -> int:
    values = [float(value) for row in instance.get("distanceMatrix", []) for value in row]
    max_arc = max(values, default=1.0)
    node_count = max(1, len(instance.get("nodes", [])))
    return max(1_000_000, int(round(max_arc * node_count * multiplier)))


def solution_key(metrics: Dict[str, Any]) -> tuple[int, int, float]:
    feasible_penalty = 0 if metrics.get("feasible") else 1
    return feasible_penalty, int(metrics.get("vehicleCount", 10**9)), float(metrics.get("totalDistance", 1e18))


def evaluate_solution(instance: Dict[str, Any], solution: Dict[str, Any], label: str) -> Dict[str, Any]:
    metrics = check_solution(instance, solution)
    return {
        "label": label,
        "feasible": metrics["feasible"],
        "vehicleCount": metrics["vehicleCount"],
        "totalDistance": metrics["totalDistance"],
        "objectiveGapPercent": metrics["objectiveGapPercent"],
        "hardViolationCount": len(metrics.get("violations", [])),
        "violations": metrics.get("violations", []),
        "solution": solution,
    }


def run_instance(instance_name: str, time_limit_ms: int, output_root: Path, max_runs: int, fixed_cost_multiplier: int) -> Dict[str, Any]:
    started = time.perf_counter()
    instance = load_homberger(instance_name)
    bks = instance.get("bestKnown", {})
    per_run_ms = max(1, time_limit_ms // max(1, max_runs))
    fixed_cost = vehicle_fixed_cost(instance, fixed_cost_multiplier)
    candidates: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    strategy_pairs = [
        (first, local)
        for first in FIRST_SOLUTION_STRATEGIES
        for local in LOCAL_SEARCH_METAHEURISTICS
    ][:max_runs]
    for index, (first_strategy, local_strategy) in enumerate(strategy_pairs, start=1):
        run_started = time.perf_counter()
        solution = ortools_baseline_solution(
            instance,
            per_run_ms,
            f"academic-max-quality-run-{index}",
            vehicle_fixed_cost=fixed_cost,
            first_solution_strategy=first_strategy,
            local_search_metaheuristic=local_strategy,
        )
        runtime_ms = int((time.perf_counter() - run_started) * 1000)
        if solution.get("evidenceGapReason"):
            runs.append({
                "run": index,
                "firstSolutionStrategy": first_strategy,
                "localSearchMetaheuristic": local_strategy,
                "runtimeMs": runtime_ms,
                "evidenceGapReason": solution["evidenceGapReason"],
            })
            continue
        evaluated = evaluate_solution(instance, solution, f"{first_strategy}+{local_strategy}")
        candidates.append(evaluated)
        runs.append({
            "run": index,
            "firstSolutionStrategy": first_strategy,
            "localSearchMetaheuristic": local_strategy,
            "runtimeMs": runtime_ms,
            "feasible": evaluated["feasible"],
            "vehicleCount": evaluated["vehicleCount"],
            "totalDistance": evaluated["totalDistance"],
            "objectiveGapPercent": evaluated["objectiveGapPercent"],
        })
    if not candidates:
        row = {
            "instance": instance_name,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["no-candidate-solution"],
            "runs": runs,
        }
        write_json(output_root / instance_name / "metrics.json", row)
        return row
    best = min(candidates, key=lambda item: solution_key(item))
    runtime_ms = int((time.perf_counter() - started) * 1000)
    final_vehicle_count = int(best["vehicleCount"])
    bks_vehicles = int(bks.get("vehicleCount", final_vehicle_count) or final_vehicle_count)
    distance_gap = best["objectiveGapPercent"]
    hard_violations = int(best["hardViolationCount"])
    if hard_violations:
        verdict = "FAIL"
        reasons = best["violations"]
    elif final_vehicle_count <= bks_vehicles and distance_gap is not None and float(distance_gap) <= 20.0:
        verdict = "PASS"
        reasons = ["academic-max-quality-within-target"]
    else:
        verdict = "PASS_WITH_LIMITS"
        reasons = []
        if final_vehicle_count > bks_vehicles:
            reasons.append("vehicle-count-above-best-known")
        if distance_gap is None:
            reasons.append("best-known-objective-missing")
        elif float(distance_gap) > 20.0:
            reasons.append("objective-gap-above-pass-threshold")
    row = {
        "instance": instance_name,
        "profile": "academic-max-quality",
        "orToolsRuns": len(runs),
        "perRunTimeLimitMs": per_run_ms,
        "runtimeMs": runtime_ms,
        "runtimeMinutes": runtime_ms / 60_000,
        "vehicleFixedCost": fixed_cost,
        "initialVehicles": runs[0].get("vehicleCount") if runs else None,
        "finalVehicles": final_vehicle_count,
        "bksVehicles": bks.get("vehicleCount"),
        "vehicleGap": final_vehicle_count - bks_vehicles,
        "initialDistance": runs[0].get("totalDistance") if runs else None,
        "finalDistance": best["totalDistance"],
        "bksDistance": bks.get("objective"),
        "distanceGap": distance_gap,
        "hardViolationCount": hard_violations,
        "bestRunLabel": best["label"],
        "runs": runs,
        "verdict": verdict,
        "verdictReasons": reasons,
    }
    case_root = output_root / instance_name
    write_json(case_root / "solution.json", best["solution"])
    write_json(case_root / "metrics.json", row)
    return row


def markdown(rows: Sequence[Dict[str, Any]]) -> str:
    lines = ["# Academic Max Quality Report", ""]
    lines.append("| Case | Final vehicles | BKS vehicles | Vehicle gap | Final distance | Distance gap | Runs | Runtime min | Verdict | Reasons |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for row in rows:
        distance_gap = row.get("distanceGap")
        gap_text = "n/a" if distance_gap is None else f"{float(distance_gap):.2f}%"
        lines.append(
            "| {instance} | {finalVehicles} | {bksVehicles} | {vehicleGap} | {finalDistance:.2f} | {gap} | {orToolsRuns} | {runtimeMinutes:.2f} | {verdict} | {reasons} |".format(
                gap=gap_text,
                reasons=", ".join(row.get("verdictReasons", [])),
                **row,
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run academic max-quality Homberger optimization.")
    parser.add_argument("--instances", default=",".join(DEFAULT_INSTANCES))
    parser.add_argument("--time-limit", default="30m")
    parser.add_argument("--or-tools-runs", type=int, default=6)
    parser.add_argument("--fixed-cost-multiplier", type=int, default=1_000_000)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [
        run_instance(instance, parse_duration_ms(args.time_limit), output_root, args.or_tools_runs, args.fixed_cost_multiplier)
        for instance in instances
    ]
    result = {"schemaVersion": "academic-max-quality/v1", "results": rows}
    write_json(output_root / "academic_max_quality_results.json", result)
    (output_root / "academic_max_quality_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[ACADEMIC MAX QUALITY JSON] {output_root / 'academic_max_quality_results.json'}")
    print(f"[ACADEMIC MAX QUALITY REPORT] {output_root / 'academic_max_quality_report.md'}")
    return 1 if any(row["verdict"] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
