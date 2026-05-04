from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass(frozen=True)
class TrafficMatrixResult:
    durationMatrix: List[List[float]]
    distanceMatrix: List[List[float]]
    trafficContext: Dict[str, Any]
    providerDiagnostics: Dict[str, Any]


class TrafficProvider(Protocol):
    def build_duration_matrix(self, nodes: List[Dict[str, Any]], region: str, timestamp: str, traffic_context: Dict[str, Any]) -> TrafficMatrixResult:
        ...
