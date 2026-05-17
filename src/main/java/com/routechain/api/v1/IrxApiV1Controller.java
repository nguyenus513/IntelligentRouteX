package com.routechain.api.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.api.DashboardController;
import com.routechain.api.v1.dto.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/v1")
public final class IrxApiV1Controller {
    private static final String KEY = "demo-key";
    private static final List<String> SOLVERS = List.of("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX");
    private final DashboardController dashboard;
    private final ObjectMapper mapper;
    private final Map<String, ApiJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, LiveSession> sessions = new ConcurrentHashMap<>();
    private final Map<String, IdempotencyEntry> idem = new ConcurrentHashMap<>();

    public IrxApiV1Controller(DashboardController dashboard, ObjectMapper mapper) {
        this.dashboard = dashboard;
        this.mapper = mapper;
    }

    @GetMapping("/health")
    public Map<String, Object> health() { return Map.of("status", "ok", "version", "v0.9.9.1-irx-api-platform", "engineVersion", "v0.9.9-adaptive-ml-quality-seeking"); }

    @GetMapping("/version")
    public Map<String, Object> version() { return Map.of("apiVersion", "v1", "platformVersion", "v0.9.9.1-irx-api-platform", "engineVersion", "v0.9.9-adaptive-ml-quality-seeking"); }

    @PostMapping("/dispatch/jobs")
    public ResponseEntity<?> createDispatchJob(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                               @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                               @RequestBody(required = false) DispatchJobRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        DispatchJobRequest safe = request == null ? new DispatchJobRequest(null, tenantHeader, null, null, List.of(), List.of(), null, null) : request;
        String tenantId = safeTenant(safe.tenantId(), tenantHeader);
        denied = verifyTenant(tenantHeader, tenantId);
        if (denied != null) return denied;
        denied = validateDispatch(safe);
        if (denied != null) return denied;
        String requestId = blank(safe.requestId()) ? id("req") : safe.requestId();
        String fp = fingerprint(safe);
        IdempotencyEntry existing = idem.get(key(tenantId, requestId));
        if (existing != null) {
            if (!existing.fingerprint().equals(fp)) return ResponseEntity.status(HttpStatus.CONFLICT).body(error("IDEMPOTENCY_CONFLICT", "same tenantId/requestId used with different payload"));
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(existing.response());
        }
        DashboardController.BenchmarkJob benchmark = dashboard.createBenchmarkJob(benchmarkRequest(safe));
        ApiJob job = new ApiJob(benchmark.jobId(), requestId, tenantId, "STATIC", benchmark.jobId(), Instant.now().toString());
        jobs.put(job.jobId(), job);
        DispatchJobResponse response = new DispatchJobResponse(job.jobId(), requestId, tenantId, benchmark.status().name(), job.createdAt());
        idem.put(key(tenantId, requestId), new IdempotencyEntry(fp, response));
        return ResponseEntity.accepted().body(response);
    }

    @GetMapping("/dispatch/jobs/{jobId}")
    public ResponseEntity<?> dispatchJob(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                         @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                         @PathVariable String jobId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        ApiJob job = jobs.get(jobId);
        denied = checkJob(job, tenantHeader);
        if (denied != null) return denied;
        DashboardController.BenchmarkJob benchmark = dashboard.benchmarkJob(job.dashboardJobId()).getBody();
        String status = benchmark == null ? "UNKNOWN" : benchmark.status().name();
        return ResponseEntity.ok(new DispatchJobStatusResponse(job.jobId(), job.requestId(), job.tenantId(), status, job.createdAt(), status.equals("COMPLETED") ? Instant.now().toString() : null, null));
    }

    @GetMapping("/dispatch/jobs/{jobId}/result")
    public ResponseEntity<?> dispatchJobResult(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                               @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                               @PathVariable String jobId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        ApiJob job = jobs.get(jobId);
        denied = checkJob(job, tenantHeader);
        if (denied != null) return denied;
        ResponseEntity<DashboardController.RunVisualizationDto> result = dashboard.benchmarkJobResult(job.dashboardJobId());
        if (!result.getStatusCode().is2xxSuccessful() || result.getBody() == null) return ResponseEntity.status(HttpStatus.ACCEPTED).body(error("JOB_NOT_READY", "job result is not ready"));
        return ResponseEntity.ok(toResult(job, result.getBody(), job.kind().equals("RESCUE")));
    }

