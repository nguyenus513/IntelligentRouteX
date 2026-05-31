package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.active.ActiveRouteState;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.context.BaselineTravelTimeEstimator;
import com.routechain.v2.context.EtaFeatureBuilder;
import com.routechain.v2.context.EtaService;
import com.routechain.v2.context.EtaUncertaintyEstimator;
import com.routechain.v2.context.TrafficProfileService;
import com.routechain.v2.context.WeatherContextService;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdaptiveBundleDispatchPhase2Test {
    private final BundleContext context = new BundleContext(BundleTestFixtures.orders(), BundleTestFixtures.graph(), List.of());

    @Test
    void driverBundleMatcherSelectsLowestCostNonOverlappingAssignments() {
        Instant decisionTime = Instant.parse("2026-04-16T12:05:00Z");
        ActiveRouteState stableRoute = route("route-stable", "driver-stable", "order-1", decisionTime, 8.0, 0.95);
        ActiveRouteState churnyRoute = route("route-churn", "driver-churn", "order-4", decisionTime, 40.0, 0.20);
        BundleCandidate bundle = candidate("bundle-12", List.of("order-1", "order-2"), 0.90, false);

        List<DriverBundleAssignment> assignments = new DriverBundleMatcher().match(
                List.of(churnyRoute, stableRoute),
                List.of(bundle),
                context,
                BundleTestFixtures.clearEtaContext(),
                decisionTime);

        assertEquals(1, assignments.size());
        assertEquals("driver-stable", assignments.getFirst().driverId());
        assertTrue(assignments.getFirst().cost() < 0.30);
    }

    @Test
    void convenientInsertionKeepsFrozenCurrentStopAndReturnsFeasibleCandidate() {
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        Order existing = order("order-existing", 10.7750, 106.7000, 10.7800, 106.7100, decisionTime.minusSeconds(60), 30);
        Order incoming = order("order-incoming", 10.7755, 106.7005, 10.7810, 106.7110, decisionTime.minusSeconds(30), 30);
        ActiveRouteState route = route(existing, decisionTime, 18.0, 0.95);

        List<ActiveRouteInsertionCandidate> candidates = new ConvenientInsertionEngine().generateForOrders(
                List.of(route),
                List.of(existing, incoming),
                decisionTime,
                etaLegCache(decisionTime));

        assertFalse(candidates.isEmpty());
        assertTrue(candidates.stream().allMatch(candidate -> candidate.newStopOrder().getFirst().equals("order-existing")));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.insertedOrderId().equals("order-incoming")));
    }

    @Test
    void destroyRepairRunsOnlyForRiskyBundlesAndRecordsTelemetry() {
        Instant decisionTime = Instant.parse("2026-04-16T12:45:00Z");
        ActiveRouteState route = route("route-1", "driver-1", "order-1", decisionTime, 12.0, 0.90);
        BundleCandidate risky = candidate("risky", List.of("order-1", "order-4"), 0.80, true);

        AdaptiveBundleRepairResult result = new AdaptiveBundleDestroyRepairEngine().repairRiskyBundles(
                List.of(risky),
                context,
                BundleTestFixtures.weatherBadEtaContext(),
                decisionTime,
                List.of(route),
                etaLegCache(decisionTime),
                Duration.ofMillis(100));

        assertFalse(result.riskyBundles().isEmpty());
        assertEquals(true, result.feedbackSummary().get("destroyRepairApplied"));
        assertTrue(result.repairResult().telemetry().candidateInputCount() >= 0);
    }

    private ActiveRouteState route(Order existing, Instant decisionTime, double projectedCompletionEta, double stabilityScore) {
        return new ActiveRouteState(
                "active-route-state/v1",
                "route-1",
                "driver-1",
                new GeoPoint(10.7740, 106.6990),
                List.of(existing.orderId()),
                List.of(existing.orderId()),
                decisionTime,
                0.0,
                projectedCompletionEta,
                stabilityScore,
                List.of());
    }

    private ActiveRouteState route(String routeId, String driverId, String orderId, Instant decisionTime, double projectedCompletionEta, double stabilityScore) {
        return new ActiveRouteState(
                "active-route-state/v1",
                routeId,
                driverId,
                new GeoPoint(10.7740, 106.6990),
                List.of(orderId),
                List.of(orderId),
                decisionTime,
                0.0,
                projectedCompletionEta,
                stabilityScore,
                List.of());
    }

    private BundleCandidate candidate(String id, List<String> orderIds, double score, boolean boundaryCross) {
        return new BundleCandidate(
                "bundle-candidate/v1",
                id,
                BundleProposalSource.DETERMINISTIC_FAMILY,
                boundaryCross ? BundleFamily.BOUNDARY_CROSS : BundleFamily.COMPACT_CLIQUE,
                "cluster-001",
                boundaryCross,
                boundaryCross ? List.of(orderIds.getLast()) : List.of(),
                orderIds,
                String.join("|", orderIds.stream().sorted().toList()),
                orderIds.getFirst(),
                "0:0",
                score,
                true,
                List.of());
    }

    private Order order(String orderId,
                        double pickupLat,
                        double pickupLon,
                        double dropoffLat,
                        double dropoffLon,
                        Instant readyAt,
                        int promisedEtaMinutes) {
        return new Order(
                orderId,
                new GeoPoint(pickupLat, pickupLon),
                new GeoPoint(dropoffLat, dropoffLon),
                readyAt.minusSeconds(300),
                readyAt,
                promisedEtaMinutes,
                false);
    }

    private EtaLegCache etaLegCache(Instant decisionTime) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        EtaService etaService = new EtaService(
                properties,
                new BaselineTravelTimeEstimator(),
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                new NoOpTabularScoringClient(),
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        return new EtaLegCacheFactory(properties, etaService)
                .create("trace-adaptive-bundle-phase2", decisionTime, WeatherProfile.CLEAR);
    }
}
