package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class FreshnessAwareInsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double freshnessLift = (1.0 - candidate.freshnessRisk()) * 0.04;
        double protectedFoodLift = candidate.freshnessRisk() > 0.45 ? Math.max(0.0, 0.08 - candidate.freshnessRisk() * 0.06) : 0.0;
        double highRiskPenalty = candidate.freshnessRisk() > 0.75 ? 0.05 : 0.0;
        return solution(candidate,
                RepairOperator.FRESHNESS_AWARE_INSERTION.name(),
                "alns-freshness-aware-insertion",
                candidate.feasible() ? freshnessLift + protectedFoodLift - highRiskPenalty : -0.05);
    }
}
