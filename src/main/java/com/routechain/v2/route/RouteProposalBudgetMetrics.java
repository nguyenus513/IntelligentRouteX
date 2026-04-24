package com.routechain.v2.route;

import java.util.Map;

public record RouteProposalBudgetMetrics(
        String schemaVersion,
        boolean budgetEnabled,
        String budgetMode,
        int budgetMaxTotalRouteProposals,
        int candidateCountBeforeBudget,
        int candidateCountAfterBudget,
        int candidateCountBeforePrune,
        int candidateCountAfterPrune,
        int proposalPrunedBeforeRoutePool,
        Map<String, Integer> pruneReasonCounts,
        int routeVectorComputedCount,
        int routeVectorReusedCount,
        double routeVectorCacheHitRate) {

    public static RouteProposalBudgetMetrics empty() {
        return new RouteProposalBudgetMetrics(
                "route-proposal-budget-metrics/v1",
                false,
                "disabled",
                0,
                0,
                0,
                0,
                0,
                0,
                Map.of(),
                0,
                0,
                0.0);
    }
}
