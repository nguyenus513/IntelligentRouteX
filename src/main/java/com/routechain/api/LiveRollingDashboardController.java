package com.routechain.api;

import com.routechain.v2.live.DriverTelemetrySnapshot;
import com.routechain.v2.live.DriverTelemetryStore;
import com.routechain.v2.live.LiveCyclePolicy;
import com.routechain.v2.live.LiveCycleResult;
import com.routechain.v2.live.LiveCycleStore;
import com.routechain.v2.live.LiveOrderIntakeBuffer;
import com.routechain.v2.live.LiveOrderSnapshot;
import com.routechain.v2.live.RollingDispatchCycleScheduler;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/dashboard/live")
public final class LiveRollingDashboardController {
    private final LiveOrderIntakeBuffer orderBuffer;
    private final DriverTelemetryStore telemetryStore;
    private final RollingDispatchCycleScheduler scheduler;
    private final LiveCycleStore cycleStore;

    public LiveRollingDashboardController(LiveOrderIntakeBuffer orderBuffer,
                                          DriverTelemetryStore telemetryStore,
                                          RollingDispatchCycleScheduler scheduler,
                                          LiveCycleStore cycleStore) {
        this.orderBuffer = orderBuffer;
        this.telemetryStore = telemetryStore;
        this.scheduler = scheduler;
        this.cycleStore = cycleStore;
    }

    @PostMapping("/start")
    public Map<String, Object> start(@RequestBody(required = false) LiveCyclePolicy policy) {
        scheduler.start(policy);
        return Map.of("status", "started", "running", scheduler.running(), "policy", scheduler.policy());
    }

    @PostMapping("/stop")
    public Map<String, Object> stop() {
        scheduler.stop();
        return Map.of("status", "stopped", "running", scheduler.running());
    }

    @GetMapping("/state")
    public Map<String, Object> state() {
        return scheduler.state();
    }

    @PostMapping("/orders")
    public Map<String, Object> orders(@RequestBody LiveOrderBatch request) {
        List<LiveOrderSnapshot> added = orderBuffer.add(request == null ? List.of() : request.orders(), Instant.now()).stream()
                .map(state -> state.order())
                .toList();
        return Map.of("accepted", added.size(), "orders", added);
    }

    @PostMapping("/drivers/location")
    public Map<String, Object> drivers(@RequestBody LiveDriverBatch request) {
        List<DriverTelemetrySnapshot> drivers = telemetryStore.update(request == null ? List.of() : request.drivers(), Instant.now());
        return Map.of("driverCount", drivers.size(), "drivers", drivers);
    }

    @PostMapping("/cycles/run-now")
    public LiveCycleResult runNow() {
        return scheduler.runNow();
    }

    @GetMapping("/cycles/{cycleId}/result")
    public ResponseEntity<LiveCycleResult> cycle(@PathVariable String cycleId) {
        return cycleStore.get(cycleId).map(ResponseEntity::ok).orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record LiveOrderBatch(List<LiveOrderSnapshot> orders) {
    }

    public record LiveDriverBatch(List<DriverTelemetrySnapshot> drivers) {
    }
}
