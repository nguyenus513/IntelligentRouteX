package com.routechain.v2.routing;

import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalEngine;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RouteVectorCache {
    private final Map<String, Entry> entries = new LinkedHashMap<>();
    private int computedCount;
    private int reusedCount;

    public Entry get(RouteProposal proposal, DispatchCandidateContext context, String weatherBucket, String trafficBucket) {
        return entries.get(signature(proposal, context, weatherBucket, trafficBucket));
    }

    public void put(RouteProposal proposal,
                    DispatchCandidateContext context,
                    String weatherBucket,
                    String trafficBucket,
                    RouteVectorSummary summary,
                    List<LegRouteVector> legs) {
        entries.put(signature(proposal, context, weatherBucket, trafficBucket), new Entry(summary, List.copyOf(legs)));
        computedCount++;
    }

    public void markReused() {
        reusedCount++;
    }

    public int computedCount() {
        return computedCount;
    }

    public int reusedCount() {
        return reusedCount;
    }

    public double hitRate() {
        int total = computedCount + reusedCount;
        return total == 0 ? 0.0 : reusedCount / (double) total;
    }

    private String signature(RouteProposal proposal, DispatchCandidateContext context, String weatherBucket, String trafficBucket) {
        return String.join("|",
                proposal.bundleId(),
                proposal.anchorOrderId(),
                proposal.driverId(),
                RouteProposalEngine.stopOrderSignature(proposal.stopOrder()),
                context.corridorSignature(proposal.bundleId()),
                weatherBucket == null ? "weather:unknown" : weatherBucket,
                trafficBucket == null ? "traffic:unknown" : trafficBucket);
    }

    public record Entry(RouteVectorSummary summary, List<LegRouteVector> legs) {
    }
}
