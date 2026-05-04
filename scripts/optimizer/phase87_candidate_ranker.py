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

    def ranking_key(self) -> tuple[float, float, float, float, str]:
        risk = self.slackRisk + self.capacityRisk + (1.0 - self.lockSafety) + max(0.0, 1.0 - self.trafficRobustness)
        compatibility = -(self.routeCompatibility + self.clusterRelatedness)
        return (self.estimatedDistanceDelta, risk, compatibility, -self.lockSafety, self.moveId)

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
            )
            scored.append({**move, "rankScore": score.to_dict(), "rankKey": score.ranking_key()})
        return sorted(scored, key=lambda item: item["rankKey"])
