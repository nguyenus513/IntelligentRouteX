from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class StageRuntimeSample:
    stage: str
    runtime_ms: float
    candidate_count: int = 0
    feasible_count: int = 0
    fallback_level: str | None = None


@dataclass
class StageRuntimeProfiler:
    samples: List[StageRuntimeSample] = field(default_factory=list)

    def record(self, stage: str, runtime_ms: float, candidate_count: int = 0, feasible_count: int = 0, fallback_level: str | None = None) -> None:
        self.samples.append(StageRuntimeSample(stage, runtime_ms, candidate_count, feasible_count, fallback_level))

    def summary(self) -> Dict[str, Any]:
        by_stage: Dict[str, List[StageRuntimeSample]] = {}
        for sample in self.samples:
            by_stage.setdefault(sample.stage, []).append(sample)
        stage_summary: Dict[str, Any] = {}
        for stage, samples in by_stage.items():
            runtimes = [sample.runtime_ms for sample in samples]
            candidates = sum(sample.candidate_count for sample in samples)
            feasible = sum(sample.feasible_count for sample in samples)
            stage_summary[stage] = {
                "count": len(samples),
                "runtimeMsP50": _percentile(runtimes, 50),
                "runtimeMsP95": _percentile(runtimes, 95),
                "runtimeMsP99": _percentile(runtimes, 99),
                "candidateCount": candidates,
                "feasibleCandidateCount": feasible,
                "feasibleCandidateRatio": feasible / candidates if candidates else None,
                "fallbackLevels": sorted({sample.fallback_level for sample in samples if sample.fallback_level}),
            }
        return {"stageCount": len(stage_summary), "stages": stage_summary}


@dataclass(frozen=True)
class OperatorStats:
    attempts: int = 0
    accepted: int = 0
    rejected: int = 0
    vehicle_delta: int = 0
    distance_delta: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempts": self.attempts,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "acceptRate": self.accepted / self.attempts if self.attempts else 0.0,
            "vehicleDelta": self.vehicle_delta,
            "distanceDelta": self.distance_delta,
        }


class OperatorScoreboard:
    def __init__(self) -> None:
        self._stats: Dict[str, OperatorStats] = {}

    def record(self, operator: str, accepted: bool, before_vehicle_count: int, after_vehicle_count: int, before_distance: float, after_distance: float) -> None:
        current = self._stats.get(operator, OperatorStats())
        self._stats[operator] = OperatorStats(
            attempts=current.attempts + 1,
            accepted=current.accepted + (1 if accepted else 0),
            rejected=current.rejected + (0 if accepted else 1),
            vehicle_delta=current.vehicle_delta + (after_vehicle_count - before_vehicle_count),
            distance_delta=current.distance_delta + (after_distance - before_distance),
        )

    def summary(self) -> Dict[str, Any]:
        operators = {operator: stats.to_dict() for operator, stats in sorted(self._stats.items())}
        ranked = sorted(
            operators.items(),
            key=lambda item: (item[1]["vehicleDelta"], item[1]["distanceDelta"], -item[1]["acceptRate"]),
        )
        return {
            "operatorCount": len(operators),
            "operators": operators,
            "bestOperators": [operator for operator, _ in ranked[:5]],
        }

    @classmethod
    def from_moves(cls, moves: Iterable[Any]) -> "OperatorScoreboard":
        scoreboard = cls()
        for move in moves:
            scoreboard.record(
                operator=str(getattr(move, "operator", "unknown")),
                accepted=bool(getattr(move, "accepted", False)),
                before_vehicle_count=int(getattr(move, "before_vehicle_count", 0)),
                after_vehicle_count=int(getattr(move, "after_vehicle_count", 0)),
                before_distance=float(getattr(move, "before_distance", 0.0)),
                after_distance=float(getattr(move, "after_distance", 0.0)),
            )
        return scoreboard


