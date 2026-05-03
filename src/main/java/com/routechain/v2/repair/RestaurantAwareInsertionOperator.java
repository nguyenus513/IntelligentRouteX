package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class RestaurantAwareInsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double compactnessLift = candidate.pickupInsertionIndex() <= 1 ? 0.025 : 0.01;
        double churnPenalty = candidate.churnRisk() * 0.03;
        return solution(candidate, RepairOperator.RESTAURANT_AWARE_INSERTION.name(), "alns-restaurant-aware-insertion", candidate.feasible() ? compactnessLift - churnPenalty : -0.04);
    }
}
