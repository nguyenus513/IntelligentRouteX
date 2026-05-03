package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class DeadlineAwareInsertionOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double pickupUrgencyLift = Math.max(0.0, 0.03 - candidate.projectedPickupEtaMinutes() * 0.0025);
        double lateRiskRescueLift = candidate.reasons().stream().anyMatch(reason -> reason.contains("late") || reason.contains("urgent")) ? 0.055 : 0.0;
        double completionPenalty = Math.max(0.0, candidate.incrementalCompletionEtaMinutes() - 8.0) * 0.006;
        return solution(candidate, RepairOperator.DEADLINE_AWARE_INSERTION.name(), "alns-deadline-aware-insertion", candidate.feasible() ? pickupUrgencyLift + lateRiskRescueLift - completionPenalty : -0.05);
    }
}
