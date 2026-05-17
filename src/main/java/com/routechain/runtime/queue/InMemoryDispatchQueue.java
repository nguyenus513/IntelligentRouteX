package com.routechain.runtime.queue;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryDispatchQueue implements DispatchQueue {
    private final Map<QueueLane, List<DispatchJobEnvelope>> lanes = new ConcurrentHashMap<>();
    public void enqueue(DispatchJobEnvelope envelope) { lanes.computeIfAbsent(envelope.lane(), ignored -> new ArrayList<>()).add(envelope); }
    public List<DispatchJobEnvelope> drainPriorityOrder() {
        List<DispatchJobEnvelope> all = new ArrayList<>();
        lanes.values().forEach(all::addAll);
        all.sort(Comparator.comparingInt(DispatchJobEnvelope::priority));
        return all;
    }
    public Map<QueueLane, Integer> depthByLane() {
        Map<QueueLane, Integer> depth = new ConcurrentHashMap<>();
        for (QueueLane lane : QueueLane.values()) depth.put(lane, lanes.getOrDefault(lane, List.of()).size());
        return depth;
    }
}
