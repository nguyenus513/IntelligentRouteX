package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public final class RouteSplitMergeOperator extends AbstractCandidateRepairOperator {
    @Override
    public RepairSolution apply(ActiveRouteInsertionCandidate candidate) {
        double suffixRelief = Math.max(0.0, candidate.newStopOrder().size() - 4) * 0.025;
        double freshnessRelief = Math.max(0.0, candidate.freshnessRisk() - 0.45) * 0.07;
        double churnPenalty = candidate.churnRisk() * 0.035;
        double delta = candidate.feasible() ? Math.min(0.14, suffixRelief + freshnessRelief) - churnPenalty : -0.05;
        return solution(candidate, RepairOperator.ROUTE_SPLIT_MERGE.name(), "alns-route-split-merge", delta);
    }
}
