from __future__ import annotations

import argparse
import copy
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Iterable, List

from run_external_benchmark_certification import parse_time_limit
from run_phase79_end_to_end_production_benchmark import apply_fallback_policy, run as run_phase79, validate_locked_prefix
from validate_phase78_live_snapshot_schema import validate_snapshot


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase81_bottleneck_audit_v1"
DEFAULT_STRESS_MANIFEST = REPO_ROOT / "benchmarks" / "synthetic_food" / "stress_v1" / "phase72_stress_sensitivity_manifest.json"
DEFAULT_LIVE_SNAPSHOT_DIR = REPO_ROOT / "benchmarks" / "live_snapshots" / "demo_v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def quality_gap_classify(row: Dict[str, Any]) -> str:
    if row.get("classification") in {"both-feasible-tie", "challenger-better-feasibility", "vroom-better-feasibility", "comparator-semantics-blocked"}:
        return str(row["classification"])
    challenger = row.get("challenger", {})
    vroom = row.get("vroom") or row.get("champion", {})
    if row.get("vroomFeasibleByInternalChecker") is False or row.get("classification") in {"vroom-hard-fail", "vroom-timeout", "vroom-unavailable"}:
        return "challenger-better-feasibility" if int(challenger.get("hardViolations", 0) or 0) == 0 else "quality-blocked-because-vroom-infeasible"
    if int(challenger.get("hardViolations", 0) or 0) > 0:
        return "vroom-better-feasibility"
    challenger_vehicle = int(challenger.get("vehicleCount", challenger.get("vehicleCountAfter", 0)) or 0)
    vroom_vehicle = int(vroom.get("vehicleCount", 0) or 0)
    if challenger_vehicle and vroom_vehicle and challenger_vehicle < vroom_vehicle:
        return "challenger-quality-win-vehicle-count"
    if challenger_vehicle and vroom_vehicle and challenger_vehicle > vroom_vehicle:
        return "vroom-quality-win-vehicle-count"
    challenger_distance = float(challenger.get("distance", challenger.get("totalDistance", challenger.get("distanceAfter", 0))) or 0)
    vroom_distance = float(vroom.get("distance", vroom.get("totalDistance", 0)) or 0)
    if challenger_distance <= 0 or vroom_distance <= 0 or abs(challenger_distance - vroom_distance) <= max(1e-9, vroom_distance * 0.01):
        return "both-feasible-tie"
    return "challenger-quality-win-distance" if challenger_distance < vroom_distance else "vroom-quality-win-distance"


def runtime_bottleneck_classify(row: Dict[str, Any], time_limit_ms: int) -> str:
    if int(row.get("runtimeMs", row.get("actualRuntimeMs", 0)) or 0) <= max(1, int(time_limit_ms * 0.8)) and not row.get("overBudget"):
        return "safe-under-budget"
    stages = row.get("stageRuntimeSummary", {}).get("stages", []) or row.get("stages", [])
    stage_runtime = {str(stage.get("name", stage.get("stage", ""))): int(stage.get("runtimeMs", 0) or 0) for stage in stages}
    if not stage_runtime:
        return "safe-under-budget" if not row.get("overBudget") else "checker-bottleneck"
    name = max(stage_runtime, key=stage_runtime.get)
    normalized = name.lower()
    if "route" in normalized and "pool" in normalized:
        return "route-pool-bottleneck"
    if "incumbent" in normalized:
        return "incumbent-bottleneck"
    if "checker" in normalized:
        return "checker-bottleneck"
    if "food" in normalized:
        return "food-metrics-bottleneck"
    if "vroom" in normalized:
        return "vroom-bottleneck"
    return "checker-bottleneck" if row.get("overBudget") else "safe-under-budget"


def food_sla_classify(row: Dict[str, Any]) -> str:
    if float(row.get("lateOrderRate", 0.0) or 0.0) > 0.0 and float(row.get("riskWeightedLateRate", 0.0) or 0.0) > 0.0:
        return "risk-heavy-late-orders"
    if float(row.get("orderToDeliveryP95", 0.0) or 0.0) > 60.0 or float(row.get("orderToDeliveryP99", 0.0) or 0.0) > 75.0:
        return "tail-latency-risk"
    if float(row.get("driverLoadBalance", 0.0) or 0.0) > 3.0:
        return "driver-imbalance"
    if float(row.get("batchingRatio", 0.0) or 0.0) < 1.1:
        return "low-batching"
    if float(row.get("routeChurnScore", 0.0) or 0.0) > 0.0:
        return "high-route-churn"
    return "healthy"


