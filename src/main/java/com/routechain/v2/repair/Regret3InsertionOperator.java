package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class Regret3InsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double suffixComplexityLift = Math.min(0.025, Math.max(0, candidate.newStopOrder().size() - 2) * 0.004);
        return solution(candidate, RepairOperator.REGRET_3_INSERTION.name(), "alns-regret-3-insertion", candidate.feasible() ? suffixComplexityLift : -0.04);
    }
}
