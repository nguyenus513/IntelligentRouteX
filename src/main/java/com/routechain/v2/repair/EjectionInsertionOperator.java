package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class EjectionInsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double overloadLift = Math.max(0.0, candidate.newStopOrder().size() - 3) * 0.025;
        double detourRelief = Math.max(0.0, candidate.routeShapeRisk() - 0.35) * 0.08;
        double churnPenalty = candidate.churnRisk() * 0.025;
        double delta = candidate.feasible() ? Math.min(0.16, overloadLift + detourRelief) - churnPenalty : -0.05;
        return solution(candidate, RepairOperator.EJECTION_INSERTION.name(), "alns-ejection-insertion", delta);
    }
}
