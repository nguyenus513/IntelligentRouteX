package com.routechain.v2.route;

import java.util.List;
import java.util.Map;

public record RouteProposalPruneResult(
        List<DriverCandidate> driverCandidates,
        List<PickupAnchor> pickupAnchors,
        List<RouteProposalCandidate> candidates,
        int candidateCountBeforePrune,
        int candidateCountAfterPrune,
        int proposalPrunedBeforeRoutePool,
        Map<String, Integer> pruneReasonCounts) {
}
