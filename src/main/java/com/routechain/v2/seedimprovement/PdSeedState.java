package com.routechain.v2.seedimprovement;

import com.routechain.v2.hybrid.CandidateSource;

import java.util.List;

public record PdSeedState(
        String seedId,
        CandidateSource source,
        int inputOrderCount,
        List<PdRouteState> routes,
        int assignedCount,
        int totalOrders,
        int lateCount,
        double totalLatenessMinutes,
        double distanceKm,
        double durationMinutes,
        double loadBalanceScore) {

    public PdSeedState {
        seedId = seedId == null ? "" : seedId;
        inputOrderCount = Math.max(0, inputOrderCount);
        totalOrders = Math.max(totalOrders, inputOrderCount);
        routes = routes == null ? List.of() : List.copyOf(routes);
    }

    public PdSeedState withRoutes(List<PdRouteState> nextRoutes) {
        return new PdSeedState(seedId, source, inputOrderCount, nextRoutes, assignedCount, totalOrders, lateCount, totalLatenessMinutes, distanceKm, durationMinutes, loadBalanceScore);
    }
}