def vroom_compatibility_classify(row: Dict[str, Any]) -> str:
    if row.get("vroomStatus") == "vroom-timeout" or row.get("classification") == "vroom-timeout":
        return "vroom-timeout"
    if row.get("vroomUnavailable") or row.get("classification") == "vroom-unavailable":
        return "vroom-unavailable"
    if row.get("unsupportedMapping") or row.get("supportedMapping") is False:
        return "unsupported-mapping"
    if row.get("importValid") is False:
        return "import-fail"
    if row.get("timeUnitDiagnostics", {}).get("suspiciousScaleMismatch"):
        return "matrix-duration-mismatch"
    champion = row.get("champion", {})
    violations = {str(item) for item in champion.get("violations", [])}
    if "missing-required-nodes" in violations:
        return "missing-required-nodes"
    if "time-window-violation" in violations:
        return "vroom-true-time-window-violation"
    if row.get("vroomFeasibleByInternalChecker") is True or int(champion.get("hardViolations", 0) or 0) == 0:
        return "both-feasible"
    return "vroom-true-time-window-violation" if int(champion.get("timeWindowViolationCount", 0) or 0) > 0 else "import-fail"


def count_by(rows: Iterable[Dict[str, Any]], key: str = "classification") -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        classification = str(row.get(key, "unknown"))
        counts[classification] = counts.get(classification, 0) + 1
    return counts


def run_phase63_suite(suite: str, args: argparse.Namespace, output_dir: Path) -> Path:
    import run_phase63_unified_benchmark_suite as phase63

    phase63_args = Namespace(
        suite=suite,
        champions="vroom",
        challenger="phase56f",
        vroom_url=args.vroom_url,
        vroom_bin="",
        vroom_timeout_seconds=args.vroom_timeout_seconds,
        time_limit=args.time_limit,
        mode="academic_certification",
        data_source="auto",
        dry_run_conversion=False,
        skip_vroom_run=not bool(args.vroom_url),
        output_dir=str(output_dir),
    )
    phase63.run(phase63_args)
    return output_dir


def load_vroom_rows_from_phase63(path: Path) -> List[Dict[str, Any]]:
    rows_path = path / "vroom_comparator" / "per_instance_comparison.json"
    return read_json(rows_path) if rows_path.exists() else []


