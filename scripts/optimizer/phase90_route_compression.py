from __future__ import annotations

from typing import Any, Dict, Iterable, List

from external_benchmark_support import route_distance
from optimizer.phase85_pair_utils import extract_request_pairs
from optimizer.phase87_insertion_index import InsertionIndex
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer


from optimizer.phase90_deadline import Deadline
class RouteCompression:
    def __init__(self) -> None:
        self.index = InsertionIndex()
        self.scorer = ExactDeltaScorer()

    def generate(self, instance: Dict[str, Any], incumbent: Dict[str, Any], maxCandidates: int = 32, deadline: Deadline | None = None) -> Iterable[Dict[str, Any]]:
        routes = [[str(stop) for stop in route] for route in incumbent.get("routes", [])]
        pairs = extract_request_pairs(instance, incumbent)
        route_infos = []
        for route_index, route in enumerate(routes):
            route_pairs = [pair for pair in pairs if pair["routeIndex"] == route_index]
            if route_pairs:
                route_infos.append((len(route_pairs), -route_distance(instance, route) / max(1, len(route_pairs)), route_index, route_pairs))
        yielded = 0
        for _, _, remove_index, removed_pairs in sorted(route_infos):
            if deadline is not None and deadline.should_stop(5):
                return
            candidate_routes = [list(route) for index, route in enumerate(routes) if index != remove_index]
            ok = True
            for pair in sorted(removed_pairs, key=lambda item: (-len(str(item["requestId"])), item["requestId"])):
                best = None
                best_key = None
                for target_index, route in enumerate(candidate_routes):
                    if deadline is not None and deadline.should_stop(5):
                        return
                    for option in self.index.enumerate_options(instance, route, pair["request"], top_k=4):
                        attempt = [list(item) for item in candidate_routes]
                        attempt[target_index] = option["route"]
                        candidate = {"routes": [route for route in attempt if len(route) > 2]}
                        delta = self.scorer.score(instance, incumbent, candidate)
                        key = delta.stable_key()
                        if best_key is None or key < best_key:
                            best_key = key
                            best = attempt
                if best is None:
                    ok = False
                    break
                candidate_routes = best
            if ok:
                candidate = {"routes": [route for route in candidate_routes if len(route) > 2]}
                delta = self.scorer.score(instance, incumbent, candidate)
                if delta.has_quality_potential():
                    yielded += 1
                    yield {"solution": candidate, "delta": delta.to_dict(), "estimatedDistanceDelta": delta.distanceDelta}
                    if yielded >= maxCandidates:
                        return
