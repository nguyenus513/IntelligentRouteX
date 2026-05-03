package com.routechain.v2.objective;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidate;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UnifiedObjectiveIntelligenceTest {
    private final UnifiedObjective objective = new UnifiedObjective();

    @Test
    void penalizesHighRawScoreCandidateWithFreshnessRisk() {
        SelectorCandidate risky = candidate("risky", 0.95, List.of("order-1", "order-2"), List.of(), List.of("food-on-vehicle-hard-limit"));
        SelectorCandidate safe = candidate("safe", 0.86, List.of("order-1"), List.of(), List.of());

        ObjectiveBreakdown riskyBreakdown = objective.scoreSelectorCandidate(risky);
        ObjectiveBreakdown safeBreakdown = objective.scoreSelectorCandidate(safe);

        assertTrue(safeBreakdown.totalUtility() > riskyBreakdown.totalUtility());
        assertTrue(riskyBreakdown.riskCost() > safeBreakdown.riskCost());
        assertTrue(riskyBreakdown.reasons().contains("objective-freshness-penalty"));
    }

    @Test
    void rewardsCoverageButDoesNotHideHardInfeasibility() {
        SelectorCandidate infeasibleBundle = candidate("bundle", 0.99, List.of("order-1", "order-2", "order-3"), List.of(), List.of());
        infeasibleBundle = new SelectorCandidate(
                infeasibleBundle.schemaVersion(),
                infeasibleBundle.proposalId(),
                infeasibleBundle.bundleId(),
                infeasibleBundle.anchorOrderId(),
                infeasibleBundle.driverId(),
                infeasibleBundle.orderIds(),
                infeasibleBundle.robustUtility(),
                infeasibleBundle.routeValue(),
                infeasibleBundle.source(),
                infeasibleBundle.clusterId(),
                infeasibleBundle.boundaryCross(),
                infeasibleBundle.selectionScore(),
                false,
                infeasibleBundle.reasons(),
                infeasibleBundle.degradeReasons());

        ObjectiveBreakdown breakdown = objective.scoreSelectorCandidate(infeasibleBundle);

        assertTrue(breakdown.rewardValue() > 0.0);
        assertEquals(Double.NEGATIVE_INFINITY, breakdown.totalUtility());
        assertTrue(breakdown.hard().violations().contains("candidate-marked-infeasible"));
    }

    @Test
    void rewardsActiveRouteDiversityButPenalizesChurn() {
        SelectorCandidate stable = candidate("stable", 0.82, List.of("order-1"), List.of(), List.of());
        SelectorCandidate churn = candidate("churn", 0.82, List.of("order-1"), List.of(), List.of("frozen-prefix-mutated"), RouteProposalSource.ACTIVE_ROUTE_INSERTION);

        ObjectiveBreakdown stableBreakdown = objective.scoreSelectorCandidate(stable);
        ObjectiveBreakdown churnBreakdown = objective.scoreSelectorCandidate(churn);

        assertTrue(churnBreakdown.rewardValue() > stableBreakdown.rewardValue());
        assertTrue(churnBreakdown.fairnessCost() > stableBreakdown.fairnessCost());
        assertTrue(stableBreakdown.totalUtility() > churnBreakdown.totalUtility());
    }

    private SelectorCandidate candidate(String proposalId,
                                        double score,
                                        List<String> orderIds,
                                        List<String> reasons,
                                        List<String> degradeReasons) {
        return candidate(proposalId, score, orderIds, reasons, degradeReasons, RouteProposalSource.HEURISTIC_FAST);
    }

    private SelectorCandidate candidate(String proposalId,
                                        double score,
                                        List<String> orderIds,
                                        List<String> reasons,
                                        List<String> degradeReasons,
                                        RouteProposalSource source) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                "bundle-" + proposalId,
                orderIds.getFirst(),
                "driver-" + proposalId,
                orderIds,
                score,
                score,
                source,
                "cluster-" + proposalId,
                false,
                score,
                true,
                reasons,
                degradeReasons);
    }
}
