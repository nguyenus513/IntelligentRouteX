package com.routechain.v2.routing;

import java.util.ArrayList;
import java.util.List;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class BudgetedRoutingProvider implements RoutingProvider {
    private final RoutingProvider primary;
    private final RoutingProvider fallback;
    private final int maxPrimaryRoutes;
    private final long windowNanos;
    private final AtomicInteger primaryRouteCount = new AtomicInteger();
    private final AtomicLong windowStartedAtNanos = new AtomicLong(System.nanoTime());

    public BudgetedRoutingProvider(RoutingProvider primary, RoutingProvider fallback, int maxPrimaryRoutes) {
        this(primary, fallback, maxPrimaryRoutes, Duration.ofSeconds(30));
    }

    public BudgetedRoutingProvider(RoutingProvider primary, RoutingProvider fallback, int maxPrimaryRoutes, Duration windowDuration) {
        this.primary = primary;
        this.fallback = fallback;
        this.maxPrimaryRoutes = Math.max(0, maxPrimaryRoutes);
        Duration safeWindow = windowDuration == null || windowDuration.isNegative() || windowDuration.isZero()
                ? Duration.ofSeconds(30)
                : windowDuration;
        this.windowNanos = safeWindow.toNanos();
    }

    @Override
    public String providerId() {
        return primary.providerId() + "-budgeted";
    }

    @Override
    public boolean ready() {
        return primary.ready() || fallback.ready();
    }

    @Override
    public RoutingSnapResult snap(RouteStop stop) {
        if (!primary.ready()) {
            return fallback.snap(stop);
        }
        return primary.snap(stop);
    }

    @Override
    public RoutingRouteResult route(BestPathRequest request) {
        if (!"road-refinement".equals(request.routingIntent())) {
            return fallbackWithReason(request, "routing-primary-shortlist-only");
        }
        if (!primary.ready()) {
            return fallbackWithReason(request, "routing-primary-not-ready");
        }
        resetWindowIfExpired();
        int current = primaryRouteCount.incrementAndGet();
        if (current > maxPrimaryRoutes) {
            return fallbackWithReason(request, "routing-primary-budget-exhausted");
        }
        return primary.route(request);
    }

    private void resetWindowIfExpired() {
        long now = System.nanoTime();
        long startedAt = windowStartedAtNanos.get();
        if (now - startedAt < windowNanos) {
            return;
        }
        if (windowStartedAtNanos.compareAndSet(startedAt, now)) {
            primaryRouteCount.set(0);
        }
    }

    private RoutingRouteResult fallbackWithReason(BestPathRequest request, String reason) {
        RoutingRouteResult result = fallback.route(request);
        List<String> reasons = new ArrayList<>(result.degradeReasons());
        reasons.add(reason);
        LegRouteVector leg = result.legVector().withRoutingGeometry(
                result.legVector().routingProvider(),
                result.legVector().geometryKind(),
                result.polyline(),
                reason);
        return new RoutingRouteResult(result.schemaVersion(), result.provider(), result.geometryKind(), leg, result.corridorPreferenceScore(), result.polyline(), reasons);
    }
}
