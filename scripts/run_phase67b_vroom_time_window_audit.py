from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from phase67_synthetic_instance_loader import load_benchmark_instance
from run_phase58a_vroom_industry_comparator import map_vroom_step, shipment_step_id_map, index_node_map


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "final" / "synthetic_food_full_real_20260504_131148"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def node_by_id(instance: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(node.get("id")): node for node in instance.get("nodes", [])}


def matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}


def travel_time(instance: Dict[str, Any], left: str, right: str, matrix_name: str = "distanceMatrix") -> float:
    indexes = matrix_index(instance)
    matrix = instance.get(matrix_name) or instance.get("distanceMatrix")
    return float(matrix[indexes[str(left)]][indexes[str(right)]])


def request_duration(request: Dict[str, Any], left_index: int, right_index: int) -> float:
    matrix = request.get("matrices", {}).get("car", {}).get("durations", [])
    return float(matrix[left_index][right_index])


def classify_step_violation(arrival: float, ready: float | None, due: float | None, service: float) -> str | None:
    if ready is not None and arrival < ready:
        return "early-without-wait"
    if due is not None and arrival > due:
        return "late-arrival"
    if due is not None and arrival + service > due:
        return "service-pushes-past-due"
    return None


def timeline_for_route(instance: Dict[str, Any], vroom_request: Dict[str, Any], route: Dict[str, Any], route_index: int) -> Dict[str, Any]:
    nodes = node_by_id(instance)
    id_map = shipment_step_id_map(vroom_request)
    index_map = index_node_map(instance)
    rows = []
    previous_node = None
    previous_index = None
    internal_elapsed = None
    duration_elapsed = None
    for step_index, step in enumerate(route.get("steps", [])):
        mapped = map_vroom_step(step, id_map, index_map)
        node_id = mapped.get("nodeId")
        if node_id is None and step.get("location_index") is not None:
            node_id = index_map.get(int(step.get("location_index")))
        node = nodes.get(str(node_id), {}) if node_id is not None else {}
        current_index = int(step.get("location_index", previous_index if previous_index is not None else 0) or 0)
        if internal_elapsed is None:
            internal_elapsed = float(step.get("arrival", 0.0) or 0.0)
            duration_elapsed = float(step.get("arrival", 0.0) or 0.0)
            travel_internal = 0.0
            travel_duration = 0.0
        else:
            travel_internal = travel_time(instance, str(previous_node), str(node_id), "distanceMatrix") if previous_node is not None and node_id is not None else 0.0
            travel_duration = request_duration(vroom_request, int(previous_index or 0), current_index)
            internal_elapsed += travel_internal
            duration_elapsed += travel_duration
        ready = float(node.get("readyTime")) if node and node.get("readyTime") is not None else None
        due = float(node.get("dueTime")) if node and node.get("dueTime") is not None else None
        service = float(node.get("serviceTime", step.get("service", 0.0)) or 0.0) if node else float(step.get("service", 0.0) or 0.0)
        waiting_internal = False
        waiting_duration = False
        if ready is not None and internal_elapsed < ready:
            internal_elapsed = ready
            waiting_internal = True
        if ready is not None and duration_elapsed < ready:
            duration_elapsed = ready
            waiting_duration = True
        vroom_arrival = float(step.get("arrival", 0.0) or 0.0)
        rows.append(
            {
                "routeIndex": route_index,
                "stepIndex": step_index,
                "nodeId": node_id,
                "stepType": step.get("type"),
                "vroomArrival": vroom_arrival,
                "recomputedArrivalDistance": internal_elapsed,
                "recomputedArrivalDuration": duration_elapsed,
                "readyTime": ready,
                "dueTime": due,
                "serviceTime": service,
                "vroomService": step.get("service"),
                "travelFromPreviousDistance": travel_internal,
                "travelFromPreviousDuration": travel_duration,
                "waitingAppliedDistance": waiting_internal,
                "waitingAppliedDuration": waiting_duration,
                "vroomWaitingTime": step.get("waiting_time"),
                "vroomViolationType": classify_step_violation(vroom_arrival, ready, due, service),
                "distanceViolationType": classify_step_violation(internal_elapsed, ready, due, service),
                "durationViolationType": classify_step_violation(duration_elapsed, ready, due, service),
                "mappingSource": mapped.get("source"),
            }
        )
        internal_elapsed += service
        duration_elapsed += service
        previous_node = node_id
        previous_index = current_index
    return {"routeIndex": route_index, "steps": rows}