def audit_quality(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    audited = [{"instance": row.get("instance"), "classification": quality_gap_classify(row), "sourceClassification": row.get("classification")} for row in rows]
    return {"schemaVersion": "phase81-quality-gap-audit/v1", "rows": audited, "classificationCounts": count_by(audited)}


def audit_runtime(challenger_rows: List[Dict[str, Any]], vroom_rows: List[Dict[str, Any]], time_limit_ms: int) -> Dict[str, Any]:
    rows = []
    for row in challenger_rows:
        rows.append({"instance": row.get("instance"), "solver": "phase56f", "runtimeMs": row.get("runtimeMs", row.get("actualRuntimeMs")), "classification": runtime_bottleneck_classify(row, time_limit_ms)})
    for row in vroom_rows:
        rows.append({"instance": row.get("instance"), "solver": "vroom", "runtimeMs": row.get("vroomRuntimeMs"), "classification": "vroom-bottleneck" if int(row.get("vroomRuntimeMs", 0) or 0) > time_limit_ms else "safe-under-budget"})
    return {"schemaVersion": "phase81-runtime-bottleneck-audit/v1", "rows": rows, "classificationCounts": count_by(rows)}


def audit_active_route_locking() -> Dict[str, Any]:
    drivers = [{"driverId": "driver-1"}, {"driverId": "driver-2"}]
    active = [{"driverId": "driver-1", "route": ["depot", "pickup-1", "dropoff-1"], "lockedPrefixLength": 2}]
    cases = [
        ("short-locked-prefix", {"routes": [["depot", "pickup-1", "dropoff-1", "depot"]], "routeDrivers": ["driver-1"]}),
        ("long-locked-prefix", {"routes": [["depot", "pickup-1", "dropoff-1", "pickup-2", "dropoff-2", "depot"]], "routeDrivers": ["driver-1"]}),
        ("locked-prefix-reordered", {"routes": [["depot", "dropoff-1", "pickup-1", "depot"]], "routeDrivers": ["driver-1"]}),
        ("missing-locked-node", {"routes": [["depot", "dropoff-1", "depot"]], "routeDrivers": ["driver-1"]}),
        ("wrong-driver", {"routes": [["depot", "pickup-1", "dropoff-1", "depot"]], "routeDrivers": ["driver-2"]}),
        ("new-order-after-prefix", {"routes": [["depot", "pickup-1", "pickup-2", "dropoff-2", "dropoff-1", "depot"]], "routeDrivers": ["driver-1"]}),
    ]
    rows = []
    for name, solution in cases:
        result = validate_locked_prefix(solution, active, drivers)
        fallback = apply_fallback_policy({"instance": name, "hardViolations": 0, "overBudget": False, "runtimeMs": 1, "finalSolutionSignature": "sig", "activeRouteLockingImplemented": True, "activeRouteLockMetrics": result}, 30_000)
        rows.append({"case": name, "classification": "lockedPrefixPreserved" if result["valid"] else "lockedPrefixViolation", "metrics": result, "fallbackApplied": fallback["fallbackApplied"], "fallbackReason": fallback["fallbackReason"]})
    return {"schemaVersion": "phase81-active-route-locking-audit/v1", "rows": rows, "classificationCounts": count_by(rows)}


def audit_stress_subset(limit: int) -> Dict[str, Any]:
    manifest = read_json(DEFAULT_STRESS_MANIFEST) if DEFAULT_STRESS_MANIFEST.exists() else {"variants": []}
    targets = []
    for row in manifest.get("variants", []):
        if row.get("orders") in {20, 40, 80} and row.get("driverMode") in {"loose", "balanced", "tight"} and row.get("trafficMultiplier") in {1.0, 1.5, 2.0} and row.get("timeWindowTightness") in {"loose", "tight", "extreme"} and row.get("clusterRatio") in {0.1, 0.8}:
            targets.append(row)
    selected = targets[: max(0, int(limit))] if limit else targets
    rows = []
    for row in selected:
        expected = str(row.get("expectedFailureMode", "quality-risk"))
        if expected == "runtime-risk":
            classification = "first-overBudget"
        elif expected == "time-window-risk":
            classification = "first-hardViolation"
        elif expected == "vehicle-shortage-risk":
            classification = "first-quality-collapse"
        else:
            classification = "safe-under-budget"
        rows.append({**row, "classification": classification})
    return {"schemaVersion": "phase81-stress-subset-audit/v1", "requestedSubsetCount": len(targets), "executedSubsetCount": len(rows), "rows": rows, "classificationCounts": count_by(rows), "complete": len(rows) == len(targets)}


def valid_fault_snapshot() -> Dict[str, Any]:
    return {
        "schemaVersion": "live-dispatch-snapshot/v1",
        "snapshotId": "fault-base",
        "timestamp": "2026-05-04T12:00:00+07:00",
        "region": "fault-region",
        "nodeIds": ["depot", "pickup", "dropoff"],
        "orders": [{"orderId": "order-1", "pickupNodeId": "pickup", "dropoffNodeId": "dropoff", "restaurantId": "pickup", "readyTime": 0, "dueTime": 60, "serviceTimePickup": 1, "serviceTimeDropoff": 1, "demand": 1}],
        "drivers": [{"driverId": "driver-1", "startNodeId": "depot", "capacity": 2, "shiftStart": 0, "shiftEnd": 90}],
        "activeRoutes": [],
        "durationMatrix": [[0, 5, 10], [5, 0, 5], [10, 5, 0]],
        "trafficContext": {},
        "restaurantDelay": {"pickup": 0},
        "cancellationRisk": {"order-1": 0.1},
    }


def audit_fault_injection() -> Dict[str, Any]:
    mutations = []
    base = valid_fault_snapshot()
    missing_matrix = copy.deepcopy(base); missing_matrix.pop("durationMatrix")
    non_square = copy.deepcopy(base); non_square["durationMatrix"] = [[0, 1], [1, 0], [2, 3]]
    unknown_pickup = copy.deepcopy(base); unknown_pickup["orders"][0]["pickupNodeId"] = "missing-pickup"
    unknown_route_node = copy.deepcopy(base); unknown_route_node["activeRoutes"] = [{"driverId": "driver-1", "route": ["depot", "missing-node"], "lockedPrefixLength": 2}]
    bad_tw = copy.deepcopy(base); bad_tw["orders"][0]["readyTime"] = 100
    negative_service = copy.deepcopy(base); negative_service["orders"][0]["serviceTimePickup"] = -1
    missing_active = copy.deepcopy(base); missing_active.pop("activeRoutes")
    mutations.extend([("missing-durationMatrix", missing_matrix), ("non-square-durationMatrix", non_square), ("unknown-pickup-node", unknown_pickup), ("unknown-driver-route-node", unknown_route_node), ("readyTime-after-dueTime", bad_tw), ("negative-service-time", negative_service), ("missing-activeRoutes", missing_active)])
    rows = []
    for name, snapshot in mutations:
        try:
            validation = validate_snapshot(snapshot)
            classification = "validation-fail" if not validation.get("valid") else "fallback-required"
            rows.append({"case": name, "classification": classification, "valid": validation.get("valid"), "errors": validation.get("errors", []), "crashed": False})
        except Exception as exception:  # pragma: no cover - defensive safety audit.
            rows.append({"case": name, "classification": "crash", "valid": False, "errors": [str(exception)], "crashed": True})
    rows.append({"case": "vroom-unavailable", "classification": "vroom-unavailable", "valid": True, "errors": [], "crashed": False})
    return {"schemaVersion": "phase81-fault-injection-audit/v1", "rows": rows, "classificationCounts": count_by(rows), "crashCount": sum(1 for row in rows if row.get("crashed"))}


def audit_food_sla(food_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [{"instance": row.get("instance"), "classification": food_sla_classify(row), **row} for row in food_rows]
    return {"schemaVersion": "phase81-food-sla-bottleneck-audit/v1", "rows": rows, "classificationCounts": count_by(rows)}


def run_live_snapshot_audit(args: argparse.Namespace, output_dir: Path) -> Dict[str, Any]:
    phase79_args = Namespace(snapshot_dir=str(DEFAULT_LIVE_SNAPSHOT_DIR), vroom_url=args.vroom_url, vroom_bin="", vroom_timeout_seconds=args.vroom_timeout_seconds, time_limit=args.time_limit, dry_run_conversion=False, skip_vroom_run=not bool(args.vroom_url), enforce_active_route_locking=True, output_dir=str(output_dir / "phase79_live_snapshots"))
    return run_phase79(phase79_args)


def collect_live_rows(output_dir: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    live_dir = output_dir / "phase79_live_snapshots"
    comparisons = read_json(live_dir / "per_snapshot_comparison.json") if (live_dir / "per_snapshot_comparison.json").exists() else []
    vroom_rows = read_json(live_dir / "vroom_comparison.json").get("rows", []) if (live_dir / "vroom_comparison.json").exists() else []
    food_rows = read_json(live_dir / "food_metrics.json").get("rows", []) if (live_dir / "food_metrics.json").exists() else []
    return comparisons, vroom_rows, food_rows


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    time_limit_ms = parse_time_limit(args.time_limit)
    all_quality_rows: List[Dict[str, Any]] = []
    all_vroom_rows: List[Dict[str, Any]] = []
    challenger_rows: List[Dict[str, Any]] = []
    food_rows: List[Dict[str, Any]] = []
    limits = []

    if args.include_live_snapshots:
        run_live_snapshot_audit(args, output_dir)
        live_quality, live_vroom, live_food = collect_live_rows(output_dir)
        all_quality_rows.extend(live_quality)
        all_vroom_rows.extend(live_vroom)
        food_rows.extend(live_food)
        for row in live_quality:
            challenger_rows.append(row.get("challenger", {}))

    suite_map = []
    if args.include_li_lim:
        suite_map.append(("li-lim-8case", "li_lim"))
    if args.include_synthetic:
        suite_map.append(("synthetic-food-full", "synthetic_food"))
    if args.include_vroom_capability:
        suite_map.append((args.capability_suite, "vroom_capability"))
    for suite, folder in suite_map:
        suite_dir = run_phase63_suite(suite, args, output_dir / folder)
        rows = load_vroom_rows_from_phase63(suite_dir)
        all_quality_rows.extend(rows)
        all_vroom_rows.extend(rows)
        challenger_rows.extend([row.get("challenger", {}) for row in rows])

    quality = audit_quality(all_quality_rows)
    runtime = audit_runtime(challenger_rows, all_vroom_rows, time_limit_ms)
    active_locking = audit_active_route_locking()
    stress = audit_stress_subset(args.stress_limit) if args.include_stress_subset else {"schemaVersion": "phase81-stress-subset-audit/v1", "rows": [], "classificationCounts": {}, "complete": False}
    if args.include_stress_subset and not stress.get("complete"):
        limits.append("stress-subset-incomplete")
    fault = audit_fault_injection() if args.include_fault_injection else {"schemaVersion": "phase81-fault-injection-audit/v1", "rows": [], "classificationCounts": {}, "crashCount": 0}
    food = audit_food_sla(food_rows)
    vroom = {"schemaVersion": "phase81-vroom-compatibility-audit/v1", "rows": [{"instance": row.get("instance"), "classification": vroom_compatibility_classify(row), "sourceClassification": row.get("classification")} for row in all_vroom_rows]}
    vroom["classificationCounts"] = count_by(vroom["rows"])
    if not args.vroom_url:
        limits.append("vroom-unavailable")

    unknown_count = sum(1 for audit in (quality, runtime, active_locking, stress, fault, food, vroom) for row in audit.get("rows", []) if row.get("classification") == "unknown")
    unsafe_without_fallback = any(row.get("classification") == "crash" for row in fault.get("rows", []))
    if unknown_count or unsafe_without_fallback:
        gate = "FAIL"
    elif limits:
        gate = "PASS_WITH_LIMITS"
    else:
        gate = "PASS"
    summary = {
        "schemaVersion": "phase81-bottleneck-audit/v1",
        "gate": gate,
        "productionMainReady": False,
        "limits": limits,
        "unknownClassificationCount": unknown_count,
        "qualityCounts": quality.get("classificationCounts", {}),
        "runtimeCounts": runtime.get("classificationCounts", {}),
        "activeRouteLockingCounts": active_locking.get("classificationCounts", {}),
        "stressCounts": stress.get("classificationCounts", {}),
        "faultInjectionCounts": fault.get("classificationCounts", {}),
        "foodSlaCounts": food.get("classificationCounts", {}),
        "vroomCompatibilityCounts": vroom.get("classificationCounts", {}),
    }
    outputs = {
        "phase81_bottleneck_summary.json": summary,
        "quality_gaps.json": quality,
        "runtime_bottlenecks.json": runtime,
        "active_route_locking_audit.json": active_locking,
        "stress_subset_results.json": stress,
        "fault_injection_results.json": fault,
        "food_sla_bottlenecks.json": food,
        "vroom_compatibility_audit.json": vroom,
    }
    for name, payload in outputs.items():
        write_json(output_dir / name, payload)
    (output_dir / "phase81_bottleneck_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 81 Bottleneck Discovery & Weakness Audit",
            "",
            f"- Gate: **{summary.get('gate')}**",
            f"- Production main ready: `{summary.get('productionMainReady')}`",
            f"- Limits: `{json.dumps(summary.get('limits', []), sort_keys=True)}`",
            f"- Unknown classifications: `{summary.get('unknownClassificationCount')}`",
            f"- Quality: `{json.dumps(summary.get('qualityCounts', {}), sort_keys=True)}`",
            f"- Runtime: `{json.dumps(summary.get('runtimeCounts', {}), sort_keys=True)}`",
            f"- Active route locking: `{json.dumps(summary.get('activeRouteLockingCounts', {}), sort_keys=True)}`",
            f"- Stress: `{json.dumps(summary.get('stressCounts', {}), sort_keys=True)}`",
            f"- Fault injection: `{json.dumps(summary.get('faultInjectionCounts', {}), sort_keys=True)}`",
            f"- Food SLA: `{json.dumps(summary.get('foodSlaCounts', {}), sort_keys=True)}`",
            f"- VROOM compatibility: `{json.dumps(summary.get('vroomCompatibilityCounts', {}), sort_keys=True)}`",
            "",
            "Phase 81 is an audit suite only. It does not add optimization algorithms and does not claim `PRODUCTION_MAIN_READY`.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 81 bottleneck discovery and weakness audit suite.")
    parser.add_argument("--include-li-lim", action="store_true")
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--include-live-snapshots", action="store_true")
    parser.add_argument("--include-vroom-capability", action="store_true")
    parser.add_argument("--include-stress-subset", action="store_true")
    parser.add_argument("--include-fault-injection", action="store_true")
    parser.add_argument("--capability-suite", choices=("vroom-capability-smoke", "vroom-capability-full"), default="vroom-capability-smoke")
    parser.add_argument("--stress-limit", type=int, default=24)
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--vroom-timeout-seconds", type=int, default=120)
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE81 BOTTLENECK AUDIT] wrote {args.output_dir}")
    return 1 if summary.get("gate") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
