from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class CandidateMoveScore:
    moveId: str
    estimatedDistanceDelta: float
    slackRisk: float = 0.0
    routeCompatibility: float = 0.0
    clusterRelatedness: float = 0.0
    trafficRobustness: float = 0.0
    lockSafety: float = 1.0
    capacityRisk: float = 0.0
    estimatedSlackMin: float = 0.0
    riskScore: float = 0.0
    objectivePotential: float = 0.0
    feasibilityProbability: float = 1.0

    def ranking_key(self) -> tuple[float, float, float, float, float, str]:
        risk = self.riskScore + self.slackRisk + self.capacityRisk + (1.0 - self.lockSafety) + max(0.0, 1.0 - self.trafficRobustness) + max(0.0, 1.0 - self.feasibilityProbability)
        compatibility = -(self.routeCompatibility + self.clusterRelatedness)
        return (self.estimatedDistanceDelta, risk, -self.objectivePotential, compatibility, -self.lockSafety, self.moveId)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CandidateRanker:
    def rank(self, moves: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scored = []
        for index, move in enumerate(moves):
            score = CandidateMoveScore(
                moveId=str(move.get("moveId", index)),
                estimatedDistanceDelta=float(move.get("estimatedDistanceDelta", 0.0) or 0.0),
                slackRisk=float(move.get("slackRisk", 0.0) or 0.0),
                routeCompatibility=float(move.get("routeCompatibility", 0.0) or 0.0),
                clusterRelatedness=float(move.get("clusterRelatedness", 0.0) or 0.0),
                trafficRobustness=float(move.get("trafficRobustness", 1.0) or 1.0),
                lockSafety=float(move.get("lockSafety", 1.0) or 1.0),
                capacityRisk=float(move.get("capacityRisk", 0.0) or 0.0),
                estimatedSlackMin=float(move.get("estimatedSlackMin", 0.0) or 0.0),
                riskScore=float(move.get("riskScore", 0.0) or 0.0),
                objectivePotential=float(move.get("objectivePotential", 0.0) or 0.0),
                feasibilityProbability=float(move.get("feasibilityProbability", 1.0) or 1.0),
            )
            scored.append({**move, "rankScore": score.to_dict(), "rankKey": score.ranking_key()})
        return sorted(scored, key=lambda item: item["rankKey"])
