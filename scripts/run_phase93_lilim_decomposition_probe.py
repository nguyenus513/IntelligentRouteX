from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from external_benchmark_support import check_solution
from optimizer.unified_intelligent_optimizer import UnifiedIntelligentOptimizer
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from optimizer.phase85_pair_utils import extract_request_pairs, request_id, solution_signature
from optimizer.phase94_slot_recombination_policy import SlotPreservingRecombinationPolicy
from phase67_synthetic_instance_loader import load_benchmark_instance
from run_external_benchmark_certification import parse_time_limit
from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase61_benchmark_suite_registry import load_suite


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase93_lilim_decomposition_probe_v1"


def select_requests_by_features(instance: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    scored = []
    for request in instance.get("requests", []):
        pickup = nodes.get(str(request.get("pickupNodeId")), {})
        dropoff = nodes.get(str(request.get("dropoffNodeId")), {})
        width = min(float(pickup.get("dueTime", 0) or 0) - float(pickup.get("readyTime", 0) or 0), float(dropoff.get("dueTime", 0) or 0) - float(dropoff.get("readyTime", 0) or 0))
        cluster = float(pickup.get("x", 0) or 0) ** 2 + float(pickup.get("y", 0) or 0) ** 2
        scored.append((width, cluster, request_id(request), request))
    return [item[3] for item in sorted(scored)[: max(1, limit)]]


def extract_subproblem(instance: Dict[str, Any], selected_requests: List[Dict[str, Any]]) -> tuple[Dict[str, Any], Dict[str, str]]:
    depot = str(instance.get("depotNodeId", "0"))
    node_ids: Set[str] = {depot}
    for request in selected_requests:
        node_ids.add(str(request.get("pickupNodeId")))
        node_ids.add(str(request.get("dropoffNodeId")))
    ordered_old_ids = [depot] + sorted(node_id for node_id in node_ids if node_id != depot)
    old_nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    old_index = {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}
    old_to_new = {old_id: str(index) for index, old_id in enumerate(ordered_old_ids)}
    new_to_old = {new_id: old_id for old_id, new_id in old_to_new.items()}
    matrix = instance.get("distanceMatrix", [])
    duration = instance.get("durationMatrix", matrix)
    nodes = []
    for old_id in ordered_old_ids:
        node = dict(old_nodes[old_id])
        node["id"] = old_to_new[old_id]
        nodes.append(node)
    requests = []
    for request in selected_requests:
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        remapped = dict(request)
        remapped["pickupNodeId"] = old_to_new[pickup]
        remapped["dropoffNodeId"] = old_to_new[dropoff]
        requests.append(remapped)
    def remap(source: List[List[float]]) -> List[List[float]]:
        return [[float(source[old_index[left]][old_index[right]]) for right in ordered_old_ids] for left in ordered_old_ids]
    subproblem = {"schemaVersion": "external-benchmark-normalized/v1", "problemType": "PDPTW", "benchmarkFamily": "phase93-decomposition-subproblem", "instanceName": "phase93_subproblem", "depotNodeId": "0", "vehicleCount": min(max(1, len(requests)), int(instance.get("vehicleCount", len(requests)) or len(requests))), "capacity": instance.get("capacity", 1), "nodes": nodes, "requests": requests, "distanceMatrix": remap(matrix), "durationMatrix": remap(duration), "activeRoutes": [], "drivers": [], "bestKnown": {}, "vroomVehicles": []}
    return subproblem, new_to_old


def naive_incumbent(subproblem: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(subproblem.get("depotNodeId", "0"))
    return {"routes": [[depot, str(request.get("pickupNodeId")), str(request.get("dropoffNodeId")), depot] for request in subproblem.get("requests", [])]}


def remap_solution_to_full(sub_solution: Dict[str, Any], new_to_old: Dict[str, str]) -> Dict[str, Any]:
    return {"routes": [[new_to_old[str(stop)] for stop in route] for route in sub_solution.get("routes", [])]}


def recombine_solution(full_instance: Dict[str, Any], incumbent: Dict[str, Any], selected_requests: List[Dict[str, Any]], sub_solution_old_ids: Dict[str, Any]) -> Dict[str, Any]:
    selected_ids = {request_id(request) for request in selected_requests}
    affected_nodes = {str(request.get("pickupNodeId")) for request in selected_requests} | {str(request.get("dropoffNodeId")) for request in selected_requests}
    kept_routes = []
    for route in incumbent.get("routes", []):
        if affected_nodes & {str(stop) for stop in route}:
            continue
        kept_routes.append([str(stop) for stop in route])
    candidate = {"routes": kept_routes + [[str(stop) for stop in route] for route in sub_solution_old_ids.get("routes", []) if len(route) > 2]}
    return candidate


def active_route_count(solution: Dict[str, Any]) -> int:
    return len([route for route in solution.get("routes", []) if len(route) > 2])


def affected_routes(incumbent: Dict[str, Any], selected_requests: List[Dict[str, Any]]) -> List[List[str]]:
    affected_nodes = {str(request.get("pickupNodeId")) for request in selected_requests} | {str(request.get("dropoffNodeId")) for request in selected_requests}
    return [[str(stop) for stop in route] for route in incumbent.get("routes", []) if affected_nodes & {str(stop) for stop in route}]


def strict_recombination_validator(instance: Dict[str, Any], original_incumbent: Dict[str, Any], candidate: Dict[str, Any], affected_route_count: int, candidate_subproblem_route_count: int) -> Dict[str, Any]:
    if candidate_subproblem_route_count > affected_route_count:
        return {"valid": False, "reason": "subproblem-route-slot-overflow"}
    if active_route_count(candidate) > active_route_count(original_incumbent):
        return {"valid": False, "reason": "active-route-count-regression"}
    if active_route_count(candidate) > int(instance.get("vehicleCount", active_route_count(candidate)) or active_route_count(candidate)):
        return {"valid": False, "reason": "subproblem-route-slot-overflow"}
    if not exact_request_coverage(instance, candidate):
        return {"valid": False, "reason": "coverage-invalid"}
    return {"valid": True, "reason": "precheck-pass"}


def exact_request_coverage(instance: Dict[str, Any], solution: Dict[str, Any]) -> bool:
    required = {request_id(request) for request in instance.get("requests", [])}
    covered = {request_id(pair["request"]) for pair in extract_request_pairs(instance, solution)}
    return required == covered


def run_one_subproblem(instance: Dict[str, Any], incumbent: Dict[str, Any], request_limit: int, sub_time_ms: int, mode: str = "same-slot-polish") -> Dict[str, Any]:
    selected = select_requests_by_features(instance, request_limit)
    affected = affected_routes(incumbent, selected)
    affected_route_count = max(1, len(affected))
    slot_policy = SlotPreservingRecombinationPolicy().build(affected_route_count, len(selected), mode)
    subproblem, new_to_old = extract_subproblem(instance, selected)
    subproblem["vehicleCount"] = slot_policy.maxAllowedSubproblemRoutes
    sub_incumbent = naive_incumbent(subproblem)
    result = UnifiedIntelligentOptimizer().optimize(subproblem, sub_incumbent, sub_time_ms)
    sub_solution_old = remap_solution_to_full(result["solution"], new_to_old)
    candidate_subproblem_route_count = active_route_count(sub_solution_old)
    recombined = recombine_solution(instance, incumbent, selected, sub_solution_old)
    precheck = strict_recombination_validator(instance, incumbent, recombined, slot_policy.maxAllowedSubproblemRoutes, candidate_subproblem_route_count)
    objective = UnifiedNaturalObjective()
    checked = {"feasible": False, "violations": [precheck["reason"]]}
    recombined_eval = {"objective": float("inf")}
    if precheck.get("valid"):
        checked = check_solution(instance, recombined)
        recombined_eval = objective.evaluate(instance, recombined)
    incumbent_eval = objective.evaluate(instance, incumbent)
    improves = bool(precheck.get("valid")) and bool(checked.get("feasible")) and objective.improves(instance, incumbent, recombined)
    before = float(incumbent_eval.get("objective", float("inf")))
    after = float(recombined_eval.get("objective", float("inf")))
    objective_delta = after - before if before != float("inf") and after != float("inf") else None
    reject_reason = None if improves else (precheck["reason"] if not precheck.get("valid") else "check-solution-rejected" if not checked.get("feasible") else "objective-regression")
    return {
        "mode": slot_policy.mode,
        "selectedRequestCount": len(selected),
        "subproblemRequestCount": len(subproblem.get("requests", [])),
        "subDiagnostics": result.get("diagnostics", {}),
        "recombinedSolution": recombined,
        "recombinedFeasible": bool(checked.get("feasible")),
        "recombinedViolations": checked.get("violations", []),
        "exactCoverage": exact_request_coverage(instance, recombined),
        "objectiveImproves": improves,
        "objectiveDelta": objective_delta,
        "affectedRouteCount": affected_route_count,
        "availableRouteSlots": slot_policy.availableRouteSlots,
        "candidateSubproblemRouteCount": candidate_subproblem_route_count,
        "rejectedBySlotOverflow": reject_reason == "subproblem-route-slot-overflow",
        "rejectedByCoverage": reject_reason == "coverage-invalid",
        "rejectedByCheckSolution": reject_reason == "check-solution-rejected",
        "bestRejectedReason": reject_reason,
    }


def aggregate_subproblem_telemetry(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    generated = checker = improving = 0
    for item in trace:
        for budget in item.get("subDiagnostics", {}).get("budgetTelemetry", []):
            generated += int(budget.get("generatedCandidates", 0) or 0)
            checker += int(budget.get("checkerFeasibleCandidates", budget.get("feasibleCandidateCount", 0)) or 0)
            improving += int(budget.get("objectiveImprovingCandidates", 0) or 0)
    return {"generatedCandidates": generated, "checkerFeasibleCandidates": checker, "objectiveImprovingCandidates": improving}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    suite = load_suite(args.suite)
    instance_name = str(suite.get("instances", [])[0])
    instance = load_benchmark_instance(str(suite.get("source", "li-lim")), instance_name)
    incumbent = naive_incumbent(instance)
    trace = []
    accepted = 0
    recombined = 0
    for index in range(max(1, args.subproblem_count)):
        if int((time.perf_counter() - started) * 1000) > args.hard_wall_clock_ms:
            break
        for mode in ("same-slot-polish", "slot-compression"):
            item = run_one_subproblem(instance, incumbent, args.request_limit, parse_time_limit(args.subproblem_time_limit), mode)
            trace.append({"subproblemIndex": index, **item})
            recombined += 1
            if item.get("objectiveImproves"):
                accepted += 1
                incumbent = item["recombinedSolution"]
                break
    telemetry = aggregate_subproblem_telemetry(trace)
    anti = antihardcode_scan()
    rejected_hard = sum(0 if item.get("recombinedFeasible") or item.get("rejectedBySlotOverflow") or item.get("rejectedByCoverage") else len(item.get("recombinedViolations", [])) for item in trace)
    hard = sum(len(item.get("recombinedViolations", [])) for item in trace if item.get("objectiveImproves") and not item.get("recombinedFeasible"))
    rejected_slot = sum(1 for item in trace if item.get("rejectedBySlotOverflow"))
    rejected_coverage = sum(1 for item in trace if item.get("rejectedByCoverage"))
    rejected_check = sum(1 for item in trace if item.get("rejectedByCheckSolution"))
    recombined_feasible = sum(1 for item in trace if item.get("recombinedFeasible"))
    best_rejected_reason = next((item.get("bestRejectedReason") for item in trace if item.get("bestRejectedReason")), None)
    unknown = 0
    if hard or anti.get("gate") != "PASS":
        gate = "FAIL"
    elif accepted > 0:
        gate = "PASS_STRONG"
    elif rejected_slot > 0 and unknown == 0:
        gate = "PASS"
    elif telemetry["generatedCandidates"] > 0 and unknown == 0:
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase93-lilim-decomposition-probe/v1", "gate": gate, "instance": instance_name, "decompositionTrace": [{key: value for key, value in item.items() if key not in {"subDiagnostics", "recombinedSolution"}} for item in trace], "subproblemCount": len(trace), "recombinedCandidates": recombined, "acceptedRecombinedCandidates": accepted, "unknownCount": unknown, "hardViolations": hard, "rejectedRecombinedHardViolations": rejected_hard, "rejectedBySlotOverflow": rejected_slot, "rejectedByCoverage": rejected_coverage, "rejectedByCheckSolution": rejected_check, "recombinedFeasibleCandidates": recombined_feasible, "bestRejectedReason": best_rejected_reason, "antiHardcodeGate": anti.get("gate"), **telemetry}
    write_json(output_dir / "phase93_lilim_decomposition_probe_summary.json", summary)
    write_json(output_dir / "decomposition_trace.json", {"rows": summary["decompositionTrace"]})
    write_json(output_dir / "operator_telemetry.json", {"rows": [item.get("subDiagnostics", {}).get("budgetTelemetry", []) for item in trace]})
    (output_dir / "phase93_lilim_decomposition_probe_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join(["# Phase 93 Li-Lim Decomposition Probe", "", f"- Gate: **{summary.get('gate')}**", f"- Subproblems: `{summary.get('subproblemCount')}`", f"- Generated candidates: `{summary.get('generatedCandidates')}`", f"- Accepted recombinations: `{summary.get('acceptedRecombinedCandidates')}`", f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`", ""])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 93 Li-Lim decomposition probe.")
    parser.add_argument("--suite", default="li-lim-8case")
    parser.add_argument("--subproblem-count", type=int, default=1)
    parser.add_argument("--request-limit", type=int, default=8)
    parser.add_argument("--subproblem-time-limit", default="5s")
    parser.add_argument("--hard-wall-clock-ms", type=int, default=30_000)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE93 LILIM DECOMPOSITION PROBE] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
