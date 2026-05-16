package com.routechain.v2.live;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.unified.DispatchMode;
import com.routechain.v2.unified.DispatchPolicy;
import com.routechain.v2.unified.DispatchStrategy;
import com.routechain.v2.unified.UnifiedDispatchCore;
import com.routechain.v2.unified.UnifiedDispatchRequest;
import com.routechain.v2.unified.UnifiedDispatchResult;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Service
public final class RollingDispatchCycleScheduler {
    private static final Region LIVE_REGION = new Region("live-hcm", "Live HCM");

    private final LiveOrderIntakeBuffer orderBuffer;
    private final DriverTelemetryStore telemetryStore;
    private final LiveCycleStore cycleStore;
    private final UnifiedDispatchCore unifiedDispatchCore;
    private volatile boolean running;
    private volatile LiveCyclePolicy policy = LiveCyclePolicy.defaults();

    public RollingDispatchCycleScheduler(LiveOrderIntakeBuffer orderBuffer,
                                         DriverTelemetryStore telemetryStore,
                                         LiveCycleStore cycleStore,
                                         UnifiedDispatchCore unifiedDispatchCore) {
        this.orderBuffer = orderBuffer;
        this.telemetryStore = telemetryStore;
        this.cycleStore = cycleStore;
        this.unifiedDispatchCore = unifiedDispatchCore;
    }

    public void start(LiveCyclePolicy nextPolicy) {
        this.policy = nextPolicy == null ? LiveCyclePolicy.defaults() : nextPolicy;
        this.running = true;
    }

    public void stop() {
        this.running = false;
    }

    public boolean running() {
        return running;
    }

    public LiveCyclePolicy policy() {
        return policy;
    }

    public LiveCycleResult runNow() {
        Instant started = Instant.now();
        orderBuffer.expireOld(started, policy.maxOrderWaitSeconds());
        List<LiveOrderState> eligible = orderBuffer.eligible(started, policy.mustDispatchAfterSeconds());
        List<DriverTelemetrySnapshot> drivers = telemetryStore.all();
        String cycleId = "LCY-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        List<String> inputOrderIds = eligible.stream().map(state -> state.order().orderId()).toList();
        orderBuffer.markInCycle(inputOrderIds, started);
        UnifiedDispatchResult unified = unifiedDispatchCore.dispatch(new UnifiedDispatchRequest(
                "unified-dispatch-request/v1",
                cycleId,
                DispatchMode.LIVE_ROLLING,
                DispatchStrategy.MULTI_PASS_COVERAGE,
                eligible.stream().map(state -> toOrder(state.order(), started)).toList(),
                drivers.stream().map(RollingDispatchCycleScheduler::toDriver).toList(),
                List.of(LIVE_REGION),
                WeatherProfile.CLEAR,
                DispatchPolicy.dashboardDefault(eligible.size(), drivers.size()),
                started));
        Set<String> assigned = new LinkedHashSet<>();
        for (DispatchAssignment assignment : unified.dispatchResult().assignments()) {
            assigned.addAll(assignment.orderIds());
        }
        List<String> deferred = inputOrderIds.stream().filter(orderId -> !assigned.contains(orderId)).toList();
        Instant completed = Instant.now();
        orderBuffer.markAssigned(List.copyOf(assigned), completed);
        orderBuffer.markDeferred(deferred, completed, "not-selected-in-cycle");
        orderBuffer.expireOld(completed, policy.maxOrderWaitSeconds());
        List<String> expired = orderBuffer.all().stream()
                .filter(state -> state.status() == LiveOrderStatus.EXPIRED)
                .map(state -> state.order().orderId())
                .toList();
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("coreEntrypoint", "UnifiedDispatchCore.dispatch");
        diagnostics.put("dispatchMode", DispatchMode.LIVE_ROLLING.name());
        diagnostics.put("running", running);
        diagnostics.put("inputOrderIds", inputOrderIds);
        diagnostics.put("assignedCount", assigned.size());
        diagnostics.put("deferredCount", deferred.size());
        diagnostics.put("expiredCount", expired.size());
        diagnostics.put("policy", policy);
        LiveCycleResult result = new LiveCycleResult(cycleId, started, completed, eligible.size(), drivers.size(), List.copyOf(assigned), deferred, expired, unified, diagnostics);
        cycleStore.put(result);
        return result;
    }

    public Map<String, Object> state() {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("running", running);
        state.put("policy", policy);
        state.put("orders", orderBuffer.all());
        state.put("drivers", telemetryStore.all());
        state.put("cycles", cycleStore.all().stream().map(cycle -> Map.of(
                "cycleId", cycle.cycleId(),
                "inputOrderCount", cycle.inputOrderCount(),
                "driverCount", cycle.driverCount(),
                "assignedCount", cycle.assignedOrderIds().size(),
                "deferredCount", cycle.deferredOrderIds().size(),
                "expiredCount", cycle.expiredOrderIds().size(),
                "completedAt", cycle.completedAt().toString())).toList());
        return state;
    }

    private static Order toOrder(LiveOrderSnapshot snapshot, Instant decisionTime) {
        return new Order(snapshot.orderId(), new GeoPoint(snapshot.pickupLat(), snapshot.pickupLng()), new GeoPoint(snapshot.dropoffLat(), snapshot.dropoffLng()), decisionTime, decisionTime, snapshot.deadlineMinutes(), snapshot.priority() >= 2);
    }

    private static Driver toDriver(DriverTelemetrySnapshot snapshot) {
        return new Driver(snapshot.driverId(), new GeoPoint(snapshot.lat(), snapshot.lng()));
    }
}
