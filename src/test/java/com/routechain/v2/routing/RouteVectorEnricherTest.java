package com.routechain.v2.routing;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteTestFixtures;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteVectorEnricherTest {

    @Test
    void enrichesProposalWithDeterministicLegMetrics() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(properties);
        String bundleId = context.bundleIds().getFirst();
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                "proposal-1",
                bundleId,
                context.bundle(bundleId).seedOrderId(),
                context.availableDrivers().getFirst().driverId(),
                RouteProposalSource.HEURISTIC_FAST,
                context.bundle(bundleId).orderIds(),
                4.0,
                18.0,
                0.7,
                true,
                List.of(),
                List.of());
        RouteVectorEnricher enricher = new RouteVectorEnricher(
                new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()),
                new DecisionStageLogger(properties));

        RouteProposal enriched = enricher.enrich("trace-route", proposal, context);

        assertTrue(enriched.geometryAvailable());
        assertTrue(enriched.legCount() > 0);
        assertTrue(enriched.totalDistanceMeters() > 0.0);
        assertFalse(enriched.legs().isEmpty());
        assertEquals("synthetic", enriched.legs().getFirst().routingProvider());
        assertEquals("synthetic-straight-line", enriched.legs().getFirst().geometryKind());
        assertEquals(2, enriched.legs().getFirst().polyline().size());
    }

    @Test
    void multiOrderRoutePreservesPickupBeforeOwnDropoff() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(properties);
        String bundleId = context.bundleIds().stream()
                .filter(id -> context.bundle(id).orderIds().size() >= 3)
                .findFirst()
                .orElseThrow();
        List<String> stopOrder = context.bundle(bundleId).orderIds().stream().limit(3).toList();
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                "proposal-pickups-before-dropoffs",
                bundleId,
                stopOrder.getFirst(),
                context.availableDrivers().getFirst().driverId(),
                RouteProposalSource.HEURISTIC_FAST,
                stopOrder,
                4.0,
                18.0,
                0.7,
                true,
                List.of(),
                List.of());
        RouteVectorEnricher enricher = new RouteVectorEnricher(
                new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()),
                new DecisionStageLogger(properties));

        RouteProposal enriched = enricher.enrich("trace-pickups-before-dropoffs", proposal, context);
        List<String> legTransitions = enriched.legs().stream()
                .map(leg -> leg.fromStopId() + "->" + leg.toStopId())
                .toList();

        assertEquals(stopOrder.size() * 2 - 1, enriched.legCount());
        for (String orderId : stopOrder) {
            int pickupIndex = firstTransitionIndexContaining(legTransitions, orderId + ":pickup");
            int dropoffIndex = firstTransitionIndexContaining(legTransitions, orderId + ":dropoff");
            assertTrue(pickupIndex >= 0, "missing pickup for " + orderId);
            assertTrue(dropoffIndex >= 0, "missing dropoff for " + orderId);
            assertTrue(pickupIndex <= dropoffIndex, "dropoff must not appear before pickup for " + orderId);
        }
    }

    @Test
    void emitsTraceFamiliesEvenWhenRouteHasSingleStop() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        Path feedbackDir = Files.createTempDirectory("route-vector-feedback");
        properties.getFeedback().setBaseDir(feedbackDir.toString());
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(properties);
        String bundleId = context.bundleIds().getFirst();
        String singleStopId = context.bundle(bundleId).seedOrderId();
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                "proposal-single-stop",
                bundleId,
                singleStopId,
                context.availableDrivers().getFirst().driverId(),
                RouteProposalSource.HEURISTIC_FAST,
                List.of(singleStopId),
                2.0,
                6.0,
                0.9,
                true,
                List.of(),
                List.of());
        RouteVectorEnricher enricher = new RouteVectorEnricher(
                new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()),
                new DecisionStageLogger(properties));

        RouteProposal enriched = enricher.enrich("trace-single-stop", proposal, context);

        assertTrue(enriched.geometryAvailable());
        assertTrue(enriched.legs().stream().allMatch(leg -> !leg.polyline().isEmpty()));
        assertTrue(Files.isRegularFile(feedbackDir.resolve("decision-stage").resolve("route_leg_vector_trace").resolve("trace-single-stop-proposal-single-stop.json")));
        assertTrue(Files.isRegularFile(feedbackDir.resolve("decision-stage").resolve("route_vector_summary_trace").resolve("trace-single-stop-proposal-single-stop.json")));
    }

    private int firstTransitionIndexContaining(List<String> transitions, String stopId) {
        for (int index = 0; index < transitions.size(); index++) {
            if (transitions.get(index).contains(stopId)) {
                return index;
            }
        }
        return -1;
    }}
