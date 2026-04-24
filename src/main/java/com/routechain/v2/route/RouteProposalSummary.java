package com.routechain.v2.route;

import com.routechain.v2.SchemaVersioned;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public record RouteProposalSummary(
        String schemaVersion,
        int driverCandidateCount,
        int proposalTupleCount,
        int proposalCount,
        int retainedProposalCount,
        Map<RouteProposalSource, Integer> sourceCounts,
        RouteProposalBudgetMetrics budgetMetrics,
        List<String> degradeReasons) implements SchemaVersioned {

    public RouteProposalSummary {
        budgetMetrics = budgetMetrics == null ? RouteProposalBudgetMetrics.empty() : budgetMetrics;
    }

    public RouteProposalSummary(String schemaVersion,
                                int driverCandidateCount,
                                int proposalTupleCount,
                                int proposalCount,
                                int retainedProposalCount,
                                Map<RouteProposalSource, Integer> sourceCounts,
                                List<String> degradeReasons) {
        this(
                schemaVersion,
                driverCandidateCount,
                proposalTupleCount,
                proposalCount,
                retainedProposalCount,
                sourceCounts,
                RouteProposalBudgetMetrics.empty(),
                degradeReasons);
    }

    public static RouteProposalSummary empty() {
        return new RouteProposalSummary(
                "route-proposal-summary/v1",
                0,
                0,
                0,
                0,
                new EnumMap<>(RouteProposalSource.class),
                RouteProposalBudgetMetrics.empty(),
                List.of());
    }
}
