from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from external_benchmark_support import check_solution
from run_external_benchmark_certification import parse_time_limit
from phase67_synthetic_instance_loader import load_benchmark_instance
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


def rounded(value: float, mode: str) -> int:
    if mode == "floor":
        return int(value // 1)
    if mode == "ceil":
        integer = int(value)
        return integer if integer == value else integer + 1
    return int(round(value))


def time_window(node: Dict[str, Any], scale: float = 1.0, rounding: str = "round") -> List[List[int]]:
    return [[rounded(float(node.get("readyTime", 0.0)) * scale, rounding), rounded(float(node.get("dueTime", 0.0)) * scale, rounding)]]


def vroom_location(indexes: Dict[str, int], node_id: str) -> List[int]:
    return [indexes[str(node_id)]]


def convert_pdptw_to_vroom(instance: Dict[str, Any], time_scale: float = 1.0, rounding: str = "round") -> Dict[str, Any]:
    nodes = node_by_id(instance)
    indexes = matrix_index(instance)
    depot = str(instance.get("depotNodeId", "0"))
    capacity = int(instance.get("capacity", 0) or 0)
    vehicle_count = int(instance.get("vehicleCount", 1) or 1)
    matrix = [[rounded(float(value) * time_scale, rounding) for value in row] for row in instance.get("distanceMatrix", [])]
    shipments = []
    for request_index, request in enumerate(instance.get("requests", []), start=1):
        pickup_id = str(request.get("pickupNodeId"))
        dropoff_id = str(request.get("dropoffNodeId"))
        pickup = nodes[pickup_id]
        dropoff = nodes[dropoff_id]
        amount = abs(int(round(float(pickup.get("demand", request.get("demand", 1) or 1))))) or 1
        shipment = {
            "pickup": {
                "id": request_index * 2 - 1,
                "location_index": indexes[pickup_id],
                "service": rounded(float(pickup.get("serviceTime", 0.0)) * time_scale, rounding),
                "time_windows": time_window(pickup, time_scale, rounding),
                "description": pickup_id,
            },
            "delivery": {
                "id": request_index * 2,
                "location_index": indexes[dropoff_id],
                "service": rounded(float(dropoff.get("serviceTime", 0.0)) * time_scale, rounding),
                "time_windows": time_window(dropoff, time_scale, rounding),
                "description": dropoff_id,
            },
            "amount": [amount],
        }
        if request.get("skills"):
            shipment["skills"] = [int(skill) for skill in request.get("skills", [])]
        if request.get("priority") is not None:
            shipment["priority"] = int(request.get("priority"))
        shipments.append(shipment)
    if instance.get("vroomVehicles"):
        vehicles = instance["vroomVehicles"]
    else:
        vehicles = []
        depot_node = nodes[depot]
        for vehicle_id in range(1, vehicle_count + 1):
            vehicles.append(
                {
                    "id": vehicle_id,
                    "start_index": indexes[depot],
                    "end_index": indexes[depot],
                    "capacity": [capacity],
                    "time_window": time_window(depot_node, time_scale, rounding)[0],
                }
            )
    return {
        "vehicles": vehicles,
        "shipments": shipments,
        "matrices": {"car": {"durations": matrix, "distances": matrix}},
    }


def request_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_vroom_request(payload: Dict[str, Any], node_count: int) -> Dict[str, Any]:
    errors = []
    matrix = payload.get("matrices", {}).get("car", {}).get("durations", [])
    if len(matrix) != node_count or any(len(row) != node_count for row in matrix):
        errors.append("matrix-dimension-mismatch")
    if not payload.get("vehicles"):
        errors.append("vehicle-count-zero")
    for vehicle in payload.get("vehicles", []):
        if not vehicle.get("capacity"):
            errors.append("vehicle-capacity-missing")
    for shipment in payload.get("shipments", []):
        if not shipment.get("amount"):
            errors.append("shipment-amount-missing")
        for side in ("pickup", "delivery"):
            step = shipment.get(side, {})
            location = step.get("location_index")
            if location is None or int(location) < 0 or int(location) >= node_count:
                errors.append(f"{side}-location-missing")
            if int(step.get("service", 0) or 0) < 0:
                errors.append(f"{side}-service-negative")
            for window in step.get("time_windows", []):
                if len(window) != 2 or int(window[0]) > int(window[1]):
                    errors.append(f"{side}-time-window-invalid")
    return {"valid": not errors, "errors": sorted(set(errors))}


def time_unit_diagnostics(instance: Dict[str, Any], payload: Dict[str, Any], response: Dict[str, Any] | None = None) -> Dict[str, Any]:
    matrix_values = [float(value) for row in payload.get("matrices", {}).get("car", {}).get("durations", []) for value in row]
    windows: List[float] = []
    services: List[float] = []
    for vehicle in payload.get("vehicles", []):
        window = vehicle.get("time_window", [])
        if len(window) == 2:
            windows.extend([float(window[0]), float(window[1])])
    for shipment in payload.get("shipments", []):
        for side in ("pickup", "delivery"):
            step = shipment.get(side, {})
            services.append(float(step.get("service", 0.0) or 0.0))
            for window in step.get("time_windows", []):
                if len(window) == 2:
                    windows.extend([float(window[0]), float(window[1])])
    arrivals = []
    if response:
        for route in response.get("routes", []):
            for step in route.get("steps", []):
                if step.get("arrival") is not None:
                    arrivals.append(float(step.get("arrival")))
    matrix_max = max(matrix_values) if matrix_values else 0.0
    window_span = (max(windows) - min(windows)) if windows else 0.0
    suspicious = []
    if matrix_max > max(1.0, window_span) * 10.0:
        suspicious.append("matrix-too-large-vs-time-windows")
    if window_span > 0 and 0 < matrix_max < window_span / 10_000.0:
        suspicious.append("matrix-too-small-vs-time-windows")
    return {
        "matrixMin": min(matrix_values) if matrix_values else None,
        "matrixMax": matrix_max if matrix_values else None,
        "timeWindowMin": min(windows) if windows else None,
        "timeWindowMax": max(windows) if windows else None,
        "serviceTimeMin": min(services) if services else None,
        "serviceTimeMax": max(services) if services else None,
        "routeArrivalMax": max(arrivals) if arrivals else None,
        "suspiciousScaleMismatch": suspicious,
    }


def shipment_step_id_map(vroom_request: Dict[str, Any]) -> Dict[Tuple[str, int], str]:
    mapping: Dict[Tuple[str, int], str] = {}
    for shipment in vroom_request.get("shipments", []):
        pickup = shipment.get("pickup", {})
        delivery = shipment.get("delivery", {})
        if pickup.get("id") is not None:
            mapping[("pickup", int(pickup["id"]))] = str(pickup.get("description"))
        if delivery.get("id") is not None:
            mapping[("delivery", int(delivery["id"]))] = str(delivery.get("description"))
    return mapping


def index_node_map(instance: Dict[str, Any]) -> Dict[int, str]:
    return {index: str(node.get("id")) for index, node in enumerate(instance.get("nodes", []))}


def map_vroom_step(step: Dict[str, Any], id_map: Dict[Tuple[str, int], str], index_map: Dict[int, str]) -> Dict[str, Any]:
    if step.get("type") in {"start", "end", "break"}:
        return {"nodeId": None, "source": "depot-or-nonservice", "ambiguous": False}
    candidates: List[Tuple[str, str]] = []
    step_type = str(step.get("type"))
    if step_type in {"pickup", "delivery"} and step.get("id") is not None:
        key = (step_type, int(step["id"]))
        if key in id_map:
            candidates.append(("shipment-step-id", id_map[key]))
    description = step.get("description")
    if description is not None:
        candidates.append(("description", str(description)))
    if step.get("location_index") is not None:
        index = int(step.get("location_index"))
        if index in index_map:
            candidates.append(("location-index", index_map[index]))
    unique_nodes = {node_id for _, node_id in candidates}
    if len(unique_nodes) > 1:
        return {"nodeId": None, "source": "ambiguous", "ambiguous": True, "candidates": candidates}
    if candidates:
        return {"nodeId": candidates[0][1], "source": candidates[0][0], "ambiguous": False}
    return {"nodeId": None, "source": "unmapped", "ambiguous": True}


def vroom_output_to_solution(instance: Dict[str, Any], payload: Dict[str, Any], vroom_request: Dict[str, Any] | None = None) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    id_map = shipment_step_id_map(vroom_request or {})
    index_map = index_node_map(instance)
    routes: List[List[str]] = []
    mapping_trace = []
    ambiguous = []
    for route in payload.get("routes", []):
        stops = [depot]
        for step in route.get("steps", []):
            mapped = map_vroom_step(step, id_map, index_map)
            node_id = mapped["nodeId"]
            mapping_trace.append({"stepType": step.get("type"), "stepId": step.get("id"), "mappedNodeId": node_id, "mappingSource": mapped["source"], "mappingCandidates": mapped.get("candidates", []), "arrival": step.get("arrival"), "service": step.get("service")})
            if mapped["ambiguous"]:
                ambiguous.append(step)
            if node_id is None or node_id == depot:
                continue
            stops.append(str(node_id))
        stops.append(depot)
        if len(stops) > 2:
            routes.append(stops)
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": "vroom-industry-champion", "routes": routes, "vroomStepMappingTrace": mapping_trace, "vroomAmbiguousStepCount": len(ambiguous)}


def vroom_self_consistency(instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    nodes = node_by_id(instance)
    rows = []
    for mapped in solution.get("vroomStepMappingTrace", []):
        node_id = mapped.get("mappedNodeId")
        node = nodes.get(str(node_id), {}) if node_id is not None else {}
        arrival = mapped.get("arrival")
        reason = None
        if arrival is not None and node:
            ready = float(node.get("readyTime", 0.0))
            due = float(node.get("dueTime", 0.0))
            if float(arrival) < ready:
                reason = "arrival-before-ready"
            elif float(arrival) > due:
                reason = "arrival-after-due"
        rows.append({**mapped, "internalReady": node.get("readyTime"), "internalDue": node.get("dueTime"), "violationReason": reason})
    return {"steps": rows, "violationReasons": sorted({row["violationReason"] for row in rows if row.get("violationReason")})}


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


def run_vroom_http(vroom_url: str, request: Dict[str, Any], timeout_seconds: int = 120) -> Tuple[Dict[str, Any] | None, str | None, str]:
    data = json.dumps(request).encode("utf-8")
    url = vroom_url.rstrip("/")
    http_request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8")), None, "ok"
    except (urllib.error.URLError, TimeoutError, OSError) as exception:
        status = "vroom-timeout" if "timed out" in str(exception).lower() else "vroom-error"
        return None, str(exception), status


def run_vroom_bin(vroom_bin: str, request_path: Path, timeout_seconds: int = 120) -> Tuple[Dict[str, Any] | None, str | None, str]:
    try:
        completed = subprocess.run([vroom_bin, "-i", str(request_path)], capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exception:
        return None, str(exception), "vroom-timeout"
    except OSError as exception:
        return None, str(exception), "vroom-error"
    if completed.returncode != 0:
        return None, completed.stderr.strip() or completed.stdout.strip(), "vroom-schema-error"
    try:
        return json.loads(completed.stdout), None, "ok"
    except json.JSONDecodeError as exception:
        return None, str(exception), "vroom-schema-error"


def classify(champion: Dict[str, Any], challenger: Dict[str, Any], unsupported_mapping: bool, vroom_unavailable: bool, distance_tolerance: float = 0.01, vroom_status: str = "ok", import_valid: bool = True) -> str:
    if unsupported_mapping:
        return "unsupported-mapping"
    if not import_valid and vroom_status == "ok":
        return "vroom-import-fail"
    if vroom_status == "vroom-timeout":
        return "vroom-timeout"
    if vroom_status == "vroom-schema-error":
        return "vroom-schema-error"
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
    instance = load_benchmark_instance(getattr(args, "benchmark_source", "li-lim"), instance_name, args.data_source)
    vroom_request = convert_pdptw_to_vroom(instance, args.time_scale, args.rounding)
    request_digest = request_hash(vroom_request)
    request_validation = validate_vroom_request(vroom_request, len(instance.get("nodes", [])))
    time_diagnostics = time_unit_diagnostics(instance, vroom_request)
    instance_artifact_dir = output_dir / "vroom_artifacts" / instance_name
    request_path = output_dir / "vroom_requests" / f"{instance_name}.json"
    write_json(request_path, vroom_request)
    write_json(instance_artifact_dir / "raw_request.json", vroom_request)
    unsupported_mapping = not vroom_request.get("shipments") or not request_validation.get("valid")
    vroom_payload = None
    vroom_error = None
    vroom_status = "dry-run" if args.dry_run_conversion else "skipped" if args.skip_vroom_run else "not-configured"
    vroom_runtime_ms = 0
    if not args.skip_vroom_run and not args.dry_run_conversion:
        started = time.perf_counter()
        if args.vroom_url:
            vroom_payload, vroom_error, vroom_status = run_vroom_http(args.vroom_url, vroom_request, args.vroom_timeout_seconds)
        elif args.vroom_bin:
            vroom_payload, vroom_error, vroom_status = run_vroom_bin(args.vroom_bin, request_path, args.vroom_timeout_seconds)
        else:
            vroom_error = "vroom-runner-not-configured"
            vroom_status = "vroom-unavailable"
        vroom_runtime_ms = int((time.perf_counter() - started) * 1000)
    if vroom_payload is not None:
        write_json(instance_artifact_dir / "raw_response.json", vroom_payload)
    if vroom_error:
        instance_artifact_dir.mkdir(parents=True, exist_ok=True)
        (instance_artifact_dir / "raw_error.txt").write_text(vroom_error, encoding="utf-8")
    vroom_unavailable = bool(vroom_error)
    champion_solution = {"routes": []}
    champion_metrics = {"hardViolations": 0 if args.dry_run_conversion or args.skip_vroom_run else 1, "vehicleCount": None, "totalDistance": None, "objective": None, "feasible": False, "violations": [vroom_error] if vroom_error else []}
    coverage = {"valid": False, "missing": [], "duplicate": [], "incomplete": []}
    self_consistency = {"steps": [], "violationReasons": []}
    import_valid = False
    if vroom_payload is not None:
        write_json(output_dir / "vroom_results" / f"{instance_name}.json", vroom_payload)
        time_diagnostics = time_unit_diagnostics(instance, vroom_request, vroom_payload)
        champion_solution = vroom_output_to_solution(instance, vroom_payload, vroom_request)
        coverage = exact_pair_coverage(instance, champion_solution)
        self_consistency = vroom_self_consistency(instance, champion_solution)
        import_valid = bool(coverage.get("valid")) and int(champion_solution.get("vroomAmbiguousStepCount", 0) or 0) == 0
        champion_metrics = metrics(instance, champion_solution, args.mode)
    challenger_summary = run_stable_promoted([instance_name], output_dir / "challenger_results" / instance_name, args.data_source, parse_time_limit(args.challenger_time_limit), args.mode, repeat=1, benchmark_source=getattr(args, "benchmark_source", "li-lim"), stable_incumbent_replay=True)
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
    vroom_returned_unassigned = bool((vroom_payload or {}).get("unassigned"))
    raw_artifacts = {
        "rawRequestPath": str(instance_artifact_dir / "raw_request.json"),
        "rawResponsePath": str(instance_artifact_dir / "raw_response.json") if vroom_payload is not None else None,
        "rawErrorPath": str(instance_artifact_dir / "raw_error.txt") if vroom_error else None,
    }
    classification = classify(
        champion_metrics,
        challenger_metrics,
        unsupported_mapping,
        vroom_unavailable or args.dry_run_conversion or args.skip_vroom_run,
        vroom_status=vroom_status,
        import_valid=import_valid or args.dry_run_conversion or args.skip_vroom_run,
    )
    return {
        "instance": instance.get("instanceName", instance_name),
        "classification": classification,
        "unsupportedMapping": unsupported_mapping,
        "supportedMapping": not unsupported_mapping,
        "importValid": import_valid,
        "vroomUnavailable": vroom_unavailable or args.dry_run_conversion or args.skip_vroom_run,
        "vroomError": vroom_error,
        "vroomStatus": vroom_status,
        "vroomRuntimeMs": vroom_runtime_ms,
        "requestHash": request_digest,
        "requestValidation": request_validation,
        "vroomUnassigned": (vroom_payload or {}).get("unassigned", []),
        "vroomReturnedUnassigned": vroom_returned_unassigned,
        "vroomSummary": (vroom_payload or {}).get("summary"),
        "vroomFeasibleByInternalChecker": bool(champion_metrics.get("feasible")),
        "vroomCoverage": coverage,
        "vroomSelfConsistency": self_consistency,
        "timeUnitDiagnostics": time_diagnostics,
        "rawArtifacts": raw_artifacts,
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
    blocking_counts = ["vroom-win", "challenger-hard-fail", "unsupported-mapping", "vroom-unavailable", "vroom-timeout", "vroom-schema-error", "vroom-import-fail"]
    promote_candidate = diagnostic_pass and not dry_run and all(counts.get(name, 0) == 0 for name in blocking_counts)
    return {
        "classificationCounts": counts,
        "challengerHardFailCount": challenger_hard,
        "diagnosticGate": "PROMOTE_CANDIDATE" if promote_candidate else "DIAGNOSTIC_PASS" if diagnostic_pass else "FAIL",
    }


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 58B VROOM Adapter Diagnostics", "", f"Gate: **{summary['aggregate']['diagnosticGate']}**", "", "| Instance | Classification | VROOM Vehicles | Challenger Vehicles | VROOM Distance | Challenger Distance |", "|---|---|---:|---:|---:|---:|"]
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['classification']} | {row['champion'].get('vehicleCount')} | {row['challenger'].get('vehicleCount')} | {row['champion'].get('totalDistance')} | {row['challenger'].get('totalDistance')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 56F stable runner against VROOM industry-standard champion.")
    parser.add_argument("--instances", default="lrc202,lrc106")
    parser.add_argument("--benchmark-source", choices=("li-lim", "synthetic-food", "vroom-capability", "live-snapshot"), default="li-lim")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--challenger-time-limit", default="30s")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--vroom-bin", default="")
    parser.add_argument("--vroom-timeout-seconds", type=int, default=120)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--rounding", choices=("floor", "round", "ceil"), default="round")
    parser.add_argument("--dry-run-conversion", action="store_true")
    parser.add_argument("--skip-vroom-run", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [run_instance(instance, args, output_dir) for instance in instances]
    summary = {"schemaVersion": "phase58b-vroom-adapter-diagnostics/v1", "champion": "vroom", "challenger": "phase56f-stable-certification", "rows": rows, "aggregate": aggregate(rows, args.dry_run_conversion or args.skip_vroom_run)}
    write_json(output_dir / "per_instance_comparison.json", rows)
    write_json(output_dir / "aggregate_summary.json", summary)
    (output_dir / "aggregate_summary.md").write_text(markdown(summary), encoding="utf-8")
    print(f"[PHASE58A VROOM COMPARATOR] wrote {output_dir}")
    return 0 if summary["aggregate"]["diagnosticGate"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