def classify_instance(timelines: List[Dict[str, Any]], instance: Dict[str, Any]) -> Dict[str, Any]:
    steps = [step for route in timelines for step in route.get("steps", [])]
    vroom_violations = [step for step in steps if step.get("vroomViolationType")]
    distance_violations = [step for step in steps if step.get("distanceViolationType")]
    duration_violations = [step for step in steps if step.get("durationViolationType")]
    waits = [step for step in steps if float(step.get("vroomWaitingTime") or 0.0) > 0]
    duration_distance_delta = [abs(float(step.get("travelFromPreviousDistance") or 0.0) - float(step.get("travelFromPreviousDuration") or 0.0)) for step in steps]
    if vroom_violations:
        classification = "vroom-true-time-window-violation"
    elif any(step.get("distanceViolationType") == "early-without-wait" for step in steps) and waits:
        classification = "internal-checker-waiting-semantics-mismatch"
    elif any(step.get("vroomService") != step.get("serviceTime") for step in steps if step.get("stepType") not in {"start", "end"}):
        classification = "service-time-semantics-mismatch"
    elif duration_violations and not distance_violations:
        classification = "matrix-duration-mismatch"
    elif distance_violations and not duration_violations:
        classification = "matrix-duration-mismatch"
    elif any(step.get("stepType") in {"start", "end"} and step.get("vroomViolationType") for step in steps):
        classification = "depot-window-mismatch"
    else:
        classification = "unknown"
    return {
        "classification": classification,
        "vroomViolationCount": len(vroom_violations),
        "distanceViolationCount": len(distance_violations),
        "durationViolationCount": len(duration_violations),
        "vroomUsesWaiting": bool(waits),
        "internalCheckerAllowsWaiting": True,
        "serviceCheckedBeforeAddingService": True,
        "maxDurationDistanceDelta": max(duration_distance_delta) if duration_distance_delta else 0.0,
        "topViolations": vroom_violations[:10] or distance_violations[:10] or duration_violations[:10],
    }


def audit_instance(input_dir: Path, row: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    instance_name = str(row.get("instance"))
    raw_request = read_json(Path(row.get("rawArtifacts", {}).get("rawRequestPath")))
    raw_response = read_json(Path(row.get("rawArtifacts", {}).get("rawResponsePath")))
    instance = load_benchmark_instance("synthetic-food", instance_name)
    timelines = [timeline_for_route(instance, raw_request, route, route_index) for route_index, route in enumerate(raw_response.get("routes", []))]
    classification = classify_instance(timelines, instance)
    payload = {"instance": instance_name, "sourceClassification": row.get("classification"), "audit": classification, "timelines": timelines}
    write_json(output_dir / "per_instance_timelines" / f"{instance_name}.json", payload)
    return {"instance": instance_name, **classification}


def run(input_dir: Path) -> Dict[str, Any]:
    rows = read_json(input_dir / "vroom_comparator" / "per_instance_comparison.json")
    output_dir = input_dir / "vroom_time_window_audit"
    audited = [audit_instance(input_dir, row, output_dir) for row in rows if row.get("classification") == "vroom-hard-fail"]
    unknown_count = sum(1 for row in audited if row.get("classification") == "unknown")
    summary = {"schemaVersion": "phase67b-vroom-time-window-audit/v1", "inputDir": str(input_dir), "auditedInstanceCount": len(audited), "unknownCount": unknown_count, "gate": "PASS" if audited and unknown_count == 0 else "FAIL", "rows": audited}
    write_json(output_dir / "phase67b_vroom_tw_audit.json", summary)
    (output_dir / "phase67b_vroom_tw_audit.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 67B VROOM Time-Window Audit", "", f"Gate: **{summary['gate']}**", "", "| Instance | Classification | VROOM TW Violations | Distance Violations | Duration Violations |", "|---|---|---:|---:|---:|"]
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['classification']} | {row['vroomViolationCount']} | {row['distanceViolationCount']} | {row['durationViolationCount']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit VROOM synthetic time-window hard failures.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    args = parser.parse_args()
    summary = run(Path(args.input_dir))
    print(f"[PHASE67B VROOM TW AUDIT] wrote {Path(args.input_dir) / 'vroom_time_window_audit'}")
    return 0 if summary["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
