package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

public final class MutableSuffixAlns {
    private final MutableSuffixStateFactory stateFactory = new MutableSuffixStateFactory();
    private final SuffixStateScorer scorer = new SuffixStateScorer();
    private final List<SuffixDestroyOperator> destroyOperators = List.of(
            new LateRiskRemovalOperator(),
            new HighDetourRemovalOperator(),
            new WeakBundleRemovalOperator(),
            new OverloadedSuffixRemovalOperator(),
            new ShawRelatedRemovalOperator(),
            new ControlledRandomRemovalOperator());
    private final List<SuffixRepairOperator> repairOperators = List.of(
            new RegretOrderReinsertionOperator(),
            new DeadlineAwareReinsertionOperator(),
            new FreshnessAwareReinsertionOperator(),
            new RouteShapeAwareReinsertionOperator(),
            new PairPreservingReinsertionOperator());

    public RepairSolution improve(ActiveRouteInsertionCandidate candidate, Duration budget) {
        MutableSuffixState initial = stateFactory.fromCandidate(candidate);
        MutableSuffixState best = initial;
        double bestScore = scorer.score(initial);
        RepairBudgetController budgetController = new RepairBudgetController(budget, destroyOperators.size() * repairOperators.size());
        int iteration = 0;
        for (SuffixDestroyOperator destroyOperator : destroyOperators) {
            MutableSuffixState destroyed = destroyOperator.destroy(initial);
            for (SuffixRepairOperator repairOperator : repairOperators) {
                if (!budgetController.canContinue(iteration++)) {
                    return toSolution(candidate, best, bestScore);
                }
                MutableSuffixState repaired = repairOperator.repair(destroyed);
                double repairedScore = scorer.score(repaired);
                if (repaired.feasible() && repairedScore > bestScore + 1e-9) {
                    best = repaired;
                    bestScore = repairedScore;
                }
            }
        }
        return toSolution(candidate, best, bestScore);
    }

    private RepairSolution toSolution(ActiveRouteInsertionCandidate original,
                                      MutableSuffixState state,
                                      double score) {
        ActiveRouteInsertionCandidate repaired = new ActiveRouteInsertionCandidate(
                original.schemaVersion(),
                original.candidateId(),
                original.routeId(),
                original.driverId(),
                original.insertedOrderId(),
                original.pickupInsertionIndex(),
                state.mutableStops(),
                original.projectedPickupEtaMinutes(),
                original.projectedCompletionEtaMinutes(),
                original.incrementalCompletionEtaMinutes(),
                original.freshnessRisk(),
                original.churnRisk(),
                original.routeShapeRisk(),
                score,
                state.feasible(),
                append(original.reasons(), state.operatorTrace()),
                state.violations());
        return new RepairSolution(repaired, score, state.feasible(), operatorNames(state), repaired.reasons());
    }

    private List<String> append(List<String> reasons, List<String> extraReasons) {
        List<String> appended = new ArrayList<>(reasons);
        appended.addAll(extraReasons);
        return appended.stream().distinct().toList();
    }

    private List<String> operatorNames(MutableSuffixState state) {
        return state.operatorTrace().stream()
                .filter(trace -> trace.startsWith("alns-"))
                .distinct()
                .toList();
    }
}
