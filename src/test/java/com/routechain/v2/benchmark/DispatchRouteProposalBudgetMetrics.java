package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;

import java.util.Map;

public record DispatchRouteProposalBudgetMetrics(
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
        double routeVectorCacheHitRate) implements SchemaVersioned {

    public static DispatchRouteProposalBudgetMetrics empty() {
        return new DispatchRouteProposalBudgetMetrics(
                "dispatch-route-proposal-budget-metrics/v1",
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
