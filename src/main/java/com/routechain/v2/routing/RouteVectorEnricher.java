package com.routechain.v2.routing;

import com.routechain.domain.Order;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.RouteProposal;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class RouteVectorEnricher {
    private final RoutingProvider routingProvider;
    private final DecisionStageLogger decisionStageLogger;
    private final HarvestRecorder harvestRecorder;

    public RouteVectorEnricher(BestPathRouter bestPathRouter, DecisionStageLogger decisionStageLogger, HarvestRecorder harvestRecorder) {
        this(new SyntheticRoutingProvider(bestPathRouter), decisionStageLogger, harvestRecorder);
    }

    public RouteVectorEnricher(RoutingProvider routingProvider, DecisionStageLogger decisionStageLogger, HarvestRecorder harvestRecorder) {
        this.routingProvider = routingProvider;
        this.decisionStageLogger = decisionStageLogger;
        this.harvestRecorder = harvestRecorder;
    }

    public RouteVectorEnricher(BestPathRouter bestPathRouter, DecisionStageLogger decisionStageLogger) {
        this(bestPathRouter, decisionStageLogger, null);
    }

    public RouteProposal enrich(String traceId, RouteProposal proposal, DispatchCandidateContext context) {
        return enrich(traceId, proposal, context, null, null, null);
    }

    public RouteProposal enrich(String traceId,
                                RouteProposal proposal,
                                DispatchCandidateContext context,
                                RouteVectorCache cache,
                                String weatherBucket,
                                String trafficBucket) {
        return enrich(traceId, proposal, context, cache, weatherBucket, trafficBucket, "pool-enrichment");
    }

    public RouteProposal enrich(String traceId,
                                RouteProposal proposal,
                                DispatchCandidateContext context,
                                RouteVectorCache cache,
                                String weatherBucket,
                                String trafficBucket,
                                String routingIntent) {
        if (cache != null) {
            RouteVectorCache.Entry cached = cache.get(proposal, context, weatherBucket, trafficBucket);
            if (cached != null) {
                cache.markReused();
                RouteVectorSummary summary = summaryForProposal(proposal, cached.summary());
                writeTraceFamilies(traceId, proposal.proposalId(), summary, cached.legs());
                return proposal.withRouteVectors(summary, cached.legs());
            }
        }
        List<RouteStop> stops = toRouteStops(proposal, context);
        if (stops.size() < 2) {
            RouteVectorSummary summary = emptySummary(proposal);
            writeTraceFamilies(traceId, proposal.proposalId(), summary, List.of());
            if (harvestRecorder != null) {
                harvestRecorder.recordRouteVector(traceId, Instant.now(), proposal, summary, List.of(), stops);
            }
            if (cache != null) {
                cache.put(proposal, context, weatherBucket, trafficBucket, summary, List.of());
            }
            return proposal.withRouteVectors(summary, List.of());
        }
        List<LegRouteVector> legs = new ArrayList<>();
        double corridorPreferenceTotal = 0.0;
        for (int index = 0; index < stops.size() - 1; index++) {
            RoutingRouteResult result = routingProvider.route(new BestPathRequest(
                    stops.get(index),
                    stops.get(index + 1),
                    context.corridorSignature(proposal.bundleId()),
                    "synthetic",
                    15,
                    routingIntent));
            legs.add(result.legVector());
            corridorPreferenceTotal += result.corridorPreferenceScore();
        }
        RouteVectorSummary summary = summarize(proposal, legs, corridorPreferenceTotal / legs.size());
        writeTraceFamilies(traceId, proposal.proposalId(), summary, legs);
        if (harvestRecorder != null) {
            harvestRecorder.recordRouteVector(traceId, Instant.now(), proposal, summary, legs, stops);
        }
        if (cache != null) {
            cache.put(proposal, context, weatherBucket, trafficBucket, summary, legs);
        }
        return proposal.withRouteVectors(summary, legs);
    }

    private RouteVectorSummary summaryForProposal(RouteProposal proposal, RouteVectorSummary cached) {
        return new RouteVectorSummary(
                cached.schemaVersion(),
                proposal.proposalId(),
                cached.legCount(),
                cached.totalDistanceMeters(),
                cached.totalTravelTimeSeconds(),
                cached.avgSpeedMps(),
                cached.majorRoadRatio(),
                cached.minorRoadRatio(),
                cached.turnCount(),
                cached.uTurnCount(),
                cached.straightnessScore(),
                cached.corridorPreferenceScore(),
                cached.congestionScore(),
                cached.routeCost(),
                cached.directionSignature(),
                cached.geometryAvailable());
    }

    private List<RouteStop> toRouteStops(RouteProposal proposal, DispatchCandidateContext context) {
        List<RouteStop> stops = new ArrayList<>();
        List<Order> pickupOrders = proposal.stopOrder().stream()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .toList();
        for (String stopOrderId : proposal.stopOrder()) {
            Order order = context.order(stopOrderId);
            if (order == null) {
                continue;
            }
            stops.add(new RouteStop(
                    order.orderId() + ":pickup",
                    order.pickupPoint().latitude(),
                    order.pickupPoint().longitude(),
                    order.orderId().equals(proposal.anchorOrderId()) ? "pickup-anchor" : "pickup",
                    context.corridorSignature(proposal.bundleId()),
                    proposal.projectedPickupEtaMinutes()));
        }
        for (Order order : deliveryOrder(pickupOrders)) {
            stops.add(new RouteStop(
                    order.orderId() + ":dropoff",
                    order.dropoffPoint().latitude(),
                    order.dropoffPoint().longitude(),
                    "dropoff",
                    context.corridorSignature(proposal.bundleId()),
                    proposal.projectedCompletionEtaMinutes()));
        }
        return List.copyOf(stops);
    }

    private List<Order> deliveryOrder(List<Order> pickupOrders) {
        if (pickupOrders.size() <= 1) {
            return List.copyOf(pickupOrders);
        }
        List<Order> remaining = new ArrayList<>(pickupOrders);
        List<Order> ordered = new ArrayList<>(pickupOrders.size());
        Order lastPickup = pickupOrders.getLast();
        while (!remaining.isEmpty()) {
            Order fromOrder = ordered.isEmpty() ? lastPickup : ordered.getLast();
            boolean fromPickup = ordered.isEmpty();
            Order next = remaining.stream()
                    .min(Comparator.comparingDouble((Order candidate) -> distanceSquared(
                                    fromPickup ? fromOrder.pickupPoint().latitude() : fromOrder.dropoffPoint().latitude(),
                                    fromPickup ? fromOrder.pickupPoint().longitude() : fromOrder.dropoffPoint().longitude(),
                                    candidate.dropoffPoint().latitude(),
                                    candidate.dropoffPoint().longitude()))
                            .thenComparing(Order::orderId))
                    .orElse(remaining.getFirst());
            ordered.add(next);
            remaining.remove(next);
        }
        return List.copyOf(ordered);
    }

    private double distanceSquared(double fromLat, double fromLon, double toLat, double toLon) {
        double deltaLat = fromLat - toLat;
        double deltaLon = fromLon - toLon;
        return (deltaLat * deltaLat) + (deltaLon * deltaLon);
    }

    private RouteVectorSummary summarize(RouteProposal proposal,
                                         List<LegRouteVector> legs,
                                         double corridorPreferenceScore) {
        double totalDistanceMeters = legs.stream().mapToDouble(LegRouteVector::distanceMeters).sum();
        double totalTravelTimeSeconds = legs.stream().mapToDouble(LegRouteVector::travelTimeSeconds).sum();
        double avgSpeedMps = totalTravelTimeSeconds <= 0.0 ? 0.0 : totalDistanceMeters / totalTravelTimeSeconds;
        double majorRoadRatio = legs.stream().mapToDouble(LegRouteVector::majorRoadRatio).average().orElse(0.0);
        double minorRoadRatio = legs.stream().mapToDouble(LegRouteVector::minorRoadRatio).average().orElse(0.0);
        int turnCount = legs.stream().mapToInt(LegRouteVector::turnCount).sum();
        int uTurnCount = legs.stream().mapToInt(LegRouteVector::uTurnCount).sum();
        double straightnessScore = legs.stream().mapToDouble(LegRouteVector::straightnessScore).average().orElse(0.0);
        double congestionScore = legs.stream().mapToDouble(LegRouteVector::congestionScore).average().orElse(0.0);
        double routeCost = legs.stream().mapToDouble(LegRouteVector::routeCost).sum();
        String directionSignature = legs.stream()
                .map(leg -> "%.0f".formatted(leg.bearingMeanDeg()))
                .collect(java.util.stream.Collectors.joining(">"));
        return new RouteVectorSummary(
                "route-vector-summary/v1",
                proposal.proposalId(),
                legs.size(),
                totalDistanceMeters,
                totalTravelTimeSeconds,
                avgSpeedMps,
                majorRoadRatio,
                minorRoadRatio,
                turnCount,
                uTurnCount,
                straightnessScore,
                corridorPreferenceScore,
                congestionScore,
                routeCost,
                directionSignature,
                true);
    }

    private RouteVectorSummary emptySummary(RouteProposal proposal) {
        return new RouteVectorSummary(
                "route-vector-summary/v1",
                proposal.proposalId(),
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0,
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                "",
                false);
    }

    private void writeTraceFamilies(String traceId,
                                    String proposalId,
                                    RouteVectorSummary summary,
                                    List<LegRouteVector> legs) {
        decisionStageLogger.writeFamily("route_leg_vector_trace", traceId, proposalId, java.util.Map.of(
                "schemaVersion", "route-leg-vector-trace/v1",
                "traceId", traceId,
                "proposalId", proposalId,
                "legs", legs));
        decisionStageLogger.writeFamily("route_vector_summary_trace", traceId, proposalId, summary);
    }
}
