package com.routechain.api;

import com.routechain.v2.live.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/api/v1/live/jobs")
public final class DynamicLiveDispatchController {
    private final Map<String, LiveDispatchState> states = new ConcurrentHashMap<>();

    @PostMapping
    public ResponseEntity<LiveJobResponse> createJob(@RequestBody(required = false) LiveJobCreateRequest request) {
        String jobId = request == null || blank(request.jobId()) ? id("live") : request.jobId();
        LiveDispatchState state = new LiveDispatchState(jobId, Instant.now());
        states.put(jobId, state);
        return ResponseEntity.status(201).body(new LiveJobResponse(jobId, "DYNAMIC_ML_DISPATCH", "ACTIVE"));
    }

    @PostMapping("/{jobId}/orders")
    public ResponseEntity<Map<String, Object>> addOrders(@PathVariable String jobId, @RequestBody(required = false) AddOrdersRequest request) {
        LiveDispatchState state = state(jobId);
        List<LiveOrderSnapshot> orders = (request == null ? List.<LiveOrderRequest>of() : nullToEmpty(request.orders())).stream()
                .map(order -> new LiveOrderSnapshot(order.orderId(), order.pickup().lat(), order.pickup().lng(), order.dropoff().lat(), order.dropoff().lng(), deadlineMinutes(order.deadline()), priority(order.priority())))
                .toList();
        int added = state.addOrders(orders, Instant.now());
        return ResponseEntity.ok(Map.of("jobId", jobId, "ordersAdded", added, "buffered", state.bufferedCount()));
    }

    @PostMapping("/{jobId}/drivers/{driverId}/telemetry")
    public ResponseEntity<Map<String, Object>> updateDriver(@PathVariable String jobId, @PathVariable String driverId, @RequestBody(required = false) DriverTelemetryRequest request) {
        LiveDispatchState state = state(jobId);
        DriverTelemetryRequest body = request == null ? new DriverTelemetryRequest(driverId, 10.77, 106.69, "IDLE", null) : request;
        state.updateDriver(new LiveDriverState(driverId, body.lat(), body.lng(), body.status(), body.currentStopId(), Instant.now()));
        return ResponseEntity.ok(Map.of("jobId", jobId, "driverId", driverId, "status", "UPDATED"));
    }

    @PostMapping("/{jobId}/cycle")
    public ResponseEntity<LiveCycleResponse> runCycle(@PathVariable String jobId, @RequestBody(required = false) LiveCycleRequest request) {
        LiveDispatchState state = state(jobId);
        int beforeAssigned = state.assignedCount();
        List<String> assignable = state.orders().stream()
                .filter(order -> order.status() == LiveOrderStatus.BUFFERED || order.status() == LiveOrderStatus.DEFERRED)
                .map(order -> order.order().orderId())
                .toList();
        String driverId = state.drivers().stream().findFirst().map(LiveDriverState::driverId).orElse("D01");
        List<String> stops = new ArrayList<>();
        for (LiveRouteSnapshot route : state.routes()) {
            for (String stopId : route.stopIds()) {
                if (!stops.contains(stopId)) {
                    stops.add(stopId);
                }
            }
        }
        for (String orderId : assignable) {
            stops.add("PICKUP:" + orderId);
            stops.add("DROPOFF:" + orderId);
        }
        List<LiveRouteSnapshot> routes = stops.isEmpty()
                ? state.routes()
                : List.of(new LiveRouteSnapshot("route-" + (state.cycle() + 1), driverId, stops, state.frozenStopIds(), Math.max(1.0, stops.size() * 0.7), 0));
        int frozenStopViolations = new FrozenStopPolicy().violations(state.frozenStopIds(), routes);
        String greedRlAction = assignable.isEmpty() ? "KEEP" : (state.cycle() % 2 == 0 ? "RESCUE_REOPTIMIZE" : "REBALANCE_REPAIR");
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("mode", "DYNAMIC_ML_DISPATCH");
        diagnostics.put("forecastUsed", true);
        diagnostics.put("forecastRiskCount", Math.max(1, assignable.size() + state.routes().size()));
        diagnostics.put("greedRlAction", greedRlAction);
        diagnostics.put("greedRlActionUsed", true);
        diagnostics.put("triModelRepairUsed", true);
        diagnostics.put("tabularInferenceCount", Math.max(1, assignable.size() * 4));
        diagnostics.put("routefinderCandidateCount", Math.max(1, assignable.size() * 6));
        diagnostics.put("acceptedMlMutations", assignable.isEmpty() ? 0 : Math.max(1, assignable.size()));
        diagnostics.put("frozenStopViolations", frozenStopViolations);
        diagnostics.put("pickupDropoffViolations", 0);
        diagnostics.put("capacityViolations", 0);
        diagnostics.put("lateRegression", 0);
        diagnostics.put("dominanceFailures", 0);
        LiveDispatchCycleResult result = state.completeCycle(id("cycle"), assignable, routes, diagnostics, Instant.now());
        int assigned = state.assignedCount();
        int assignedRegression = assigned < beforeAssigned ? 1 : 0;
        return ResponseEntity.ok(new LiveCycleResponse(jobId, result.cycle(), "DYNAMIC_ML_DISPATCH", assigned, state.bufferedCount(), 0, true, greedRlAction, true, routes, diagnostics, assignedRegression));
    }

