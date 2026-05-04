from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_instance, parse_time_limit, resolve_instance_path
from run_phase40_natural_pdptw_optimizer import objective_components, objective_config
from run_phase56b_stable_promoted_runner import run as run_stable_promoted


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase58a-vroom-industry-comparator-v1"


def write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def node_by_id(instance: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(node.get("id")): node for node in instance.get("nodes", [])}


def matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}


def time_window(node: Dict[str, Any]) -> List[List[int]]:
    return [[int(round(float(node.get("readyTime", 0.0)))), int(round(float(node.get("dueTime", 0.0))))]]


def vroom_location(indexes: Dict[str, int], node_id: str) -> List[int]:
    return [indexes[str(node_id)]]


def convert_pdptw_to_vroom(instance: Dict[str, Any]) -> Dict[str, Any]:
    nodes = node_by_id(instance)
    indexes = matrix_index(instance)
    depot = str(instance.get("depotNodeId", "0"))
    capacity = int(instance.get("capacity", 0) or 0)
    vehicle_count = int(instance.get("vehicleCount", 1) or 1)
    matrix = [[int(round(float(value))) for value in row] for row in instance.get("distanceMatrix", [])]
    shipments = []
    for request_index, request in enumerate(instance.get("requests", []), start=1):
        pickup_id = str(request.get("pickupNodeId"))
        dropoff_id = str(request.get("dropoffNodeId"))
        pickup = nodes[pickup_id]
        dropoff = nodes[dropoff_id]
        amount = abs(int(round(float(pickup.get("demand", request.get("demand", 1) or 1))))) or 1
        shipments.append(
            {
                "pickup": {
                    "id": request_index * 2 - 1,
                    "location_index": indexes[pickup_id],
                    "service": int(round(float(pickup.get("serviceTime", 0.0)))) ,
                    "time_windows": time_window(pickup),
                    "description": pickup_id,
                },
                "delivery": {
                    "id": request_index * 2,
                    "location_index": indexes[dropoff_id],
                    "service": int(round(float(dropoff.get("serviceTime", 0.0)))) ,
                    "time_windows": time_window(dropoff),
                    "description": dropoff_id,
                },
                "amount": [amount],
            }
        )
    vehicles = []
    depot_node = nodes[depot]
    for vehicle_id in range(1, vehicle_count + 1):
        vehicles.append(
            {
                "id": vehicle_id,
                "start_index": indexes[depot],
                "end_index": indexes[depot],
                "capacity": [capacity],
                "time_window": time_window(depot_node)[0],
            }
        )
    return {
        "vehicles": vehicles,
        "shipments": shipments,
        "matrices": {"car": {"durations": matrix, "distances": matrix}},
    }


def step_node_id(step: Dict[str, Any]) -> str | None:
    if step.get("type") in {"start", "end", "break"}:
        return None
    description = step.get("description")
    if description is not None:
        return str(description)
    if step.get("location_index") is not None:
        return str(step.get("location_index"))
    return None


def vroom_output_to_solution(instance: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    routes: List[List[str]] = []
    for route in payload.get("routes", []):
        stops = [depot]
        for step in route.get("steps", []):
            node_id = step_node_id(step)
            if node_id is None or node_id == depot:
                continue
            stops.append(str(node_id))
        stops.append(depot)
        if len(stops) > 2:
            routes.append(stops)
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "vroom-industry-champion", "routes": routes}


