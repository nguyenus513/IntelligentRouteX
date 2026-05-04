from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from optimizer.phase84_route_pool_memory import RouteColumn
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from optimizer.phase85_pair_utils import solution_signature
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from run_phase56b_stable_promoted_runner import canonicalize_solution


from optimizer.phase90_deadline import Deadline
class RoutePoolRecombiner:
    def __init__(self) -> None:
        self.objective = UnifiedNaturalObjective()
        self.scorer = ExactDeltaScorer()
        self.lastRejectedNonInternal = 0

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], route_pool: Any, maxCandidates: int = 16, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        self.lastRejectedNonInternal = 0
        columns = self._internal_columns(route_pool)
        required = self._required_requests(instance)
        if not required:
            return
        yielded = 0
        starts = sorted(columns, key=lambda column: (column.distance / max(1, len(column.requestSet)), len(column.requestSet), column.signature))[:maxCandidates]
        for start in starts:
            if deadline is not None and deadline.should_stop(5):
                return
            selected = self._greedy_cover(required, columns, [start])
            if selected is None:
                continue
            candidate = canonicalize_solution(instance, {"routes": [column.route for column in selected]})
            if solution_signature(candidate) == solution_signature(incumbent):
                continue
            delta = self.scorer.score(instance, incumbent, candidate)
            if not delta.has_quality_potential():
                continue
            yielded += 1
            yield {"solution": candidate, "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta, "estimator": {"routePoolColumns": len(selected), **delta.to_dict()}}
            if yielded >= maxCandidates:
                return

    def _internal_columns(self, route_pool: Any) -> List[RouteColumn]:
        columns = list(getattr(route_pool, "columns", {}).values())
        internal = []
        for column in columns:
            if getattr(column, "provenance", "internal") != "internal" or not getattr(column, "allowedForClaim", True):
                self.lastRejectedNonInternal += 1
                continue
            internal.append(column)
        return sorted(internal, key=lambda column: (column.distance, column.signature))

    def _required_requests(self, instance: Dict[str, Any]) -> Set[str]:
        return {str(request.get("orderId", f"{request.get('pickupNodeId')}->{request.get('dropoffNodeId')}")) for request in instance.get("requests", [])}

    def _greedy_cover(self, required: Set[str], columns: List[RouteColumn], seeds: List[RouteColumn]) -> List[RouteColumn] | None:
        selected: List[RouteColumn] = []
        covered: Set[str] = set()
        for column in seeds:
            request_set = set(column.requestSet)
            if covered & request_set:
                return None
            selected.append(column)
            covered.update(request_set)
        while covered != required:
            remaining = required - covered
            compatible = [column for column in columns if set(column.requestSet) <= remaining and column not in selected]
            if not compatible:
                return None
            best = sorted(compatible, key=lambda column: (column.distance / max(1, len(column.requestSet)), -len(column.requestSet), column.signature))[0]
            selected.append(best)
            covered.update(best.requestSet)
        return selected
