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
from optimizer.phase90_deadline import Deadline
from optimizer.phase90_improvement_opportunity import ImprovementOpportunityDetector
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
        self.opportunity = ImprovementOpportunityDetector()

    def optimize(self, instance: Dict[str, Any], incumbent: Dict[str, Any], time_limit_ms: int) -> Dict[str, Any]:
        started = time.perf_counter()
        deadline = Deadline.from_time_limit_ms(time_limit_ms)
        current = canonicalize_solution(instance, incumbent)
        features = self.extractor.extract(instance, current).to_dict()
        pool = RoutePoolMemory()
        pool.add_solution(instance, current, "incumbent")
        operator_names = self.portfolio.names()
        budgets = self.budget.allocate(max(1, int(time_limit_ms * 0.25)), features, operator_names)
        checked_candidate_traces = []
        pruned_candidate_samples = []
        safe_return = False
        early_stop_reason = None
        for _ in range(min(8, len(operator_names))):
            if deadline.should_stop(25):
                safe_return = True
                early_stop_reason = "deadline"
                break
            name = self.hyper.select(operator_names, features)
            if name is None:
                break
            op_started = time.perf_counter()
            operator_result = self.portfolio.apply(name, instance, current, features, budgets.get(name), pool, deadline)
            checked_candidate_traces.extend(operator_result.get("checkedCandidateTraces", [])[: max(0, 100 - len(checked_candidate_traces))])
            pruned_candidate_samples.extend(operator_result.get("prunedCandidateSamples", [])[: max(0, 100 - len(pruned_candidate_samples))])
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
            self.hyper.record(name, reward, runtime_ms, bool(candidate_eval.get("feasible")), accepted, operator_telemetry)
            if name in budgets:
                budgets[name].usedMs += runtime_ms
                budgets[name].generatedCandidates += int(operator_telemetry.get("generatedCandidates", 0) or 0)
                budgets[name].generatedMoves += int(operator_telemetry.get("generatedMoves", 0) or 0)
                budgets[name].rankedMoves += int(operator_telemetry.get("rankedMoves", 0) or 0)
                budgets[name].prunedMoves += int(operator_telemetry.get("prunedMoves", 0) or 0)
                budgets[name].candidateChecks += int(operator_telemetry.get("candidateChecks", 1) or 0)
                checker_feasible = int(operator_telemetry.get("checkerFeasibleCandidates", operator_telemetry.get("feasibleCandidates", 1 if candidate_eval.get("feasible") else 0)) or 0)
                objective_improving = int(operator_telemetry.get("objectiveImprovingCandidates", 1 if accepted else 0) or 0)
                objective_not_improved = int(operator_telemetry.get("objectiveNotImprovedCandidates", 0) or 0)
                budgets[name].feasibleCandidateCount += checker_feasible
                budgets[name].checkerFeasibleCandidates += checker_feasible
                budgets[name].objectiveImprovingCandidates += objective_improving
                budgets[name].objectiveNotImprovedCandidates += objective_not_improved
                budgets[name].acceptedCount += int(operator_telemetry.get("acceptedCandidates", 1 if accepted else 0) or 0)
                budgets[name].prunedNoQualityPotential += int(operator_telemetry.get("prunedNoQualityPotential", 0) or 0)
                budgets[name].alnsIterations += int(operator_telemetry.get("alnsIterations", 0) or 0)
                budgets[name].intermediateWorseAcceptedForSearch += int(operator_telemetry.get("intermediateWorseAcceptedForSearch", 0) or 0)
                budgets[name].finalCheckerFeasibleCandidates += int(operator_telemetry.get("finalCheckerFeasibleCandidates", 0) or 0)
                budgets[name].finalObjectiveImprovingCandidates += int(operator_telemetry.get("finalObjectiveImprovingCandidates", 0) or 0)
                budgets[name].routePoolColumnCount = max(budgets[name].routePoolColumnCount, int(operator_telemetry.get("routePoolColumnCount", 0) or 0))
                budgets[name].populationDiversity = max(budgets[name].populationDiversity, int(operator_telemetry.get("populationDiversity", 0) or 0))
                budgets[name].ejectionDepthUsed = max(budgets[name].ejectionDepthUsed, int(operator_telemetry.get("ejectionDepthUsed", 0) or 0))
                budgets[name].safeReturn = bool(budgets[name].safeReturn or operator_telemetry.get("safeReturn", False))
                if operator_telemetry.get("earlyStopReason") and not budgets[name].earlyStopReason:
                    budgets[name].earlyStopReason = str(operator_telemetry.get("earlyStopReason"))
                repair_reasons = dict(budgets[name].repairFailReasons or {})
                for reason, count in (operator_telemetry.get("repairFailReasons", {}) or {}).items():
                    repair_reasons[str(reason)] = repair_reasons.get(str(reason), 0) + int(count or 0)
                budgets[name].repairFailReasons = repair_reasons
                budgets[name].roi = reward / max(1, runtime_ms)
                budgets[name].prunedByCapacity += int(operator_telemetry.get("prunedByCapacity", 0) or 0)
                budgets[name].prunedByTimeWindow += int(operator_telemetry.get("prunedByTimeWindow", 0) or 0)
                budgets[name].prunedByLock += int(operator_telemetry.get("prunedByLock", 0) or 0)
                budgets[name].estimatedFeasibleMoves += int(operator_telemetry.get("estimatedFeasibleMoves", 0) or 0)
                budgets[name].fullCheckPassRate = float(operator_telemetry.get("fullCheckPassRate", budgets[name].fullCheckPassRate) or 0.0)
                budgets[name].nearFeasibleRepairAttempts += int(operator_telemetry.get("nearFeasibleRepairAttempts", 0) or 0)
                budgets[name].nearFeasibleRepairSuccesses += int(operator_telemetry.get("nearFeasibleRepairSuccesses", 0) or 0)
                if operator_telemetry.get("bestEstimatedDistanceDelta") is not None:
                    value = float(operator_telemetry["bestEstimatedDistanceDelta"])
                    budgets[name].bestEstimatedDistanceDelta = value if budgets[name].bestEstimatedDistanceDelta is None else min(budgets[name].bestEstimatedDistanceDelta, value)
                if operator_telemetry.get("bestActualDistanceDelta") is not None:
                    value = float(operator_telemetry["bestActualDistanceDelta"])
                    budgets[name].bestActualDistanceDelta = value if budgets[name].bestActualDistanceDelta is None else min(budgets[name].bestActualDistanceDelta, value)
                if operator_telemetry.get("bestDistanceDelta") is not None:
                    value = float(operator_telemetry["bestDistanceDelta"])
                    budgets[name].bestDistanceDelta = value if budgets[name].bestDistanceDelta is None else min(budgets[name].bestDistanceDelta, value)
                if operator_telemetry.get("bestVehicleDelta") is not None:
                    value = float(operator_telemetry["bestVehicleDelta"])
                    budgets[name].bestVehicleDelta = value if budgets[name].bestVehicleDelta is None else min(budgets[name].bestVehicleDelta, value)
                merged_reasons = dict(budgets[name].failReasons or {})
                for reason, count in operator_telemetry.get("failReasons", {}).items():
                    merged_reasons[str(reason)] = merged_reasons.get(str(reason), 0) + int(count or 0)
                budgets[name].failReasons = merged_reasons
            pool.add_solution(instance, candidate, name)
        if not deadline.should_stop(25):
            selected = self.selector.select(instance, current, pool)
            if self.objective.improves(instance, current, selected) and self.lock.accepts(instance, selected):
                current = selected
        else:
            safe_return = True
            early_stop_reason = early_stop_reason or "deadline"
        evaluation = self.objective.evaluate(instance, current)
        improvement_opportunity = self.opportunity.detect(instance, current, pool)
        diagnostics = {
            "schemaVersion": "phase84-unified-intelligent-optimizer/v1",
            "deterministicSeed": self.deterministic_seed,
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "features": features,
            "operatorTelemetry": self.hyper.telemetry(),
            "budgetTelemetry": self.budget.telemetry(budgets),
            "routePoolStats": pool.stats(),
            "checkedCandidateTraces": checked_candidate_traces,
            "prunedCandidateSamples": pruned_candidate_samples,
            "objective": evaluation,
            "acceptedOnlyNaturalImprovement": True,
            "improvementOpportunity": improvement_opportunity,
            "earlyStopReason": early_stop_reason,
            "safeReturn": safe_return,
        }
        return {"solution": current, "diagnostics": diagnostics}
