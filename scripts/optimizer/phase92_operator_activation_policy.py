from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from external_benchmark_support import route_distance
from optimizer.phase85_pair_utils import extract_request_pairs


@dataclass(frozen=True)
class ActivationDecision:
    operator: str
    reason: str
    expectedOpportunityType: str
    priority: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OperatorActivationPolicy:
    def activate(self, instance: Dict[str, Any], solution: Dict[str, Any], features: Dict[str, Any], remaining_budget_ms: int, operators: List[str]) -> List[ActivationDecision]:
        route_count = len([route for route in solution.get("routes", []) if len(route) > 2])
        request_count = len(instance.get("requests", []))
        histogram = self._route_size_histogram(instance, solution)
        overlap = self._route_overlap_score(instance, solution)
        capacity_pressure = float(features.get("capacityPressure", 0.0) or 0.0)
        tightness = float(features.get("timeWindowTightness", 0.0) or 0.0)
        cluster = float(features.get("clusterScore", 0.0) or 0.0)
        weak_route = any(size <= 1 for size in histogram)
        distance_outlier = self._distance_outlier(instance, solution, histogram)
        decisions: List[ActivationDecision] = []
        for operator in operators:
            lowered = operator.lower()
            priority = 1.0
            reason = "baseline-activation"
            opportunity = "pair-relocation"
            if "compression" in lowered or "elimination" in lowered or "ejection" in lowered:
                opportunity = "route-count-reduction"
                priority += (0.5 if weak_route else 0.0) + capacity_pressure + route_count / max(1, request_count)
                reason = "weak-route" if weak_route else "capacity-route-pressure"
            elif "polish" in lowered or "swap" in lowered or "relocate" in lowered:
                opportunity = "distance-polish"
                priority += (0.5 if distance_outlier else 0.0) + overlap + cluster
                reason = "distance-outlier" if distance_outlier else "route-overlap"
            elif "alns" in lowered or "population" in lowered or "pool" in lowered:
                opportunity = "ejection-repair" if weak_route else "route-compression"
                priority += 0.75 + overlap + tightness + max(0.0, remaining_budget_ms / 10_000.0)
                reason = "large-neighborhood-opportunity"
            if remaining_budget_ms <= 0:
                reason = "deadline-before-generation"
                priority = -1.0
            decisions.append(ActivationDecision(operator, reason, opportunity, priority))
        return sorted(decisions, key=lambda item: (-item.priority, item.operator))

    def _route_size_histogram(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> List[int]:
        routes = [route for route in solution.get("routes", []) if len(route) > 2]
        counts = [0 for _ in routes]
        for pair in extract_request_pairs(instance, {"routes": routes}):
            counts[int(pair["routeIndex"])] += 1
        return counts

    def _route_overlap_score(self, instance: Dict[str, Any], solution: Dict[str, Any]) -> float:
        pairs = extract_request_pairs(instance, solution)
        if len(pairs) < 2:
            return 0.0
        route_sets: Dict[int, set[str]] = {}
        for pair in pairs:
            route_sets.setdefault(int(pair["routeIndex"]), set()).update({str(pair.get("pickup")), str(pair.get("dropoff"))})
        values = list(route_sets.values())
        comparisons = 0
        overlap = 0.0
        for left_index, left in enumerate(values):
            for right in values[left_index + 1 :]:
                comparisons += 1
                overlap += len(left & right) / max(1, len(left | right))
        return overlap / max(1, comparisons)

    def _distance_outlier(self, instance: Dict[str, Any], solution: Dict[str, Any], histogram: List[int]) -> bool:
        routes = [route for route in solution.get("routes", []) if len(route) > 2]
        ratios = [route_distance(instance, route) / max(1, size) for route, size in zip(routes, histogram) if size > 0]
        if len(ratios) < 2:
            return bool(ratios and ratios[0] > 0)
        avg = sum(ratios) / len(ratios)
        return max(ratios) > avg * 1.25