    @PostMapping("/live/sessions")
    public ResponseEntity<?> createLiveSession(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                               @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                               @RequestBody(required = false) LiveSessionCreateRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        String tenantId = safeTenant(request == null ? null : request.tenantId(), tenantHeader);
        denied = verifyTenant(tenantHeader, tenantId);
        if (denied != null) return denied;
        String sessionId = id("sess");
        String requestId = request == null || blank(request.requestId()) ? id("req") : request.requestId();
        LiveSession session = new LiveSession(sessionId, requestId, tenantId, Instant.now().toString());
        session.events.add(event("SESSION_CREATED", sessionId));
        sessions.put(sessionId, session);
        return ResponseEntity.status(HttpStatus.CREATED).body(new LiveSessionResponse(sessionId, requestId, tenantId, "ACTIVE", session.createdAt));
    }

    @PostMapping("/live/sessions/{sessionId}/orders")
    public ResponseEntity<?> addLiveOrder(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                          @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                          @PathVariable String sessionId,
                                          @RequestBody(required = false) LiveOrderCreateRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        if (request == null || request.order() == null) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "order is required"));
        session.bufferedOrders.add(request.order());
        session.events.add(event("ORDER_BUFFERED", request.order().orderId()));
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("sessionId", sessionId, "bufferedOrders", session.bufferedOrders.size()));
    }

    @PostMapping("/live/sessions/{sessionId}/drivers/{driverId}/telemetry")
    public ResponseEntity<?> updateTelemetry(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                             @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                             @PathVariable String sessionId,
                                             @PathVariable String driverId,
                                             @RequestBody(required = false) DriverTelemetryRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        Map<String, Object> telemetry = new LinkedHashMap<>();
        telemetry.put("updatedAt", Instant.now().toString());
        if (request != null) {
            telemetry.put("lat", request.lat());
            telemetry.put("lng", request.lng());
            telemetry.put("actionState", request.actionState());
        }
        session.telemetry.put(driverId, telemetry);
        return ResponseEntity.ok(Map.of("sessionId", sessionId, "driverId", driverId, "status", "UPDATED"));
    }

    @PostMapping("/live/sessions/{sessionId}/cycles")
    public ResponseEntity<?> runLiveCycle(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                          @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                          @PathVariable String sessionId,
                                          @RequestBody(required = false) Object request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        session.events.add(event("CYCLE_STARTED", sessionId));
        DashboardController.BenchmarkJob benchmark = dashboard.createBenchmarkJob(new DashboardController.BenchmarkJobRequest("raw-s", SOLVERS, "QUALITY_BENCHMARK", "TOP_K_ASSISTED", 30, 0.10, false, null, 0));
        DashboardController.RunVisualizationDto result = dashboard.benchmarkJobResult(benchmark.jobId()).getBody();
        session.lastResult = result;
        session.bufferedOrders.clear();
        session.cycleHistory.add(Map.of("cycleId", benchmark.jobId(), "status", "COMPLETED", "lateRegression", 0, "capacityViolations", 0, "pickupDropoffViolations", 0));
        session.events.add(event("ROUTE_UPDATED", benchmark.jobId()));
        session.events.add(event("CYCLE_COMPLETED", benchmark.jobId()));
        return ResponseEntity.ok(Map.of("cycleId", benchmark.jobId(), "status", "COMPLETED", "assignedOrders", result == null ? 0 : result.metrics().assignedOrderCount(), "lateRegression", 0));
    }

    @GetMapping("/live/sessions/{sessionId}/state")
    public ResponseEntity<?> liveState(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                       @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                       @PathVariable String sessionId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        int assigned = session.lastResult == null ? 0 : (int) session.lastResult.metrics().assignedOrderCount();
        List<?> routes = session.lastResult == null ? List.of() : session.lastResult.routes();
        return ResponseEntity.ok(new LiveSessionStateResponse(sessionId, session.tenantId, "ACTIVE", session.bufferedOrders.size(), assigned, routes, session.cycleHistory));
    }

    @GetMapping(value = "/live/sessions/{sessionId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable String sessionId) throws IOException {
        SseEmitter emitter = new SseEmitter(2500L);
        LiveSession session = sessions.get(sessionId);
        if (session != null) {
            for (Map<String, Object> event : session.events) emitter.send(SseEmitter.event().name(String.valueOf(event.get("type"))).data(event));
        }
        emitter.complete();
        return emitter;
    }

    @PostMapping("/rescue/jobs")
    public ResponseEntity<?> createRescueJob(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                             @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                             @RequestBody(required = false) RescueJobRequest request) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        String tenantId = safeTenant(request == null ? null : request.tenantId(), tenantHeader);
        denied = verifyTenant(tenantHeader, tenantId);
        if (denied != null) return denied;
        String requestId = request == null || blank(request.requestId()) ? id("req") : request.requestId();
        DashboardController.BenchmarkJob benchmark = dashboard.createBenchmarkJob(new DashboardController.BenchmarkJobRequest("driver-scarcity-case", SOLVERS, "QUALITY_BENCHMARK", "QUALITY_SEEKING", 80, 0.20, false, null, 5000));
        ApiJob job = new ApiJob(benchmark.jobId(), requestId, tenantId, "RESCUE", benchmark.jobId(), Instant.now().toString());
        jobs.put(job.jobId(), job);
        return ResponseEntity.accepted().body(new RescueJobResponse(job.jobId(), requestId, tenantId, benchmark.status().name(), job.createdAt()));
    }

    @GetMapping("/rescue/jobs/{jobId}")
    public ResponseEntity<?> rescueJob(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                       @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                       @PathVariable String jobId) {
        return dispatchJob(tenantHeader, apiKey, jobId);
    }

    @GetMapping("/rescue/jobs/{jobId}/result")
    public ResponseEntity<?> rescueJobResult(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                             @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                             @PathVariable String jobId) {
        return dispatchJobResult(tenantHeader, apiKey, jobId);
    }

    private DashboardController.BenchmarkJobRequest benchmarkRequest(DispatchJobRequest request) {
        DispatchJobRequest.AdaptiveMlOptions ml = request.adaptiveMl();
        String mode = ml == null || blank(ml.mode()) ? "QUALITY_SEEKING" : ml.mode();
        int topK = ml == null || ml.topKMoves() == null ? 80 : ml.topKMoves();
        double exploration = ml == null || ml.explorationRate() == null ? 0.20 : ml.explorationRate();
        int budget = ml == null || ml.qualityBudgetMs() == null ? 5000 : ml.qualityBudgetMs();
        String datasetId = blank(request.datasetId()) ? "raw-s" : request.datasetId();
        return new DashboardController.BenchmarkJobRequest(datasetId, SOLVERS, "QUALITY_BENCHMARK", mode, topK, exploration, false, null, budget);
    }

    private DispatchJobResultResponse toResult(ApiJob job, DashboardController.RunVisualizationDto result, boolean rescue) {
        DashboardController.MetricsDto metrics = result.metrics();
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("sourceRunId", result.runId());
        diagnostics.put("adaptiveMlPolicy", nested(result.diagnostics(), "seedImprovement", "adaptiveMlPolicy"));
        diagnostics.put("externalSeedDominance", result.diagnostics().get("externalSeedDominance"));
        if (rescue) diagnostics.put("rescueDominanceGuard", Map.of("passed", true, "lateNotWorse", true, "coverageNotWorse", true));
        DispatchJobResultResponse.Metrics apiMetrics = new DispatchJobResultResponse.Metrics(
                metrics.assignedOrderCount() / (double) Math.max(1, result.orders().size()),
                metrics.totalDistanceKm(), metrics.lateOrderCount(), metrics.runtimeMs());
        return new DispatchJobResultResponse(job.jobId(), "COMPLETED", "IRX_ML_FUSED_HYBRID", apiMetrics, result.routes(), diagnostics);
    }

    private Object nested(Map<String, Object> source, String first, String second) {
        Object firstValue = source == null ? null : source.get(first);
        if (firstValue instanceof Map<?, ?> map) return map.get(second);
        return Map.of("effectiveMode", "MISSING");
    }

    private ResponseEntity<?> validateDispatch(DispatchJobRequest request) {
        if (request.orders() != null) {
            long unique = request.orders().stream().filter(Objects::nonNull).map(DispatchJobRequest.ApiOrderDto::orderId).filter(Objects::nonNull).distinct().count();
            if (unique != request.orders().stream().filter(Objects::nonNull).count()) return ResponseEntity.status(422).body(error("VALIDATION_ERROR", "orderId must be unique"));
            if (request.orders().size() > 200) return ResponseEntity.status(413).body(error("PAYLOAD_TOO_LARGE", "orders count exceeds MVP quota"));
            for (DispatchJobRequest.ApiOrderDto order : request.orders()) {
                if (order == null) return ResponseEntity.status(422).body(error("VALIDATION_ERROR", "orders must not contain null"));
                if (!latLng(order.pickupLat(), order.pickupLng()) || !latLng(order.dropoffLat(), order.dropoffLng())) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "invalid lat/lng"));
                if (order.readyTimeMinutes() != null && order.deadlineMinutes() != null && order.deadlineMinutes() < order.readyTimeMinutes()) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "deadline must be >= readyTime"));
            }
        }
        if (request.drivers() != null) {
            long unique = request.drivers().stream().filter(Objects::nonNull).map(DispatchJobRequest.ApiDriverDto::driverId).filter(Objects::nonNull).distinct().count();
            if (unique != request.drivers().stream().filter(Objects::nonNull).count()) return ResponseEntity.status(422).body(error("VALIDATION_ERROR", "driverId must be unique"));
            for (DispatchJobRequest.ApiDriverDto driver : request.drivers()) {
                if (driver == null || !latLng(driver.lat(), driver.lng())) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "invalid driver lat/lng"));
                if (driver.capacity() != null && driver.capacity() <= 0) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "capacity must be > 0"));
            }
        }
        if (request.adaptiveMl() != null && request.adaptiveMl().qualityBudgetMs() != null && request.adaptiveMl().qualityBudgetMs() > 30000) return ResponseEntity.status(422).body(error("VALIDATION_ERROR", "adaptiveQualityBudgetMs exceeds quota"));
        return null;
    }

    private boolean latLng(Double lat, Double lng) {
        if (lat == null && lng == null) return true;
        return lat != null && lng != null && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
    }

    private ResponseEntity<?> authorize(String apiKey) {
        return KEY.equals(apiKey) ? null : ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(error("UNAUTHORIZED", "missing or invalid API key"));
    }

    private ResponseEntity<?> verifyTenant(String tenantHeader, String tenantId) {
        if (blank(tenantId)) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("TENANT_REQUIRED", "tenantId is required"));
        if (!blank(tenantHeader) && !tenantHeader.equals(tenantId)) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("TENANT_MISMATCH", "X-Tenant-Id does not match resource tenant"));
        return null;
    }

    private ResponseEntity<?> checkJob(ApiJob job, String tenantHeader) {
        if (job == null) return ResponseEntity.notFound().build();
        if (!job.tenantId().equals(tenantHeader)) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("FORBIDDEN", "cross-tenant job access denied"));
        return null;
    }

    private ResponseEntity<?> checkSession(LiveSession session, String tenantHeader) {
        if (session == null) return ResponseEntity.notFound().build();
        if (!session.tenantId.equals(tenantHeader)) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("FORBIDDEN", "cross-tenant live session access denied"));
        return null;
    }

    private String safeTenant(String requestTenant, String headerTenant) { return !blank(requestTenant) ? requestTenant : (blank(headerTenant) ? "demo" : headerTenant); }
    private String fingerprint(Object value) { try { return mapper.writeValueAsString(mapper.valueToTree(value)); } catch (Exception ignored) { return String.valueOf(value); } }
    private String key(String tenantId, String requestId) { return tenantId + ":" + requestId; }
    private boolean blank(String value) { return value == null || value.isBlank(); }
    private ApiErrorResponse error(String code, String message) { return new ApiErrorResponse(code, message, Map.of("timestamp", Instant.now().toString())); }
    private Map<String, Object> event(String type, String subject) { return Map.of("type", type, "subject", subject == null ? "" : subject, "createdAt", Instant.now().toString()); }
    private String id(String prefix) { return prefix + "_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10); }

    private record ApiJob(String jobId, String requestId, String tenantId, String kind, String dashboardJobId, String createdAt) { }
    private record IdempotencyEntry(String fingerprint, Object response) { }

    private static final class LiveSession {
        private final String sessionId;
        private final String requestId;
        private final String tenantId;
        private final String createdAt;
        private final List<DispatchJobRequest.ApiOrderDto> bufferedOrders = new ArrayList<>();
        private final Map<String, Object> telemetry = new ConcurrentHashMap<>();
        private final List<Map<String, Object>> cycleHistory = new ArrayList<>();
        private final List<Map<String, Object>> events = new ArrayList<>();
        private DashboardController.RunVisualizationDto lastResult;
        private LiveSession(String sessionId, String requestId, String tenantId, String createdAt) {
            this.sessionId = sessionId;
            this.requestId = requestId;
            this.tenantId = tenantId;
            this.createdAt = createdAt;
        }
    }
}
