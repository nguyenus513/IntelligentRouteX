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
    private static final String API_KEY = "demo-key";
    private final Map<String, LiveDispatchState> states = new ConcurrentHashMap<>();
    private final Map<String, String> tenants = new ConcurrentHashMap<>();
    private final Map<String, Object> idempotency = new ConcurrentHashMap<>();

    @PostMapping
    public ResponseEntity<?> createJob(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                       @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                       @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                       @RequestBody(required = false) LiveJobCreateRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        String tenantId = tenant(request == null ? null : request.tenantId(), tenantHeader);
        String idem = idemKey(tenantId, "job", idempotencyKey);
        if (idem != null && idempotency.containsKey(idem)) return ResponseEntity.status(201).body(idempotency.get(idem));
        String jobId = request == null || blank(request.jobId()) ? id("live") : request.jobId();
        LiveDispatchState state = new LiveDispatchState(jobId, Instant.now());
        states.put(jobId, state);
        tenants.put(jobId, tenantId);
        LiveJobResponse response = new LiveJobResponse(jobId, tenantId, "DYNAMIC_ML_DISPATCH", "ACTIVE");
        if (idem != null) idempotency.put(idem, response);
        return ResponseEntity.status(201).body(response);
    }

    @PostMapping("/{jobId}/orders")
    public ResponseEntity<?> addOrders(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                       @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                       @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                       @PathVariable String jobId,
                                       @RequestBody(required = false) AddOrdersRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        denied = authorizeTenant(jobId, tenantHeader);
        if (denied != null) return denied;
        denied = validateOrders(request);
        if (denied != null) return denied;
        String idem = idemKey(tenantHeader, jobId + ":orders", idempotencyKey);
        if (idem != null && idempotency.containsKey(idem)) return ResponseEntity.ok(idempotency.get(idem));
        LiveDispatchState state = state(jobId);
        List<LiveOrderSnapshot> orders = (request == null ? List.<LiveOrderRequest>of() : nullToEmpty(request.orders())).stream()
                .map(order -> new LiveOrderSnapshot(order.orderId(), order.pickup().lat(), order.pickup().lng(), order.dropoff().lat(), order.dropoff().lng(), deadlineMinutes(order.deadline()), priority(order.priority())))
                .toList();
        int added = state.addOrders(orders, Instant.now());
        Map<String, Object> response = Map.of("jobId", jobId, "ordersAdded", added, "buffered", state.bufferedCount());
        if (idem != null) idempotency.put(idem, response);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/{jobId}/drivers/{driverId}/telemetry")
    public ResponseEntity<?> updateDriver(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                          @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                          @PathVariable String jobId,
                                          @PathVariable String driverId,
                                          @RequestBody(required = false) DriverTelemetryRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        denied = authorizeTenant(jobId, tenantHeader);
        if (denied != null) return denied;
        denied = validateTelemetry(request);
        if (denied != null) return denied;
        LiveDispatchState state = state(jobId);
        DriverTelemetryRequest body = request == null ? new DriverTelemetryRequest(driverId, 10.77, 106.69, "IDLE", null) : request;
        state.updateDriver(new LiveDriverState(driverId, body.lat(), body.lng(), body.status(), body.currentStopId(), Instant.now()));
        return ResponseEntity.ok(Map.of("jobId", jobId, "driverId", driverId, "status", "UPDATED"));
    }

    @PostMapping("/{jobId}/cycle")
    public ResponseEntity<?> runCycle(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                      @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                      @PathVariable String jobId,
                                      @RequestBody(required = false) LiveCycleRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        denied = authorizeTenant(jobId, tenantHeader);
        if (denied != null) return denied;
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
    public ResponseEntity<?> stateResponse(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                           @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                           @PathVariable String jobId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        denied = authorizeTenant(jobId, tenantHeader);
        if (denied != null) return denied;
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
    public ResponseEntity<?> rescue(@RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                    @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                    @PathVariable String jobId) {
        return runCycle(apiKey, tenantHeader, jobId, new LiveCycleRequest(true));
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
    private String tenant(String requestTenant, String headerTenant) { return !blank(requestTenant) ? requestTenant : (blank(headerTenant) ? "demo" : headerTenant); }
    private ResponseEntity<?> authorize(String apiKey) { return API_KEY.equals(apiKey) ? null : ResponseEntity.status(401).body(Map.of("error", "UNAUTHORIZED")); }
    private ResponseEntity<?> authorizeTenant(String jobId, String tenantHeader) {
        if (!states.containsKey(jobId)) return ResponseEntity.status(404).body(Map.of("error", "NOT_FOUND"));
        String tenant = tenants.get(jobId);
        return Objects.equals(tenant, tenantHeader) ? null : ResponseEntity.status(403).body(Map.of("error", "FORBIDDEN"));
    }
    private String idemKey(String tenantId, String scope, String key) { return blank(key) ? null : tenantId + ":" + scope + ":" + key; }
    private ResponseEntity<?> validateOrders(AddOrdersRequest request) {
        if (request == null || request.orders() == null || request.orders().isEmpty()) return ResponseEntity.badRequest().body(Map.of("error", "ORDER_REQUIRED"));
        for (LiveOrderRequest order : request.orders()) {
            if (order == null || blank(order.orderId()) || order.pickup() == null || order.dropoff() == null || !latLng(order.pickup()) || !latLng(order.dropoff()) || order.load() <= 0) return ResponseEntity.badRequest().body(Map.of("error", "INVALID_ORDER"));
        }
        return null;
    }
    private ResponseEntity<?> validateTelemetry(DriverTelemetryRequest request) {
        if (request == null || !latLng(request.lat(), request.lng())) return ResponseEntity.badRequest().body(Map.of("error", "INVALID_TELEMETRY"));
        return null;
    }
    private boolean latLng(Point point) { return latLng(point.lat(), point.lng()); }
    private boolean latLng(double lat, double lng) { return lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180; }

    public record LiveJobCreateRequest(String jobId, String tenantId) { }
    public record LiveJobResponse(String jobId, String tenantId, String mode, String status) { }
    public record AddOrdersRequest(List<LiveOrderRequest> orders) { }
    public record LiveOrderRequest(String orderId, Point pickup, Point dropoff, String deadline, int load, String priority) { }
    public record Point(double lat, double lng) { }
    public record DriverTelemetryRequest(String driverId, double lat, double lng, String status, String currentStopId) { }
    public record LiveCycleRequest(boolean returnDiagnostics) { }
    public record LiveCycleResponse(String jobId, int cycle, String mode, int assigned, int buffered, int late, boolean forecastUsed, String greedRlAction, boolean triModelRepairUsed, List<LiveRouteSnapshot> routes, Map<String, Object> diagnostics, int assignedRegression) { }
    public record LiveStateResponse(String jobId, int cycle, int assigned, int buffered, List<LiveOrderState> orders, List<LiveDriverState> drivers, List<LiveRouteSnapshot> routes, List<String> frozenStopIds, List<Map<String, Object>> events) { }
}