@dataclass(frozen=True)
class OptimizerLoadSnapshot:
    order_count: int
    driver_count: int
    active_route_count: int
    queue_lag_ms: float = 0.0
    hot_partition_ratio: float = 1.0
    feasible_candidate_ratio: float = 1.0


@dataclass(frozen=True)
class BudgetAllocation:
    mode: str
    max_tick_ms: int
    incumbent_ms: int
    candidate_ms: int
    repair_ms: int
    scenario_ms: int
    selector_ms: int
    reserve_ms: int
    degrade_level: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class DifficultyEstimator:
    def score(self, snapshot: OptimizerLoadSnapshot) -> float:
        supply_pressure = snapshot.order_count / max(1, snapshot.driver_count)
        route_pressure = snapshot.active_route_count / max(1, snapshot.driver_count)
        lag_pressure = snapshot.queue_lag_ms / 1_000.0
        skew_pressure = max(0.0, snapshot.hot_partition_ratio - 1.0)
        infeasible_pressure = max(0.0, 1.0 - snapshot.feasible_candidate_ratio) * 4.0
        return supply_pressure + route_pressure + lag_pressure + skew_pressure + infeasible_pressure


class DegradeModeController:
    def level(self, snapshot: OptimizerLoadSnapshot, difficulty: float) -> str:
        if snapshot.queue_lag_ms >= 5_000 or snapshot.hot_partition_ratio >= 4.0 or difficulty >= 12.0:
            return "L4_SAFE_HOLD"
        if snapshot.queue_lag_ms >= 2_000 or snapshot.hot_partition_ratio >= 3.0 or difficulty >= 8.0:
            return "L3_INCUMBENT_PLUS_FAST_REPAIR"
        if snapshot.queue_lag_ms >= 1_000 or snapshot.hot_partition_ratio >= 2.0 or difficulty >= 5.0:
            return "L2_SMALL_POOL"
        if difficulty >= 3.0:
            return "L1_REDUCED_SCENARIO"
        return "L0_FULL"


class BudgetAllocator:
    def __init__(self, max_tick_ms: int = 800) -> None:
        self._max_tick_ms = max_tick_ms
        self._difficulty = DifficultyEstimator()
        self._degrade = DegradeModeController()

    def allocate(self, snapshot: OptimizerLoadSnapshot) -> BudgetAllocation:
        difficulty = self._difficulty.score(snapshot)
        level = self._degrade.level(snapshot, difficulty)
        if level == "L4_SAFE_HOLD":
            parts = (120, 80, 80, 20, 50, 450)
        elif level == "L3_INCUMBENT_PLUS_FAST_REPAIR":
            parts = (100, 100, 180, 30, 80, 310)
        elif level == "L2_SMALL_POOL":
            parts = (80, 140, 230, 60, 120, 170)
        elif level == "L1_REDUCED_SCENARIO":
            parts = (60, 160, 280, 80, 150, 70)
        else:
            parts = (50, 170, 300, 100, 150, 30)
        scale = self._max_tick_ms / 800.0
        incumbent, candidate, repair, scenario, selector, reserve = [max(1, int(value * scale)) for value in parts]
        return BudgetAllocation(
            mode="resource-aware-quality-per-ms",
            max_tick_ms=self._max_tick_ms,
            incumbent_ms=incumbent,
            candidate_ms=candidate,
            repair_ms=repair,
            scenario_ms=scenario,
            selector_ms=selector,
            reserve_ms=reserve,
            degrade_level=level,
        )


class HotKeyDetector:
    def ratio(self, partition_loads: Iterable[int]) -> float:
        loads = [load for load in partition_loads if load >= 0]
        if not loads:
            return 1.0
        median = statistics.median(loads)
        if median <= 0:
            return float(max(loads)) if max(loads) > 0 else 1.0
        return float(max(loads)) / float(median)

    def should_split(self, partition_loads: Iterable[int], threshold: float = 2.0) -> bool:
        return self.ratio(partition_loads) >= threshold


def _percentile(values: List[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile / 100.0))
    return float(ordered[index])
