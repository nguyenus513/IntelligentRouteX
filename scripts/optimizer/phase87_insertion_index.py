from __future__ import annotations

from typing import Any, Dict, List

from external_benchmark_support import route_distance
from optimizer.phase85_pair_utils import insert_pair_positions, request_id
from optimizer.phase87_candidate_ranker import CandidateRanker
from optimizer.phase88_delta_feasibility import DeltaFeasibilityEstimator


class InsertionIndex:
    def __init__(self) -> None:
        self.estimator = DeltaFeasibilityEstimator()
        self.lastTelemetry: Dict[str, int] = {}
        self.lastPrunedSamples: List[Dict[str, Any]] = []

    def enumerate_options(self, instance: Dict[str, Any], route: List[str], request: Dict[str, Any], top_k: int = 8) -> List[Dict[str, Any]]:
        base_distance = route_distance(instance, route)
        moves = []
        telemetry = {"generatedOptions": 0, "prunedByCapacity": 0, "prunedByTimeWindow": 0, "prunedByLock": 0, "topKReturned": 0}
        self.lastPrunedSamples = []
        for pickup_pos, dropoff_pos, candidate_route in insert_pair_positions(route, request):
            telemetry["generatedOptions"] += 1
            estimate = self.estimator.estimate_pair_insertion(instance, route, request, pickup_pos, dropoff_pos)
            if not estimate.capacityOk:
                telemetry["prunedByCapacity"] += 1
                self._sample_pruned("capacity", request, candidate_route, estimate.to_dict())
                continue
            if not estimate.timeWindowLikelyOk:
                telemetry["prunedByTimeWindow"] += 1
                self._sample_pruned("timeWindow", request, candidate_route, estimate.to_dict())
                continue
            if not estimate.lockOk:
                telemetry["prunedByLock"] += 1
                self._sample_pruned("lock", request, candidate_route, estimate.to_dict())
                continue
            distance_delta = route_distance(instance, candidate_route) - base_distance
            capacity_risk = self._capacity_risk(instance, candidate_route)
            slack_risk = self._slack_risk(instance, candidate_route)
            moves.append(
                {
                    "moveId": f"{request_id(request)}:{pickup_pos}:{dropoff_pos}",
                    "request": request,
                    "route": candidate_route,
                    "pickupPos": pickup_pos,
                    "dropoffPos": dropoff_pos,
                    "estimatedDistanceDelta": distance_delta,
                    "capacityRisk": capacity_risk,
                    "slackRisk": slack_risk,
                    "estimatedSlackMin": estimate.estimatedSlackMin,
                    "riskScore": estimate.riskScore,
                    "objectivePotential": -distance_delta,
                    "feasibilityProbability": 1.0 / (1.0 + estimate.riskScore),
                    "routeCompatibility": 1.0 / (1.0 + max(0.0, distance_delta)),
                    "clusterRelatedness": 0.0,
                    "trafficRobustness": 1.0 / (1.0 + slack_risk),
                    "lockSafety": 1.0,
                }
            )
        ranked = CandidateRanker().rank(moves)[:top_k]
        telemetry["topKReturned"] = len(ranked)
        self.lastTelemetry = telemetry
        return ranked

    def _sample_pruned(self, reason: str, request: Dict[str, Any], candidate_route: List[str], estimate: Dict[str, Any]) -> None:
        if len(self.lastPrunedSamples) < 20:
            self.lastPrunedSamples.append({"pruneReason": reason, "requestId": request_id(request), "candidateRoute": candidate_route, "estimator": estimate})

    def _capacity_risk(self, instance: Dict[str, Any], route: List[str]) -> float:
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        capacity = int(instance.get("capacity", 0) or 0)
        load = 0
        risk = 0.0
        for stop in route:
            load += int(float(nodes.get(str(stop), {}).get("demand", 0) or 0))
            if load < 0 or load > capacity:
                risk += 1.0
        return risk

    def _slack_risk(self, instance: Dict[str, Any], route: List[str]) -> float:
        nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
        risk = 0.0
        for stop in route:
            node = nodes.get(str(stop), {})
            width = float(node.get("dueTime", 0.0) or 0.0) - float(node.get("readyTime", 0.0) or 0.0)
            if width < 5.0:
                risk += 1.0
        return risk
