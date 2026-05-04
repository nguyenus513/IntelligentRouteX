from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from phase67_synthetic_instance_loader import DEFAULT_LIVE_SNAPSHOT_DIR
from run_external_benchmark_certification import parse_time_limit
from run_phase56b_stable_promoted_runner import run as run_phase56f
from run_phase71_food_dispatch_metrics import compute_instance_metrics
from validate_phase78_live_snapshot_schema import validate_snapshot


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "benchmarks" / "live_snapshots" / "demo_v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase79_end_to_end_v1"
DEFAULT_CONVERTED_DIR = DEFAULT_LIVE_SNAPSHOT_DIR


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def snapshot_node_ids(snapshot: Dict[str, Any]) -> List[str]:
    if snapshot.get("nodeIds"):
        return [str(node_id) for node_id in snapshot["nodeIds"]]
    node_ids = ["depot"]
    for driver in snapshot.get("drivers", []):
        node_id = str(driver.get("startNodeId"))
        if node_id not in node_ids:
            node_ids.append(node_id)
    for order in snapshot.get("orders", []):
        for key in ("pickupNodeId", "dropoffNodeId"):
            node_id = str(order.get(key))
            if node_id not in node_ids:
                node_ids.append(node_id)
    return node_ids


def convert_live_snapshot_to_pdptw_instance(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    node_ids = snapshot_node_ids(snapshot)
    matrix = snapshot.get("durationMatrix", [])
    if len(node_ids) != len(matrix):
        raise ValueError("nodeIds length must match durationMatrix size")

    restaurant_delay = snapshot.get("restaurantDelay", {})
    cancellation_risk = snapshot.get("cancellationRisk", {})
    orders_by_pickup = {str(order["pickupNodeId"]): order for order in snapshot.get("orders", [])}
    orders_by_dropoff = {str(order["dropoffNodeId"]): order for order in snapshot.get("orders", [])}
    depot = node_ids[0]
    drivers = snapshot.get("drivers", [])
    capacity = max([int(driver.get("capacity", 0) or 0) for driver in drivers] or [0])
    shift_start = min([float(driver.get("shiftStart", 0) or 0) for driver in drivers] or [0.0])
    shift_end = max([float(driver.get("shiftEnd", 0) or 0) for driver in drivers] or [0.0])
    nodes = []
    for index, node_id in enumerate(node_ids):
        if node_id in orders_by_pickup:
            order = orders_by_pickup[node_id]
            ready_time = float(order["readyTime"]) + float(restaurant_delay.get(str(order.get("restaurantId")), 0) or 0)
            due_time = float(order["dueTime"])
            service_time = float(order.get("serviceTimePickup", 0) or 0)
            demand = int(order.get("demand", 1) or 1)
        elif node_id in orders_by_dropoff:
            order = orders_by_dropoff[node_id]
            ready_time = float(order["readyTime"])
            due_time = float(order["dueTime"])
            service_time = float(order.get("serviceTimeDropoff", 0) or 0)
            demand = -int(order.get("demand", 1) or 1)
        else:
            ready_time = shift_start
            due_time = shift_end
            service_time = 0.0
            demand = 0
        nodes.append({"id": node_id, "x": float(index), "y": 0.0, "readyTime": ready_time, "dueTime": due_time, "serviceTime": service_time, "demand": demand})

    requests = []
    for order in snapshot.get("orders", []):
        order_id = str(order["orderId"])
        requests.append(
            {
                "orderId": order_id,
                "pickupNodeId": str(order["pickupNodeId"]),
                "dropoffNodeId": str(order["dropoffNodeId"]),
                "demand": int(order.get("demand", 1) or 1),
                "cancellationRisk": float(cancellation_risk.get(order_id, 0.0) or 0.0),
            }
        )

    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "problemType": "PDPTW",
        "benchmarkFamily": "live-snapshot",
        "instanceName": str(snapshot["snapshotId"]),
        "depotNodeId": depot,
        "vehicleCount": len(drivers),
        "capacity": capacity,
        "nodes": nodes,
        "requests": requests,
        "orders": requests,
        "drivers": drivers,
        "activeRoutes": snapshot.get("activeRoutes", []),
        "distanceMatrix": matrix,
        "durationMatrix": matrix,
        "constraints": {"pickupDelivery": True, "timeWindows": True, "capacity": capacity},
        "metadata": {
            "schemaVersion": "phase79-live-snapshot-conversion/v1",
            "snapshotId": snapshot.get("snapshotId"),
            "region": snapshot.get("region"),
            "timestamp": snapshot.get("timestamp"),
            "trafficContext": snapshot.get("trafficContext", {}),
            "restaurantDelay": restaurant_delay,
            "cancellationRisk": cancellation_risk,
            "activeRoutes": snapshot.get("activeRoutes", []),
            "activeRouteLockingImplemented": False,
        },
    }


