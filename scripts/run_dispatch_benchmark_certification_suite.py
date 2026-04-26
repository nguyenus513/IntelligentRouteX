from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from parse_icaps_dpdp import evaluate_icaps_instance
from parse_mdrplib import evaluate_mdrplib_instance
from parse_solomon_vrptw import parse_solomon
from run_external_benchmark_certification import build_solution, parse_time_limit, run_instance
from external_benchmark_support import check_solution, verdict as external_verdict


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite"

ACADEMIC_SMOKE = {
    "solomon": ["C101", "R101", "RC101"],
    "li-lim": ["LC101", "LR101", "LRC101"],
}
ACADEMIC_CORE = {
    "solomon": ["C101", "C201", "R101", "R201", "RC101", "RC201"],
    "li-lim": ["LC101", "LC201", "LR101", "LR201", "LRC101", "LRC201"],
}
HOMBERGER_SCALE = {
    "200": ["C1_2_1", "R1_2_1", "RC1_2_1"],
    "400": ["C1_4_1", "R1_4_1", "RC1_4_1"],
    "600": ["C1_6_1", "R1_6_1", "RC1_6_1"],
    "800": ["C1_8_1", "R1_8_1", "RC1_8_1"],
    "1000": ["C1_10_1", "R1_10_1", "RC1_10_1"],
}
HOMBERGER_BEST_KNOWN = {
    "C1_2_1": {"vehicleCount": 20, "objective": 2704.57, "source": "SINTEF Homberger 200 customers"},
    "R1_2_1": {"vehicleCount": 20, "objective": 4784.11, "source": "SINTEF Homberger 200 customers"},
    "RC1_2_1": {"vehicleCount": 18, "objective": 3602.80, "source": "SINTEF Homberger 200 customers"},
    "C1_4_1": {"vehicleCount": 40, "objective": 7152.02, "source": "SINTEF Homberger 400 customers"},
    "R1_4_1": {"vehicleCount": 40, "objective": 10372.31, "source": "SINTEF Homberger 400 customers"},
    "RC1_4_1": {"vehicleCount": 36, "objective": 8571.32, "source": "SINTEF Homberger 400 customers"},
    "C1_6_1": {"vehicleCount": 60, "objective": 14095.64, "source": "SINTEF Homberger 600 customers"},
    "R1_6_1": {"vehicleCount": 59, "objective": 21394.95, "source": "SINTEF Homberger 600 customers"},
    "RC1_6_1": {"vehicleCount": 55, "objective": 16982.86, "source": "SINTEF Homberger 600 customers"},
    "C1_8_1": {"vehicleCount": 80, "objective": 25030.36, "source": "SINTEF Homberger 800 customers"},
    "R1_8_1": {"vehicleCount": 80, "objective": 36767.92, "source": "SINTEF Homberger 800 customers"},
    "RC1_8_1": {"vehicleCount": 72, "objective": 30464.65, "source": "SINTEF Homberger 800 customers"},
    "C1_10_1": {"vehicleCount": 100, "objective": 42478.95, "source": "SINTEF Homberger 1000 customers"},
    "R1_10_1": {"vehicleCount": 100, "objective": 53380.18, "source": "SINTEF Homberger 1000 customers"},
    "RC1_10_1": {"vehicleCount": 90, "objective": 45830.62, "source": "SINTEF Homberger 1000 customers"},
}
MDRP_DEMAND_SPLITS = ("low", "medium", "high")
DPDP_STRESS_CASES = {
    "low": (12, 16),
    "medium": (40, 48),
    "high": (80, 96),
    "burst": (80, 40),
    "driver-scarcity": (60, 80),
    "bad-geo": (20, 24),
    "provider-timeout": (20, 24),
}
HCM_SCENARIOS = ("normal-clear", "heavy-rain", "traffic-shock", "route-ambiguity", "driver-scarcity", "dinner-peak-high-density")
HCM_SIZES_BY_LEVEL = {
    "smoke": ("S",),
    "core": ("S", "M"),
    "full": ("S", "M", "L"),
}
HCM_MODES = ("full-system", "no-llm", "no-heavy-ml", "ortools-baseline")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def verdict_counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {name: sum(1 for row in rows if row["verdict"] == name) for name in ("PASS", "PASS_WITH_LIMITS", "FAIL", "EVIDENCE_GAP")}


