package com.routechain.v2.active;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
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

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveRouteInsertionGeneratorTest {

    private final ActiveRouteInsertionGenerator generator = new ActiveRouteInsertionGenerator();

    @Test
    void generatesFeasibleActiveRouteInsertionForNearbyReadyOrder() {
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        Order existing = order("order-existing", 10.7750, 106.7000, 10.7800, 106.7100, decisionTime.minusSeconds(60), 30);
        Order incoming = order("order-incoming", 10.7755, 106.7005, 10.7810, 106.7110, decisionTime.minusSeconds(30), 30);
        ActiveRouteState route = route(existing, decisionTime, 18.0, 0.90);

        List<ActiveRouteInsertionCandidate> candidates = generator.generate(
                List.of(route),
                List.of(existing, incoming),
                decisionTime,
                etaLegCache(decisionTime));

        assertFalse(candidates.isEmpty());
        ActiveRouteInsertionCandidate best = candidates.getFirst();
        assertEquals("order-incoming", best.insertedOrderId());
        assertTrue(best.feasible());
        assertTrue(best.score() > 0.0);
        assertTrue(best.newStopOrder().containsAll(List.of("order-existing", "order-incoming")));
        assertTrue(best.reasons().contains("active-route-regret-insertion"));
        assertTrue(best.reasons().contains("active-route-pickup-dropoff-precedence"));
    }

    @Test
    void rejectsInsertionWhenOrderWouldBePickedBeforeReady() {
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        Order existing = order("order-existing", 10.7750, 106.7000, 10.7800, 106.7100, decisionTime.minusSeconds(60), 30);
        Order notReady = order("order-not-ready", 10.7755, 106.7005, 10.7810, 106.7110, decisionTime.plusSeconds(900), 30);
        ActiveRouteState route = route(existing, decisionTime, 18.0, 0.90);

        List<ActiveRouteInsertionCandidate> candidates = generator.generate(
                List.of(route),
                List.of(existing, notReady),
                decisionTime,
                etaLegCache(decisionTime));

        assertTrue(candidates.stream()
                .filter(candidate -> candidate.insertedOrderId().equals("order-not-ready"))
                .allMatch(candidate -> !candidate.feasible()
                        && candidate.degradeReasons().contains("active-insertion-pickup-before-ready")));
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

    private com.routechain.v2.cluster.EtaLegCache etaLegCache(Instant decisionTime) {
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
                .create("trace-active-insertion", decisionTime, WeatherProfile.CLEAR);
    }
}
