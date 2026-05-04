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
        self._pruneTelemetry: Dict[str, int] = {}

    def names(self) -> List[str]:
        return [spec.name for spec in self.specs]

    def spec(self, name: str) -> OperatorSpec:
        return next((spec for spec in self.specs if spec.name == name), OperatorSpec(name))

    def apply(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], features: Dict[str, Any], budget: Any | None = None, route_pool: Any | None = None) -> Dict[str, Any]:
        spec = self.spec(name)
        started = time.perf_counter()
        candidates = self._generate(name, instance, canonicalize_solution(instance, solution), spec, route_pool)
        generated = 0
        self._pruneTelemetry = {"prunedByCapacity": 0, "prunedByTimeWindow": 0, "prunedByLock": 0, "estimatedFeasibleMoves": 0, "nearFeasibleRepairAttempts": 0, "nearFeasibleRepairSuccesses": 0}
        best = solution
        best_key = self._candidate_key(instance, solution)
        checks = 0
        feasible = 0
        fail_reasons: Dict[str, int] = {}
        best_estimated_distance_delta = None
        for candidate in candidates:
            generated += 1
            best_estimated_distance_delta = min(best_estimated_distance_delta, candidate.get("estimatedDistanceDelta", 0.0)) if best_estimated_distance_delta is not None else candidate.get("estimatedDistanceDelta", 0.0)
            if int((time.perf_counter() - started) * 1000) > spec.maxRuntimeMs:
                fail_reasons["runtime-cap"] = fail_reasons.get("runtime-cap", 0) + 1
                break
            if checks >= spec.maxCandidateChecks:
                fail_reasons["candidate-cap"] = fail_reasons.get("candidate-cap", 0) + 1
                break
            checks += 1
            candidate = canonicalize_solution(instance, candidate.get("solution", candidate))
            result = self.validator.validate(instance, solution, candidate, require_improvement=True)
            if not result.get("valid"):
                reason = str(result.get("reason", "rejected"))
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                continue
            feasible += 1
            key = self._candidate_key(instance, candidate)
            if key < best_key:
                best = candidate
                best_key = key
        telemetry = {"generatedCandidates": generated, "generatedMoves": generated, "rankedMoves": generated, "prunedMoves": max(0, generated - checks), "candidateChecks": checks, "checkedCandidates": checks, "feasibleCandidates": feasible, "acceptedCandidates": 1 if best is not solution else 0, "failReasons": fail_reasons, "topRejectedReason": max(fail_reasons.items(), key=lambda item: item[1])[0] if fail_reasons else None, "bestEstimatedDistanceDelta": best_estimated_distance_delta, "bestActualDistanceDelta": None, "fullCheckPassRate": feasible / max(1, checks), **self._pruneTelemetry}
        return {"solution": best, "telemetry": telemetry}

    def _generate(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], spec: OperatorSpec, route_pool: Any | None) -> Iterable[Dict[str, Any]]:
        if name in {"intra-route-pair-relocate", "slack-aware-insertion", "traffic-aware-insertion", "lock-aware-insertion"}:
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
            yield from self._two_pair_swap(instance, solution, spec)
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
                yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": option.get("estimatedDistanceDelta", 0.0)}

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
                    yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": option.get("estimatedDistanceDelta", 0.0)}

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
                        yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": left_option.get("estimatedDistanceDelta", 0.0) + right_option.get("estimatedDistanceDelta", 0.0)}

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
                yield {"solution": {"routes": [route for route in candidate_routes if len(route) > 2]}, "estimatedDistanceDelta": -1.0}

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
        return options

    def _candidate_key(self, instance: Dict[str, Any], candidate: Dict[str, Any]) -> tuple[float, float, float, str]:
        checked = check_solution(instance, candidate)
        objective = self.objective.evaluate(instance, candidate).get("objective", float("inf"))
        return (float(checked.get("vehicleCount", 10**9) or 10**9), float(objective), float(checked.get("totalDistance", 10**9) or 10**9), solution_signature(candidate))
