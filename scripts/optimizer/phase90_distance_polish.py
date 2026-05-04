from __future__ import annotations

from typing import Any, Dict, Iterable, List

from optimizer.phase85_pair_utils import extract_request_pairs, remove_pair_from_route
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer


from optimizer.phase90_deadline import Deadline
class DistancePolish:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.scorer = ExactDeltaScorer()

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], maxCandidates: int = 64, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in incumbent.get("routes", [])]
        yielded = 0
        for pair in extract_request_pairs(instance, incumbent):
            if deadline is not None and deadline.should_stop(5):
                return
            route_index = pair["routeIndex"]
            stripped = remove_pair_from_route(routes[route_index], pair["request"])
            for option in self.index.enumerate_options(instance, stripped, pair["request"], top_k=8):
                if deadline is not None and deadline.should_stop(5):
                    return
                candidate_routes = [list(route) for route in routes]
                candidate_routes[route_index] = option["route"]
                candidate = {"routes": [route for route in candidate_routes if len(route) > 2]}
                delta = self.scorer.score(instance, incumbent, candidate)
                if delta.distanceDelta < 0:
                    yielded += 1
                    yield {"solution": candidate, "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta}
                    if yielded >= maxCandidates:
                        return