def challenger_metrics(row: Dict[str, Any], instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    food_metrics = compute_instance_metrics(instance, solution)
    return {
        "runtimeMs": int(row.get("actualRuntimeMs", row.get("runtimeMs", 0)) or 0),
        "hardViolations": int(row.get("hardViolations", 0) or 0),
        "overBudget": bool(row.get("wallClockOverBudget") or row.get("stageRuntimeSummary", {}).get("overBudget")),
        "vehicleCount": row.get("vehicleCountAfter"),
        "distance": row.get("distanceAfter"),
        "objective": row.get("objectiveAfter"),
        "finalSolutionSignature": row.get("finalSolutionSignature"),
        "verdict": row.get("verdict"),
        "foodMetrics": food_metrics,
    }


def run_challenger(instances: List[str], output_dir: Path, time_limit_ms: int, time_limit_text: str) -> Dict[str, Any]:
    summary = run_phase56f(instances, output_dir, "auto", time_limit_ms, "production_food_dispatch", repeat=1, benchmark_source="live-snapshot", stable_incumbent_replay=True)
    rows = []
    for row in summary.get("results", []):
        instance_name = str(row.get("instance"))
        instance = read_json(DEFAULT_CONVERTED_DIR / f"{instance_name}.json")
        solution = read_json(output_dir / instance_name / "final_solution.json")
        rows.append({"instance": instance_name, **challenger_metrics(row, instance, solution), "timeLimit": time_limit_text})
    return {"summary": summary, "rows": rows}


def run_vroom(instances: List[str], output_dir: Path, args: argparse.Namespace) -> Dict[str, Any]:
    import run_phase58a_vroom_industry_comparator as phase58

    phase58_args = Namespace(
        benchmark_source="live-snapshot",
        data_source="auto",
        mode="production_food_dispatch",
        challenger_time_limit=args.time_limit,
        vroom_url=args.vroom_url,
        vroom_bin=args.vroom_bin,
        vroom_timeout_seconds=args.vroom_timeout_seconds,
        time_scale=1.0,
        rounding="round",
        dry_run_conversion=args.dry_run_conversion,
        skip_vroom_run=args.skip_vroom_run,
    )
    rows = [phase58.run_instance(instance, phase58_args, output_dir) for instance in instances]
    summary = {"schemaVersion": "phase79-vroom-comparison/v1", "rows": rows, "aggregate": phase58.aggregate(rows, args.dry_run_conversion or args.skip_vroom_run)}
    write_json(output_dir / "per_snapshot_vroom_rows.json", rows)
    write_json(output_dir / "aggregate_summary.json", summary)
    return summary


def fair_compare(challenger: Dict[str, Any], vroom_row: Dict[str, Any] | None) -> str:
    if int(challenger.get("hardViolations", 0) or 0) > 0:
        return "challenger-hard-fail"
    if vroom_row is None:
        return "vroom-unavailable"
    if vroom_row.get("vroomStatus") == "vroom-timeout" or vroom_row.get("classification") == "vroom-timeout":
        return "vroom-timeout"
    if vroom_row.get("vroomUnavailable"):
        return "vroom-unavailable"
    if not vroom_row.get("supportedMapping", True) or not vroom_row.get("importValid", True):
        return "comparator-semantics-blocked"
    champion = vroom_row.get("champion", {})
    vroom_hard = int(champion.get("hardViolations", 0) or 0) > 0 or not bool(vroom_row.get("vroomFeasibleByInternalChecker"))
    if vroom_hard:
        if vroom_row.get("timeUnitDiagnostics", {}).get("suspiciousScaleMismatch"):
            return "comparator-semantics-blocked"
        return "challenger-better-feasibility"
    challenger_distance = float(challenger.get("distance", 0.0) or 0.0)
    vroom_distance = float(champion.get("totalDistance", 0.0) or 0.0)
    if challenger_distance <= 0 or vroom_distance <= 0:
        return "both-feasible-tie"
    tolerance = max(1e-9, vroom_distance * 0.01)
    if abs(challenger_distance - vroom_distance) <= tolerance:
        return "both-feasible-tie"
    return "both-feasible-challenger-distance-win" if challenger_distance < vroom_distance else "both-feasible-vroom-distance-win"


def apply_fallback_policy(challenger: Dict[str, Any], time_limit_ms: int) -> Dict[str, Any]:
    reasons = []
    if int(challenger.get("hardViolations", 0) or 0) > 0:
        reasons.append("challenger-hard-violation")
    if challenger.get("overBudget"):
        reasons.append("challenger-over-budget")
    if int(challenger.get("runtimeMs", 0) or 0) > time_limit_ms:
        reasons.append("runtime-exceeds-budget")
    if not challenger.get("finalSolutionSignature"):
        reasons.append("checker-unavailable-or-missing-signature")
    return {"instance": challenger.get("instance"), "fallbackApplied": bool(reasons), "fallbackReason": ",".join(reasons) if reasons else None, "productionCandidateSafe": not reasons}


def summarize_gate(validation_rows: List[Dict[str, Any]], comparisons: List[Dict[str, Any]], fallback_decisions: List[Dict[str, Any]]) -> str:
    if any(not row.get("valid") for row in validation_rows):
        return "FAIL"
    if any(row.get("classification") == "unknown" for row in comparisons):
        return "FAIL"
    if any(decision.get("fallbackApplied") for decision in fallback_decisions):
        return "FAIL"
    limited = any(row.get("activeRouteLockingImplemented") is False for row in validation_rows) or any(row.get("classification") in {"vroom-unavailable", "comparator-semantics-blocked", "vroom-timeout"} for row in comparisons)
    return "PASS_WITH_LIMITS" if limited else "PASS"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    snapshot_dir = Path(args.snapshot_dir)
    output_dir = Path(args.output_dir)
    converted_dir = DEFAULT_CONVERTED_DIR
    converted_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = sorted(snapshot_dir.glob("*.json"))
    validation_rows = []
    instances = []
    for path in snapshot_paths:
        snapshot = read_json(path)
        validation = validate_snapshot(snapshot)
        row = {"snapshotPath": str(path), "snapshotId": snapshot.get("snapshotId"), "valid": bool(validation.get("valid")), "errors": validation.get("errors", []), "activeRouteLockingImplemented": False}
        validation_rows.append(row)
        if not validation.get("valid"):
            continue
        instance = convert_live_snapshot_to_pdptw_instance(snapshot)
        write_json(converted_dir / f"{instance['instanceName']}.json", instance)
        write_json(output_dir / "converted_instances" / f"{instance['instanceName']}.json", instance)
        instances.append(str(instance["instanceName"]))

    if any(not row.get("valid") for row in validation_rows):
        summary = {"schemaVersion": "phase79-end-to-end-production-benchmark/v1", "gate": "FAIL", "validation": validation_rows, "reason": "invalid-live-snapshot"}
        write_outputs(output_dir, summary, [], [], [], [], [])
        return summary

    time_limit_ms = parse_time_limit(args.time_limit)
    challenger = run_challenger(instances, output_dir / "challenger_phase56f", time_limit_ms, args.time_limit)
    vroom = run_vroom(instances, output_dir / "vroom_comparison", args)
    vroom_by_instance = {str(row.get("instance")): row for row in vroom.get("rows", [])}
    comparisons = []
    food_rows = []
    fallback_decisions = []
    for challenger_row in challenger["rows"]:
        instance_name = str(challenger_row["instance"])
        vroom_row = vroom_by_instance.get(instance_name)
        classification = fair_compare(challenger_row, vroom_row)
        fallback_decision = apply_fallback_policy(challenger_row, time_limit_ms)
        comparisons.append({"instance": instance_name, "classification": classification, "challenger": challenger_row, "vroom": vroom_row})
        food_rows.append({"instance": instance_name, **challenger_row.get("foodMetrics", {})})
        fallback_decisions.append(fallback_decision)

    gate = summarize_gate(validation_rows, comparisons, fallback_decisions)
    classification_counts: Dict[str, int] = {}
    for comparison in comparisons:
        classification_counts[comparison["classification"]] = classification_counts.get(comparison["classification"], 0) + 1
    summary = {
        "schemaVersion": "phase79-end-to-end-production-benchmark/v1",
        "gate": gate,
        "verdict": "PRODUCTION_CANDIDATE_SHADOW_MODE" if gate in {"PASS", "PASS_WITH_LIMITS"} else "NOT_READY",
        "productionMainReady": False,
        "snapshotCount": len(snapshot_paths),
        "validSnapshotCount": sum(1 for row in validation_rows if row.get("valid")),
        "challenger": "phase56f",
        "champion": "vroom",
        "classificationCounts": classification_counts,
        "activeRouteLockingImplemented": False,
        "outputDir": str(output_dir),
    }
    write_outputs(output_dir, summary, validation_rows, comparisons, fallback_decisions, food_rows, vroom.get("rows", []))
    return summary


def write_outputs(output_dir: Path, summary: Dict[str, Any], validation_rows: List[Dict[str, Any]], comparisons: List[Dict[str, Any]], fallback_decisions: List[Dict[str, Any]], food_rows: List[Dict[str, Any]], vroom_rows: List[Dict[str, Any]]) -> None:
    write_json(output_dir / "phase79_summary.json", summary)
    write_json(output_dir / "snapshot_validation.json", validation_rows)
    write_json(output_dir / "per_snapshot_comparison.json", comparisons)
    write_json(output_dir / "fallback_decisions.json", fallback_decisions)
    write_json(output_dir / "food_metrics.json", {"schemaVersion": "phase79-food-metrics/v1", "rows": food_rows})
    write_json(output_dir / "vroom_comparison.json", {"schemaVersion": "phase79-vroom-comparison-rows/v1", "rows": vroom_rows})
    (output_dir / "phase79_summary.md").write_text(markdown(summary, comparisons, fallback_decisions), encoding="utf-8")


def markdown(summary: Dict[str, Any], comparisons: List[Dict[str, Any]], fallback_decisions: List[Dict[str, Any]]) -> str:
    lines = [
        "# Phase 79 End-to-End Production Benchmark",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Verdict: `{summary.get('verdict')}`",
        f"- Production main ready: `{summary.get('productionMainReady')}`",
        f"- Classification counts: `{json.dumps(summary.get('classificationCounts', {}), sort_keys=True)}`",
        f"- Active-route locking implemented: `{summary.get('activeRouteLockingImplemented')}`",
        "",
        "| Snapshot | Classification | Fallback Applied |",
        "|---|---|---:|",
    ]
    fallback_by_instance = {str(row.get("instance")): row for row in fallback_decisions}
    for comparison in comparisons:
        fallback = fallback_by_instance.get(str(comparison.get("instance")), {})
        lines.append(f"| {comparison.get('instance')} | {comparison.get('classification')} | {fallback.get('fallbackApplied')} |")
    lines.extend(["", "This harness does not claim `PRODUCTION_MAIN_READY`; it is a benchmark-to-production bridge for shadow/canary readiness evidence.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 79 end-to-end production-like benchmark harness.")
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR))
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--vroom-bin", default="")
    parser.add_argument("--vroom-timeout-seconds", type=int, default=120)
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--dry-run-conversion", action="store_true")
    parser.add_argument("--skip-vroom-run", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE79 END-TO-END PRODUCTION BENCHMARK] wrote {args.output_dir}")
    return 1 if summary.get("gate") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
