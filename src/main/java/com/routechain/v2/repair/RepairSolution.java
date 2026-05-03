package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

import java.util.List;

public record RepairSolution(
        ActiveRouteInsertionCandidate candidate,
        double score,
        boolean feasible,
        List<String> operatorNames,
        List<String> reasons) {

    public static RepairSolution fromCandidate(ActiveRouteInsertionCandidate candidate) {
        return new RepairSolution(
                candidate,
                candidate.score(),
                candidate.feasible(),
                List.of(),
                candidate.reasons());
    }
}
