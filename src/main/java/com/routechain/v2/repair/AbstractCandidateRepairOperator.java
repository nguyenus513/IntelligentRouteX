package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

import java.util.ArrayList;
import java.util.List;

abstract class AbstractCandidateRepairOperator implements RepairOperatorStrategy {

    protected RepairSolution solution(ActiveRouteInsertionCandidate candidate,
                                      String operatorName,
                                      String reason,
                                      double scoreDelta) {
        ActiveRouteInsertionCandidate repaired = new ActiveRouteInsertionCandidate(
                candidate.schemaVersion(),
                candidate.candidateId(),
                candidate.routeId(),
                candidate.driverId(),
                candidate.insertedOrderId(),
                candidate.pickupInsertionIndex(),
                candidate.newStopOrder(),
                candidate.projectedPickupEtaMinutes(),
                candidate.projectedCompletionEtaMinutes(),
                candidate.incrementalCompletionEtaMinutes(),
                candidate.freshnessRisk(),
                candidate.churnRisk(),
                candidate.routeShapeRisk(),
                Math.max(0.0, Math.min(1.0, candidate.score() + scoreDelta)),
                candidate.feasible(),
                append(candidate.reasons(), reason),
                candidate.degradeReasons());
        return new RepairSolution(
                repaired,
                repaired.score(),
                repaired.feasible(),
                List.of(operatorName),
                repaired.reasons());
    }

    protected List<String> append(List<String> reasons, String reason) {
        List<String> appended = new ArrayList<>(reasons);
        appended.add(reason);
        return appended.stream().distinct().toList();
    }
}
