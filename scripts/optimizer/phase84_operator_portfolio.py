from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from external_benchmark_support import check_solution
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from optimizer.phase85_candidate_validator import CandidateValidator
from optimizer.phase85_pair_utils import extract_request_pairs, insert_pair_positions, remove_pair_from_route, solution_signature
from optimizer.phase87_candidate_ranker import CandidateRanker
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_alns_repair_engine import ALNSRepairEngine
from optimizer.phase90_deadline import Deadline
from optimizer.phase90_distance_polish import DistancePolish
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from optimizer.phase90_local_search_chain import LocalSearchChain
from optimizer.phase90_route_compression import RouteCompression
from optimizer.phase90_route_pool_recombiner import RoutePoolRecombiner
from optimizer.phase90_route_population import RoutePopulation
from optimizer.phase92_final_candidate_bridge import FinalCandidateBridge
from optimizer.phase92_operator_activation_policy import OperatorActivationPolicy
from run_phase79_end_to_end_production_benchmark import validate_locked_prefix
from run_phase56b_stable_promoted_runner import canonicalize_solution


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    maxRuntimeMs: int = 100
    maxCandidateChecks: int = 100
    maxDepth: int = 2
    maxBeam: int = 8
    maxRoutes: int = 8
    maxPairs: int = 32


