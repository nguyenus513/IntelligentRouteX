package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class Regret2InsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double delta = candidate.feasible() ? Math.max(0.0, 0.035 - candidate.incrementalCompletionEtaMinutes() * 0.002) : -0.05;
        return solution(candidate, RepairOperator.REGRET_2_INSERTION.name(), "alns-regret-2-insertion", delta);
    }
}