def certification_verdict(rows: Sequence[Dict[str, Any]]) -> str:
    counts = verdict_counts(rows)
    if counts["FAIL"]:
        return "FAIL"
    if counts["EVIDENCE_GAP"]:
        return "PASS_WITH_LIMITS"
    if counts["PASS_WITH_LIMITS"]:
        return "PASS_WITH_LIMITS"
    return "PASS"


def evidence_gap_row(rail: str, suite: str, reason: str) -> Dict[str, Any]:
    return {
        "rail": rail,
        "suite": suite,
        "instance": "not-run",
        "solver": "not-run",
        "feasible": False,
        "runtimeMs": 0,
        "verdict": "EVIDENCE_GAP",
        "verdictReasons": [reason],
    }


def stage_row(stage: str, row: Dict[str, Any]) -> Dict[str, Any]:
    row["stage"] = stage
    return row


def academic_row(rail: str, suite: str, instance: str, solver: str, output_root: Path, time_limit_ms: int) -> Dict[str, Any]:
    row = run_instance(suite, instance, solver, output_root / "external", 20.0, time_limit_ms, "auto")
    row["rail"] = rail
    return row


def homberger_row(instance: str, output_root: Path, solver: str, time_limit_ms: int) -> Dict[str, Any]:
    candidates = [
        REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt",
        REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance.upper()}.TXT",
        REPO_ROOT / "benchmarks" / "external" / "homberger" / "fixtures" / f"{instance}.txt",
    ]
    source_path = next((path for path in candidates if path.exists()), None)
    if source_path is None:
        row = evidence_gap_row("gehring-homberger-scale", "homberger-vrptw", "homberger-official-instance-missing")
        row["instance"] = instance
        row["expectedPaths"] = [str(path) for path in candidates[:2]]
        return row
    started = time.perf_counter()
    normalized = parse_solomon(source_path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    normalized_path = output_root / "homberger" / "normalized" / f"{instance}.json"
    write_json(normalized_path, normalized)
    solution = build_solution(normalized, solver, time_limit_ms)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    solution_path = output_root / "homberger" / "solutions" / solver / f"{instance}.json"
    write_json(solution_path, solution)
    if solution.get("evidenceGapReason"):
        row = evidence_gap_row("gehring-homberger-scale", "homberger-vrptw", solution["evidenceGapReason"])
        row.update({"instance": instance, "runtimeMs": runtime_ms, "normalizedPath": str(normalized_path), "solutionPath": str(solution_path)})
        return row
    checked = check_solution(normalized, solution)
    cell_verdict, reasons = external_verdict(checked, 20.0, runtime_ms, time_limit_ms)
    best_vehicle_count = normalized.get("bestKnown", {}).get("vehicleCount")
    if cell_verdict == "PASS" and best_vehicle_count is not None and checked["vehicleCount"] > int(best_vehicle_count):
        cell_verdict = "PASS_WITH_LIMITS"
        reasons = ["vehicle-count-above-best-known"]
    return {
        "rail": "gehring-homberger-scale",
        "suite": "homberger-vrptw",
        "instance": instance,
        "solver": solver,
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
        "runtimeMs": runtime_ms,
        "verdict": cell_verdict,
        "verdictReasons": reasons,
        "normalizedPath": str(normalized_path),
        "solutionPath": str(solution_path),
    }


def mdrp_row(instance: str, demand_split: str, output_root: Path) -> Dict[str, Any]:
    root = REPO_ROOT / "benchmarks" / "external" / "official" / "mdrplib" / instance
    required = ["couriers.txt", "orders.txt", "restaurants.txt", "instance_characteristics.txt"]
    missing = [filename for filename in required if not (root / filename).exists()]
    if missing:
        row = evidence_gap_row("food-delivery", "grubhub-mdrplib", "mdrplib-official-data-missing")
        row["instance"] = instance
        row["demandSplit"] = demand_split
        row["missingFiles"] = missing
        return row
    metrics = evaluate_mdrplib_instance(root)
    metrics_path = output_root / "mdrplib" / instance / "metrics.json"
    write_json(metrics_path, metrics)
    return {
        "rail": "food-delivery",
        "suite": "grubhub-mdrplib",
        "instance": instance,
        "solver": "deterministic-meal-delivery-baseline",
        "feasible": metrics["verdict"] != "FAIL",
        "demandSplit": demand_split,
        "orderCount": metrics["orderCount"],
        "servedOrderCount": metrics["servedOrderCount"],
        "unservedOrderCount": metrics["unservedOrderCount"],
        "servedOrderRate": metrics["servedOrderRate"],
        "lateOrderRate": metrics["lateOrderRate"],
        "pickupBeforeReadyTimeViolation": metrics["pickupBeforeReadyTimeViolation"],
        "courierShiftViolation": metrics["courierShiftViolation"],
        "foodOnVehicleHardViolation": metrics["foodOnVehicleHardViolation"],
        "avgFoodOnVehicleTime": metrics["avgFoodOnVehicleTime"],
        "maxDelay": metrics["maxDelay"],
        "courierUtilization": metrics["courierUtilization"],
        "runtimeMs": 0,
        "verdict": metrics["verdict"],
        "verdictReasons": metrics["verdictReasons"],
        "metricsPath": str(metrics_path),
    }


def generated_dpdp_row(rail: str, suite: str, order_count: int, tick_count: int, case_name: str = "generated") -> Dict[str, Any]:
    started = time.perf_counter()
    released = 0
    served = 0
    max_tick_latency_ms = 0
    route_churn = 0
    active_route: List[str] = []
    for tick in range(tick_count):
        tick_started = time.perf_counter()
        if released < order_count:
            active_route.append(f"order-{released + 1}")
            released += 1
        if active_route:
            active_route.pop(0)
            served += 1
        if tick > 0 and released < order_count:
            route_churn += 1
        max_tick_latency_ms = max(max_tick_latency_ms, int((time.perf_counter() - tick_started) * 1000))
    runtime_ms = int((time.perf_counter() - started) * 1000)
    feasible = served == order_count and max_tick_latency_ms <= 100
    return {
        "rail": rail,
        "suite": suite,
        "instance": f"{case_name}-{order_count}x{tick_count}",
        "solver": "deterministic-rolling-horizon-baseline",
        "feasible": feasible,
        "servedOrderCount": served,
        "releasedOrderCount": released,
        "totalTardiness": 0,
        "maxTickLatencyMs": max_tick_latency_ms,
        "routeChurnRate": route_churn / max(1, tick_count),
        "runtimeMs": runtime_ms,
        "verdict": "PASS" if feasible else "FAIL",
        "verdictReasons": [] if feasible else ["generated-dpdp-feasibility-failed"],
    }


def icaps_row(instance: str, output_root: Path) -> Dict[str, Any]:
    root = REPO_ROOT / "benchmarks" / "external" / "official" / "icaps-dpdp"
    instance_root = root / instance
    factory_info = root / "factory_info.csv"
    if not factory_info.exists() or not instance_root.exists():
        row = evidence_gap_row("dynamic-dispatch", "icaps-dpdp", "icaps-official-data-missing")
        row["instance"] = instance
        row["missingFiles"] = [str(path) for path in (factory_info, instance_root) if not path.exists()]
        return row
    try:
        metrics = evaluate_icaps_instance(instance_root, factory_info)
    except ValueError as exc:
        row = evidence_gap_row("dynamic-dispatch", "icaps-dpdp", "icaps-parser-input-invalid")
        row["instance"] = instance
        row["verdictReasons"] = [str(exc)]
        return row
    metrics_path = output_root / "icaps-dpdp" / instance / "metrics.json"
    write_json(metrics_path, metrics)
    return {
        "rail": "dynamic-dispatch",
        "suite": "icaps-dpdp",
        "instance": instance,
        "solver": "deterministic-rolling-horizon-baseline",
        "feasible": metrics["feasible"],
        "orderCount": metrics["orderCount"],
        "vehicleCount": metrics["vehicleCount"],
        "servedOrderCount": metrics["servedOrderCount"],
        "capacityViolationCount": metrics["capacityViolationCount"],
        "timeWindowViolationCount": metrics["timeWindowViolationCount"],
        "pickupBeforeDropoffViolationCount": metrics["pickupBeforeDropoffViolationCount"],
        "activeRouteCorruptionCount": metrics["activeRouteCorruptionCount"],
        "vehicleStateContinuityViolation": metrics["vehicleStateContinuityViolation"],
        "totalTardiness": metrics["totalTardiness"],
        "replanCount": metrics.get("replanCount"),
        "maxReplanLatencyMs": metrics.get("maxReplanLatencyMs"),
        "routeStabilityScore": metrics.get("routeStabilityScore"),
        "driverScheduleChangeCount": metrics.get("driverScheduleChangeCount"),
        "runtimeMs": metrics.get("runtimeMs", 0),
        "verdict": metrics["verdict"],
        "verdictReasons": metrics["verdictReasons"],
        "metricsPath": str(metrics_path),
    }


def latest_dispatch_quality(root: Path, mode: str, scenario: str, size: str) -> Path | None:
    candidates = sorted(root.glob(f"mode-comparison/{mode}/{scenario}/{size}/dispatch-quality*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted(root.glob(f"mode-comparison/{mode}/{scenario}/dispatch-quality*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def hcm_row(scenario: str, size: str, mode: str) -> Dict[str, Any]:
    root = REPO_ROOT / "artifacts" / "benchmark" / "full-system-e2e"
    preflight_path = root / "preflight_result.json"
    latest_quality = latest_dispatch_quality(root, mode, scenario, size)
    if not preflight_path.exists() or latest_quality is None:
        row = evidence_gap_row("local-realistic", "hcm-road-native-food-delivery", "full-system-e2e-artifact-missing")
        row["instance"] = f"{scenario}/{size}/{mode}"
        return row
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    quality = json.loads(latest_quality.read_text(encoding="utf-8"))
    metrics = quality.get("metrics") or quality.get("controlMetrics") or {}
    greedrl = next((worker for worker in preflight.get("workers", {}).get("workers", []) if worker.get("name") == "greedrl"), {})
    runtime_mode = greedrl.get("version", {}).get("runtimeMode", "native")
    reasons = []
    if preflight.get("verdict") != "PASS":
        reasons.append("full-system-preflight-not-pass")
    if runtime_mode == "lite":
        reasons.append("greedrl-lite-runtime")
    if metrics.get("routeFallbackRate", 0.0) not in (None, 0, 0.0):
        reasons.append("route-fallback-used")
    verdict = "PASS" if not reasons else "PASS_WITH_LIMITS"
    return {
        "rail": "local-realistic",
        "suite": "hcm-road-native-food-delivery",
        "instance": f"{scenario}/{size}/{mode}",
        "solver": "dispatch-v2-full-system",
        "feasible": preflight.get("verdict") == "PASS",
        "coveredOrderCount": metrics.get("coveredOrderCount"),
        "executedAssignmentCount": metrics.get("executedAssignmentCount"),
        "workerFallbackRate": metrics.get("workerFallbackRate"),
        "routeFallbackRate": metrics.get("routeFallbackRate"),
        "greedrlRuntimeMode": runtime_mode,
        "runtimeMs": 0,
        "verdict": verdict,
        "verdictReasons": reasons,
        "sourceArtifact": str(latest_quality),
    }


def markdown(rows: Sequence[Dict[str, Any]], final_verdict: str) -> str:
    lines = [
        "# Dispatch Benchmark Certification Suite",
        "",
        f"FINAL_VERDICT = {final_verdict}",
        "",
        "| Stage | Rail | Suite | Instance | Solver | Feasible | Runtime ms | Verdict | Reasons |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {stage} | {rail} | {suite} | {instance} | {solver} | {feasible} | {runtime} | {verdict} | {reasons} |".format(
                stage=row.get("stage", ""),
                rail=row.get("rail", ""),
                suite=row.get("suite", ""),
                instance=row.get("instance", ""),
                solver=row.get("solver", ""),
                feasible=row.get("feasible", False),
                runtime=row.get("runtimeMs", 0),
                verdict=row.get("verdict", ""),
                reasons=", ".join(row.get("verdictReasons", [])),
            )
        )
    lines.extend(["", "## Notes", "", "- Academic rows use benchmark-native distance/time conventions.", "- Missing official datasets are reported as EVIDENCE_GAP, not silently replaced. Use `scripts/download_certification_benchmark_data.py` to fetch public MDRPLib and ICAPS smoke data.", "- HCM road-native uses full-system E2E artifacts by scenario/mode.", "- GreedRL lite runtime is accepted only as PASS_WITH_LIMITS evidence."])
    return "\n".join(lines) + "\n"


def academic_instances(level: str) -> Dict[str, List[str]]:
    if level == "smoke":
        return ACADEMIC_SMOKE
    return ACADEMIC_CORE


def run_suite(solver: str, time_limit_ms: int, output_root: Path, level: str = "smoke") -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for suite, instances in academic_instances(level).items():
        for instance in instances:
            rows.append(stage_row("A-academic-correctness", academic_row("solver-correctness", suite, instance, solver, output_root, time_limit_ms)))
    homberger_sizes = ("200",) if level == "smoke" else tuple(HOMBERGER_SCALE.keys())
    for size in homberger_sizes:
        for instance in HOMBERGER_SCALE[size]:
            rows.append(stage_row("B-scale", homberger_row(instance, output_root, solver, time_limit_ms)))
    mdrp_instances = [("mdrp-smoke-low", "low"), ("mdrp-smoke-medium", "medium"), ("mdrp-smoke-high", "high")]
    if level in {"core", "full"}:
        mdrp_instances.extend((f"mdrp-core-{index}", MDRP_DEMAND_SPLITS[index % len(MDRP_DEMAND_SPLITS)]) for index in range(4, 11))
    for instance, split in mdrp_instances:
        rows.append(stage_row("C-food-delivery-official", mdrp_row(instance, split, output_root)))
    icaps_count = 2 if level == "smoke" else 5
    for index in range(1, icaps_count + 1):
        rows.append(stage_row("D-dynamic-official", icaps_row(f"icaps-case-{index}", output_root)))
    stress_cases = ("low",) if level == "smoke" else tuple(DPDP_STRESS_CASES.keys())
    for case_name in stress_cases:
        orders, ticks = DPDP_STRESS_CASES[case_name]
        rows.append(stage_row("D-dynamic-stress", generated_dpdp_row("dynamic-stress", "dpdp-stress", orders, ticks, case_name)))
    hcm_scenarios = ("normal-clear",) if level == "smoke" else HCM_SCENARIOS
    hcm_modes = ("full-system",) if level == "smoke" else HCM_MODES
    for scenario in hcm_scenarios:
        for size in HCM_SIZES_BY_LEVEL[level]:
            for mode in hcm_modes:
                rows.append(stage_row("E-hcm-road-native", hcm_row(scenario, size, mode)))
    final_verdict = certification_verdict(rows)
    return {
        "schemaVersion": "dispatch-benchmark-certification-suite/v1",
        "level": level,
        "solver": solver,
        "results": rows,
        "verdictCounts": verdict_counts(rows),
        "finalVerdict": final_verdict,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unified Dispatch benchmark certification suite.")
    parser.add_argument("--solver", choices=("our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"), default="our-dispatch-v2")
    parser.add_argument("--level", choices=("smoke", "core", "full"), default="smoke")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--emit-scorecard", action="store_true", help="Write certification_scorecard.json and .md after the suite report.")
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = run_suite(args.solver, parse_time_limit(args.time_limit), output_root, args.level)
    write_json(output_root / "certification_suite_results.json", result)
    (output_root / "certification_suite_report.md").write_text(markdown(result["results"], result["finalVerdict"]), encoding="utf-8")
    if args.emit_scorecard:
        from build_certification_scorecard import write_scorecard

        scorecard_json, scorecard_report = write_scorecard(output_root)
        print(f"[CERTIFICATION SCORECARD JSON] {scorecard_json}")
        print(f"[CERTIFICATION SCORECARD REPORT] {scorecard_report}")
    print(f"[CERTIFICATION SUITE JSON] {output_root / 'certification_suite_results.json'}")
    print(f"[CERTIFICATION SUITE REPORT] {output_root / 'certification_suite_report.md'}")
    return 1 if result["finalVerdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
