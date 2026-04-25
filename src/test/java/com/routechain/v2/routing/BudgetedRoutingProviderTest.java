package com.routechain.v2.routing;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BudgetedRoutingProviderTest {

    @Test
    void onlyUsesPrimaryForRoadRefinementWithinWindowBudget() {
        CountingProvider primary = new CountingProvider("primary", "primary-road");
        CountingProvider fallback = new CountingProvider("fallback", "synthetic-straight-line");
        BudgetedRoutingProvider provider = new BudgetedRoutingProvider(primary, fallback, 1, Duration.ofSeconds(30));

        RoutingRouteResult poolResult = provider.route(request("pool-enrichment"));
        RoutingRouteResult firstRoadResult = provider.route(request("road-refinement"));
        RoutingRouteResult secondRoadResult = provider.route(request("road-refinement"));

        assertEquals("synthetic-straight-line", poolResult.geometryKind());
        assertEquals("primary-road", firstRoadResult.geometryKind());
        assertEquals("synthetic-straight-line", secondRoadResult.geometryKind());
        assertEquals(1, primary.routeCalls.get());
        assertEquals(2, fallback.routeCalls.get());
        assertEquals(List.of("fallback", "routing-primary-shortlist-only"), poolResult.degradeReasons());
        assertEquals(List.of("fallback", "routing-primary-budget-exhausted"), secondRoadResult.degradeReasons());
    }

    private BestPathRequest request(String intent) {
        return new BestPathRequest(
                new RouteStop("from", 10.0, 106.0, "from", "zone", 0.0),
                new RouteStop("to", 10.1, 106.1, "to", "zone", 0.0),
                "traffic",
                "clear",
                15,
                intent);
    }

    private static final class CountingProvider implements RoutingProvider {
        private final String providerId;
        private final String geometryKind;
        private final AtomicInteger routeCalls = new AtomicInteger();

        private CountingProvider(String providerId, String geometryKind) {
            this.providerId = providerId;
            this.geometryKind = geometryKind;
        }

        @Override
        public String providerId() {
            return providerId;
        }

        @Override
        public boolean ready() {
            return true;
        }

        @Override
        public RoutingSnapResult snap(RouteStop stop) {
            return new RoutingSnapResult("snap/v1", providerId, "identity", stop.latitude(), stop.longitude(), stop.latitude(), stop.longitude(), 0.0, 1.0, stop.stopId(), stop.stopId(), List.of());
        }

        @Override
        public RoutingRouteResult route(BestPathRequest request) {
            routeCalls.incrementAndGet();
            List<RoutePolylinePoint> polyline = List.of(
                    new RoutePolylinePoint(request.fromStop().latitude(), request.fromStop().longitude(), "from"),
                    new RoutePolylinePoint(request.toStop().latitude(), request.toStop().longitude(), "to"));
            LegRouteVector leg = new LegRouteVector(
                    "route-leg-vector/v1",
                    request.fromStop().stopId(),
                    request.toStop().stopId(),
                    0.1,
                    0.1,
                    45.0,
                    45.0,
                    45.0,
                    1000.0,
                    180.0,
                    5.5,
                    0.8,
                    0.2,
                    2,
                    1,
                    1,
                    0,
                    0.8,
                    0.1,
                    0.1,
                    200.0,
                    providerId,
                    geometryKind,
                    polyline,
                    "");
            return new RoutingRouteResult("route/v1", providerId, geometryKind, leg, 0.7, polyline, List.of(providerId));
        }
    }
}
