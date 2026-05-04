from __future__ import annotations

from typing import Any, Dict, Iterable

from run_phase56b_stable_promoted_runner import canonicalize_solution

from optimizer.phase90_distance_polish import DistancePolish
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from optimizer.phase90_route_compression import RouteCompression


from optimizer.phase90_deadline import Deadline
class LocalSearchChain:
    def __init__(self) -> None:
        self.polish = DistancePolish()
        self.compression = RouteCompression()
        self.scorer = ExactDeltaScorer()

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], maxChains: int = 64, maxDepth: int = 3, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        yielded = 0
        frontier = [canonicalize_solution(instance, incumbent)]
        seen = set()
        for depth in range(max(1, maxDepth)):
            if deadline is not None and deadline.should_stop(5):
                return
            next_frontier = []
            for base in frontier:
                for raw in self._step_candidates(instance, incumbent, base, max(1, maxChains - yielded), deadline):
                    candidate = canonicalize_solution(instance, raw.get("solution", raw))
                    signature = self._signature(candidate)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    delta = self.scorer.score(instance, incumbent, candidate)
                    if not delta.has_quality_potential():
                        continue
                    payload = {"solution": candidate, "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta, "estimator": {"phase90ChainDepth": depth + 1, **delta.to_dict()}}
                    yielded += 1
                    next_frontier.append(candidate)
                    yield payload
                    if yielded >= maxChains:
                        return
            frontier = next_frontier[: max(1, maxChains // 4)]
            if not frontier:
                return

    def _step_candidates(self, instance: Dict[str, Any], incumbent: Dict[str, Any], base: Dict[str, Any], limit: int, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        count = 0
        for generator in (self.polish.generate(instance, base, limit, deadline), self.compression.generate(instance, base, max(1, limit // 2), deadline)):
            for candidate in generator:
                if deadline is not None and deadline.should_stop(5):
                    return
                count += 1
                yield candidate
                if count >= limit:
                    return

    def _signature(self, solution: Dict[str, Any]) -> str:
        return "|".join(",".join(str(stop) for stop in route) for route in solution.get("routes", []))