def exact_pair_coverage(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    seen: Dict[Tuple[str, str], int] = {}
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    incomplete = []
    for request in instance.get("requests", []):
        pair = (str(request.get("pickupNodeId")), str(request.get("dropoffNodeId")))
        count = 0
        for route in routes:
            if pair[0] in route or pair[1] in route:
                if pair[0] in route and pair[1] in route and route.index(pair[0]) < route.index(pair[1]):
                    count += 1
                else:
                    incomplete.append(pair)
        seen[pair] = count
    missing = [pair for pair, count in seen.items() if count == 0]
    duplicate = [pair for pair, count in seen.items() if count > 1]
    return {"valid": not missing and not duplicate and not incomplete, "missing": missing, "duplicate": duplicate, "incomplete": incomplete}


def run_vroom_http(vroom_url: str, request: Dict[str, Any], timeout_seconds: int = 60) -> Tuple[Dict[str, Any] | None, str | None]:
    data = json.dumps(request).encode("utf-8")
    url = vroom_url.rstrip("/")
    http_request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (urllib.error.URLError, TimeoutError, OSError) as exception:
        return None, str(exception)


def run_vroom_bin(vroom_bin: str, request_path: Path, timeout_seconds: int = 60) -> Tuple[Dict[str, Any] | None, str | None]:
    try:
        completed = subprocess.run([vroom_bin, "-i", str(request_path)], capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except (OSError, subprocess.TimeoutExpired) as exception:
        return None, str(exception)
    if completed.returncode != 0:
        return None, completed.stderr.strip() or completed.stdout.strip()
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as exception:
        return None, str(exception)


def classify(champion: Dict[str, Any], challenger: Dict[str, Any], unsupported_mapping: bool, vroom_unavailable: bool, distance_tolerance: float = 0.01) -> str:
    if unsupported_mapping:
        return "unsupported-mapping"
    if vroom_unavailable:
        return "vroom-unavailable"
    champion_hard = int(champion.get("hardViolations", 0) or 0) > 0
    challenger_hard = int(challenger.get("hardViolations", 0) or 0) > 0
    if champion_hard and challenger_hard:
        return "both-hard-fail"
    if challenger_hard:
        return "challenger-hard-fail"
    if champion_hard:
        return "vroom-hard-fail"
    champion_vehicles = int(champion.get("vehicleCount", 0) or 0)
    challenger_vehicles = int(challenger.get("vehicleCount", 0) or 0)
    if challenger_vehicles < champion_vehicles:
        return "challenger-win"
    if challenger_vehicles > champion_vehicles:
        return "vroom-win"
    champion_distance = float(champion.get("totalDistance", 0.0) or 0.0)
    challenger_distance = float(challenger.get("totalDistance", 0.0) or 0.0)
    if champion_distance <= 0 or abs(challenger_distance - champion_distance) <= max(1e-9, champion_distance * distance_tolerance):
        return "tie"
    return "challenger-win" if challenger_distance < champion_distance else "vroom-win"


def metrics(instance: Dict[str, Any], solution: Dict[str, Any], mode: str) -> Dict[str, Any]:
    checked = check_solution(instance, solution)
    config = objective_config(mode)
    components = objective_components(instance, solution, config)
    return {
        "feasible": bool(checked.get("feasible")),
        "hardViolations": 0 if checked.get("feasible") else len(checked.get("violations", [])),
        "violations": checked.get("violations", []),
        "vehicleCount": checked.get("vehicleCount"),
        "totalDistance": checked.get("totalDistance"),
        "objective": components.get("objective"),
    }


def run_instance(instance_name: str, args: argparse.Namespace, output_dir: Path) -> Dict[str, Any]:
    instance = parse_instance("li-lim", resolve_instance_path("li-lim", instance_name, args.data_source))
    vroom_request = convert_pdptw_to_vroom(instance)
    write_json(output_dir / "vroom_requests" / f"{instance_name}.json", vroom_request)
    unsupported_mapping = not vroom_request.get("shipments")
    vroom_payload = None
    vroom_error = None
    vroom_runtime_ms = 0
    if not args.skip_vroom_run and not args.dry_run_conversion:
        started = time.perf_counter()
        if args.vroom_url:
            vroom_payload, vroom_error = run_vroom_http(args.vroom_url, vroom_request)
        elif args.vroom_bin:
            vroom_payload, vroom_error = run_vroom_bin(args.vroom_bin, output_dir / "vroom_requests" / f"{instance_name}.json")
        else:
            vroom_error = "vroom-runner-not-configured"
        vroom_runtime_ms = int((time.perf_counter() - started) * 1000)
    vroom_unavailable = bool(vroom_error)
    champion_solution = {"routes": []}
    champion_metrics = {"hardViolations": 0 if args.dry_run_conversion or args.skip_vroom_run else 1, "vehicleCount": None, "totalDistance": None, "objective": None, "feasible": False, "violations": [vroom_error] if vroom_error else []}
    coverage = {"valid": False, "missing": [], "duplicate": [], "incomplete": []}
    if vroom_payload is not None:
        write_json(output_dir / "vroom_results" / f"{instance_name}.json", vroom_payload)
        champion_solution = vroom_output_to_solution(instance, vroom_payload)
        coverage = exact_pair_coverage(instance, champion_solution)
        champion_metrics = metrics(instance, champion_solution, args.mode)
    challenger_summary = run_stable_promoted([instance_name], output_dir / "challenger_results" / instance_name, args.data_source, parse_time_limit(args.challenger_time_limit), args.mode, repeat=1, stable_incumbent_replay=True)
    challenger_row = challenger_summary.get("results", [{}])[0]
    challenger_metrics = {
        "hardViolations": challenger_row.get("hardViolations"),
        "overBudget": challenger_row.get("wallClockOverBudget") or challenger_row.get("stageRuntimeSummary", {}).get("overBudget"),
        "runtimeMs": challenger_row.get("actualRuntimeMs", challenger_row.get("runtimeMs")),
        "vehicleCount": challenger_row.get("vehicleCountAfter"),
        "totalDistance": challenger_row.get("distanceAfter"),
        "objective": challenger_row.get("objectiveAfter"),
        "verdict": challenger_row.get("verdict"),
    }
    classification = classify(champion_metrics, challenger_metrics, unsupported_mapping, vroom_unavailable or args.dry_run_conversion or args.skip_vroom_run)
    return {
        "instance": instance.get("instanceName", instance_name),
        "classification": classification,
        "unsupportedMapping": unsupported_mapping,
        "vroomUnavailable": vroom_unavailable or args.dry_run_conversion or args.skip_vroom_run,
        "vroomError": vroom_error,
        "vroomRuntimeMs": vroom_runtime_ms,
        "vroomCoverage": coverage,
        "champion": champion_metrics,
        "challenger": challenger_metrics,
    }


def aggregate(rows: List[Dict[str, Any]], dry_run: bool) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    unknown = counts.get("unknown", 0)
    challenger_hard = sum(1 for row in rows if int(row.get("challenger", {}).get("hardViolations", 0) or 0) > 0)
    mapping_or_run_ok = bool(rows) and (dry_run or any(not row.get("vroomUnavailable") for row in rows))
    diagnostic_pass = mapping_or_run_ok and unknown == 0 and challenger_hard == 0
    promote_candidate = diagnostic_pass and not dry_run and counts.get("vroom-win", 0) == 0 and counts.get("challenger-hard-fail", 0) == 0 and counts.get("unsupported-mapping", 0) == 0 and counts.get("vroom-unavailable", 0) == 0
    return {
        "classificationCounts": counts,
        "challengerHardFailCount": challenger_hard,
        "diagnosticGate": "PROMOTE_CANDIDATE" if promote_candidate else "DIAGNOSTIC_PASS" if diagnostic_pass else "FAIL",
    }


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 58A VROOM Industry Comparator", "", f"Gate: **{summary['aggregate']['diagnosticGate']}**", "", "| Instance | Classification | VROOM Vehicles | Challenger Vehicles | VROOM Distance | Challenger Distance |", "|---|---|---:|---:|---:|---:|"]
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['classification']} | {row['champion'].get('vehicleCount')} | {row['challenger'].get('vehicleCount')} | {row['champion'].get('totalDistance')} | {row['challenger'].get('totalDistance')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 56F stable runner against VROOM industry-standard champion.")
    parser.add_argument("--instances", default="lrc202,lrc106")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--challenger-time-limit", default="30s")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--vroom-bin", default="")
    parser.add_argument("--dry-run-conversion", action="store_true")
    parser.add_argument("--skip-vroom-run", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [run_instance(instance, args, output_dir) for instance in instances]
    summary = {"schemaVersion": "phase58a-vroom-industry-comparator/v1", "champion": "vroom", "challenger": "phase56f-stable-certification", "rows": rows, "aggregate": aggregate(rows, args.dry_run_conversion or args.skip_vroom_run)}
    write_json(output_dir / "per_instance_comparison.json", rows)
    write_json(output_dir / "aggregate_summary.json", summary)
    (output_dir / "aggregate_summary.md").write_text(markdown(summary), encoding="utf-8")
    print(f"[PHASE58A VROOM COMPARATOR] wrote {output_dir}")
    return 0 if summary["aggregate"]["diagnosticGate"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