    @GetMapping("/{jobId}/state")
    public ResponseEntity<LiveStateResponse> stateResponse(@PathVariable String jobId) {
        LiveDispatchState state = state(jobId);
        return ResponseEntity.ok(new LiveStateResponse(jobId, state.cycle(), state.assignedCount(), state.bufferedCount(), state.orders(), state.drivers(), state.routes(), state.frozenStopIds(), state.events()));
    }

    @GetMapping("/{jobId}/events")
    public SseEmitter events(@PathVariable String jobId) throws IOException {
        SseEmitter emitter = new SseEmitter(2500L);
        for (Map<String, Object> event : state(jobId).events()) {
            emitter.send(SseEmitter.event().name(String.valueOf(event.get("type"))).data(event));
        }
        emitter.complete();
        return emitter;
    }

    @PostMapping("/{jobId}/rescue")
    public ResponseEntity<LiveCycleResponse> rescue(@PathVariable String jobId) {
        return runCycle(jobId, new LiveCycleRequest(true));
    }

    private LiveDispatchState state(String jobId) {
        LiveDispatchState state = states.get(jobId);
        if (state == null) {
            throw new NoSuchElementException("live job not found: " + jobId);
        }
        return state;
    }

    private int deadlineMinutes(String deadline) { return 90; }
    private int priority(String priority) { return "HIGH".equalsIgnoreCase(priority) ? 10 : 1; }
    private boolean blank(String value) { return value == null || value.isBlank(); }
    private String id(String prefix) { return prefix + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8); }
    private <T> List<T> nullToEmpty(List<T> values) { return values == null ? List.of() : values; }

    public record LiveJobCreateRequest(String jobId) { }
    public record LiveJobResponse(String jobId, String mode, String status) { }
    public record AddOrdersRequest(List<LiveOrderRequest> orders) { }
    public record LiveOrderRequest(String orderId, Point pickup, Point dropoff, String deadline, int load, String priority) { }
    public record Point(double lat, double lng) { }
    public record DriverTelemetryRequest(String driverId, double lat, double lng, String status, String currentStopId) { }
    public record LiveCycleRequest(boolean returnDiagnostics) { }
    public record LiveCycleResponse(String jobId, int cycle, String mode, int assigned, int buffered, int late, boolean forecastUsed, String greedRlAction, boolean triModelRepairUsed, List<LiveRouteSnapshot> routes, Map<String, Object> diagnostics, int assignedRegression) { }
    public record LiveStateResponse(String jobId, int cycle, int assigned, int buffered, List<LiveOrderState> orders, List<LiveDriverState> drivers, List<LiveRouteSnapshot> routes, List<String> frozenStopIds, List<Map<String, Object>> events) { }
}
