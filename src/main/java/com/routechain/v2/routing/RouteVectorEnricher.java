package com.routechain.v2.routing;

import com.routechain.domain.Order;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.RouteProposal;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public final class RouteVectorEnricher {
    private final RoutingProvider routingProvider;
    private final OsrmTableClient osrmTableClient;
    private final PickupDeliveryPermutationOptimizer routeSequenceOptimizer;
    private final DecisionStageLogger decisionStageLogger;
    private final HarvestRecorder harvestRecorder;

    public RouteVectorEnricher(BestPathRouter bestPathRouter, DecisionStageLogger decisionStageLogger, HarvestRecorder harvestRecorder) {
        this(new SyntheticRoutingProvider(bestPathRouter), decisionStageLogger, harvestRecorder);
    }

    public RouteVectorEnricher(RoutingProvider routingProvider, DecisionStageLogger decisionStageLogger, HarvestRecorder harvestRecorder) {
        this(routingProvider, null, decisionStageLogger, harvestRecorder);
    }

    public RouteVectorEnricher(RoutingProvider routingProvider,
                               OsrmTableClient osrmTableClient,
                               DecisionStageLogger decisionStageLogger,
                               HarvestRecorder harvestRecorder) {
        this.routingProvider = routingProvider;
        this.osrmTableClient = osrmTableClient;
        this.routeSequenceOptimizer = new PickupDeliveryPermutationOptimizer();
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
        List<Order> pickupOrders = proposal.stopOrder().stream()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .toList();
        List<RouteStop> fallbackStops = pickupThenDropoffStops(proposal, context, pickupOrders);
        if (pickupOrders.isEmpty() || pickupOrders.size() > 5) {
            return fallbackStops;
        }
        RouteStop driverStop = driverStop(proposal, context);
        if (driverStop == null) {
            return fallbackStops;
        }
        List<PickupDeliveryStop> pickupStops = pickupOrders.stream()
                .map(order -> PickupDeliveryStop.pickup(order.orderId(), routeStopForPickup(proposal, context, order)))
                .toList();
        List<PickupDeliveryStop> dropoffStops = pickupOrders.stream()
                .map(order -> PickupDeliveryStop.dropoff(order.orderId(), routeStopForDropoff(proposal, context, order)))
                .toList();
        DurationMatrix matrix = durationMatrix(driverStop, pickupStops, dropoffStops);
        List<RouteSequence> sequences = routeSequenceOptimizer.optimize(
                driverStop,
                pickupStops,
                dropoffStops,
                matrix,
                RouteOptimizationConstraints.defaults());
        return sequences.stream()
                .filter(RouteSequence::feasible)
                .findFirst()
                .map(sequence -> sequence.stops().stream()
                        .map(PickupDeliveryStop::routeStop)
                        .toList())
                .filter(stops -> !stops.isEmpty())
                .orElse(fallbackStops);
    }

    private List<RouteStop> pickupThenDropoffStops(RouteProposal proposal,
                                                   DispatchCandidateContext context,
                                                   List<Order> pickupOrders) {
        List<RouteStop> stops = new ArrayList<>();
        for (String stopOrderId : proposal.stopOrder()) {
            Order order = context.order(stopOrderId);
            if (order != null) {
                stops.add(routeStopForPickup(proposal, context, order));
            }
        }
        for (Order order : pickupOrders) {
            stops.add(routeStopForDropoff(proposal, context, order));
        }
        return List.copyOf(stops);
    }

    private RouteStop routeStopForPickup(RouteProposal proposal, DispatchCandidateContext context, Order order) {
        return new RouteStop(
                order.orderId() + ":pickup",
                order.pickupPoint().latitude(),
                order.pickupPoint().longitude(),
                order.orderId().equals(proposal.anchorOrderId()) ? "pickup-anchor" : "pickup",
                context.corridorSignature(proposal.bundleId()),
                proposal.projectedPickupEtaMinutes());
    }

    private RouteStop routeStopForDropoff(RouteProposal proposal, DispatchCandidateContext context, Order order) {
        return new RouteStop(
                order.orderId() + ":dropoff",
                order.dropoffPoint().latitude(),
                order.dropoffPoint().longitude(),
                "dropoff",
                context.corridorSignature(proposal.bundleId()),
                proposal.projectedCompletionEtaMinutes());
    }

    private RouteStop driverStop(RouteProposal proposal, DispatchCandidateContext context) {
        com.routechain.domain.Driver driver = context.driver(proposal.driverId());
        if (driver == null || driver.currentLocation() == null) {
            return null;
        }
        return new RouteStop(
                proposal.driverId() + ":driver",
                driver.currentLocation().latitude(),
                driver.currentLocation().longitude(),
                "driver",
                context.corridorSignature(proposal.bundleId()),
                0.0);
    }

    private DurationMatrix durationMatrix(RouteStop driverStop,
                                          List<PickupDeliveryStop> pickupStops,
                                          List<PickupDeliveryStop> dropoffStops) {
        List<RouteStop> routeStops = java.util.stream.Stream.concat(pickupStops.stream(), dropoffStops.stream())
                .map(PickupDeliveryStop::routeStop)
                .toList();
        List<RouteStop> sources = new ArrayList<>(routeStops.size() + 1);
        sources.add(driverStop);
        sources.addAll(routeStops);
        if (osrmTableClient != null) {
            DurationMatrix matrix = osrmTableClient.fetchMatrix(sources, routeStops);
            if (matrix != null && matrix.degradeReasons().isEmpty() && !matrix.durationsSeconds().isEmpty()) {
                return matrix;
            }
        }
        return syntheticDurationMatrix(sources, routeStops);
    }

    private DurationMatrix syntheticDurationMatrix(List<RouteStop> sources, List<RouteStop> destinations) {
        List<List<Double>> durations = new ArrayList<>(sources.size());
        List<List<Double>> distances = new ArrayList<>(sources.size());
        for (RouteStop source : sources) {
            List<Double> durationRow = new ArrayList<>(destinations.size());
            List<Double> distanceRow = new ArrayList<>(destinations.size());
            for (RouteStop destination : destinations) {
                double distanceMeters = haversineMeters(source.latitude(), source.longitude(), destination.latitude(), destination.longitude());
                distanceRow.add(distanceMeters);
                durationRow.add(distanceMeters / 8.0);
            }
            durations.add(java.util.Collections.unmodifiableList(durationRow));
            distances.add(java.util.Collections.unmodifiableList(distanceRow));
        }
        return new DurationMatrix(
                "duration-matrix/v1",
                "synthetic-local",
                sources,
                destinations,
                sources.stream().map(source -> MatrixPoint.unsnapped(source, "synthetic-local-matrix")).toList(),
                destinations.stream().map(destination -> MatrixPoint.unsnapped(destination, "synthetic-local-matrix")).toList(),
                java.util.Collections.unmodifiableList(durations),
                java.util.Collections.unmodifiableList(distances),
                0,
                0,
                0L,
                List.of("synthetic-local-matrix"));
    }

    private double haversineMeters(double fromLat, double fromLon, double toLat, double toLon) {
        double earthRadiusMeters = 6_371_000.0;
        double lat1 = Math.toRadians(fromLat);
        double lat2 = Math.toRadians(toLat);
        double deltaLat = Math.toRadians(toLat - fromLat);
        double deltaLon = Math.toRadians(toLon - fromLon);
        double a = Math.sin(deltaLat / 2.0) * Math.sin(deltaLat / 2.0)
                + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2.0) * Math.sin(deltaLon / 2.0);
        double c = 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
        return earthRadiusMeters * c;
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
