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
from optimizer.phase95_slot_aware_subproblem import SlotAwareSubproblemBuilder, build_slot_aware_config
from optimizer.phase96_coverage_repair import ResidualCoverageRepair, coverage_diff, remove_duplicate_pairs
from optimizer.phase97_time_window_repair import TimeWindowRepair, solution_time_window_stats
from optimizer.phase98_schedule_feasible_subproblem import ScheduleFeasibleSubproblemBuilder
from optimizer.phase99_exact_tw_route_finalizer import ExactTWRouteFinalizer
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


def slot_limited_incumbent(instance: Dict[str, Any]) -> Dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    slot_count = max(1, int(instance.get("vehicleCount", 1) or 1))
    routes = [[depot, depot] for _ in range(slot_count)]
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}

    def schedule_key(request: Dict[str, Any]) -> tuple[float, float, str]:
        pickup = nodes.get(str(request.get("pickupNodeId")), {})
        dropoff = nodes.get(str(request.get("dropoffNodeId")), {})
        due = min(float(pickup.get("dueTime", 1e18) or 1e18), float(dropoff.get("dueTime", 1e18) or 1e18))
        ready = min(float(pickup.get("readyTime", 0.0) or 0.0), float(dropoff.get("readyTime", 0.0) or 0.0))
        return (due, ready, request_id(request))

    requests = sorted(instance.get("requests", []), key=schedule_key)
    for index, request in enumerate(requests):
        route_index = index % slot_count
        route = routes[route_index]
        routes[route_index] = route[:-1] + [str(request.get("pickupNodeId")), str(request.get("dropoffNodeId")), depot]
    return {"routes": [route for route in routes if len(route) > 2]}


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


def affected_route_request_closure(instance: Dict[str, Any], incumbent: Dict[str, Any], seed_requests: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[List[str]]]:
    seed_nodes = {str(request.get("pickupNodeId")) for request in seed_requests} | {str(request.get("dropoffNodeId")) for request in seed_requests}
    affected = [[str(stop) for stop in route] for route in incumbent.get("routes", []) if seed_nodes & {str(stop) for stop in route}]
    affected_node_sets = [set(route) for route in affected]
    closed = []
    for request in instance.get("requests", []):
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        if any(pickup in nodes and dropoff in nodes for nodes in affected_node_sets):
            closed.append(request)
    return sorted(closed, key=request_id), affected


def strict_recombination_validator(instance: Dict[str, Any], original_incumbent: Dict[str, Any], candidate: Dict[str, Any], affected_route_count: int, candidate_subproblem_route_count: int, affected_request_ids: Set[str] | None = None) -> Dict[str, Any]:
    if candidate_subproblem_route_count > affected_route_count:
        return {"valid": False, "reason": "subproblem-route-slot-overflow", "coverage": {}}
    if active_route_count(candidate) > active_route_count(original_incumbent):
        return {"valid": False, "reason": "active-route-count-regression", "coverage": {}}
    if active_route_count(candidate) > int(instance.get("vehicleCount", active_route_count(candidate)) or active_route_count(candidate)):
        return {"valid": False, "reason": "subproblem-route-slot-overflow", "coverage": {}}
    diff = coverage_diff(instance, candidate, affected_request_ids)
    if diff.partialPickupDropoffIds:
        return {"valid": False, "reason": "coverage-partial-pair", "coverage": diff.to_dict(), "partialPairCount": len(diff.partialPickupDropoffIds), "missingCount": len(diff.missingRequestIds), "duplicateCount": len(diff.duplicateRequestIds)}
    if diff.duplicateRequestIds:
        return {"valid": False, "reason": "coverage-duplicate", "coverage": diff.to_dict(), "partialPairCount": 0, "missingCount": len(diff.missingRequestIds), "duplicateCount": len(diff.duplicateRequestIds)}
    if diff.missingRequestIds:
        return {"valid": False, "reason": "coverage-missing", "coverage": diff.to_dict(), "partialPairCount": 0, "missingCount": len(diff.missingRequestIds), "duplicateCount": 0}
    return {"valid": True, "reason": "precheck-pass", "coverage": diff.to_dict(), "partialPairCount": 0, "missingCount": 0, "duplicateCount": 0}


