from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from run_phase56b_stable_promoted_runner import canonicalize_solution


OperatorFn = Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    maxRuntimeMs: int = 100
    maxCandidateChecks: int = 100
    maxDepth: int = 2
    maxBeam: int = 8
    maxRoutes: int = 8
    maxPairs: int = 32


class OperatorPortfolio:
    def __init__(self) -> None:
        self.specs = [
            OperatorSpec("regret-2-construction"),
            OperatorSpec("regret-3-construction"),
            OperatorSpec("slack-aware-insertion"),
            OperatorSpec("cluster-aware-insertion"),
            OperatorSpec("traffic-aware-insertion"),
            OperatorSpec("lock-aware-insertion"),
            OperatorSpec("related-request-destroy"),
            OperatorSpec("low-slack-destroy"),
            OperatorSpec("high-detour-destroy"),
            OperatorSpec("pd-aware-pair-relocate"),
            OperatorSpec("cross-route-pair-swap"),
            OperatorSpec("route-elimination"),
            OperatorSpec("ejection-chain-repair"),
            OperatorSpec("route-pool-recombination"),
            OperatorSpec("affected-neighborhood-exact-selector"),
        ]

    def names(self) -> List[str]:
        return [spec.name for spec in self.specs]

    def apply(self, name: str, instance: Dict[str, Any], solution: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        # Phase 84 scaffold keeps all operators bounded and safe: each operator
        # currently returns a canonical internal candidate and contributes route-pool
        # provenance/ROI telemetry. Future implementations can replace this body
        # without changing the unified feature-driven scheduler contract.
        return canonicalize_solution(instance, solution)
