package com.routechain.v2.routing;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public final class CachingRoutingProvider implements RoutingProvider {
    private final RoutingProvider delegate;
    private final Map<String, RoutingRouteResult> routeCache = new ConcurrentHashMap<>();
    private final AtomicInteger hits = new AtomicInteger();
    private final AtomicInteger misses = new AtomicInteger();

    public CachingRoutingProvider(RoutingProvider delegate) {
        this.delegate = delegate;
    }

    @Override
    public String providerId() {
        return delegate.providerId() + "-cached";
    }

    @Override
    public boolean ready() {
        return delegate.ready();
    }

    @Override
    public RoutingSnapResult snap(RouteStop stop) {
        return delegate.snap(stop);
    }

    @Override
    public RoutingRouteResult route(BestPathRequest request) {
        String key = routeKey(request);
        RoutingRouteResult cached = routeCache.get(key);
        if (cached != null) {
            hits.incrementAndGet();
            return cached;
        }
        misses.incrementAndGet();
        RoutingRouteResult result = delegate.route(request);
        if (result != null) {
            routeCache.put(key, result);
        }
        return result;
    }

    public Map<String, Object> stats() {
        int hitCount = hits.get();
        int missCount = misses.get();
        int requests = hitCount + missCount;
        return Map.of(
                "routeCacheRequests", requests,
                "routeCacheHits", hitCount,
                "routeCacheMisses", missCount,
                "routeCacheHitRate", requests == 0 ? 0.0 : hitCount / (double) requests,
                "routeCacheSize", routeCache.size());
    }

    private String routeKey(BestPathRequest request) {
        RouteStop from = request.fromStop();
        RouteStop to = request.toStop();
        return request.routingIntent() + "|" + request.trafficProfile() + "|" + request.weatherClass()
                + "|" + request.timeBucketMinutes()
                + "|" + coordinate(from) + "->" + coordinate(to);
    }

    private String coordinate(RouteStop stop) {
        return "%.6f,%.6f".formatted(stop.latitude(), stop.longitude());
    }
}
