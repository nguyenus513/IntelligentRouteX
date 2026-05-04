from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from external_benchmark_support import route_distance
from optimizer.phase85_pair_utils import insert_pair_positions, remove_pair_from_route
from optimizer.phase88_route_schedule_cache import RouteScheduleCache


@dataclass(frozen=True)
class DeltaFeasibility:
    precedenceOk: bool
    capacityOk: bool
    timeWindowLikelyOk: bool
    lockOk: bool
    estimatedDistanceDelta: float
    estimatedSlackMin: float
    riskScore: float
    capacityPeak: int
    timeWindowRisk: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeltaFeasibilityEstimator:
    def __init__(self) -> None:
        self.cache = RouteScheduleCache()

    def estimate_pair_insertion(self, instance: Dict[str, Any], route: List[str], request: Dict[str, Any], pickup_pos: int, dropoff_pos: int) -> DeltaFeasibility:
        options = [item for item in insert_pair_positions(route, request) if item[0] == pickup_pos and item[1] == dropoff_pos]
        candidate_route = options[0][2] if options else route
        before = self.cache.build(instance, route)
        after = self.cache.build(instance, candidate_route)
        capacity = int(instance.get("capacity", 0) or 0)
        locked_end = before.lockedPrefixEndIndex
        lock_ok = pickup_pos > locked_end and dropoff_pos > locked_end
        slack_min = min(after.forwardSlack) if after.forwardSlack else 0.0
        capacity_ok = after.capacityPeak <= capacity and min(after.loadProfile or [0]) >= 0
        time_ok = after.timeWindowRisk <= 1e-9
        risk = (0.0 if capacity_ok else 10.0) + after.timeWindowRisk + (0.0 if lock_ok else 10.0)
        return DeltaFeasibility(True, capacity_ok, time_ok, lock_ok, after.routeDistance - before.routeDistance, slack_min, risk, after.capacityPeak, after.timeWindowRisk)

    def estimate_pair_relocate(self, instance: Dict[str, Any], source_route: List[str], target_route: List[str], request: Dict[str, Any]) -> List[DeltaFeasibility]:
        stripped = remove_pair_from_route(source_route, request)
        return [self.estimate_pair_insertion(instance, target_route, request, pickup, dropoff) for pickup, dropoff, _ in insert_pair_positions(target_route, request)] + [self._route_delta(instance, source_route, stripped)]

    def estimate_pair_swap(self, instance: Dict[str, Any], route_a: List[str], route_b: List[str], request_a: Dict[str, Any], request_b: Dict[str, Any]) -> DeltaFeasibility:
        base = route_distance(instance, route_a) + route_distance(instance, route_b)
        a_base = remove_pair_from_route(route_a, request_a)
        b_base = remove_pair_from_route(route_b, request_b)
        a_options = insert_pair_positions(a_base, request_b)[:1]
        b_options = insert_pair_positions(b_base, request_a)[:1]
        if not a_options or not b_options:
            return DeltaFeasibility(False, False, False, False, 0.0, 0.0, 999.0, 0, 999.0)
        a_schedule = self.cache.build(instance, a_options[0][2])
        b_schedule = self.cache.build(instance, b_options[0][2])
        capacity = int(instance.get("capacity", 0) or 0)
        capacity_ok = a_schedule.capacityPeak <= capacity and b_schedule.capacityPeak <= capacity and min(a_schedule.loadProfile or [0]) >= 0 and min(b_schedule.loadProfile or [0]) >= 0
        time_risk = a_schedule.timeWindowRisk + b_schedule.timeWindowRisk
        distance_delta = a_schedule.routeDistance + b_schedule.routeDistance - base
        risk = (0.0 if capacity_ok else 10.0) + time_risk
        return DeltaFeasibility(True, capacity_ok, time_risk <= 1e-9, True, distance_delta, min((a_schedule.forwardSlack or [0]) + (b_schedule.forwardSlack or [0])), risk, max(a_schedule.capacityPeak, b_schedule.capacityPeak), time_risk)

    def _route_delta(self, instance: Dict[str, Any], before: List[str], after: List[str]) -> DeltaFeasibility:
        before_schedule = self.cache.build(instance, before)
        after_schedule = self.cache.build(instance, after)
        capacity = int(instance.get("capacity", 0) or 0)
        capacity_ok = after_schedule.capacityPeak <= capacity and min(after_schedule.loadProfile or [0]) >= 0
        return DeltaFeasibility(True, capacity_ok, after_schedule.timeWindowRisk <= 1e-9, True, after_schedule.routeDistance - before_schedule.routeDistance, min(after_schedule.forwardSlack or [0]), after_schedule.timeWindowRisk + (0 if capacity_ok else 10), after_schedule.capacityPeak, after_schedule.timeWindowRisk)
