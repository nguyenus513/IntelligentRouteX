from __future__ import annotations

import time
from typing import Any, Dict

from optimizer.phase84_adaptive_budget import AdaptiveBudgetController
from optimizer.phase84_feature_extractor import InstanceFeatureExtractor
from optimizer.phase84_hyper_heuristic import AdaptiveHyperHeuristic
from optimizer.phase84_lock_aware_optimizer import LockAwareOptimizer
from optimizer.phase84_operator_portfolio import OperatorPortfolio
from optimizer.phase84_route_pool_memory import RoutePoolMemory
from optimizer.phase84_route_set_selector import AdaptiveRouteSetSelector
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from run_phase56b_stable_promoted_runner import canonicalize_solution


class UnifiedIntelligentOptimizer:
    def __init__(self, deterministic_seed: int = 84) -> None:
        self.deterministic_seed = deterministic_seed
        self.extractor = InstanceFeatureExtractor()
        self.objective = UnifiedNaturalObjective()
        self.budget = AdaptiveBudgetController()
        self.portfolio = OperatorPortfolio()
        self.hyper = AdaptiveHyperHeuristic()
        self.selector = AdaptiveRouteSetSelector()
        self.lock = LockAwareOptimizer()

    def optimize(self, instance: Dict[str, Any], incumbent: Dict[str, Any], time_limit_ms: int) -> Dict[str, Any]:
        started = time.perf_counter()
        current = canonicalize_solution(instance, incumbent)
        features = self.extractor.extract(instance, current).to_dict()
        pool = RoutePoolMemory()
        pool.add_solution(instance, current, "incumbent")
        operator_names = self.portfolio.names()
        budgets = self.budget.allocate(max(1, int(time_limit_ms * 0.25)), features, operator_names)
        for _ in range(min(8, len(operator_names))):
            name = self.hyper.select(operator_names, features)
            if name is None:
                break
            op_started = time.perf_counter()
            operator_result = self.portfolio.apply(name, instance, current, features, budgets.get(name), pool)
            candidate = operator_result.get("solution", current)
            operator_telemetry = operator_result.get("telemetry", {})
            runtime_ms = int((time.perf_counter() - op_started) * 1000)
            candidate_eval = self.objective.evaluate(instance, candidate)
            accepted = bool(candidate_eval.get("feasible")) and self.objective.improves(instance, current, candidate)
            if accepted and self.lock.accepts(instance, candidate):
                current = candidate
            reward = 0.0
            if accepted:
                reward = 1.0
            self.hyper.record(name, reward, runtime_ms, bool(candidate_eval.get("feasible")), accepted)
            if name in budgets:
                budgets[name].usedMs += runtime_ms
                budgets[name].generatedCandidates += int(operator_telemetry.get("generatedCandidates", 0) or 0)
                budgets[name].candidateChecks += int(operator_telemetry.get("candidateChecks", 1) or 0)
                budgets[name].feasibleCandidateCount += int(operator_telemetry.get("feasibleCandidates", 1 if candidate_eval.get("feasible") else 0) or 0)
                budgets[name].acceptedCount += int(operator_telemetry.get("acceptedCandidates", 1 if accepted else 0) or 0)
                budgets[name].roi = reward / max(1, runtime_ms)
                merged_reasons = dict(budgets[name].failReasons or {})
                for reason, count in operator_telemetry.get("failReasons", {}).items():
                    merged_reasons[str(reason)] = merged_reasons.get(str(reason), 0) + int(count or 0)
                budgets[name].failReasons = merged_reasons
            pool.add_solution(instance, candidate, name)
        selected = self.selector.select(instance, current, pool)
        if self.objective.improves(instance, current, selected) and self.lock.accepts(instance, selected):
            current = selected
        evaluation = self.objective.evaluate(instance, current)
        diagnostics = {
            "schemaVersion": "phase84-unified-intelligent-optimizer/v1",
            "deterministicSeed": self.deterministic_seed,
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "features": features,
            "operatorTelemetry": self.hyper.telemetry(),
            "budgetTelemetry": self.budget.telemetry(budgets),
            "routePoolStats": pool.stats(),
            "objective": evaluation,
            "acceptedOnlyNaturalImprovement": True,
        }
        return {"solution": current, "diagnostics": diagnostics}
