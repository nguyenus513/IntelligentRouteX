package com.routechain.v2.active;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidate;
import com.routechain.v2.selector.SelectorCandidateEnvelope;

import java.util.ArrayList;
import java.util.List;

public final class ActiveInsertionSelectorBridge {

    public List<SelectorCandidateEnvelope> bridge(List<ActiveRouteInsertionCandidate> activeInsertionCandidates) {
        if (activeInsertionCandidates == null || activeInsertionCandidates.isEmpty()) {
            return List.of();
        }
        return activeInsertionCandidates.stream()
                .map(this::bridge)
                .toList();
    }

    public SelectorCandidateEnvelope bridge(ActiveRouteInsertionCandidate insertionCandidate) {
        List<String> orderIds = insertionCandidate.newStopOrder().stream()
                .distinct()
                .toList();
        SelectorCandidate selectorCandidate = new SelectorCandidate(
                "selector-candidate/v1",
                insertionCandidate.candidateId(),
                insertionCandidate.routeId(),
                insertionCandidate.insertedOrderId(),
                insertionCandidate.driverId(),
                orderIds,
                insertionCandidate.score(),
                1.0 - insertionCandidate.routeShapeRisk(),
                RouteProposalSource.ACTIVE_ROUTE_INSERTION,
                "active-route:" + insertionCandidate.routeId(),
                false,
                selectionScore(insertionCandidate),
                insertionCandidate.feasible(),
                reasons(insertionCandidate),
                insertionCandidate.degradeReasons());
        return new SelectorCandidateEnvelope(selectorCandidate, insertionCandidate.projectedPickupEtaMinutes());
    }

    private double selectionScore(ActiveRouteInsertionCandidate insertionCandidate) {
        double feasibilityLift = insertionCandidate.feasible() ? 0.08 : -0.30;
        double stabilityLift = 0.06 * (1.0 - insertionCandidate.churnRisk());
        double freshnessLift = 0.06 * (1.0 - insertionCandidate.freshnessRisk());
        return Math.max(0.0, Math.min(1.0, insertionCandidate.score() + feasibilityLift + stabilityLift + freshnessLift));
    }

    private List<String> reasons(ActiveRouteInsertionCandidate insertionCandidate) {
        ArrayList<String> reasons = new ArrayList<>(insertionCandidate.reasons());
        reasons.add("selector-active-route-insertion-bridge");
        if (insertionCandidate.feasible()) {
            reasons.add("active-insertion-hard-guards-passed");
        }
        return reasons.stream().distinct().toList();
    }
}
