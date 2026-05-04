from __future__ import annotations

from typing import Any, Dict, Iterable, List

from external_benchmark_support import check_solution
from optimizer.phase85_pair_utils import extract_request_pairs, request_id, solution_signature
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from run_phase56b_stable_promoted_runner import canonicalize_solution


class FinalCandidateBridge:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.scorer = ExactDeltaScorer()
        self.lastTelemetry: Dict[str, Any] = {"intermediateStatesSeen": 0, "bridgedFinalCandidates": 0, "bridgeFailReasons": {}}

    def bridge(self, instance: Dict[str, Any], incumbent: Dict[str, Any], candidates: Iterable[Dict[str, Any]], max_candidates: int = 8) -> List[Dict[str, Any]]:
        self.lastTelemetry = {"intermediateStatesSeen": 0, "bridgedFinalCandidates": 0, "bridgeFailReasons": {}}
        bridged: List[Dict[str, Any]] = []
        seen = {solution_signature(incumbent)}
        for raw in candidates:
            self.lastTelemetry["intermediateStatesSeen"] += 1
            solution = canonicalize_solution(instance, raw.get("solution", raw))
            completed = self._complete_coverage(instance, solution)
            if completed is None:
                self._count("coverage-completion-failed")
                continue
            completed = canonicalize_solution(instance, completed)
            signature = solution_signature(completed)
            if signature in seen:
                self._count("duplicate-final")
                continue
            seen.add(signature)
            checked = check_solution(instance, completed)
            if not checked.get("feasible"):
                self._count("checker-infeasible")
                continue
            delta = self.scorer.score(instance, incumbent, completed)
            payload = {"solution": completed, "candidateStage": "final", "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta, "estimator": {"bridge": True, **delta.to_dict()}}
            bridged.append(payload)
            self.lastTelemetry["bridgedFinalCandidates"] += 1
            if len(bridged) >= max_candidates:
                break
        return bridged

    def _complete_coverage(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any] | None:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) >= 2]
        depot = str(instance.get("depotNodeId", "0"))
        if not routes:
            routes = [[depot, depot]]
        covered = {request_id(pair["request"]) for pair in extract_request_pairs(instance, {"routes": routes})}
        requests = {request_id(request): request for request in instance.get("requests", [])}
        missing = [requests[key] for key in sorted(set(requests) - covered)]
        current = routes
        for request in missing:
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
        return {"routes": [route for route in current if len(route) > 2]}

    def _count(self, reason: str) -> None:
        reasons = self.lastTelemetry.setdefault("bridgeFailReasons", {})
        reasons[reason] = reasons.get(reason, 0) + 1
