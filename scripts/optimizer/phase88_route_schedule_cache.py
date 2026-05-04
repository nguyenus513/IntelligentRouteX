from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from external_benchmark_support import route_distance


@dataclass(frozen=True)
class RouteSchedule:
    route: List[str]
    arrivalTimes: List[float]
    serviceStartTimes: List[float]
    departureTimes: List[float]
    loadProfile: List[int]
    forwardSlack: List[float]
    backwardSlack: List[float]
    capacityPeak: int
    timeWindowRisk: float
    routeDistance: float
    lockedPrefixEndIndex: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}


def travel(instance: Dict[str, Any], left: str, right: str) -> float:
    matrix = instance.get("durationMatrix") or instance.get("distanceMatrix")
    indexes = matrix_index(instance)
    return float(matrix[indexes[str(left)]][indexes[str(right)]])


class RouteScheduleCache:
    def build(self, instance: Dict[str, Any], route: List[str]) -> RouteSchedule:
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        arrivals: List[float] = []
        starts: List[float] = []
        departures: List[float] = []
        loads: List[int] = []
        elapsed = 0.0
        load = 0
        risk = 0.0
        for index, stop in enumerate(route):
            if index > 0:
                elapsed += travel(instance, route[index - 1], stop)
            node = nodes.get(str(stop), {})
            ready = float(node.get("readyTime", 0.0) or 0.0)
            due = float(node.get("dueTime", 1e18) or 1e18)
            arrival = elapsed
            start = max(arrival, ready)
            if start > due:
                risk += start - due
            departure = start + float(node.get("serviceTime", 0.0) or 0.0)
            load += int(float(node.get("demand", 0) or 0))
            arrivals.append(arrival)
            starts.append(start)
            departures.append(departure)
            loads.append(load)
            elapsed = departure
        due_slacks = [float(nodes.get(str(stop), {}).get("dueTime", 1e18) or 1e18) - starts[index] for index, stop in enumerate(route)]
        forward = [min(due_slacks[index:]) if index < len(due_slacks) else 0.0 for index in range(len(due_slacks))]
        backward = [min(due_slacks[: index + 1]) if due_slacks else 0.0 for index in range(len(due_slacks))]
        return RouteSchedule(
            route=[str(stop) for stop in route],
            arrivalTimes=arrivals,
            serviceStartTimes=starts,
            departureTimes=departures,
            loadProfile=loads,
            forwardSlack=forward,
            backwardSlack=backward,
            capacityPeak=max(loads) if loads else 0,
            timeWindowRisk=risk,
            routeDistance=route_distance(instance, [str(stop) for stop in route]),
            lockedPrefixEndIndex=self._locked_prefix_end(instance, route),
        )

    def _locked_prefix_end(self, instance: Dict[str, Any], route: List[str]) -> int:
        for active in instance.get("activeRoutes", []):
            prefix = [str(stop) for stop in active.get("route", [])[: int(active.get("lockedPrefixLength", 0) or 0)]]
            if prefix and [str(stop) for stop in route[: len(prefix)]] == prefix:
                return len(prefix) - 1
        return 0
