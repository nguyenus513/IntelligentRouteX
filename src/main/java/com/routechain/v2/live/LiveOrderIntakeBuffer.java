package com.routechain.v2.live;

import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public final class LiveOrderIntakeBuffer {
    private final Map<String, LiveOrderState> orders = new LinkedHashMap<>();

    public synchronized List<LiveOrderState> add(List<LiveOrderSnapshot> snapshots, Instant now) {
        List<LiveOrderState> added = new ArrayList<>();
        for (LiveOrderSnapshot snapshot : snapshots == null ? List.<LiveOrderSnapshot>of() : snapshots) {
            if (snapshot == null || snapshot.orderId() == null || snapshot.orderId().isBlank()) {
                continue;
            }
            LiveOrderState state = new LiveOrderState(snapshot, LiveOrderStatus.BUFFERED, now, now, 0, "buffered");
            orders.put(snapshot.orderId(), state);
            added.add(state);
        }
        return added;
    }

    public synchronized List<LiveOrderState> eligible(Instant now, int mustDispatchAfterSeconds) {
        return orders.values().stream()
                .filter(state -> state.status() == LiveOrderStatus.BUFFERED || state.status() == LiveOrderStatus.DEFERRED)
                .filter(state -> state.deferCount() == 0 || Duration.between(state.createdAt(), now).toSeconds() >= mustDispatchAfterSeconds)
                .toList();
    }

    public synchronized void markInCycle(List<String> orderIds, Instant now) {
        orderIds.forEach(orderId -> update(orderId, LiveOrderStatus.IN_CYCLE, now, null));
    }

    public synchronized void markAssigned(List<String> orderIds, Instant now) {
        orderIds.forEach(orderId -> update(orderId, LiveOrderStatus.ASSIGNED, now, "assigned-by-unified-core"));
    }

    public synchronized void markDeferred(List<String> orderIds, Instant now, String reason) {
        orderIds.forEach(orderId -> {
            LiveOrderState current = orders.get(orderId);
            if (current != null) {
                orders.put(orderId, new LiveOrderState(current.order(), LiveOrderStatus.DEFERRED, current.createdAt(), now, current.deferCount() + 1, reason));
            }
        });
    }

    public synchronized void expireOld(Instant now, int maxOrderWaitSeconds) {
        orders.replaceAll((orderId, state) -> {
            if ((state.status() == LiveOrderStatus.BUFFERED || state.status() == LiveOrderStatus.DEFERRED)
                    && Duration.between(state.createdAt(), now).toSeconds() > maxOrderWaitSeconds) {
                return new LiveOrderState(state.order(), LiveOrderStatus.EXPIRED, state.createdAt(), now, state.deferCount(), "max-wait-exceeded");
            }
            return state;
        });
    }

    public synchronized List<LiveOrderState> all() {
        return List.copyOf(orders.values());
    }

    public synchronized void clear() {
        orders.clear();
    }

    private void update(String orderId, LiveOrderStatus status, Instant now, String reason) {
        LiveOrderState current = orders.get(orderId);
        if (current != null) {
            orders.put(orderId, new LiveOrderState(current.order(), status, current.createdAt(), now, current.deferCount(), reason == null ? current.reason() : reason));
        }
    }
}
