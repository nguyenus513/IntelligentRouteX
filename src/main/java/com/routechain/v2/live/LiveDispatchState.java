package com.routechain.v2.live;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class LiveDispatchState {
    private final String jobId;
    private final Instant createdAt;
    private final Map<String, LiveOrderState> orders = new LinkedHashMap<>();
    private final Map<String, LiveDriverState> drivers = new LinkedHashMap<>();
    private final List<LiveRouteSnapshot> routes = new ArrayList<>();
    private final List<String> frozenStopIds = new ArrayList<>();
    private final List<Map<String, Object>> events = new ArrayList<>();
    private int cycle;

    public LiveDispatchState(String jobId, Instant createdAt) {
        this.jobId = jobId;
        this.createdAt = createdAt;
    }

    public synchronized int addOrders(List<LiveOrderSnapshot> snapshots, Instant now) {
        int count = 0;
        for (LiveOrderSnapshot snapshot : snapshots == null ? List.<LiveOrderSnapshot>of() : snapshots) {
            if (snapshot == null || snapshot.orderId() == null || snapshot.orderId().isBlank()) {
                continue;
            }
            orders.put(snapshot.orderId(), new LiveOrderState(snapshot, LiveOrderStatus.BUFFERED, now, now, 0, "live-intake"));
            events.add(event("ORDER_RECEIVED", snapshot.orderId(), now));
            events.add(event("ORDER_BUFFERED", snapshot.orderId(), now));
            count++;
        }
        return count;
    }

    public synchronized void updateDriver(LiveDriverState driver) {
        drivers.put(driver.driverId(), driver);
        events.add(event("DRIVER_TELEMETRY_UPDATED", driver.driverId(), driver.updatedAt()));
    }

    public synchronized LiveDispatchCycleResult completeCycle(String cycleId,
                                                             List<String> assignedOrderIds,
                                                             List<LiveRouteSnapshot> nextRoutes,
                                                             Map<String, Object> diagnostics,
                                                             Instant now) {
        cycle++;
        for (String orderId : assignedOrderIds) {
            LiveOrderState current = orders.get(orderId);
            if (current != null) {
                orders.put(orderId, new LiveOrderState(current.order(), LiveOrderStatus.ASSIGNED, current.createdAt(), now, current.deferCount(), "dynamic-ml-dispatch"));
                events.add(event("ORDER_ASSIGNED", orderId, now));
            }
        }
        routes.clear();
        routes.addAll(nextRoutes == null ? List.of() : nextRoutes);
        frozenStopIds.clear();
        frozenStopIds.addAll(new FrozenStopPolicy().frozenStops(routes, List.copyOf(drivers.values())));
        events.add(event("FORECAST_RISK_UPDATED", cycleId, now));
        events.add(event("GREEDRL_ACTION_SELECTED", cycleId, now));
        events.add(event("ROUTE_REOPTIMIZED", cycleId, now));
        if (!frozenStopIds.isEmpty()) {
            events.add(event("STOP_FROZEN", String.join(",", frozenStopIds), now));
        }
        events.add(event("DISPATCH_COMPLETED", cycleId, now));
        return new LiveDispatchCycleResult(cycleId, cycle, assignedOrderIds.size(), bufferedCount(), List.copyOf(frozenStopIds), List.copyOf(routes), diagnostics, now);
    }

    public synchronized int bufferedCount() {
        return (int) orders.values().stream().filter(order -> order.status() == LiveOrderStatus.BUFFERED || order.status() == LiveOrderStatus.DEFERRED).count();
    }

    public synchronized int assignedCount() {
        return (int) orders.values().stream().filter(order -> order.status() == LiveOrderStatus.ASSIGNED).count();
    }

    public synchronized List<LiveOrderState> orders() { return List.copyOf(orders.values()); }
    public synchronized List<LiveDriverState> drivers() { return List.copyOf(drivers.values()); }
    public synchronized List<LiveRouteSnapshot> routes() { return List.copyOf(routes); }
    public synchronized List<String> frozenStopIds() { return List.copyOf(frozenStopIds); }
    public synchronized List<Map<String, Object>> events() { return List.copyOf(events); }
    public synchronized int cycle() { return cycle; }
    public String jobId() { return jobId; }
    public Instant createdAt() { return createdAt; }

    private Map<String, Object> event(String type, String subject, Instant now) {
        return Map.of("type", type, "subject", subject == null ? "" : subject, "createdAt", now.toString());
    }
}