class OperatorPortfolio:
    def __init__(self) -> None:
        self.specs = [
            OperatorSpec("alns-destroy-repair", maxRuntimeMs=220, maxCandidateChecks=96, maxDepth=3, maxBeam=8),
            OperatorSpec("ejection-route-repair", maxRuntimeMs=220, maxCandidateChecks=96, maxDepth=3, maxBeam=8),
            OperatorSpec("hgs-lite-route-population", maxRuntimeMs=180, maxCandidateChecks=64, maxBeam=8),
            OperatorSpec("distance-polish", maxRuntimeMs=140, maxCandidateChecks=80),
            OperatorSpec("local-search-chain", maxRuntimeMs=180, maxCandidateChecks=80, maxDepth=3),
            OperatorSpec("route-compression", maxRuntimeMs=180, maxCandidateChecks=80),
            OperatorSpec("quality-route-pool-recombination", maxRuntimeMs=120, maxCandidateChecks=40),
            OperatorSpec("slack-aware-insertion"),
            OperatorSpec("traffic-aware-insertion"),
            OperatorSpec("lock-aware-insertion"),
            OperatorSpec("intra-route-pair-relocate"),
            OperatorSpec("pd-aware-pair-relocate"),
            OperatorSpec("cross-route-pair-swap"),
            OperatorSpec("two-pair-relocate"),
            OperatorSpec("two-pair-swap"),
            OperatorSpec("route-elimination"),
            OperatorSpec("route-compression-two-pair"),
            OperatorSpec("route-pool-recombination"),
        ]
        self.validator = CandidateValidator()
        self.objective = UnifiedNaturalObjective()
        self.insertion_index = InsertionIndex()
        self.ranker = CandidateRanker()
        self.delta_scorer = ExactDeltaScorer()
        self.alns_engine = ALNSRepairEngine()
        self.distance_polish = DistancePolish()
        self.local_chain = LocalSearchChain()
        self.route_compression = RouteCompression()
        self.route_pool_recombiner = RoutePoolRecombiner()
        self.route_population = RoutePopulation()
        self.activation_policy = OperatorActivationPolicy()
        self.final_bridge = FinalCandidateBridge()
        self._pruneTelemetry: Dict[str, int] = {}
        self.lastCheckedCandidateTraces: List[Dict[str, Any]] = []
        self.lastPrunedCandidateSamples: List[Dict[str, Any]] = []

    def names(self) -> List[str]:
        return [spec.name for spec in self.specs]

    def spec(self, name: str) -> OperatorSpec:
        return next((spec for spec in self.specs if spec.name == name), OperatorSpec(name))

    def apply(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], features: Dict[str, Any], budget: Any | None = None, route_pool: Any | None = None, deadline: Deadline | None = None) -> Dict[str, Any]:
        spec = self.spec(name)
        started = time.perf_counter()
        incumbent = canonicalize_solution(instance, solution)
        operator_deadline = deadline.child_budget(spec.maxRuntimeMs) if deadline is not None else Deadline.from_time_limit_ms(spec.maxRuntimeMs)
        if operator_deadline.expired():
            return {"solution": incumbent, "telemetry": {"generatedCandidates": 0, "candidateChecks": 0, "acceptedCandidates": 0, "earlyStopReason": "deadline", "safeReturn": True}, "checkedCandidateTraces": [], "prunedCandidateSamples": []}
        activation_decisions = self.activation_policy.activate(instance, incumbent, features, operator_deadline.remaining_ms(), self.names())
        activation = next((item for item in activation_decisions if item.operator == name), None)
        candidates = self._generate(name, instance, incumbent, spec, route_pool, operator_deadline)
        generated = 0
        self._pruneTelemetry = {"prunedByCapacity": 0, "prunedByTimeWindow": 0, "prunedByLock": 0, "estimatedFeasibleMoves": 0, "nearFeasibleRepairAttempts": 0, "nearFeasibleRepairSuccesses": 0, "prunedNoQualityPotential": 0}
        phase90_telemetry: Dict[str, Any] = {"alnsIterations": 0, "intermediateWorseAcceptedForSearch": 0, "finalCheckerFeasibleCandidates": 0, "finalObjectiveImprovingCandidates": 0, "routePoolColumnCount": len(getattr(route_pool, "columns", {}) or {}), "populationDiversity": 0, "ejectionDepthUsed": 0, "repairFailReasons": {}}
        self.lastCheckedCandidateTraces = []
        self.lastPrunedCandidateSamples = []
        no_generation_reason = activation.reason if activation is not None and activation.priority <= 0 else None
        bridged_final_candidates = 0
        intermediate_states_seen = 0
        best = incumbent
        best_key = self._candidate_key(instance, incumbent)
        checks = 0
        checker_feasible = 0
        objective_improving = 0
        objective_not_improved = 0
        accepted_count = 0
        fail_reasons: Dict[str, int] = {}
        best_estimated_distance_delta = None
        best_actual_distance_delta = None
        best_vehicle_delta = None
        raw_list = list(candidates)
        if not raw_list and not operator_deadline.should_stop(5):
            bridge_seed = self._bridge_seed_candidate(name, instance, incumbent, spec)
            if bridge_seed is not None:
                raw_list = self.final_bridge.bridge(instance, incumbent, [bridge_seed], 1)
                bridged_final_candidates += int(self.final_bridge.lastTelemetry.get("bridgedFinalCandidates", 0) or 0)
                intermediate_states_seen += int(self.final_bridge.lastTelemetry.get("intermediateStatesSeen", 0) or 0)
                if raw_list:
                    no_generation_reason = None
        if not raw_list and no_generation_reason is None:
            no_generation_reason = self._no_generation_reason(name, instance, incumbent, operator_deadline)
        for raw_candidate in raw_list:
            generated += 1
            candidate = canonicalize_solution(instance, raw_candidate.get("solution", raw_candidate))
            delta = raw_candidate.get("delta")
            if delta is None:
                delta_obj = self.delta_scorer.score(instance, incumbent, candidate)
                delta = delta_obj.to_dict()
            estimated_distance = float(delta.get("distanceDelta", raw_candidate.get("estimatedDistanceDelta", 0.0)) or 0.0)
            best_estimated_distance_delta = min(best_estimated_distance_delta, estimated_distance) if best_estimated_distance_delta is not None else estimated_distance
            if best_actual_distance_delta is None or estimated_distance < best_actual_distance_delta:
                best_actual_distance_delta = estimated_distance
            vehicle_delta = float(delta.get("vehicleDelta", 0.0) or 0.0)
            best_vehicle_delta = min(best_vehicle_delta, vehicle_delta) if best_vehicle_delta is not None else vehicle_delta
            raw_telemetry = raw_candidate.get("telemetry", {}) if isinstance(raw_candidate, dict) else {}
            self._merge_phase90_telemetry(phase90_telemetry, raw_telemetry)
            allow_final_quality_check = bool(raw_candidate.get("allowFinalQualityCheck")) if isinstance(raw_candidate, dict) else False
            if not self._has_quality_potential(delta) and not allow_final_quality_check:
                self._pruneTelemetry["prunedNoQualityPotential"] = self._pruneTelemetry.get("prunedNoQualityPotential", 0) + 1
                fail_reasons["no-quality-potential"] = fail_reasons.get("no-quality-potential", 0) + 1
                continue
            if not self._has_quality_potential(delta) and allow_final_quality_check:
                self._pruneTelemetry["prunedNoQualityPotential"] = self._pruneTelemetry.get("prunedNoQualityPotential", 0) + 1
            if operator_deadline.should_stop(5) or int((time.perf_counter() - started) * 1000) > spec.maxRuntimeMs:
                fail_reasons["runtime-cap"] = fail_reasons.get("runtime-cap", 0) + 1
                phase90_telemetry["earlyStopReason"] = "deadline" if operator_deadline.should_stop(5) else "runtime-cap"
                phase90_telemetry["safeReturn"] = True
                break
            if checks >= spec.maxCandidateChecks:
                fail_reasons["candidate-cap"] = fail_reasons.get("candidate-cap", 0) + 1
                break
            checks += 1
            feasibility_result = self.validator.validate(instance, incumbent, candidate, require_improvement=False)
            if feasibility_result.get("valid"):
                checker_feasible += 1
                if self.objective.improves(instance, incumbent, candidate):
                    objective_improving += 1
                    result = self.validator.validate(instance, incumbent, candidate, require_improvement=True)
                else:
                    objective_not_improved += 1
                    result = {"valid": False, "reason": "objective-not-improved", "details": []}
            else:
                result = feasibility_result
            trace_payload = dict(raw_candidate)
            trace_payload["delta"] = delta
            trace = self._candidate_trace(name, instance, candidate, trace_payload, result)
            self.lastCheckedCandidateTraces.append(trace)
            if not result.get("valid"):
                reason = str(result.get("reason", "rejected"))
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                continue
            accepted_count += 1
            key = self._candidate_key(instance, candidate)
            if key < best_key:
                best = candidate
                best_key = key
        telemetry = {
            "generatedCandidates": generated,
            "generatedMoves": generated,
            "rankedMoves": generated,
            "prunedMoves": max(0, generated - checks),
            "candidateChecks": checks,
            "checkedCandidates": checks,
            "checkerFeasibleCandidates": checker_feasible,
            "objectiveImprovingCandidates": objective_improving,
            "objectiveNotImprovedCandidates": objective_not_improved,
            "feasibleCandidates": checker_feasible,
            "acceptedCandidates": accepted_count,
            "failReasons": fail_reasons,
            "activationPolicy": [item.to_dict() for item in activation_decisions[:8]],
            "activatedOperators": [item.operator for item in activation_decisions[:8]],
            "activationReasons": {item.operator: item.reason for item in activation_decisions[:8]},
            "noGenerationReason": no_generation_reason,
            "intermediateStatesSeen": intermediate_states_seen + int(phase90_telemetry.get("intermediateFeasibleStates", 0) or 0),
            "bridgedFinalCandidates": bridged_final_candidates,
            "topRejectedReason": max(fail_reasons.items(), key=lambda item: item[1])[0] if fail_reasons else None,
            "bestEstimatedDistanceDelta": best_estimated_distance_delta,
            "bestActualDistanceDelta": best_actual_distance_delta,
            "bestDistanceDelta": best_actual_distance_delta,
            "bestVehicleDelta": best_vehicle_delta,
            "fullCheckPassRate": checker_feasible / max(1, checks),
            **self._pruneTelemetry,
            **phase90_telemetry,
        }
        return {"solution": best, "telemetry": telemetry, "checkedCandidateTraces": self.lastCheckedCandidateTraces, "prunedCandidateSamples": self.lastPrunedCandidateSamples}

    def _has_quality_potential(self, delta: Dict[str, Any]) -> bool:
        return (
            float(delta.get("vehicleDelta", 0.0) or 0.0) < 0
            or float(delta.get("distanceDelta", 0.0) or 0.0) < 0
            or float(delta.get("objectiveDeltaEstimate", 0.0) or 0.0) < 0
            or (float(delta.get("churnDelta", 0.0) or 0.0) < 0 and float(delta.get("distanceDelta", 0.0) or 0.0) <= 0)
        )

    def _merge_phase90_telemetry(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key in ("alnsIterations", "intermediateWorseAcceptedForSearch", "finalCheckerFeasibleCandidates", "finalObjectiveImprovingCandidates", "ejectionDepthUsed", "routePoolColumnCount", "populationDiversity"):
            if key in source:
                target[key] = max(int(target.get(key, 0) or 0), int(source.get(key, 0) or 0)) if key in {"ejectionDepthUsed", "routePoolColumnCount", "populationDiversity"} else int(target.get(key, 0) or 0) + int(source.get(key, 0) or 0)
        repair_reasons = source.get("repairFailReasons", {}) or {}
        merged = dict(target.get("repairFailReasons", {}) or {})
        for reason, count in repair_reasons.items():
            merged[str(reason)] = merged.get(str(reason), 0) + int(count or 0)
        target["repairFailReasons"] = merged

    def _generate(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec, route_pool: Any | None, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        if name == "alns-destroy-repair":
            yield from self.alns_engine.generate(instance, solution, route_pool, spec.maxCandidateChecks, spec.maxBeam, spec.maxDepth, deadline)
        elif name == "ejection-route-repair":
            yield from self.alns_engine.generate(instance, solution, route_pool, spec.maxCandidateChecks, spec.maxBeam, spec.maxDepth, deadline)
        elif name == "hgs-lite-route-population":
            seeds = []
            for raw in self.alns_engine.generate(instance, solution, route_pool, max(4, spec.maxBeam), spec.maxBeam, spec.maxDepth, deadline):
                seeds.append(raw.get("solution", raw))
            yield from self.route_population.generate(instance, solution, seeds, spec.maxCandidateChecks, deadline)
        elif name == "distance-polish":
            yield from self.distance_polish.generate(instance, solution, spec.maxCandidateChecks, deadline)
        elif name == "local-search-chain":
            yield from self.local_chain.generate(instance, solution, spec.maxCandidateChecks, spec.maxDepth, deadline)
        elif name == "route-compression":
            yield from self.route_compression.generate(instance, solution, spec.maxCandidateChecks, deadline)
        elif name == "quality-route-pool-recombination" and route_pool is not None:
            yield from self.route_pool_recombiner.generate(instance, solution, route_pool, spec.maxCandidateChecks, deadline)
            self._pruneTelemetry["rejectedNonInternalRouteColumns"] = self.route_pool_recombiner.lastRejectedNonInternal
        elif name in {"intra-route-pair-relocate", "slack-aware-insertion", "traffic-aware-insertion", "lock-aware-insertion"}:
            yield from self._intra_route_pair_relocate(instance, solution, spec)
        elif name == "pd-aware-pair-relocate":
            yield from self._cross_route_pair_relocate(instance, solution, spec)
        elif name == "cross-route-pair-swap":
            yield from self._cross_route_pair_swap(instance, solution, spec)
        elif name == "route-elimination":
            yield from self._route_elimination(instance, solution, spec)
        elif name == "route-pool-recombination" and route_pool is not None:
            yield {"routes": [column.route for column in route_pool.columns.values()]}
        elif name == "two-pair-relocate":
            yield from self._two_pair_relocate(instance, solution, spec)
        elif name == "two-pair-swap":
            yield from self._two_pair_swap(instance, solution, OperatorSpec("two-pair-swap", maxCandidateChecks=spec.maxCandidateChecks, maxBeam=2, maxPairs=4))
        elif name == "route-compression-two-pair":
            yield from self._route_elimination(instance, solution, spec)

    def _intra_route_pair_relocate(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        for pair in self._rank_pairs(instance, solution)[: spec.maxPairs]:
            route_index = pair["routeIndex"]
            route = routes[route_index]
            stripped = remove_pair_from_route(route, pair["request"])
            for option in self._insertion_options(instance, stripped, pair["request"], spec.maxBeam):
                candidate_route = option["route"]
                if candidate_route == route:
                    continue
                candidate_routes = [list(item) for item in routes]
                candidate_routes[route_index] = candidate_route
                yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": option.get("estimatedDistanceDelta", 0.0), "estimator": option.get("rankScore", {})}

    def _cross_route_pair_relocate(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        pairs = self._rank_pairs(instance, solution)[: spec.maxPairs]
        for pair in pairs:
            source_index = pair["routeIndex"]
            for target_index, target_route in enumerate(routes[: spec.maxRoutes]):
                if target_index == source_index:
                    continue
                source_route = remove_pair_from_route(routes[source_index], pair["request"])
                for option in self._insertion_options(instance, target_route, pair["request"], spec.maxBeam):
                    inserted = option["route"]
                    candidate_routes = [list(item) for item in routes]
                    candidate_routes[source_index] = source_route
                    candidate_routes[target_index] = inserted
                    yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": option.get("estimatedDistanceDelta", 0.0), "estimator": option.get("rankScore", {})}

    def _cross_route_pair_swap(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        pairs = self._rank_pairs(instance, solution)[: spec.maxPairs]
        for left in pairs:
            for right in pairs:
                if left["requestId"] >= right["requestId"] or left["routeIndex"] == right["routeIndex"]:
                    continue
                left_base = remove_pair_from_route(routes[left["routeIndex"]], left["request"])
                right_base = remove_pair_from_route(routes[right["routeIndex"]], right["request"])
                left_insertions = self._insertion_options(instance, left_base, right["request"], 2)
                right_insertions = self._insertion_options(instance, right_base, left["request"], 2)
                for left_option in left_insertions:
                    for right_option in right_insertions:
                        left_route = left_option["route"]
                        right_route = right_option["route"]
                        candidate_routes = [list(item) for item in routes]
                        candidate_routes[left["routeIndex"]] = left_route
                        candidate_routes[right["routeIndex"]] = right_route
                        yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": left_option.get("estimatedDistanceDelta", 0.0) + right_option.get("estimatedDistanceDelta", 0.0), "estimator": {"left": left_option.get("rankScore", {}), "right": right_option.get("rankScore", {})}}

    def _route_elimination(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        route_pairs = []
        for route_index, route in enumerate(routes):
            pairs = [pair for pair in self._rank_pairs(instance, solution) if pair["routeIndex"] == route_index]
            if pairs:
                distance = check_solution(instance, {"routes": [route]}).get("totalDistance", 0.0)
                route_pairs.append((len(pairs), -float(distance or 0.0), route_index, pairs))
        for _, _, remove_index, pairs in sorted(route_pairs)[: spec.maxRoutes]:
            base_routes = [list(route) for index, route in enumerate(routes) if index != remove_index]
            candidate_routes = base_routes
            ok = True
            for pair in pairs:
                best_routes = None
                best_key = None
                for target_index, target_route in enumerate(candidate_routes):
                    for option in self._insertion_options(instance, target_route, pair["request"], spec.maxBeam):
                        inserted = option["route"]
                        attempt = [list(route) for route in candidate_routes]
                        attempt[target_index] = inserted
                        key = solution_signature({"routes": attempt})
                        if best_key is None or key < best_key:
                            best_key = key
                            best_routes = attempt
                if best_routes is None:
                    ok = False
                    break
                candidate_routes = best_routes
            if ok:
                yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": -1.0, "estimator": {"estimatedDistanceDelta": -1.0}}

    def _two_pair_relocate(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        pairs = self._rank_pairs(instance, solution)[:4]
        for first in pairs:
            intermediate_routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
            intermediate_routes[first["routeIndex"]] = remove_pair_from_route(intermediate_routes[first["routeIndex"]], first["request"])
            for second in pairs:
                if first["requestId"] == second["requestId"]:
                    continue
                candidate = {"routes": [route for route in intermediate_routes if len(route) > 2]}
                yield from self._cross_route_pair_relocate(instance, candidate, OperatorSpec("two-pair-relocate", maxCandidateChecks=spec.maxCandidateChecks, maxBeam=2, maxPairs=2))

    def _two_pair_swap(self, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Iterable[Dict[str, Any]]:
        yield from self._cross_route_pair_swap(instance, solution, OperatorSpec("two-pair-swap", maxCandidateChecks=spec.maxCandidateChecks, maxBeam=2, maxPairs=4))

    def _rank_pairs(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> List[Dict[str, Any]]:
        moves = []
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        checked_routes = {index: check_solution(instance, {"routes": [route]}).get("totalDistance", 0.0) for index, route in enumerate(routes)}
        for pair in extract_request_pairs(instance, solution):
            route_distance = float(checked_routes.get(pair["routeIndex"], 0.0) or 0.0)
            moves.append({**pair, "moveId": pair["requestId"], "estimatedDistanceDelta": -route_distance / max(1, len(routes[pair["routeIndex"]]) - 2), "slackRisk": 0.0, "capacityRisk": 0.0, "routeCompatibility": 0.0})
        return self.ranker.rank(moves)

    def _insertion_options(self, instance: Dict[str, Any], route: List[str], request: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        options = self.insertion_index.enumerate_options(instance, route, request, top_k)
        telemetry = self.insertion_index.lastTelemetry
        for key in ("prunedByCapacity", "prunedByTimeWindow", "prunedByLock"):
            self._pruneTelemetry[key] = self._pruneTelemetry.get(key, 0) + int(telemetry.get(key, 0) or 0)
        self._pruneTelemetry["estimatedFeasibleMoves"] = self._pruneTelemetry.get("estimatedFeasibleMoves", 0) + len(options)
        self.lastPrunedCandidateSamples.extend(self.insertion_index.lastPrunedSamples[: max(0, 20 - len(self.lastPrunedCandidateSamples))])
        return options

    def _bridge_seed_candidate(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec) -> Dict[str, Any] | None:
        lowered = name.lower()
        if "compression" in lowered or "elimination" in lowered or "ejection" in lowered:
            for candidate in self.route_compression.generate(instance, solution, 1, Deadline.from_time_limit_ms(max(25, spec.maxRuntimeMs // 2))):
                return candidate
        if "polish" in lowered or "swap" in lowered or "relocate" in lowered or "insertion" in lowered:
            for candidate in self.distance_polish.generate(instance, solution, 1, Deadline.from_time_limit_ms(max(25, spec.maxRuntimeMs // 2))):
                return candidate
        if "alns" in lowered or "population" in lowered or "pool" in lowered:
            for candidate in self.alns_engine.generate(instance, solution, None, 4, 4, 1, Deadline.from_time_limit_ms(max(25, spec.maxRuntimeMs // 2))):
                return candidate
        return None

    def _no_generation_reason(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], deadline: Deadline) -> str:
        if deadline.expired():
            return "deadline-before-generation"
        pairs = extract_request_pairs(instance, solution)
        if not pairs:
            return "no-route-pair-found"
        if len(solution.get("routes", [])) <= 0:
            return "no-opportunity-detected"
        return "no-feasible-move"

    def _candidate_trace(self, operator: str, instance: Dict[str, Any], candidate: Dict[str, Any], raw_candidate: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        checked = check_solution(instance, candidate)
        lock = validate_locked_prefix(candidate, instance.get("activeRoutes", []), instance.get("drivers", []))
        estimator = raw_candidate.get("estimator", {}) if isinstance(raw_candidate, dict) else {}
        return {
            "operator": operator,
            "candidateSignature": solution_signature(candidate),
            "estimator": estimator,
            "delta": raw_candidate.get("delta", {}),
            "fullChecker": {"feasible": checked.get("feasible"), "violations": checked.get("violations", []), "vehicleCount": checked.get("vehicleCount"), "totalDistance": checked.get("totalDistance")},
            "lockValidator": lock,
            "rejectReason": validation.get("reason"),
        }

    def _candidate_key(self, instance: Dict[str, Any], candidate: Dict[str, Any]) -> tuple[float, float, float, str]:
        checked = check_solution(instance, candidate)
        objective = self.objective.evaluate(instance, candidate).get("objective", float("inf"))
        return (float(checked.get("vehicleCount", 10**9) or 10**9), float(objective), float(checked.get("totalDistance", 10**9) or 10**9), solution_signature(candidate))
