package com.routechain.v2.routing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public final class DurationMatrixCache {
    private final Clock clock;
    private final Duration ttl;
    private final Map<String, Entry> entries = new HashMap<>();
    private int hitCount;
    private int missCount;

    public DurationMatrixCache() {
        this(Clock.systemUTC(), Duration.ofMinutes(5));
    }

    DurationMatrixCache(Clock clock, Duration ttl) {
        this.clock = clock;
        this.ttl = ttl == null ? Duration.ofMinutes(5) : ttl;
    }

    public DurationMatrix get(String provider, List<RouteStop> sources, List<RouteStop> destinations) {
        String key = key(provider, sources, destinations, timeBucket(clock.instant()));
        Entry entry = entries.get(key);
        if (entry == null || clock.instant().isAfter(entry.expiresAt())) {
            missCount++;
            entries.remove(key);
            return null;
        }
        hitCount++;
        return entry.matrix();
    }

    public void put(String provider, List<RouteStop> sources, List<RouteStop> destinations, DurationMatrix matrix) {
        entries.put(key(provider, sources, destinations, timeBucket(clock.instant())), new Entry(matrix, clock.instant().plus(ttl)));
    }

    public int hitCount() {
        return hitCount;
    }

    public int missCount() {
        return missCount;
    }

    public int requestCount() {
        return hitCount + missCount;
    }

    public double hitRate() {
        int requests = requestCount();
        return requests == 0 ? 0.0 : hitCount / (double) requests;
    }

    public int size() {
        return entries.size();
    }

    private long timeBucket(Instant instant) {
        long bucketSeconds = Math.max(1L, ttl.toSeconds());
        return instant.getEpochSecond() / bucketSeconds;
    }

    private String key(String provider, List<RouteStop> sources, List<RouteStop> destinations, long bucket) {
        return provider + "|" + bucket + "|s=" + coordinateSignature(sources) + "|d=" + coordinateSignature(destinations);
    }

    private String coordinateSignature(List<RouteStop> stops) {
        return stops.stream()
                .map(stop -> "%.6f,%.6f".formatted(stop.latitude(), stop.longitude()))
                .sorted()
                .collect(Collectors.joining(";"));
    }

    private record Entry(DurationMatrix matrix, Instant expiresAt) {
    }
}