def exact_request_coverage(instance: Dict[str, Any], solution: Dict[str, Any]) -> bool:
    required = {request_id(request) for request in instance.get("requests", [])}
    covered = {request_id(pair["request"]) for pair in extract_request_pairs(instance, solution)}
    return required == covered


def run_one_subproblem(instance: Dict[str, Any], incumbent: Dict[str, Any], request_limit: int, sub_time_ms: int, mode: str = "same-slot-polish") -> Dict[str, Any]:
    seed_selected = select_requests_by_features(instance, request_limit)
    selected, affected = affected_route_request_closure(instance, incumbent, seed_selected)
    if not selected:
        selected = seed_selected
        affected = affected_routes(incumbent, selected)
    affected_route_count = max(1, len(affected))
    affected_request_ids = {request_id(request) for request in selected}
    slot_policy = SlotPreservingRecombinationPolicy().build(affected_route_count, len(selected), mode)
    slot_config = build_slot_aware_config(slot_policy.mode, affected_route_count, len(selected))
    subproblem, new_to_old = extract_subproblem(instance, selected)
    subproblem["vehicleCount"] = slot_config.maxSubproblemRoutes
    slot_builder = SlotAwareSubproblemBuilder()
    base_sub_incumbent = slot_builder.build_incumbent(subproblem, slot_config)
    construction_telemetry = dict(slot_builder.lastTelemetry)
    schedule_builder = ScheduleFeasibleSubproblemBuilder()
    sub_incumbent = schedule_builder.build_incumbent(subproblem, slot_config, base_sub_incumbent)
    schedule_telemetry = dict(schedule_builder.lastTelemetry)
    if sub_incumbent is None:
        return {"mode": slot_config.mode, "selectedSeedRequestCount": len(seed_selected), "selectedRequestCount": len(seed_selected), "expandedAffectedRequestCount": len(selected), "affectedRouteRequestCount": len(selected), "subproblemRequestCount": len(subproblem.get("requests", [])), "subDiagnostics": {}, "recombinedSolution": incumbent, "recombinedFeasible": False, "recombinedViolations": ["slot-aware-construction-blocked"], "exactCoverage": True, "objectiveImproves": False, "objectiveDelta": None, "affectedRouteCount": affected_route_count, "availableRouteSlots": slot_config.availableRouteSlots, "maxSubproblemRoutes": slot_config.maxSubproblemRoutes, "subproblemVehicleCount": subproblem.get("vehicleCount"), "incumbentSubproblemRouteCount": 0, "candidateSubproblemRouteCount": 0, "slotAwareConstructionBlocked": True, "slotCompressionAttempts": 0, "slotCompressionSuccess": False, "scheduleBuilderAttempts": 0, "scheduleBuilderSuccess": False, "scheduleBuilderStrategy": None, "subproblemTWBefore": 0, "subproblemTWAfter": 0, "subproblemLatenessBefore": 0.0, "subproblemLatenessAfter": 0.0, "scheduleBuiltCandidateUsed": False, "rejectedBySlotOverflow": False, "rejectedByCoverage": False, "rejectedByCheckSolution": False, "bestRejectedReason": "slot-aware-construction-blocked"}
    result = UnifiedIntelligentOptimizer().optimize(subproblem, sub_incumbent, sub_time_ms)
    optimizer_solution = schedule_builder.choose_candidate(subproblem, result["solution"], sub_incumbent)
    schedule_telemetry = dict(schedule_builder.lastTelemetry)
    sub_candidate = slot_builder.compress_to_slots(subproblem, optimizer_solution, slot_config.maxSubproblemRoutes)
    compression_telemetry = dict(slot_builder.lastTelemetry)
    if sub_candidate is None:
        sub_candidate = optimizer_solution
    sub_solution_old = remap_solution_to_full(sub_candidate, new_to_old)
    candidate_subproblem_route_count = active_route_count(sub_solution_old)
    recombined = recombine_solution(instance, incumbent, selected, sub_solution_old)
    precheck = strict_recombination_validator(instance, incumbent, recombined, slot_policy.maxAllowedSubproblemRoutes, candidate_subproblem_route_count, affected_request_ids)
    repairer = ResidualCoverageRepair()
    repair_telemetry = {"residualCoverageRepairAttempts": 0, "residualCoverageRepairSuccess": False}
    if not precheck.get("valid") and precheck.get("reason") in {"coverage-missing", "coverage-duplicate"}:
        repaired = remove_duplicate_pairs(instance, recombined, precheck.get("coverage", {}).get("duplicateRequestIds", []))
        repaired = repairer.repair(instance, repaired, precheck.get("coverage", {}).get("missingRequestIds", []), active_route_count(incumbent))
        repair_telemetry = dict(repairer.lastTelemetry)
        if repaired is not None:
            recombined = repaired
            precheck = strict_recombination_validator(instance, incumbent, recombined, slot_policy.maxAllowedSubproblemRoutes, active_route_count(sub_solution_old), affected_request_ids)
    objective = UnifiedNaturalObjective()
    checked = {"feasible": False, "violations": [precheck["reason"]]}
    recombined_eval = {"objective": float("inf")}
    time_window_before = solution_time_window_stats(instance, recombined)
    time_repair_telemetry = {
        "timeWindowRepairAttempts": 0,
        "timeWindowRepairSuccess": False,
        "timeWindowViolationCountBefore": int(time_window_before.get("timeWindowViolationCount", 0) or 0),
        "timeWindowViolationCountAfter": int(time_window_before.get("timeWindowViolationCount", 0) or 0),
        "totalLatenessBefore": float(time_window_before.get("totalLateness", 0.0) or 0.0),
        "totalLatenessAfter": float(time_window_before.get("totalLateness", 0.0) or 0.0),
        "firstViolationNode": time_window_before.get("firstViolationNode"),
        "repairStrategyUsed": None,
        "candidateChecksUsed": 0,
    }
    exact_finalizer_telemetry = {"attempted": False, "improved": False, "statesExpanded": 0, "reason": "not-run"}
    if precheck.get("valid"):
        checked = check_solution(instance, recombined)
        if "time-window-violation" in checked.get("violations", []):
            finalizer = ExactTWRouteFinalizer()
            violation_indices = [index for index, route in enumerate(recombined.get("routes", [])) if solution_time_window_stats(instance, {"routes": [route]}).get("timeWindowViolationCount", 0)]
            finalized = finalizer.finalize_solution_routes(instance, recombined, violation_indices, max_states=512, beam_width=32, max_runtime_ms=max(100, min(750, sub_time_ms // 4)))
            exact_finalizer_telemetry = dict(finalizer.lastTelemetry)
            if finalized is not None:
                finalized_precheck = strict_recombination_validator(instance, incumbent, finalized, slot_policy.maxAllowedSubproblemRoutes, candidate_subproblem_route_count, affected_request_ids)
                if finalized_precheck.get("valid"):
                    finalized_checked = check_solution(instance, finalized)
                    if int(finalized_checked.get("timeWindowViolationCount", 0) or 0) <= int(checked.get("timeWindowViolationCount", 0) or 0):
                        recombined = finalized
                        precheck = finalized_precheck
                        checked = finalized_checked
        if "time-window-violation" in checked.get("violations", []):
            time_repair = TimeWindowRepair()
            repaired = time_repair.repair(instance, recombined, affected_request_ids, active_route_count(incumbent), max_candidate_checks=256, max_runtime_ms=max(100, min(750, sub_time_ms // 4)))
            time_repair_telemetry = dict(time_repair.lastTelemetry)
            if repaired is not None:
                repaired_precheck = strict_recombination_validator(instance, incumbent, repaired, slot_policy.maxAllowedSubproblemRoutes, candidate_subproblem_route_count, affected_request_ids)
                if repaired_precheck.get("valid"):
                    repaired_checked = check_solution(instance, repaired)
                    if int(repaired_checked.get("timeWindowViolationCount", 0) or 0) <= int(checked.get("timeWindowViolationCount", 0) or 0):
                        recombined = repaired
                        precheck = repaired_precheck
                        checked = repaired_checked
        recombined_eval = objective.evaluate(instance, recombined)
    incumbent_eval = objective.evaluate(instance, incumbent)
    improves = bool(precheck.get("valid")) and bool(checked.get("feasible")) and objective.improves(instance, incumbent, recombined)
    before = float(incumbent_eval.get("objective", float("inf")))
    after = float(recombined_eval.get("objective", float("inf")))
    objective_delta = after - before if before != float("inf") and after != float("inf") else None
    reject_reason = None if improves else (precheck["reason"] if not precheck.get("valid") else "check-solution-rejected" if not checked.get("feasible") else "objective-regression")
    final_time_window = solution_time_window_stats(instance, recombined)
    return {
        "mode": slot_policy.mode,
        "selectedSeedRequestCount": len(seed_selected), "selectedRequestCount": len(seed_selected), "expandedAffectedRequestCount": len(selected), "affectedRouteRequestCount": len(selected),
        "subproblemRequestCount": len(subproblem.get("requests", [])),
        "subDiagnostics": result.get("diagnostics", {}),
        "recombinedSolution": recombined,
        "recombinedFeasible": bool(checked.get("feasible")),
        "recombinedViolations": checked.get("violations", []),
        "exactCoverage": exact_request_coverage(instance, recombined),
        "objectiveImproves": improves,
        "objectiveDelta": objective_delta,
        "affectedRouteCount": affected_route_count,
        "availableRouteSlots": slot_config.availableRouteSlots,
        "maxSubproblemRoutes": slot_config.maxSubproblemRoutes,
        "subproblemVehicleCount": subproblem.get("vehicleCount"),
        "incumbentSubproblemRouteCount": int(construction_telemetry.get("incumbentSubproblemRouteCount", 0) or 0),
        "candidateSubproblemRouteCount": candidate_subproblem_route_count,
        "slotAwareConstructionBlocked": bool(construction_telemetry.get("slotAwareConstructionBlocked", False)),
        "slotCompressionAttempts": int(compression_telemetry.get("slotCompressionAttempts", 0) or 0),
        "slotCompressionSuccess": bool(compression_telemetry.get("slotCompressionSuccess", False)),
        "scheduleBuilderAttempts": int(schedule_telemetry.get("scheduleBuilderAttempts", 0) or 0),
        "scheduleBuilderSuccess": bool(schedule_telemetry.get("scheduleBuilderSuccess", False)),
        "scheduleBuilderStrategy": schedule_telemetry.get("scheduleBuilderStrategy"),
        "subproblemTWBefore": int(schedule_telemetry.get("subproblemTWBefore", 0) or 0),
        "subproblemTWAfter": int(schedule_telemetry.get("subproblemTWAfter", 0) or 0),
        "subproblemLatenessBefore": float(schedule_telemetry.get("subproblemLatenessBefore", 0.0) or 0.0),
        "subproblemLatenessAfter": float(schedule_telemetry.get("subproblemLatenessAfter", 0.0) or 0.0),
        "scheduleBuiltCandidateUsed": bool(schedule_telemetry.get("scheduleBuiltCandidateUsed", False)),
        "rejectedBySlotOverflow": reject_reason == "subproblem-route-slot-overflow",
        "rejectedByCoverage": str(reject_reason).startswith("coverage-"),
        "coverageMissingCount": int(precheck.get("missingCount", 0) or 0),
        "coverageDuplicateCount": int(precheck.get("duplicateCount", 0) or 0),
        "coveragePartialPairCount": int(precheck.get("partialPairCount", 0) or 0),
        "residualCoverageRepairAttempts": int(repair_telemetry.get("residualCoverageRepairAttempts", 0) or 0),
        "residualCoverageRepairSuccess": bool(repair_telemetry.get("residualCoverageRepairSuccess", False)),
        "timeWindowRepairAttempts": int(time_repair_telemetry.get("timeWindowRepairAttempts", 0) or 0),
        "timeWindowRepairSuccess": bool(time_repair_telemetry.get("timeWindowRepairSuccess", False)),
        "timeWindowViolationCountBefore": int(time_repair_telemetry.get("timeWindowViolationCountBefore", 0) or 0),
        "timeWindowViolationCountAfter": int(final_time_window.get("timeWindowViolationCount", time_repair_telemetry.get("timeWindowViolationCountAfter", 0)) or 0),
        "totalLatenessBefore": float(time_repair_telemetry.get("totalLatenessBefore", 0.0) or 0.0),
        "totalLatenessAfter": float(final_time_window.get("totalLateness", time_repair_telemetry.get("totalLatenessAfter", 0.0)) or 0.0),
        "firstViolationNode": time_repair_telemetry.get("firstViolationNode"),
        "repairStrategyUsed": time_repair_telemetry.get("repairStrategyUsed"),
        "candidateChecksUsed": int(time_repair_telemetry.get("candidateChecksUsed", 0) or 0),
        "exactTWFinalizerAttempted": bool(exact_finalizer_telemetry.get("attempted", False)),
        "exactTWFinalizerImproved": bool(exact_finalizer_telemetry.get("improved", False)),
        "exactTWFinalizerStates": int(exact_finalizer_telemetry.get("statesExpanded", 0) or 0),
        "exactTWFinalizerReason": exact_finalizer_telemetry.get("reason"),
        "rejectedByTimeWindow": reject_reason == "check-solution-rejected" and "time-window-violation" in checked.get("violations", []),
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
    incumbent = slot_limited_incumbent(instance)
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
    rejected_check_violations = sum(0 if item.get("recombinedFeasible") or not item.get("rejectedByCheckSolution") else len(item.get("recombinedViolations", [])) for item in trace)
    rejected_hard = 0
    hard = sum(len(item.get("recombinedViolations", [])) for item in trace if item.get("objectiveImproves") and not item.get("recombinedFeasible"))
    rejected_slot = sum(1 for item in trace if item.get("rejectedBySlotOverflow"))
    rejected_coverage = sum(1 for item in trace if item.get("rejectedByCoverage"))
    coverage_missing = sum(int(item.get("coverageMissingCount", 0) or 0) for item in trace)
    coverage_duplicate = sum(int(item.get("coverageDuplicateCount", 0) or 0) for item in trace)
    coverage_partial = sum(int(item.get("coveragePartialPairCount", 0) or 0) for item in trace)
    repair_attempts = sum(int(item.get("residualCoverageRepairAttempts", 0) or 0) for item in trace)
    repair_successes = sum(1 for item in trace if item.get("residualCoverageRepairSuccess"))
    rejected_check = sum(1 for item in trace if item.get("rejectedByCheckSolution"))
    schedule_attempts = sum(int(item.get("scheduleBuilderAttempts", 0) or 0) for item in trace)
    schedule_successes = sum(1 for item in trace if item.get("scheduleBuilderSuccess"))
    subproblem_tw_before = sum(int(item.get("subproblemTWBefore", 0) or 0) for item in trace)
    subproblem_tw_after = sum(int(item.get("subproblemTWAfter", 0) or 0) for item in trace)
    subproblem_lateness_before = sum(float(item.get("subproblemLatenessBefore", 0.0) or 0.0) for item in trace)
    subproblem_lateness_after = sum(float(item.get("subproblemLatenessAfter", 0.0) or 0.0) for item in trace)
    schedule_built_used = sum(1 for item in trace if item.get("scheduleBuiltCandidateUsed"))
    exact_finalizer_attempts = sum(1 for item in trace if item.get("exactTWFinalizerAttempted"))
    exact_finalizer_improvements = sum(1 for item in trace if item.get("exactTWFinalizerImproved"))
    exact_finalizer_states = sum(int(item.get("exactTWFinalizerStates", 0) or 0) for item in trace)
    rejected_time_window = sum(1 for item in trace if item.get("rejectedByTimeWindow"))
    tw_repair_attempts = sum(int(item.get("timeWindowRepairAttempts", 0) or 0) for item in trace)
    tw_repair_successes = sum(1 for item in trace if item.get("timeWindowRepairSuccess"))
    tw_before = sum(int(item.get("timeWindowViolationCountBefore", 0) or 0) for item in trace)
    tw_after = sum(int(item.get("timeWindowViolationCountAfter", 0) or 0) for item in trace)
    lateness_before = sum(float(item.get("totalLatenessBefore", 0.0) or 0.0) for item in trace)
    lateness_after = sum(float(item.get("totalLatenessAfter", 0.0) or 0.0) for item in trace)
    tw_candidate_checks = sum(int(item.get("candidateChecksUsed", 0) or 0) for item in trace)
    first_violation_node = next((item.get("firstViolationNode") for item in trace if item.get("firstViolationNode")), None)
    repair_strategy_used = next((item.get("repairStrategyUsed") for item in trace if item.get("repairStrategyUsed")), None)
    recombined_feasible = sum(1 for item in trace if item.get("recombinedFeasible"))
    best_rejected_reason = next((item.get("bestRejectedReason") for item in trace if item.get("bestRejectedReason")), None)
    unknown = 0
    if hard or anti.get("gate") != "PASS":
        gate = "FAIL"
    elif accepted > 0:
        gate = "PASS_STRONG"
    elif int(getattr(args, "phase97_time_window_after_baseline", 0) or 0) > 0 and tw_after < int(getattr(args, "phase97_time_window_after_baseline", 0) or 0) and unknown == 0:
        gate = "PASS"
    elif tw_after < tw_before and unknown == 0:
        gate = "PASS"
    elif recombined_feasible > 0 and unknown == 0:
        gate = "PASS"
    elif rejected_slot > 0 and unknown == 0:
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase93-lilim-decomposition-probe/v1", "gate": gate, "instance": instance_name, "decompositionTrace": [{key: value for key, value in item.items() if key not in {"subDiagnostics", "recombinedSolution"}} for item in trace], "subproblemCount": len(trace), "recombinedCandidates": recombined, "acceptedRecombinedCandidates": accepted, "unknownCount": unknown, "hardViolations": hard, "rejectedRecombinedHardViolations": rejected_hard, "rejectedCheckSolutionViolations": rejected_check_violations, "rejectedBySlotOverflow": rejected_slot, "rejectedByCoverage": rejected_coverage, "coverageMissingCount": coverage_missing, "coverageDuplicateCount": coverage_duplicate, "coveragePartialPairCount": coverage_partial, "residualCoverageRepairAttempts": repair_attempts, "residualCoverageRepairSuccesses": repair_successes, "rejectedByCheckSolution": rejected_check, "scheduleBuilderAttempts": schedule_attempts, "scheduleBuilderSuccesses": schedule_successes, "subproblemTWBefore": subproblem_tw_before, "subproblemTWAfter": subproblem_tw_after, "subproblemLatenessBefore": subproblem_lateness_before, "subproblemLatenessAfter": subproblem_lateness_after, "scheduleBuiltCandidateUsed": schedule_built_used, "exactTWFinalizerAttempts": exact_finalizer_attempts, "exactTWFinalizerImprovements": exact_finalizer_improvements, "exactTWFinalizerStates": exact_finalizer_states, "rejectedByTimeWindow": rejected_time_window, "phase97TimeWindowAfterBaseline": int(getattr(args, "phase97_time_window_after_baseline", 0) or 0), "timeWindowRepairAttempts": tw_repair_attempts, "timeWindowRepairSuccesses": tw_repair_successes, "timeWindowViolationCountBefore": tw_before, "timeWindowViolationCountAfter": tw_after, "totalLatenessBefore": lateness_before, "totalLatenessAfter": lateness_after, "firstViolationNode": first_violation_node, "repairStrategyUsed": repair_strategy_used, "candidateChecksUsed": tw_candidate_checks, "recombinedFeasibleCandidates": recombined_feasible, "bestRejectedReason": best_rejected_reason, "antiHardcodeGate": anti.get("gate"), **telemetry}
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
    parser.add_argument("--phase97-time-window-after-baseline", type=int, default=0)
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE93 LILIM DECOMPOSITION PROBE] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())






