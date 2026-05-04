from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from external_benchmark_support import check_solution, route_distance
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from optimizer.phase85_pair_utils import extract_request_pairs, remove_pair_from_route, request_id, solution_signature
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_alns_acceptance import DeterministicRandom, accepts, decayed_temperature
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from run_phase56b_stable_promoted_runner import canonicalize_solution


from optimizer.phase90_deadline import Deadline
@dataclass(frozen=True)
class DestroyResult:
    operator: str
    routes: List[List[str]]
    removedPairs: List[Dict[str, Any]]


class ALNSRepairEngine:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.scorer = ExactDeltaScorer()
        self.objective = UnifiedNaturalObjective()
        self.lastTelemetry: Dict[str, Any] = {}

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], route_pool: Any | None = None, maxIterations: int = 48, beam: int = 8, ejectionDepth: int = 2, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        incumbent = canonicalize_solution(instance, incumbent)
        current = incumbent
        incumbent_eval = self.objective.evaluate(instance, incumbent)
        incumbent_objective = float(incumbent_eval.get("objective", float("inf")))
        current_objective = incumbent_objective
        best_objective = incumbent_objective
        best_improving: Dict[str, Any] | None = None
        deterministic_random = DeterministicRandom.from_signature(solution_signature(incumbent))
        temperature0 = max(1.0, abs(incumbent_objective) * 0.01)
        seen = {solution_signature(incumbent)}
        telemetry = {
            "alnsIterations": 0,
            "intermediateWorseAcceptedForSearch": 0,
            "worseIntermediateAccepted": 0,
            "improvingIntermediateAccepted": 0,
            "finalCheckerFeasibleCandidates": 0,
            "finalObjectiveImprovingCandidates": 0,
            "ejectionDepthUsed": 0,
            "repairFailReasons": {},
            "ejectionFailReasons": {},
            "ejectionAttempts": 0,
            "ejectionSuccesses": 0,
            "destroyRepairAttempts": 0,
            "repairSuccesses": 0,
            "intermediateFeasibleStates": 0,
            "finalCandidatesProduced": 0,
            "finalCandidatesChecked": 0,
            "bestObjectiveDelta": 0.0,
            "bestDistanceDelta": 0.0,
            "bestVehicleDelta": 0.0,
            "finalImprovingCandidateFound": False,
            "noImprovementReason": None,
            "earlyStopReason": None,
            "safeReturn": False,
        }
        yielded = 0
        self._active_deadline = deadline
        self._active_telemetry = telemetry
        repair_names = ["regret_3_repair", "regret_2_repair", "slack_aware_repair", "ejection_repair", "route_pool_repair"]
        for iteration in range(maxIterations):
            if deadline is not None and deadline.should_stop(10):
                telemetry["earlyStopReason"] = "deadline"
                telemetry["safeReturn"] = True
                break
            destroys = self._destroy_results(instance, current, beam)
            if not destroys:
                telemetry["noImprovementReason"] = "no-destroy-neighborhood"
                break
            destroy = destroys[iteration % len(destroys)]
            repair_name = repair_names[iteration % len(repair_names)]
            telemetry["alnsIterations"] += 1
            telemetry["destroyRepairAttempts"] += 1
            repaired = self._repair(instance, destroy.routes, destroy.removedPairs, repair_name, route_pool, beam, ejectionDepth)
            if repaired is None:
                self._count(telemetry["repairFailReasons"], f"{repair_name}-failed")
                continue
            telemetry["repairSuccesses"] += 1
            candidate = canonicalize_solution(instance, {"routes": repaired})
            signature = solution_signature(candidate)
            if signature in seen and candidate != current:
                self._count(telemetry["repairFailReasons"], "duplicate-solution")
                continue
            seen.add(signature)
            checked = check_solution(instance, candidate)
            telemetry["finalCandidatesProduced"] += 1
            telemetry["finalCandidatesChecked"] += 1
            if not checked.get("feasible"):
                self._count(telemetry["repairFailReasons"], "hard-violation")
                continue
            telemetry["finalCheckerFeasibleCandidates"] += 1
            telemetry["intermediateFeasibleStates"] += 1
            candidate_eval = self.objective.evaluate(instance, candidate)
            candidate_objective = float(candidate_eval.get("objective", float("inf")))
            delta = self.scorer.score(instance, incumbent, candidate)
            if candidate_objective < incumbent_objective:
                best_improving = candidate
                best_objective = min(best_objective, candidate_objective)
                telemetry["finalObjectiveImprovingCandidates"] += 1
                telemetry["finalImprovingCandidateFound"] = True
                telemetry["bestObjectiveDelta"] = min(float(telemetry["bestObjectiveDelta"]), candidate_objective - incumbent_objective)
                telemetry["bestDistanceDelta"] = min(float(telemetry["bestDistanceDelta"]), delta.distanceDelta)
                telemetry["bestVehicleDelta"] = min(float(telemetry["bestVehicleDelta"]), delta.vehicleDelta)
                yielded += 1
                yield {
                    "solution": candidate,
                    "candidateStage": "final",
                    "allowFinalQualityCheck": True,
                    "finalQualityPotential": True,
                    "delta": delta.to_dict(),
                    "estimatedDistanceDelta": delta.distanceDelta,
                    "estimator": {"destroyOperator": destroy.operator, "repairOperator": repair_name, "candidateStage": "final", "finalQualityPotential": True, **delta.to_dict()},
                    "telemetry": dict(telemetry),
                }
                if yielded >= beam:
                    break
            accepted = accepts(current_objective, candidate_objective, best_objective, decayed_temperature(temperature0, iteration), deterministic_random, iteration)
            if accepted:
                if candidate_objective < current_objective:
                    telemetry["improvingIntermediateAccepted"] += 1
                elif candidate_objective > current_objective:
                    telemetry["intermediateWorseAcceptedForSearch"] += 1
                    telemetry["worseIntermediateAccepted"] += 1
                current = candidate
                current_objective = candidate_objective
            telemetry["ejectionDepthUsed"] = max(telemetry["ejectionDepthUsed"], ejectionDepth if repair_name == "ejection_repair" else 0)
        if best_improving is None:
            telemetry["noImprovementReason"] = telemetry.get("noImprovementReason") or "bounded-search-no-improvement"
        self._active_deadline = None
        self._active_telemetry = None
        self.lastTelemetry = telemetry

    def _destroy_results(self, instance: Dict[str, Any], solution: Dict[str, Any], beam: int) -> List[DestroyResult]:
        pairs = extract_request_pairs(instance, solution)
        if not pairs:
            return []
        routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
        selectors = [
            ("shaw_related_destroy", self._shaw_related_pairs(instance, pairs)),
            ("worst_detour_destroy", self._worst_detour_pairs(instance, solution, pairs)),
            ("low_slack_destroy", self._low_slack_pairs(instance, pairs)),
            ("time_window_conflict_destroy", self._low_slack_pairs(instance, pairs)),
            ("weak_route_destroy", self._weak_route_pairs(instance, solution, pairs)),
            ("route_fragment_destroy", self._route_fragment_pairs(pairs)),
        ]
        results = []
        remove_count = max(1, min(4, len(pairs), max(1, len(pairs) // 4)))
        for name, ranked in selectors:
            removed = ranked[:remove_count]
            if not removed:
                continue
            partial = [list(route) for route in routes]
            for pair in removed:
                partial[pair["routeIndex"]] = remove_pair_from_route(partial[pair["routeIndex"]], pair["request"])
            results.append(DestroyResult(name, [route for route in partial if len(route) > 2], removed))
            if len(results) >= beam:
                break
        return results

    def _repair(self, instance: Dict[str, Any], routes: List[List[str]], removed: List[Dict[str, Any]], repair_name: str, route_pool: Any | None, beam: int, ejectionDepth: int) -> List[List[str]] | None:
        current = [list(route) for route in routes]
        order = self._repair_order(instance, current, removed, repair_name)
        if repair_name == "route_pool_repair" and route_pool is not None:
            pooled = self._try_pool_seed(instance, current, removed, route_pool)
            if pooled is not None:
                current = pooled
        for pair in order:
            if hasattr(self, "_active_deadline") and self._active_deadline is not None and self._active_deadline.should_stop(5):
                return None
            inserted = self._best_insert(instance, current, pair["request"], beam)
            if inserted is None and repair_name == "ejection_repair":
                inserted = self._ejection_insert(instance, current, pair, beam, ejectionDepth)
            if inserted is None:
                return None
            current = inserted
        return [route for route in current if len(route) > 2]

    def _best_insert(self, instance: Dict[str, Any], routes: List[List[str]], request: Dict[str, Any], beam: int) -> List[List[str]] | None:
        best_routes = None
        best_key = None
        candidate_routes = routes or [[str(instance.get("depotNodeId", "0")), str(instance.get("depotNodeId", "0"))]]
        for route_index, route in enumerate(candidate_routes):
            for option in self.index.enumerate_options(instance, route, request, max(1, beam)):
                attempt = [list(item) for item in candidate_routes]
                attempt[route_index] = option["route"]
                checked = check_solution(instance, {"routes": [route for route in attempt if len(route) > 2]})
                key = (0 if checked.get("feasible") else 1, option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": attempt}))
                if best_key is None or key < best_key:
                    best_key = key
                    best_routes = attempt
        return best_routes

    def _ejection_insert(self, instance: Dict[str, Any], routes: List[List[str]], pair: Dict[str, Any], beam: int, depth: int) -> List[List[str]] | None:
        telemetry = getattr(self, "_active_telemetry", None)
        if telemetry is not None:
            telemetry["ejectionAttempts"] = int(telemetry.get("ejectionAttempts", 0) or 0) + 1
        if depth <= 0:
            if telemetry is not None:
                self._count(telemetry.setdefault("ejectionFailReasons", {}), "depth-cap")
            return None
        candidates = []
        for route_index, route in enumerate(routes):
            route_pairs = [item for item in extract_request_pairs(instance, {"routes": [route]})]
            for eject in route_pairs[:beam]:
                base_route = remove_pair_from_route(route, eject["request"])
                for option in self.index.enumerate_options(instance, base_route, pair["request"], max(1, beam // 2)):
                    attempt = [list(item) for item in routes]
                    attempt[route_index] = option["route"]
                    reinserted = self._best_insert(instance, attempt, eject["request"], max(1, beam // 2))
                    if reinserted is not None:
                        checked = check_solution(instance, {"routes": [item for item in reinserted if len(item) > 2]})
                        candidates.append((0 if checked.get("feasible") else 1, option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": reinserted}), reinserted))
        if not candidates:
            if telemetry is not None:
                self._count(telemetry.setdefault("ejectionFailReasons", {}), "no-compatible-ejection")
            return None
        if telemetry is not None:
            telemetry["ejectionSuccesses"] = int(telemetry.get("ejectionSuccesses", 0) or 0) + 1
        return sorted(candidates, key=lambda item: item[:3])[0][3]

    def _try_pool_seed(self, instance: Dict[str, Any], routes: List[List[str]], removed: List[Dict[str, Any]], route_pool: Any) -> List[List[str]] | None:
        removed_ids = {request_id(pair["request"]) for pair in removed}
        columns = sorted(getattr(route_pool, "columns", {}).values(), key=lambda column: (column.distance, column.signature))
        seeded = [list(route) for route in routes]
        covered = self._covered_request_ids(instance, {"routes": seeded})
        for column in columns:
            if getattr(column, "provenance", "internal") != "internal" or not getattr(column, "allowedForClaim", True):
                continue
            request_set = set(column.requestSet)
            if not request_set or not request_set <= removed_ids or covered & request_set:
                continue
            seeded.append(list(column.route))
            covered.update(request_set)
        return seeded if len(seeded) != len(routes) else None

    def _repair_order(self, instance: Dict[str, Any], routes: List[List[str]], removed: List[Dict[str, Any]], repair_name: str) -> List[Dict[str, Any]]:
        if repair_name == "regret_3_repair":
            return sorted(removed, key=lambda pair: (-self._regret(instance, routes, pair["request"], 3), pair["requestId"]))
        if repair_name == "regret_2_repair":
            return sorted(removed, key=lambda pair: (-self._regret(instance, routes, pair["request"], 2), pair["requestId"]))
        return sorted(removed, key=lambda pair: (self._request_slack(instance, pair), pair["requestId"]))

    def _regret(self, instance: Dict[str, Any], routes: List[List[str]], request: Dict[str, Any], k: int) -> float:
        deltas = []
        for route in routes:
            deltas.extend(float(option.get("estimatedDistanceDelta", 0.0) or 0.0) for option in self.index.enumerate_options(instance, route, request, k))
        if not deltas:
            return 10**9
        ranked = sorted(deltas)
        return ranked[min(k - 1, len(ranked) - 1)] - ranked[0]

    def _shaw_related_pairs(self, instance: Dict[str, Any], pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        first = pairs[0]
        return sorted(pairs, key=lambda pair: (self._pair_distance(instance, first, pair), pair["requestId"]))

    def _worst_detour_pairs(self, instance: Dict[str, Any], solution: Dict[str, Any], pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        routes = solution.get("routes", [])
        return sorted(pairs, key=lambda pair: (-route_distance(instance, routes[pair["routeIndex"]]) / max(1, len(routes[pair["routeIndex"]]) - 2), pair["requestId"]))

    def _low_slack_pairs(self, instance: Dict[str, Any], pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(pairs, key=lambda pair: (self._request_slack(instance, pair), pair["requestId"]))

    def _weak_route_pairs(self, instance: Dict[str, Any], solution: Dict[str, Any], pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for pair in pairs:
            grouped.setdefault(int(pair["routeIndex"]), []).append(pair)
        routes = solution.get("routes", [])
        weak_index = sorted(grouped, key=lambda index: (len(grouped[index]), -route_distance(instance, routes[index]) / max(1, len(grouped[index])), index))[0]
        return sorted(grouped[weak_index], key=lambda pair: pair["requestId"])

    def _route_fragment_pairs(self, pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(pairs, key=lambda pair: (pair["routeIndex"], pair["pickupIndex"], pair["requestId"]))

    def _pair_distance(self, instance: Dict[str, Any], left: Dict[str, Any], right: Dict[str, Any]) -> float:
        nodes = {str(node.get("id")): idx for idx, node in enumerate(instance.get("nodes", []))}
        matrix = instance.get("distanceMatrix", [])
        left_pickup = nodes.get(str(left.get("pickup")))
        right_pickup = nodes.get(str(right.get("pickup")))
        if left_pickup is None or right_pickup is None:
            return 0.0
        return float(matrix[left_pickup][right_pickup])

    def _request_slack(self, instance: Dict[str, Any], pair: Dict[str, Any]) -> float:
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        pickup = nodes.get(str(pair.get("pickup")), {})
        dropoff = nodes.get(str(pair.get("dropoff")), {})
        return min(float(pickup.get("dueTime", 0.0) or 0.0) - float(pickup.get("readyTime", 0.0) or 0.0), float(dropoff.get("dueTime", 0.0) or 0.0) - float(dropoff.get("readyTime", 0.0) or 0.0))

    def _covered_request_ids(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> set[str]:
        return {request_id(pair["request"]) for pair in extract_request_pairs(instance, solution)}

    def _count(self, counts: Dict[str, int], key: str) -> None:
        counts[key] = counts.get(key, 0) + 1
