from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


def _matrix_index(instance: Dict[str, Any]) -> Dict[str, int]:
    return {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}


def _matrix(instance: Dict[str, Any]) -> List[List[float]]:
    return instance.get("durationMatrix") or instance.get("distanceMatrix") or []


def _distance(instance: Dict[str, Any], left: str, right: str) -> float:
    indexes = _matrix_index(instance)
    matrix = _matrix(instance)
    if left not in indexes or right not in indexes or not matrix:
        return 0.0
    return float(matrix[indexes[left]][indexes[right]])


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))]


@dataclass(frozen=True)
class InstanceFeatures:
    requestCount: int
    nodeCount: int
    vehicleCount: int
    capacity: int
    capacityPressure: float
    averageDemand: float
    pickupDropoffDistanceMean: float
    pickupDropoffDistanceP95: float
    spatialDispersion: float
    clusterScore: float
    timeWindowWidthMean: float
    timeWindowWidthP10: float
    timeWindowTightness: float
    readyDueOverlapDensity: float
    pickupDropoffMixedness: float
    trafficMultiplier: float
    trafficConfidence: float
    durationMatrixAsymmetry: float
    activeRouteCount: int
    lockedPrefixPressure: float
    initialFeasibleRouteCount: int
    initialDistance: float
    initialSlackMean: float
    initialSlackP10: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InstanceFeatureExtractor:
    def extract(self, instance: Dict[str, Any], initial_solution: Dict[str, Any] | None = None) -> InstanceFeatures:
        requests = instance.get("requests", [])
        nodes = instance.get("nodes", [])
        vehicle_count = int(instance.get("vehicleCount", 0) or 0)
        capacity = int(instance.get("capacity", 0) or 0)
        demands = [abs(float(request.get("demand", 1) or 1)) for request in requests]
        total_demand = sum(demands)
        capacity_pressure = total_demand / max(1.0, float(vehicle_count * max(1, capacity)))
        pickup_distances = [_distance(instance, str(request.get("pickupNodeId")), str(request.get("dropoffNodeId"))) for request in requests]
        xs = [float(node.get("x", 0.0) or 0.0) for node in nodes]
        ys = [float(node.get("y", 0.0) or 0.0) for node in nodes]
        centroid_x = sum(xs) / len(xs) if xs else 0.0
        centroid_y = sum(ys) / len(ys) if ys else 0.0
        dispersion_values = [math.hypot(x - centroid_x, y - centroid_y) for x, y in zip(xs, ys)]
        spatial_dispersion = sum(dispersion_values) / len(dispersion_values) if dispersion_values else 0.0
        cluster_score = 1.0 / (1.0 + spatial_dispersion)
        widths = [max(0.0, float(node.get("dueTime", 0.0) or 0.0) - float(node.get("readyTime", 0.0) or 0.0)) for node in nodes]
        width_mean = sum(widths) / len(widths) if widths else 0.0
        width_p10 = _percentile(widths, 0.10)
        distance_mean = sum(pickup_distances) / len(pickup_distances) if pickup_distances else 0.0
        time_window_tightness = 1.0 / (1.0 + width_p10)
        ready_values = [float(node.get("readyTime", 0.0) or 0.0) for node in nodes]
        due_values = [float(node.get("dueTime", 0.0) or 0.0) for node in nodes]
        overlap_span = max(0.0, min(due_values) - max(ready_values)) if due_values and ready_values else 0.0
        ready_due_overlap = overlap_span / max(1.0, max(due_values) - min(ready_values)) if due_values and ready_values else 0.0
        mixedness = distance_mean / max(1.0, spatial_dispersion)
        traffic = instance.get("metadata", {}).get("trafficContext", {}) or instance.get("trafficContext", {}) or {}
        matrix = _matrix(instance)
        asymmetry_values = []
        for left in range(len(matrix)):
            for right in range(left + 1, len(matrix)):
                a = float(matrix[left][right])
                b = float(matrix[right][left])
                asymmetry_values.append(abs(a - b) / max(1.0, max(a, b)))
        active_routes = instance.get("activeRoutes", [])
        locked_nodes = sum(int(route.get("lockedPrefixLength", 0) or 0) for route in active_routes)
        initial_routes = [route for route in (initial_solution or {}).get("routes", []) if len(route) > 2]
        initial_distance = sum(sum(_distance(instance, str(a), str(b)) for a, b in zip(route, route[1:])) for route in initial_routes)
        slack_values = [float(node.get("dueTime", 0.0) or 0.0) - float(node.get("readyTime", 0.0) or 0.0) for node in nodes]
        return InstanceFeatures(
            requestCount=len(requests),
            nodeCount=len(nodes),
            vehicleCount=vehicle_count,
            capacity=capacity,
            capacityPressure=capacity_pressure,
            averageDemand=total_demand / len(demands) if demands else 0.0,
            pickupDropoffDistanceMean=distance_mean,
            pickupDropoffDistanceP95=_percentile(pickup_distances, 0.95),
            spatialDispersion=spatial_dispersion,
            clusterScore=cluster_score,
            timeWindowWidthMean=width_mean,
            timeWindowWidthP10=width_p10,
            timeWindowTightness=time_window_tightness,
            readyDueOverlapDensity=ready_due_overlap,
            pickupDropoffMixedness=mixedness,
            trafficMultiplier=float(traffic.get("multiplier", 1.0) or 1.0),
            trafficConfidence=float(traffic.get("confidence", 1.0) or 1.0),
            durationMatrixAsymmetry=sum(asymmetry_values) / len(asymmetry_values) if asymmetry_values else 0.0,
            activeRouteCount=len(active_routes),
            lockedPrefixPressure=locked_nodes / max(1, len(nodes)),
            initialFeasibleRouteCount=len(initial_routes),
            initialDistance=initial_distance,
            initialSlackMean=sum(slack_values) / len(slack_values) if slack_values else 0.0,
            initialSlackP10=_percentile(slack_values, 0.10),
        )
