package com.routechain.runtime.metrics;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

public final class RuntimeMetricsRegistry {
    private final Map<String, AtomicLong> counters = new ConcurrentHashMap<>();
    public void increment(String name) { counters.computeIfAbsent(name, ignored -> new AtomicLong()).incrementAndGet(); }
    public long value(String name) { return counters.getOrDefault(name, new AtomicLong()).get(); }
    public Map<String, Long> snapshot() { return counters.entrySet().stream().collect(java.util.stream.Collectors.toMap(Map.Entry::getKey, e -> e.getValue().get())); }
}
