from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Set

from optimizer.phase85_pair_utils import extract_request_pairs, request_id, solution_signature
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from run_phase56b_stable_promoted_runner import canonicalize_solution


from optimizer.phase90_deadline import Deadline
@dataclass(frozen=True)
class PopulationMember:
    solution: Dict[str, Any]
    signature: str
    diversityKey: str


class RoutePopulation:
    def __init__(self, maxSize: int = 12) -> None:
        self.maxSize = maxSize
        self.members: Dict[str, PopulationMember] = {}
        self.index = InsertionIndex()
        self.scorer = ExactDeltaScorer()
        self.lastTelemetry: Dict[str, Any] = {"populationDiversity": 0, "duplicateRejected": 0}

    def add(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> bool:
        normalized = canonicalize_solution(instance, solution)
        signature = solution_signature(normalized)
        if signature in self.members:
            self.lastTelemetry["duplicateRejected"] = int(self.lastTelemetry.get("duplicateRejected", 0) or 0) + 1
            return False
        member = PopulationMember(normalized, signature, self._diversity_key(instance, normalized))
        self.members[signature] = member
        if len(self.members) > self.maxSize:
            key = sorted(self.members, key=lambda item: (self.members[item].diversityKey, item))[-1]
            self.members.pop(key, None)
        self.lastTelemetry["populationDiversity"] = len({member.diversityKey for member in self.members.values()})
        return True

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], seeds: Iterable[Dict[str, Any]] = (), maxCandidates: int = 16, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        self.add(instance, incumbent)
        for seed in seeds:
            self.add(instance, seed)
        members = sorted(self.members.values(), key=lambda member: member.signature)
        yielded = 0
        for left in members:
            if deadline is not None and deadline.should_stop(5):
                return
            for right in members:
                if deadline is not None and deadline.should_stop(5):
                    return
                if left.signature >= right.signature:
                    continue
                candidate = self._recombine(instance, incumbent, left.solution, right.solution)
                if candidate is None:
                    continue
                delta = self.scorer.score(instance, incumbent, candidate)
                if not delta.has_quality_potential():
                    continue
                yielded += 1
                yield {"solution": candidate, "candidateStage": "final", "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta, "estimator": {"populationDiversity": self.lastTelemetry.get("populationDiversity", 0), **delta.to_dict()}, "telemetry": dict(self.lastTelemetry)}
                if yielded >= maxCandidates:
                    return

    def _recombine(self, instance: Dict[str, Any], incumbent: Dict[str, Any], left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any] | None:
        required = {request_id(request) for request in instance.get("requests", [])}
        selected: List[List[str]] = []
        covered: Set[str] = set()
        candidate_routes = list(left.get("routes", [])) + list(right.get("routes", []))
        ranked = sorted(candidate_routes, key=lambda route: (-len(self._route_request_ids(instance, route)), len(route), ",".join(str(stop) for stop in route)))
        for route in ranked:
            request_ids = self._route_request_ids(instance, route)
            if request_ids and not (covered & request_ids):
                selected.append([str(stop) for stop in route])
                covered.update(request_ids)
        missing = required - covered
        if missing:
            selected = self._repair_missing(instance, selected, missing)
        if not selected or self._covered(instance, {"routes": selected}) != required:
            return None
        return canonicalize_solution(instance, {"routes": selected})

    def _repair_missing(self, instance: Dict[str, Any], routes: List[List[str]], missing: Set[str]) -> List[List[str]]:
        current = [list(route) for route in routes]
        by_id = {request_id(request): request for request in instance.get("requests", [])}
        depot = str(instance.get("depotNodeId", "0"))
        if not current:
            current = [[depot, depot]]
        for missing_id in sorted(missing):
            request = by_id[missing_id]
            best = None
            best_key = None
            for route_index, route in enumerate(current):
                for option in self.index.enumerate_options(instance, route, request, top_k=6):
                    attempt = [list(item) for item in current]
                    attempt[route_index] = option["route"]
                    key = (option.get("estimatedDistanceDelta", 0.0), solution_signature({"routes": attempt}))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = attempt
            if best is None:
                current.append([depot, str(request.get("pickupNodeId")), str(request.get("dropoffNodeId")), depot])
            else:
                current = best
        return current

    def _covered(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Set[str]:
        return {request_id(pair["request"]) for pair in extract_request_pairs(instance, solution)}

    def _route_request_ids(self, instance: Dict[str, Any], route: List[str]) -> Set[str]:
        route_set = {str(stop) for stop in route}
        ids = set()
        for request in instance.get("requests", []):
            if str(request.get("pickupNodeId")) in route_set and str(request.get("dropoffNodeId")) in route_set:
                ids.add(request_id(request))
        return ids

    def _diversity_key(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> str:
        route_sets = sorted("/".join(sorted(self._route_request_ids(instance, route))) for route in solution.get("routes", []))
        return "|".join(route_sets)
