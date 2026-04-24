package com.routechain.v2.route;

import java.util.List;

public record RouteProposalBudgetDecision(
        boolean enabled,
        String budgetMode,
        int maxTotalRouteProposals,
        int maxDriversPerBundle,
        int maxAnchorsPerBundle,
        int maxAlternativesPerTuple,
        List<String> budgetReasons) {
}
