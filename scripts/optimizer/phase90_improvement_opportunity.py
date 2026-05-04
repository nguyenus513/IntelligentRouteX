from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List

from external_benchmark_support import check_solution, route_distance
from optimizer.phase85_pair_utils import extract_request_pairs
from optimizer.phase88_route_schedule_cache import RouteScheduleCache


class ImprovementOpportunityDetector:
    def detect(self, instance: Dict[str, Any], solution: Dict[str, Any], route_pool: Any | None = None) -> Dict[str, Any]:
        routes = [[str(stop) for stop in route] for route in solution.get("routes", []) if len(route) > 2]
        requests = instance.get("requests", [])
        reasons: List[str] = []
        score = 0.0
        if not routes or not requests:
            return {"hasImprovementOpportunity": False, "score": 0.0, "reasons": []}
        capacity = max(1, int(float(instance.get("capacity", 1) or 1)))
        lower_bound = max(1, (len(requests) + capacity - 1) // capacity)
        if len(routes) > lower_bound:
            reasons.append("route-count-above-capacity-lower-bound")
            score += min(0.3, 0.1 * (len(routes) - lower_bound))
        route_pair_counts = self._route_pair_counts(instance, solution)
        if any(count <= 1 for count in route_pair_counts):
            reasons.append("weak-route")
            score += 0.2
        distances = [route_distance(instance, route) / max(1, count) for route, count in zip(routes, route_pair_counts) if count > 0]
        if distances and max(distances) > mean(distances) * 1.35:
            reasons.append("distance-outlier")
            score += 0.2
        if self._has_high_detour(instance, solution):
            reasons.append("high-detour")
            score += 0.15
        if self._unused_slack(instance, routes):
            reasons.append("unused-slack")
            score += 0.1
        if self._route_overlap(instance, solution) > 0.25:
            reasons.append("route-cluster-overlap")
            score += 0.15
        if instance.get("activeRoutes"):
            reasons.append("active-lock-limited")
            score = max(0.0, score - 0.1)
        if route_pool is not None and len(getattr(route_pool, "columns", {}) or {}) > len(routes):
            reasons.append("route-pool-alternatives")
            score += 0.1
        score = min(1.0, score)
        return {"hasImprovementOpportunity": bool(reasons) and score >= 0.2, "score": score, "reasons": reasons}

    def _route_pair_counts(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> List[int]:
        routes = [route for route in solution.get("routes", []) if len(route) > 2]
        counts = [0 for _ in routes]
        for pair in extract_request_pairs(instance, {"routes": routes}):
            counts[int(pair["routeIndex"])] += 1
        return counts

    def _has_high_detour(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> bool:
        nodes = {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}
        matrix = instance.get("distanceMatrix", [])
        for pair in extract_request_pairs(instance, solution):
            pickup = nodes.get(str(pair.get("pickup")))
            dropoff = nodes.get(str(pair.get("dropoff")))
            if pickup is None or dropoff is None:
                continue
            direct = float(matrix[pickup][dropoff] or 0.0)
            route = solution.get("routes", [])[int(pair["routeIndex"])]
            route_avg = route_distance(instance, route) / max(1, len(route) - 2)
            if route_avg > max(1.0, direct) * 1.5:
                return True
        return False

    def _unused_slack(self, instance: Dict[str, Any], routes: List[List[str]]) -> bool:
        cache = RouteScheduleCache()
        for route in routes:
            schedule = cache.build(instance, route)
            if schedule.forwardSlack and min(schedule.forwardSlack) > 20:
                return True
        return False

    def _route_overlap(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> float:
        pairs = extract_request_pairs(instance, solution)
        if len(pairs) < 2:
            return 0.0
        by_route: Dict[int, set[str]] = {}
        for pair in pairs:
            by_route.setdefault(int(pair["routeIndex"]), set()).add(str(pair.get("pickup")))
            by_route.setdefault(int(pair["routeIndex"]), set()).add(str(pair.get("dropoff")))
        overlaps = 0
        comparisons = 0
        route_sets = list(by_route.values())
        for left_index, left in enumerate(route_sets):
            for right in route_sets[left_index + 1 :]:
                comparisons += 1
                if left & right:
                    overlaps += 1
        return overlaps / max(1, comparisons)
