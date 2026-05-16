package com.routechain.v2.live;

import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public final class LiveCycleStore {
    private final Map<String, LiveCycleResult> cycles = new LinkedHashMap<>();

    public synchronized void put(LiveCycleResult result) {
        cycles.put(result.cycleId(), result);
    }

    public synchronized Optional<LiveCycleResult> get(String cycleId) {
        return Optional.ofNullable(cycles.get(cycleId));
    }

    public synchronized List<LiveCycleResult> all() {
        return List.copyOf(cycles.values());
    }

    public synchronized void clear() {
        cycles.clear();
    }
}
