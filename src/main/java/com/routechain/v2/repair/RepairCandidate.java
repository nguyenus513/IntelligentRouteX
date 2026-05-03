package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import java.util.List;

public record RepairCandidate(
        ActiveRouteInsertionCandidate insertionCandidate,
        double objectiveScore,
        boolean feasible,
        List<String> operatorsApplied,
        List<String> reasons) {
}
