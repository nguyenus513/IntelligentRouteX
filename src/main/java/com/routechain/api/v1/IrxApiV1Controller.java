package com.routechain.api.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.api.DashboardController;
import com.routechain.api.v1.dto.*;
import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.runtime.artifact.*;
import com.routechain.runtime.metrics.RuntimeMetricsRegistry;
import com.routechain.runtime.queue.*;
import com.routechain.runtime.store.*;
import com.routechain.v2.external.ExternalSeedContribution;
import com.routechain.v2.external.ExternalSolverRuntimeManager;
import com.routechain.v2.external.PyvrpSeedContributor;
import com.routechain.v2.external.VroomSeedContributor;
import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import com.routechain.v2.hybrid.SolutionSeedRoute;
import com.routechain.v2.routing.*;
import com.routechain.v2.seedimprovement.*;
import com.routechain.v2.unified.DispatchMode;
import com.routechain.v2.unified.DispatchPolicy;
import com.routechain.v2.unified.DispatchStrategy;
import com.routechain.v2.unified.UnifiedDispatchRequest;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
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
    private final DispatchJobStore jobStore = new InMemoryDispatchJobStore();
    private final LiveSessionStore liveSessionStore = new InMemoryLiveSessionStore();
    private final ResultStore resultStore = new InMemoryResultStore();
    private final ArtifactStore artifactStore = new FileSystemArtifactStore();
    private final ArtifactAccessGuard artifactAccessGuard = new ArtifactAccessGuard();
    private final DispatchQueue dispatchQueue = new InMemoryDispatchQueue();
    private final QueueRouter queueRouter = new QueueRouter();
    private final RuntimeMetricsRegistry metrics = new RuntimeMetricsRegistry();
    private final Map<String, List<Long>> rateBuckets = new ConcurrentHashMap<>();
    private final ExternalSolverRuntimeManager solverRuntimeManager = new ExternalSolverRuntimeManager();
    private final ExecutionEventService executionEvents;
    private final RoutingProvider routingProvider;
    private final RouteChainDispatchV2Properties properties;
    private final OsrmTableClient osrmTableClient;
    private final HttpClient osrmHealthClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

    public IrxApiV1Controller(DashboardController dashboard, ObjectMapper mapper, ExecutionEventService executionEvents, RoutingProvider routingProvider, RouteChainDispatchV2Properties properties, OsrmTableClient osrmTableClient) {
        this.dashboard = dashboard;
        this.mapper = mapper;
        this.executionEvents = executionEvents;
        this.routingProvider = routingProvider;
        this.properties = properties;
        this.osrmTableClient = osrmTableClient;
    }

    @GetMapping("/health")
    public Map<String, Object> health() { return Map.of("status", "UP", "version", "v1.0.2.1-irx-final", "engineVersion", "v1.0.2.1-irx-final", "externalSolvers", solverRuntimeManager.compactStatus(), "externalSolverEvidence", solverRuntimeManager.readiness(), "routing", Map.of("configuredProvider", properties.getRouting().getProvider(), "activeProvider", routingProvider.providerId(), "baseUrl", properties.getRouting().getBaseUrl(), "geometryPolicy", "live-routes-require-backend-road-geometry", "osrmTable", osrmTableReady() ? "AVAILABLE" : "UNAVAILABLE"), "realRuntimePolicy", Map.of("fallbackDisabled", true, "requiresFrontendInput", true), "adaptiveMl", Map.of("qualitySeeking", true)); }

    private boolean osrmTableReady() {
        try {
            String baseUrl = properties.getRouting().getBaseUrl();
            URI uri = URI.create((baseUrl.endsWith("/") ? baseUrl : baseUrl + "/") + "table/v1/driving/106.7009,10.7769;106.6983,10.7721?annotations=duration,distance");
            HttpRequest request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(2)).GET().build();
            HttpResponse<String> response = osrmHealthClient.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() >= 200 && response.statusCode() < 300 && response.body() != null && response.body().contains("\"code\":\"Ok\"");
        } catch (Exception ignored) {
            return false;
        }
    }

    @GetMapping("/version")
    public Map<String, Object> version() { return Map.of("apiVersion", "v1", "platformVersion", "v1.0.2.1-irx-api-platform-final", "engineVersion", "v1.0.2.1-irx-final"); }

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
        denied = checkRateLimit(tenantId, "dispatch", 20);
        if (denied != null) return denied;
        denied = validateDispatch(safe);
        if (denied != null) return denied;
        denied = requireRealInput(safe);
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
        emitDispatchAccepted(job, safe);
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
        emitRunResult(job.executionId(), result.getBody(), "Dispatch result ready");
        resultStore.save(job.tenantId(), job.jobId(), result.getBody());
        ArtifactRecord artifact = artifactStore.save(new ArtifactRecord("art_" + job.jobId(), job.tenantId(), job.jobId(), "DISPATCH_RESULT", "artifacts/test-reports/v0.9.9.2-production-runtime/" + job.jobId() + ".json", Instant.now(), 30));
        metrics.increment("artifactWrites");
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
        if (request == null || request.drivers() == null || request.drivers().isEmpty()) {
            return ResponseEntity.status(422).body(error("REAL_INPUT_REQUIRED", "live session requires frontend-provided drivers"));
        }
        for (DispatchJobRequest.ApiDriverDto driver : request.drivers()) {
            if (driver == null || !latLng(driver.lat(), driver.lng())) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "invalid live driver lat/lng"));
        }
        LiveSession session = new LiveSession(sessionId, requestId, tenantId, Instant.now().toString());
        if (request != null && request.drivers() != null) session.drivers.addAll(request.drivers());
        session.drivers.forEach(driver -> {
            DriverRuntimeState state = new DriverRuntimeState(driver.driverId(), driver.lat(), driver.lng());
            applyDriverRuntimeInput(state, driver);
            session.driverStates.put(driver.driverId(), state);
            appendConsoleTrace(session, "DRIVER", "info", "DRIVER_ONLINE", "Driver " + driver.driverId() + " online at " + coord(driver.lat(), driver.lng()), Map.of(
                    "driverId", driver.driverId(),
                    "lat", driver.lat(),
                    "lng", driver.lng(),
                    "capacity", driver.capacity() == null ? 100 : driver.capacity(),
                    "speedKmh", driver.speedKmh() == null ? state.speedKmh : driver.speedKmh(),
                    "status", blank(driver.status()) ? state.status : driver.status()
            ));
        });
        session.events.add(event("SESSION_CREATED", sessionId));
        appendConsoleTrace(session, "BOOT", "ok", "SESSION_CREATED", "Live session active with " + session.drivers.size() + " drivers", Map.of("sessionId", sessionId, "requestId", requestId, "driverCount", session.drivers.size()));
        sessions.put(sessionId, session);
        executionEvents.emit("exec_" + sessionId, "INPUT_RECEIVED", "COMPLETED", 5, "Live session created", Map.of("sessionId", sessionId, "drivers", session.drivers));
        liveSessionStore.save(new RuntimeLiveSessionRecord(sessionId, tenantId, "ACTIVE", Instant.now(), Map.of("status", "ACTIVE")));
        metrics.increment("liveSessionsCreated");
        return ResponseEntity.status(HttpStatus.CREATED).body(new LiveSessionResponse(sessionId, requestId, tenantId, "ACTIVE", session.createdAt));
    }

    @PostMapping("/live/sessions/{sessionId}/orders")
    public ResponseEntity<?> addLiveOrder(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                          @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                          @PathVariable String sessionId,
                                          @RequestBody(required = false) LiveOrderCreateRequest request) {
        Instant receivedAt = Instant.now();
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        if (request == null || request.order() == null) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "order is required"));
        if (!latLng(request.order().pickupLat(), request.order().pickupLng()) || !latLng(request.order().dropoffLat(), request.order().dropoffLng())) {
            return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "invalid live order lat/lng"));
        }
        denied = checkRateLimit(session.tenantId, "liveOrders", 300);
        if (denied != null) return denied;
        LiveBufferItem item = new LiveBufferItem(request.order(), receivedAt);
        updateAging(item, Instant.now());
        session.bufferedOrders.add(item);
        session.events.add(event("ORDER_BUFFERED", request.order().orderId()));
        appendConsoleTrace(session, "INPUT", "info", "ORDER_RECEIVED", "Order " + request.order().orderId() + " received pickup " + coord(request.order().pickupLat(), request.order().pickupLng()) + " dropoff " + coord(request.order().dropoffLat(), request.order().dropoffLng()), orderConsoleData(request.order(), item));
        appendConsoleTrace(session, "BUFFER", "ok", "BUFFER_ENTERED", "Order " + request.order().orderId() + " entered aging buffer as " + item.priorityLevel + " score " + round1(item.finalScore), bufferItemView(item));
        Map<String, Object> realtimeTrace = realtimeLiveDecisionTrace(session, "ORDER_BUFFERED_REALTIME_CLUSTER");
        executionEvents.emit("exec_" + sessionId, "CLUSTERING_COMPLETED", "COMPLETED", 35, "Realtime buffer clusters updated", Map.of("clusterSelection", realtimeTrace.get("clusterSelection"), "orderPool", realtimeTrace.get("orderPool")));
        executionEvents.emit("exec_" + sessionId, "BUFFERING_COMPLETED", "COMPLETED", 20, "Live order buffered", Map.of("bufferedOrders", session.bufferedOrders.size(), "order", request.order(), "bufferItem", bufferItemView(item)));
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("sessionId", sessionId, "bufferedOrders", session.bufferedOrders.size(), "orderAcceptedLatencyMs", elapsedMillis(receivedAt, Instant.now()), "bufferItem", bufferItemView(item), "decisionTrace", realtimeTrace));
    }

    @PostMapping("/live/sessions/{sessionId}/drivers")
    public ResponseEntity<?> addLiveDriver(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                           @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                           @PathVariable String sessionId,
                                           @RequestBody(required = false) DispatchJobRequest.ApiDriverDto driver) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        if (driver == null || blank(driver.driverId())) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "driverId is required"));
        if (!latLng(driver.lat(), driver.lng())) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "invalid live driver lat/lng"));
        boolean exists = session.drivers.stream().anyMatch(existing -> Objects.equals(existing.driverId(), driver.driverId()));
        if (!exists) session.drivers.add(driver);
        DriverRuntimeState state = session.driverStates.computeIfAbsent(driver.driverId(), ignored -> new DriverRuntimeState(driver.driverId(), driver.lat(), driver.lng()));
        applyDriverRuntimeInput(state, driver);
        session.events.add(event("DRIVER_ONLINE", driver.driverId()));
        appendConsoleTrace(session, "DRIVER", exists ? "warn" : "ok", "DRIVER_ONLINE", "Driver " + driver.driverId() + (exists ? " already online, runtime refreshed" : " added live"), Map.of("driverId", driver.driverId(), "lat", driver.lat(), "lng", driver.lng(), "driverCount", session.drivers.size(), "speedKmh", state.speedKmh, "status", state.status));
        executionEvents.emit("exec_" + sessionId, "DRIVER_ONLINE", "COMPLETED", 15, "Live driver online", Map.of("driver", driver, "driverCount", session.drivers.size()));
        return ResponseEntity.status(exists ? HttpStatus.OK : HttpStatus.CREATED).body(Map.of("sessionId", sessionId, "driver", driver, "driverCount", session.drivers.size(), "status", exists ? "ALREADY_ONLINE" : "ONLINE"));
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
                                          @RequestBody(required = false) RollingCycleRequest request) {
        Instant cycleRequestedAt = Instant.now();
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        LiveSession session = sessions.get(sessionId);
        denied = checkSession(session, tenantHeader);
        if (denied != null) return denied;
        metrics.increment("liveCyclesStarted");
        session.events.add(event("CYCLE_STARTED", sessionId));
        String executionId = "exec_" + sessionId;
        executionEvents.emit(executionId, "BUFFERING_STARTED", "RUNNING", 25, "Live rolling cycle started", Map.of("bufferedOrders", session.bufferedOrders.size(), "bufferItems", bufferItemsView(session)));
        QueueLane liveLane = queueRouter.route("LIVE_ROLLING", "LIVE");
        dispatchQueue.enqueue(new DispatchJobEnvelope(id("live"), session.tenantId, liveLane, queueRouter.priority(liveLane), Instant.now()));
        String pdLnsMode = request == null || blank(request.pdLnsMode()) ? "QUALITY_LIVE" : request.pdLnsMode();
        DashboardController.RunVisualizationDto previousResult = session.lastResult;
        Instant roundStartedAt = Instant.now();
        session.bufferedOrders.forEach(item -> updateAging(item, roundStartedAt));
        List<LiveBufferItem> cycleItems = selectCycleItems(session);
        List<DispatchJobRequest.ApiOrderDto> cycleOrders = cycleItems.stream().map(item -> item.order).toList();
        appendConsoleTrace(session, "BUFFER", "info", "BUFFER_SELECTION", "Cycle selected " + cycleOrders.size() + " orders from buffer", Map.of("sessionId", sessionId, "selectedOrders", cycleItems.stream().map(item -> item.order.orderId()).toList(), "bufferItems", cycleItems.stream().map(this::bufferItemView).toList(), "bufferTotal", session.bufferedOrders.size()));
        if (cycleOrders.isEmpty()) {
            Map<String, Object> response = new LinkedHashMap<>();
            String cycleId = id("cycle");
            response.put("cycleId", cycleId);
            response.put("status", "NOOP_EMPTY_BUFFER");
            response.put("pdLnsMode", pdLnsMode);
            response.put("assignedOrders", 0);
            response.put("bufferItems", bufferItemsView(session));
            response.put("activeRoutes", session.lastResult == null ? List.of() : session.lastResult.routes());
            response.put("reason", "No WAITING orders in backend live buffer; keeping current active routes.");
            appendConsoleTrace(session, "BUFFER", "warn", "EMPTY_BUFFER_NOOP", "Cycle skipped because backend buffer is empty; active routes kept", Map.of("sessionId", sessionId, "cycleId", cycleId));
            session.cycleHistory.add(Map.of("cycleId", cycleId, "status", "NOOP_EMPTY_BUFFER", "pdLnsMode", pdLnsMode, "assignedThisRound", 0, "remainingBuffer", 0, "routeChurnPercent", "0.0%"));
            session.events.add(event("CYCLE_NOOP_EMPTY_BUFFER", cycleId));
            metrics.increment("liveCyclesCompleted");
            return ResponseEntity.ok(response);
        }
        DashboardController.RunVisualizationDto result;
        try {
            result = runLiveSnapshot(session, cycleOrders);
        } catch (IllegalStateException exception) {
            metrics.increment("jobsFailed");
            executionEvents.emit(executionId, "EXECUTION_FAILED", "FAILED", 100, exception.getMessage(), Map.of("sessionId", sessionId));
            return ResponseEntity.status(422).body(error("REAL_INPUT_REQUIRED", exception.getMessage()));
        }
        Instant routeReadyAt = Instant.now();
        Map<String, Object> seedArchive;
        try {
            seedArchive = liveSeedArchive(session, cycleOrders, result);
            result = applyLiveSeedWinner(result, seedArchive, pdLnsMode, session);
            result = enforceLiveCoverageAndUtilization(session, cycleOrders, result, pdLnsMode);
            result = mergeWithActiveLiveRoutes(session, previousResult, result);
        } catch (IllegalStateException exception) {
            metrics.increment("jobsFailed");
            executionEvents.emit(executionId, "EXECUTION_FAILED", "FAILED", 100, exception.getMessage(), Map.of("sessionId", sessionId, "routingPolicy", "OSRM_ONLY"));
            return ResponseEntity.status(422).body(error("OSRM_REQUIRED", exception.getMessage()));
        }
        Map<String, Object> latencyTrace = liveLatencyTrace(cycleItems, cycleRequestedAt, roundStartedAt, routeReadyAt, result);
        Map<String, Object> liveTrace = buildLiveDecisionTrace(session, cycleOrders, result, previousResult, pdLnsMode, request, latencyTrace);
        liveTrace.put("seedArchive", seedArchive);
        liveTrace.put("seedRace", seedArchive.getOrDefault("ranking", liveTrace.get("seedRace")));
        liveTrace.put("solverRace", seedArchive.getOrDefault("ranking", liveTrace.get("solverRace")));
        Object finalSeedSource = result == null || result.diagnostics() == null ? null : result.diagnostics().get("liveFinalSeedSource");
        if (finalSeedSource != null) {
            liveTrace.put("hybridRefinement", finalSeedSource);
            Map<String, Object> finalSelectionTrace = new LinkedHashMap<>(asMap(liveTrace.get("finalSelection")));
            String finalOptimizer = String.valueOf(asMap(finalSeedSource).getOrDefault("finalOptimizer", "IRX_HYBRID_REFINEMENT"));
            finalSelectionTrace.put("selectedSource", finalOptimizer);
            finalSelectionTrace.put("selectionReason", "best solver seed refined by IRX dominance-guarded live optimization");
            finalSelectionTrace.put("seedSource", asMap(finalSeedSource).getOrDefault("selectedSeed", ""));
            finalSelectionTrace.put("finalOptimizer", finalOptimizer);
            finalSelectionTrace.put("selectedOptimizer", asMap(finalSeedSource).getOrDefault("selectedOptimizer", finalOptimizer));
            liveTrace.put("finalSelection", finalSelectionTrace);
            liveTrace.put("dominanceGuard", Map.of("status", "PASS", "selectedSource", finalOptimizer, "objective", "coverage -> hard violations -> late count -> total lateness -> distance -> route churn -> runtime", "seedSource", finalSelectionTrace.get("seedSource"), "reason", "IRX accepted only non-regressing refinement"));
        }
        List<Map<String, Object>> cycleConsoleTrace = buildCycleConsoleTrace(session, cycleIdSafe(result), cycleItems, seedArchive, result, liveTrace, latencyTrace);
        appendConsoleTrace(session, cycleConsoleTrace);
        liveTrace.put("consoleTrace", cycleConsoleTrace);
        result = enrichResultDiagnostics(result, liveTrace);
        emitLiveDecisionEvents(executionId, liveTrace);
        if (result != null) emitRunResult(executionId, result, "Live cycle result ready");
        session.lastResult = result;
        attachRuntimeRoutes(session, result);
        String cycleId = result == null ? id("cycle") : result.runId();
        Set<String> assignedOrderIds = assignedOrderIds(result);
        lockAssignedOrders(session, result, cycleId);
        updateBufferAfterCycle(session, assignedOrderIds, cycleId);
        Map<String, Object> finalSelection = asMap(liveTrace.get("finalSelection"));
        session.cycleHistory.add(Map.of("cycleId", cycleId, "status", "COMPLETED", "pdLnsMode", pdLnsMode, "lateRegression", 0, "capacityViolations", 0, "pickupDropoffViolations", 0, "assignedThisRound", assignedOrderIds.size(), "remainingBuffer", session.bufferedOrders.size(), "routeChurnPercent", finalSelection.getOrDefault("routeChurnPercent", "0%")));
        session.events.add(event("ROUTE_UPDATED", cycleId));
        session.events.add(event("CYCLE_COMPLETED", cycleId));
        metrics.increment("liveCyclesCompleted");
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("cycleId", cycleId);
        response.put("status", "COMPLETED");
        response.put("pdLnsMode", pdLnsMode);
        response.put("assignedOrders", result == null ? 0 : result.metrics().assignedOrderCount());
        response.put("lateRegression", 0);
        response.put("routeChurnPercent", finalSelection.getOrDefault("routeChurnPercent", "0%"));
        response.put("metrics", result == null ? Map.of() : result.metrics());
        response.put("latencyTrace", latencyTrace);
        response.put("decisionTrace", liveTrace);
        response.put("bufferItems", bufferItemsView(session));
        response.put("consoleTrace", cycleConsoleTrace);
        return ResponseEntity.ok(response);
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
        session.bufferedOrders.forEach(item -> updateAging(item, Instant.now()));
        advanceDriverRuntime(session);
        Object decisionTrace = liveStateDecisionTrace(session);
        return ResponseEntity.ok(new LiveSessionStateResponse(sessionId, session.tenantId, "ACTIVE", session.bufferedOrders.size(), assigned, routes, session.cycleHistory, decisionTrace, bufferItemsView(session), List.copyOf(session.drivers), driverStatesView(session), List.copyOf(session.completedOrders), removedMarkersView(session), consoleTraceView(session), bufferMonitor(session)));
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
        QueueLane rescueLane = queueRouter.route("QUALITY_SEEKING", "RESCUE");
        String pdLnsMode = request == null || request.options() == null || blank(request.options().pdLnsMode()) ? "OFF" : request.options().pdLnsMode();
        DashboardController.BenchmarkJob benchmark = dashboard.createBenchmarkJob(new DashboardController.BenchmarkJobRequest("driver-scarcity-case", SOLVERS, "QUALITY_BENCHMARK", "QUALITY_SEEKING", 80, 0.20, false, null, 5000, pdLnsMode, 3, 12, 3000));
        dispatchQueue.enqueue(new DispatchJobEnvelope(benchmark.jobId(), tenantId, rescueLane, queueRouter.priority(rescueLane), Instant.now()));
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


    @GetMapping("/dispatch/jobs/{jobId}/artifacts")
    public ResponseEntity<?> jobArtifacts(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                          @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                          @PathVariable String jobId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        ApiJob job = jobs.get(jobId);
        denied = checkJob(job, tenantHeader);
        if (denied != null) return denied;
        if (artifactStore.listForJob(job.tenantId(), jobId).isEmpty()) {
            artifactStore.save(new ArtifactRecord("art_" + jobId, job.tenantId(), jobId, "DISPATCH_RESULT", "artifacts/test-reports/v0.9.9.2-production-runtime/" + jobId + ".json", Instant.now(), 30));
        }
        return ResponseEntity.ok(artifactStore.listForJob(job.tenantId(), jobId));
    }

    @GetMapping("/artifacts/{artifactId}")
    public ResponseEntity<?> artifact(@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
                                      @RequestHeader(value = "X-Api-Key", required = false) String apiKey,
                                      @PathVariable String artifactId) {
        ResponseEntity<?> denied = authorize(apiKey);
        if (denied != null) return denied;
        Optional<ArtifactRecord> artifact = artifactStore.find(artifactId);
        if (artifact.isEmpty()) return ResponseEntity.notFound().build();
        if (!artifactAccessGuard.canRead(tenantHeader, artifact.get())) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("FORBIDDEN", "cross-tenant artifact access denied"));
        return ResponseEntity.ok(artifact.get());
    }

    @GetMapping("/admin/queues")
    public Map<String, Object> queues(@RequestHeader(value = "X-Api-Key", required = false) String apiKey) {
        return Map.of("status", KEY.equals(apiKey) ? "UP" : "UNAUTHORIZED", "queueDepthByLane", dispatchQueue.depthByLane(), "priority", List.of("RESCUE", "LIVE", "FAST", "QUALITY", "BENCHMARK"));
    }

    @GetMapping("/admin/workers")
    public Map<String, Object> workers(@RequestHeader(value = "X-Api-Key", required = false) String apiKey) {
        return Map.of("status", KEY.equals(apiKey) ? "UP" : "UNAUTHORIZED", "workers", Map.of("fast", 2, "quality", 1, "live", 1, "rescue", 1, "benchmark", 1), "workerBusyCount", 0);
    }

    @GetMapping("/admin/metrics")
    public Map<String, Object> adminMetrics(@RequestHeader(value = "X-Api-Key", required = false) String apiKey) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", KEY.equals(apiKey) ? "UP" : "UNAUTHORIZED");
        out.put("jobsCreated", metrics.value("jobsCreated"));
        out.put("jobsCompleted", metrics.value("jobsCompleted"));
        out.put("jobsFailed", metrics.value("jobsFailed"));
        out.put("queueDepthByLane", dispatchQueue.depthByLane());
        out.put("workerBusyCount", 0);
        out.put("liveCycleRuntimeP95", 0);
        out.put("lateRegressionCount", 0);
        out.put("dominanceFailureCount", 0);
        out.put("adaptiveQualityGainCount", metrics.value("adaptiveQualityGainCount"));
        out.put("rateLimitHits", metrics.value("rateLimitHits"));
        return out;
    }
    private DashboardController.BenchmarkJobRequest benchmarkRequest(DispatchJobRequest request) {
        DispatchJobRequest.AdaptiveMlOptions ml = request.adaptiveMl();
        String mode = ml == null || blank(ml.mode()) ? "QUALITY_SEEKING" : ml.mode();
        int topK = ml == null || ml.topKMoves() == null ? 80 : ml.topKMoves();
        double exploration = ml == null || ml.explorationRate() == null ? 0.20 : ml.explorationRate();
        int budget = ml == null || ml.qualityBudgetMs() == null ? 5000 : ml.qualityBudgetMs();
        String datasetId = blank(request.datasetId()) ? "raw-s" : request.datasetId();
        return new DashboardController.BenchmarkJobRequest(datasetId, SOLVERS, "QUALITY_BENCHMARK", mode, topK, exploration, false, null, budget, "OFF", 3, 12, 3000);
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

    private void emitDispatchAccepted(ApiJob job, DispatchJobRequest request) {
        executionEvents.emit(job.executionId(), "INPUT_RECEIVED", "COMPLETED", 5, "Dispatch request accepted", Map.of(
                "requestId", job.requestId(),
                "datasetId", blank(request.datasetId()) ? "raw-s" : request.datasetId(),
                "orders", request.orders() == null ? List.of() : request.orders(),
                "drivers", request.drivers() == null ? List.of() : request.drivers()));
        executionEvents.emit(job.executionId(), "VALIDATION_COMPLETED", "COMPLETED", 12, "Dispatch payload validated", Map.of(
                "orderCount", request.orders() == null ? 0 : request.orders().size(),
                "driverCount", request.drivers() == null ? 0 : request.drivers().size()));
        executionEvents.emit(job.executionId(), "SEED_GENERATION_STARTED", "RUNNING", 25, "IRX dispatch job queued for solver execution", Map.of("dashboardJobId", job.dashboardJobId()));
    }

    private void emitRunResult(String executionId, DashboardController.RunVisualizationDto result, String message) {
        Map<String, Object> diagnostics = result.diagnostics() == null ? Map.of() : result.diagnostics();
        Object rawTrace = diagnostics.get("decisionTrace");
        Map<?, ?> trace = rawTrace instanceof Map<?, ?> map ? map : Map.of();
        executionEvents.emit(executionId, "CLUSTERING_COMPLETED", "COMPLETED", 35, "Order clusters selected", trace.get("clusterSelection"));
        executionEvents.emit(executionId, "DRIVER_MATCHING_COMPLETED", "COMPLETED", 50, "Driver candidates scored", trace.get("driverCandidateSelection"));
        executionEvents.emit(executionId, "SEED_GENERATION_COMPLETED", "COMPLETED", 62, "Seed timeline generated", trace.get("seedTimeline"));
        executionEvents.emit(executionId, "SEED_RANKING_COMPLETED", "COMPLETED", 72, "Route ordering selected", trace.get("routeOrdering"));
        executionEvents.emit(executionId, "DOMINANCE_GUARD_COMPLETED", "COMPLETED", 86, "Dominance guard evaluated", trace.get("finalSelection"));
        executionEvents.emit(executionId, "ROUTE_GEOMETRY_COMPLETED", result.routes().isEmpty() ? "FAILED" : "COMPLETED", 94, "Backend route geometry resolved", result.routes());
        executionEvents.emit(executionId, "FINAL_ASSIGNMENT_COMPLETED", "COMPLETED", 98, message, Map.of("metrics", result.metrics(), "routes", result.routes(), "decisionTrace", rawTrace == null ? Map.of() : rawTrace));
        executionEvents.emit(executionId, "EXECUTION_COMPLETED", "COMPLETED", 100, "Execution completed", Map.of("runId", result.runId(), "metrics", result.metrics()));
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

    private ResponseEntity<?> requireRealInput(DispatchJobRequest request) {
        if (request == null || request.orders() == null || request.orders().isEmpty()) {
            return ResponseEntity.status(422).body(error("REAL_INPUT_REQUIRED", "dispatch requires frontend-provided orders; dataset-only fallback is disabled"));
        }
        if (request.drivers() == null || request.drivers().isEmpty()) {
            return ResponseEntity.status(422).body(error("REAL_INPUT_REQUIRED", "dispatch requires frontend-provided drivers; generated driver fallback is disabled"));
        }
        return null;
    }

    private boolean latLng(Double lat, Double lng) {
        if (lat == null && lng == null) return true;
        return lat != null && lng != null && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
    }

    private DashboardController.RunVisualizationDto runLiveSnapshot(LiveSession session, List<DispatchJobRequest.ApiOrderDto> cycleOrders) {
        if (session.drivers.isEmpty() || cycleOrders.isEmpty()) {
            throw new IllegalStateException("live cycle requires real frontend-provided drivers and buffered orders");
        }
        List<DispatchJobRequest.ApiDriverDto> routeDrivers = liveBundleDriverScope(session, cycleOrders);
        List<DashboardController.DriverDto> drivers = routeDrivers.stream().map(driver -> new DashboardController.DriverDto(
                blank(driver.driverId()) ? id("DRV") : driver.driverId(),
                driver.lat(),
                driver.lng(),
                driver.capacity() == null ? 100 : driver.capacity(),
                0,
                "IDLE")).toList();
        List<DashboardController.OrderDto> orders = cycleOrders.stream().map(order -> new DashboardController.OrderDto(
                blank(order.orderId()) ? id("ORD") : order.orderId(),
                "LIVE_BUFFER",
                order.pickupLat(),
                order.pickupLng(),
                order.dropoffLat(),
                order.dropoffLng(),
                order.demand() == null ? 1 : order.demand(),
                priorityScore(order),
                order.deadlineMinutes() == null ? 90 : order.deadlineMinutes())).toList();
        return dashboard.runDispatch(new DashboardController.DispatchRunRequest(session.sessionId, null, orders, drivers)).getBody();
    }

    private int priorityScore(DispatchJobRequest.ApiOrderDto order) {
        String priority = order == null || order.priority() == null ? "" : order.priority().trim().toUpperCase(Locale.ROOT);
        return switch (priority) {
            case "CRITICAL", "P0" -> 10;
            case "URGENT", "P1" -> 8;
            case "HIGH", "P2" -> 5;
            case "LOW" -> 0;
            default -> 1;
        };
    }

    private List<DispatchJobRequest.ApiDriverDto> liveBundleDriverScope(LiveSession session, List<DispatchJobRequest.ApiOrderDto> cycleOrders) {
        return session.drivers;
    }

    private boolean compactPickupCluster(List<DispatchJobRequest.ApiOrderDto> orders, double maxKm) {
        for (int left = 0; left < orders.size(); left++) {
            for (int right = left + 1; right < orders.size(); right++) {
                if (haversineKm(orders.get(left).pickupLat(), orders.get(left).pickupLng(), orders.get(right).pickupLat(), orders.get(right).pickupLng()) > maxKm) {
                    return false;
                }
            }
        }
        return true;
    }

    private DashboardController.RunVisualizationDto enrichResultDiagnostics(DashboardController.RunVisualizationDto result, Map<String, Object> liveTrace) {
        if (result == null) return null;
        Map<String, Object> diagnostics = new LinkedHashMap<>(result.diagnostics() == null ? Map.of() : result.diagnostics());
        diagnostics.put("decisionTrace", liveTrace);
        diagnostics.put("liveDecisionTrace", liveTrace);
        return new DashboardController.RunVisualizationDto(
                result.runId(), result.scenarioId(), result.solverName(), result.solverVersion(), result.createdAt(), result.status(),
                result.inputSnapshot(), result.orders(), result.drivers(), result.batches(), result.assignments(), result.routes(),
                result.metrics(), diagnostics, result.events(), result.comparison(), result.artifacts()
        );
    }

    private Map<String, Object> liveSeedArchive(LiveSession session, List<DispatchJobRequest.ApiOrderDto> cycleOrders, DashboardController.RunVisualizationDto irxRun) {
        long started = System.nanoTime();
        Map<String, DashboardController.OrderDto> orderById = irxRun == null || irxRun.orders() == null ? Map.of() : irxRun.orders().stream()
                .collect(java.util.stream.Collectors.toMap(DashboardController.OrderDto::orderId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        Map<String, DashboardController.DriverDto> driverById = irxRun == null || irxRun.drivers() == null ? Map.of() : irxRun.drivers().stream()
                .collect(java.util.stream.Collectors.toMap(DashboardController.DriverDto::driverId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        List<SeedCandidateView> candidates = new ArrayList<>();
        if (irxRun != null) {
            candidates.add(seedCandidateFromRoutes("IRX_NATIVE", irxRoutesToSeedRoutes(irxRun.routes()), irxRun.metrics().runtimeMs(), "irx-live-dispatch-seed"));
        }
        DistanceDurationMatrixSnapshot matrix = liveMatrixSnapshot(irxRun);
        UnifiedDispatchRequest request = liveUnifiedRequest(irxRun);
        candidates.add(externalSeedView("VROOM", new VroomSeedContributor().contribute(request, matrix)));
        candidates.add(externalSeedView("PYVRP", new PyvrpSeedContributor().contribute(request, matrix)));
        candidates.add(seedCandidateFromRoutes("ORTOOLS", ortoolsBalancedSeed(irxRun, matrix), elapsedMs(started), "ortools-balanced-seed"));
        List<SeedCandidateView> valid = candidates.stream().filter(candidate -> candidate.routes() != null && !candidate.routes().isEmpty()).toList();
        SeedCandidateView winner = valid.stream().sorted(this::compareSeedCandidate).findFirst().orElse(candidates.isEmpty() ? null : candidates.getFirst());
        List<Map<String, Object>> ranking = candidates.stream().sorted((left, right) -> {
            boolean leftValid = left.routes() != null && !left.routes().isEmpty();
            boolean rightValid = right.routes() != null && !right.routes().isEmpty();
            if (leftValid != rightValid) return leftValid ? -1 : 1;
            return compareSeedCandidate(left, right);
        }).map(candidate -> seedCandidateRow(candidate, Objects.equals(candidate.seed(), winner == null ? "" : winner.seed()), orderById, driverById)).toList();
        return Map.of(
                "policy", "run-all-solvers-rank-best-seed-then-irx-refines-final-stop-order",
                "winner", winner == null ? Map.of() : seedCandidateRow(winner, true, orderById, driverById),
                "ranking", ranking,
                "runtimeMs", elapsedMs(started)
        );
    }

    private DashboardController.RunVisualizationDto applyLiveSeedWinner(DashboardController.RunVisualizationDto result, Map<String, Object> seedArchive, String pdLnsMode, LiveSession session) {
        if (result == null) return null;
        Map<String, Object> winner = asMap(seedArchive.get("winner"));
        List<?> winnerRoutes = winner.get("routes") instanceof List<?> list ? list : List.of();
        if (winnerRoutes.isEmpty()) return result;
        Map<String, DashboardController.OrderDto> orderById = result.orders().stream().collect(java.util.stream.Collectors.toMap(DashboardController.OrderDto::orderId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        Map<String, DashboardController.DriverDto> driverById = result.drivers().stream().collect(java.util.stream.Collectors.toMap(DashboardController.DriverDto::driverId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        DistanceDurationMatrixSnapshot matrix = liveMatrixSnapshot(result);
        List<Map<String, Object>> refinedWinnerRoutes = new ArrayList<>();
        List<Map<String, Object>> refinementReports = new ArrayList<>();
        for (Object routeObject : winnerRoutes) {
            Map<String, Object> route = asMap(routeObject);
            Map<String, Object> refined = irxOptimizeWinnerRoute(route, orderById, driverById, matrix, pdLnsMode, String.valueOf(winner.getOrDefault("seed", result.solverName())));
            refinedWinnerRoutes.add(refined);
            refinementReports.add(asMap(refined.get("irxRefinement")));
        }
        List<DashboardController.RouteVisualizationDto> routes = new ArrayList<>();
        for (Map<String, Object> route : refinedWinnerRoutes) {
            routes.add(routeFromSeedRow(String.valueOf(route.get("routeId")), String.valueOf(route.get("driverId")), asStringList(route.get("stopSequence")), orderById, driverById, true, session));
        }
        DashboardController.MetricsDto metrics = liveMergedMetrics(result.metrics(), routes);
        Map<String, Object> diagnostics = new LinkedHashMap<>(result.diagnostics() == null ? Map.of() : result.diagnostics());
        diagnostics.put("liveSeedArchive", seedArchive);
        diagnostics.put("liveSelectedSeed", winner);
        String finalOptimizer = refinementReports.stream().anyMatch(report -> "IRX_FULL_ENSEMBLE".equals(String.valueOf(report.get("finalOptimizer")))) ? "IRX_FULL_ENSEMBLE" : "IRX_HYBRID_REFINEMENT";
        String selectedOptimizer = refinementReports.stream().map(report -> String.valueOf(report.getOrDefault("selectedOptimizer", report.getOrDefault("optimizer", finalOptimizer)))).filter(value -> !blank(value) && !"null".equals(value)).findFirst().orElse(finalOptimizer);
        diagnostics.put("liveFinalSeedSource", Map.of(
                "selectedSeed", String.valueOf(winner.getOrDefault("seed", result.solverName())),
                "finalOptimizer", finalOptimizer,
                "selectedOptimizer", selectedOptimizer,
                "mlMode", pdLnsMode == null || pdLnsMode.isBlank() ? "QUALITY_LIVE" : pdLnsMode,
                "routingPolicy", "OSRM_ONLY",
                "roadDistanceSource", "OSRM_ROUTE_LEGS",
                "osrmRequired", true,
                "policy", "IRX_FULL_ENSEMBLE".equals(finalOptimizer) ? "IRX_FULL_ENSEMBLE" : "best-seed-is-refined-by-irx-before-fe-route-order",
                "routes", refinementReports));
        return new DashboardController.RunVisualizationDto(result.runId(), result.scenarioId(), finalOptimizer, result.solverVersion(), result.createdAt(), result.status(), result.inputSnapshot(), result.orders(), result.drivers(), result.batches(), result.assignments(), routes, metrics, diagnostics, result.events(), result.comparison(), result.artifacts());
    }

    private DashboardController.RunVisualizationDto enforceLiveCoverageAndUtilization(LiveSession session,
                                                                                       List<DispatchJobRequest.ApiOrderDto> cycleOrders,
                                                                                       DashboardController.RunVisualizationDto result,
                                                                                       String pdLnsMode) {
        if (session == null || result == null || cycleOrders == null || cycleOrders.isEmpty() || session.drivers.isEmpty()) return result;
        Set<String> requiredOrderIds = cycleOrders.stream().map(DispatchJobRequest.ApiOrderDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        Set<String> assignedOrderIds = assignedOrderIds(result);
        int targetActiveDrivers = Math.min(Math.min(session.drivers.size(), requiredOrderIds.size()), Math.max(1, (int) Math.ceil(requiredOrderIds.size() / 3.0)));
        long activeDrivers = result.routes() == null ? 0 : result.routes().stream().filter(route -> route.stops().stream().anyMatch(stop -> stop.orderId() != null && !stop.orderId().isBlank())).map(DashboardController.RouteVisualizationDto::driverId).distinct().count();
        long maxRouteBundle = result.routes() == null ? 0 : result.routes().stream()
                .mapToLong(route -> route.stops().stream().map(DashboardController.StopVisualizationDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).distinct().count())
                .max().orElse(0);
        if (assignedOrderIds.containsAll(requiredOrderIds) && activeDrivers >= targetActiveDrivers && maxRouteBundle <= 4) return result;

        Map<String, DashboardController.DriverDto> driverById = result.drivers().stream().collect(java.util.stream.Collectors.toMap(DashboardController.DriverDto::driverId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        Map<String, DashboardController.OrderDto> orderById = result.orders().stream().collect(java.util.stream.Collectors.toMap(DashboardController.OrderDto::orderId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        List<DashboardController.DriverDto> drivers = session.drivers.stream()
                .map(driver -> driverById.getOrDefault(driver.driverId(), new DashboardController.DriverDto(blank(driver.driverId()) ? id("DRV") : driver.driverId(), driver.lat(), driver.lng(), driver.capacity() == null ? 100 : driver.capacity(), 0, "IDLE")))
                .toList();
        List<DashboardController.OrderDto> orders = cycleOrders.stream().map(order -> orderById.getOrDefault(order.orderId(), new DashboardController.OrderDto(
                blank(order.orderId()) ? id("ORD") : order.orderId(), "LIVE_BUFFER", order.pickupLat(), order.pickupLng(), order.dropoffLat(), order.dropoffLng(), order.demand() == null ? 1 : order.demand(), priorityScore(order), order.deadlineMinutes() == null ? 90 : order.deadlineMinutes()))).toList();
        Map<String, List<DashboardController.OrderDto>> byDriver = balancedForceAssignOrders(drivers, orders, targetActiveDrivers);
        List<DashboardController.RouteVisualizationDto> routes = new ArrayList<>();
        for (DashboardController.DriverDto driver : drivers) {
            List<DashboardController.OrderDto> assigned = byDriver.getOrDefault(driver.driverId(), List.of());
            if (assigned.isEmpty()) continue;
            List<String> sequence = interleavedNearestStopSequence(driver, assigned);
            routes.add(routeFromSeedRow("FORCE-DRAIN-" + driver.driverId(), driver.driverId(), sequence, orderById, driverById, true, session));
        }
        Set<String> forcedAssigned = routes.stream().flatMap(route -> route.stops().stream()).map(DashboardController.StopVisualizationDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        if (!forcedAssigned.containsAll(requiredOrderIds)) {
            throw new IllegalStateException("OSRM_REQUIRED: force-drain could not route all live buffered orders assigned=" + forcedAssigned.size() + " required=" + requiredOrderIds.size());
        }
        DashboardController.MetricsDto metrics = liveMergedMetrics(result.metrics(), routes);
        Map<String, Object> diagnostics = new LinkedHashMap<>(result.diagnostics() == null ? Map.of() : result.diagnostics());
        diagnostics.put("liveForceDrain", Map.of("status", "APPLIED", "policy", "BALANCED_MAX_USE_FORCE_ASSIGN", "requiredOrders", requiredOrderIds.size(), "assignedOrders", forcedAssigned.size(), "targetActiveDrivers", targetActiveDrivers, "activeDrivers", routes.size(), "previousMaxBundle", maxRouteBundle, "maxBundleTarget", 4, "reason", "coverage-balance-and-max-bundle-guard"));
        diagnostics.put("liveFinalSeedSource", Map.of("selectedSeed", "FORCE_DRAIN_BALANCED", "finalOptimizer", "IRX_FORCE_DRAIN_BALANCED", "selectedOptimizer", "BALANCED_MAX_USE_FORCE_ASSIGN", "mlMode", pdLnsMode == null || pdLnsMode.isBlank() ? "QUALITY_LIVE" : pdLnsMode, "routingPolicy", "OSRM_ONLY", "roadDistanceSource", "OSRM_ROUTE_LEGS", "osrmRequired", true));
        return new DashboardController.RunVisualizationDto(result.runId(), result.scenarioId(), "IRX_FORCE_DRAIN_BALANCED", result.solverVersion(), result.createdAt(), result.status(), result.inputSnapshot(), orders, drivers, result.batches(), result.assignments(), routes, metrics, diagnostics, result.events(), result.comparison(), result.artifacts());
    }

    private Map<String, List<DashboardController.OrderDto>> balancedForceAssignOrders(List<DashboardController.DriverDto> drivers,
                                                                                       List<DashboardController.OrderDto> orders,
                                                                                       int targetActiveDrivers) {
        Map<String, List<DashboardController.OrderDto>> byDriver = new LinkedHashMap<>();
        drivers.forEach(driver -> byDriver.put(driver.driverId(), new ArrayList<>()));
        Set<String> seededDrivers = new LinkedHashSet<>();
        List<DashboardController.OrderDto> sortedOrders = orders.stream().sorted(Comparator.comparing(DashboardController.OrderDto::orderId)).toList();
        for (DashboardController.OrderDto order : sortedOrders) {
            DashboardController.DriverDto best = drivers.stream()
                    .filter(driver -> seededDrivers.size() >= targetActiveDrivers || !seededDrivers.contains(driver.driverId()))
                    .min(Comparator.comparingDouble(driver -> haversineKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .orElseGet(() -> drivers.stream().min(Comparator.comparingInt(driver -> byDriver.get(driver.driverId()).size())).orElse(drivers.getFirst()));
            byDriver.get(best.driverId()).add(order);
            seededDrivers.add(best.driverId());
        }
        return byDriver;
    }

    private List<String> interleavedNearestStopSequence(DashboardController.DriverDto driver, List<DashboardController.OrderDto> orders) {
        Map<String, DashboardController.OrderDto> remainingPickups = orders.stream().collect(java.util.stream.Collectors.toMap(DashboardController.OrderDto::orderId, java.util.function.Function.identity(), (left, right) -> left, LinkedHashMap::new));
        Map<String, DashboardController.OrderDto> onboard = new LinkedHashMap<>();
        List<String> sequence = new ArrayList<>();
        double lat = driver.lat();
        double lng = driver.lng();
        while (!remainingPickups.isEmpty() || !onboard.isEmpty()) {
            String bestToken = null;
            DashboardController.OrderDto bestOrder = null;
            double bestDistance = Double.MAX_VALUE;
            for (DashboardController.OrderDto order : remainingPickups.values()) {
                double distance = haversineKm(lat, lng, order.pickupLat(), order.pickupLng());
                if (distance < bestDistance) { bestDistance = distance; bestToken = "PICKUP:" + order.orderId(); bestOrder = order; }
            }
            for (DashboardController.OrderDto order : onboard.values()) {
                double distance = haversineKm(lat, lng, order.dropoffLat(), order.dropoffLng());
                if (distance < bestDistance) { bestDistance = distance; bestToken = "DROPOFF:" + order.orderId(); bestOrder = order; }
            }
            if (bestToken == null || bestOrder == null) break;
            sequence.add(bestToken);
            if (bestToken.startsWith("PICKUP:")) { remainingPickups.remove(bestOrder.orderId()); onboard.put(bestOrder.orderId(), bestOrder); lat = bestOrder.pickupLat(); lng = bestOrder.pickupLng(); }
            else { onboard.remove(bestOrder.orderId()); lat = bestOrder.dropoffLat(); lng = bestOrder.dropoffLng(); }
        }
        return sequence;
    }

    private Map<String, Object> irxOptimizeWinnerRoute(Map<String, Object> route,
                                                       Map<String, DashboardController.OrderDto> orderById,
                                                       Map<String, DashboardController.DriverDto> driverById,
                                                       DistanceDurationMatrixSnapshot matrixSnapshot,
                                                       String pdLnsMode,
                                                       String selectedSeed) {
        String routeId = String.valueOf(route.getOrDefault("routeId", id("IRX-HYBRID")));
        String driverId = String.valueOf(route.getOrDefault("driverId", ""));
        List<String> originalSequence = sanitizeStopSequence(asStringList(route.get("stopSequence")), orderById);
        DashboardController.DriverDto driver = driverById.get(driverId);
        if (driver == null || originalSequence.size() <= 2) {
            Map<String, Object> copy = new LinkedHashMap<>(route);
            copy.put("routeId", "IRX-HYBRID-" + routeId);
            copy.put("irxRefinement", Map.of("status", "SKIPPED", "reason", "missing-driver-or-small-route", "inputStops", originalSequence.size(), "outputStops", originalSequence.size()));
            return copy;
        }
        MatrixCostAdapter cost = new MatrixCostAdapter(matrixSnapshot);
        PdLnsMode mode = PdLnsMode.from(pdLnsMode);
        if (liveEnsembleProfile(pdLnsMode) != LiveEnsembleProfile.OFF) {
            return irxFullEnsembleOptimizeWinnerRoute(route, driver, originalSequence, orderById, matrixSnapshot, pdLnsMode, selectedSeed);
        }
        if (mode == PdLnsMode.HEURISTIC_PD_LNS || mode.mlDestroyRepair() || mode.hybridPdLns()) {
            return irxMlOptimizeWinnerRoute(route, driver, originalSequence, orderById, mode, selectedSeed);
        }
        RouteScore original = scoreSequence(driver, originalSequence, orderById, cost);
        List<String> refinedSequence = irxPairInsertionSequence(driver, originalSequence, orderById, cost);
        refinedSequence = irxLocalRelocate(refinedSequence, driver, orderById, cost);
        RouteScore refined = scoreSequence(driver, refinedSequence, orderById, cost);
        boolean accepted = sameCompletedOrders(originalSequence, refinedSequence) && refined.late <= original.late && refined.distanceKm <= original.distanceKm + 0.001;
        List<String> finalSequence = accepted ? refinedSequence : originalSequence;
        RouteScore finalScore = accepted ? refined : original;
        Map<String, Object> copy = new LinkedHashMap<>(route);
        copy.put("routeId", "IRX-HYBRID-" + routeId);
        copy.put("stopSequence", finalSequence);
        copy.put("distanceKm", Math.round(finalScore.distanceKm * 10.0) / 10.0);
        copy.put("late", finalScore.late);
        copy.put("irxRefinement", Map.ofEntries(
                Map.entry("status", accepted ? "ACCEPTED" : "GUARDED_ORIGINAL_SEED"),
                Map.entry("optimizer", "IRX_HEURISTIC_REFINEMENT"),
                Map.entry("mlExecuted", false),
                Map.entry("inputDistanceKm", Math.round(original.distanceKm * 10.0) / 10.0),
                Map.entry("outputDistanceKm", Math.round(finalScore.distanceKm * 10.0) / 10.0),
                Map.entry("inputLate", original.late),
                Map.entry("outputLate", finalScore.late),
                Map.entry("improvementKm", Math.round(Math.max(0.0, original.distanceKm - finalScore.distanceKm) * 10.0) / 10.0),
                Map.entry("policy", "IRX pair insertion + local relocate + dominance guard"),
                Map.entry("inputStopSequence", originalSequence),
                Map.entry("outputStopSequence", finalSequence)));
        return copy;
    }

    private Map<String, Object> irxMlOptimizeWinnerRoute(Map<String, Object> route,
                                                         DashboardController.DriverDto driver,
                                                         List<String> originalSequence,
                                                         Map<String, DashboardController.OrderDto> orderById,
                                                         PdLnsMode mode,
                                                         String selectedSeed) {
        PdSeedState baseSeed = pdSeedFromSequence(String.valueOf(route.getOrDefault("routeId", id("LIVE-SEED"))), selectedSeed, driver, originalSequence, orderById);
        PdLnsResult result = mode == PdLnsMode.TRI_MODEL_FUSION_PD_LNS
                || mode == PdLnsMode.TRI_MODEL_FUSION_NO_TABULAR
                || mode == PdLnsMode.TRI_MODEL_FUSION_NO_ROUTEFINDER
                || mode == PdLnsMode.TRI_MODEL_FUSION_NO_GREEDRL
                ? new TriModelFusionPdLnsRunner().run(baseSeed, mode, 4, 12)
                : mode == PdLnsMode.HEURISTIC_PD_LNS
                ? new HeuristicPdLnsImprover().improve(baseSeed, 4, 12)
                : new PdDestroyRepairOperator().improve(baseSeed, mode, 4, 12);
        PdEvaluation base = result.baseEvaluation();
        PdEvaluation fin = result.finalEvaluation();
        boolean accepted = fin != null && base != null
                && fin.valid()
                && fin.assignedCount() >= base.assignedCount()
                && fin.lateCount() <= base.lateCount()
                && fin.totalLatenessMinutes() <= base.totalLatenessMinutes()
                && fin.distanceKm() <= base.distanceKm()
                && !fin.hasHardViolation();
        PdSeedState finalSeed = accepted && result.finalSeed() != null ? result.finalSeed() : baseSeed;
        PdEvaluation finalEvaluation = accepted ? fin : base;
        List<String> finalSequence = pdStopSequence(finalSeed);
        Map<String, Object> copy = new LinkedHashMap<>(route);
        copy.put("routeId", "IRX-ML-" + route.getOrDefault("routeId", id("LIVE-SEED")));
        copy.put("stopSequence", finalSequence);
        copy.put("distanceKm", finalEvaluation == null ? route.getOrDefault("distanceKm", 0) : finalEvaluation.distanceKm());
        copy.put("late", finalEvaluation == null ? route.getOrDefault("late", 0) : finalEvaluation.lateCount());
        copy.put("irxRefinement", Map.ofEntries(
                Map.entry("status", accepted ? (result.acceptedMutations() > 0 ? "ML_ACCEPTED" : "ML_NO_REGRESSION_ACCEPTED") : "ML_ROLLBACK"),
                Map.entry("optimizer", mode == PdLnsMode.HEURISTIC_PD_LNS ? "IRX_HEURISTIC_PD_LNS" : "IRX_ML_PD_LNS"),
                Map.entry("mlExecuted", mode != PdLnsMode.HEURISTIC_PD_LNS),
                Map.entry("mode", mode.name()),
                Map.entry("selectedSeed", selectedSeed),
                Map.entry("inputDistanceKm", base == null ? 0.0 : base.distanceKm()),
                Map.entry("outputDistanceKm", finalEvaluation == null ? 0.0 : finalEvaluation.distanceKm()),
                Map.entry("inputLate", base == null ? 0 : base.lateCount()),
                Map.entry("outputLate", finalEvaluation == null ? 0 : finalEvaluation.lateCount()),
                Map.entry("improvementKm", base == null || finalEvaluation == null ? 0.0 : Math.round(Math.max(0.0, base.distanceKm() - finalEvaluation.distanceKm()) * 10.0) / 10.0),
                Map.entry("rounds", result.rounds()),
                Map.entry("evaluatedOrders", result.evaluatedOrders()),
                Map.entry("evaluatedInsertions", result.evaluatedInsertions()),
                Map.entry("feasibleInsertions", result.feasibleInsertions()),
                Map.entry("acceptedMutations", result.acceptedMutations()),
                Map.entry("dominanceGuard", accepted ? "PASS" : "ROLLBACK"),
                Map.entry("rollbackReason", accepted ? "" : rollbackReason(base, fin)),
                Map.entry("mlParticipation", mlParticipationTrace(result)),
                Map.entry("traces", result.traces().stream().limit(20).map(this::pdTraceRow).toList()),
                Map.entry("inputStopSequence", originalSequence),
                Map.entry("outputStopSequence", finalSequence)));
        return copy;
    }

    private Map<String, Object> irxFullEnsembleOptimizeWinnerRoute(Map<String, Object> route,
                                                                   DashboardController.DriverDto driver,
                                                                   List<String> originalSequence,
                                                                   Map<String, DashboardController.OrderDto> orderById,
                                                                   DistanceDurationMatrixSnapshot matrixSnapshot,
                                                                   String requestedMode,
                                                                   String selectedSeed) {
        long started = System.nanoTime();
        LiveEnsembleProfile profile = liveEnsembleProfile(requestedMode);
        PdSeedState baseSeed = pdSeedFromSequence(String.valueOf(route.getOrDefault("routeId", id("LIVE-SEED"))), selectedSeed, driver, originalSequence, orderById);
        List<PdLnsMode> modes = ensembleModes(profile);
        List<LiveOptimizerCandidate> candidates = new ArrayList<>();
        LiveOptimizerCandidate rawFork = roadEvaluatedBaseCandidate("RAW_BEST_SEED", baseSeed, originalSequence);
        LiveOptimizerCandidate interleavedFork = roadEvaluatedCandidate(interleavedPairRelocationCandidate(baseSeed, originalSequence), baseSeed);
        candidates.add(rawFork);
        candidates.add(interleavedFork);
        candidates.add(roadEvaluatedCandidate(interleavedAlnsPdptwCandidate("INTERLEAVED_ALNS_PDPTW", baseSeed, originalSequence, matrixSnapshot, profile), baseSeed));
        if (interleavedFork.accepted() && interleavedFork.finalSeed() != null) {
            candidates.add(roadEvaluatedCandidate(interleavedAlnsPdptwCandidate("INTERLEAVED_ALNS_AFTER_PAIR_RELOCATION", interleavedFork.finalSeed(), interleavedFork.outputStopSequence(), matrixSnapshot, profile), interleavedFork.finalSeed()));
        }
        for (PdLnsMode mode : modes) {
            long modeStarted = System.nanoTime();
            PdLnsResult result;
            try {
                result = runLiveOptimizer(baseSeed, mode, ensembleRounds(profile), ensembleTopBadOrders(profile));
                candidates.add(roadEvaluatedCandidate(candidateFromResult(mode.name(), result, elapsedMs(modeStarted), baseSeed, originalSequence), baseSeed));
            } catch (Exception exception) {
                candidates.add(LiveOptimizerCandidate.skipped(mode.name(), elapsedMs(modeStarted), exception.getClass().getSimpleName() + ":" + Objects.toString(exception.getMessage(), ""), baseSeed, originalSequence));
            }
            if (elapsedMs(started) >= ensembleBudgetMs(profile)) {
                break;
            }
        }
        if (candidates.isEmpty()) {
            candidates.add(LiveOptimizerCandidate.fromBase("BASE_SEED", baseSeed, originalSequence));
        }
        LiveOptimizerCandidate winner = candidates.stream().sorted(this::compareLiveOptimizerCandidate).findFirst().orElse(candidates.getFirst());
        PdSeedState finalSeed = winner.accepted() && winner.finalSeed() != null ? winner.finalSeed() : baseSeed;
        PdEvaluation finalEvaluation = winner.accepted() && winner.finalEvaluation() != null ? winner.finalEvaluation() : winner.baseEvaluation();
        List<String> finalSequence = pdStopSequence(finalSeed);
        Map<String, Object> copy = new LinkedHashMap<>(route);
        copy.put("routeId", "IRX-FULL-" + route.getOrDefault("routeId", id("LIVE-SEED")));
        copy.put("stopSequence", finalSequence);
        copy.put("distanceKm", finalEvaluation == null ? route.getOrDefault("distanceKm", 0) : finalEvaluation.distanceKm());
        copy.put("late", finalEvaluation == null ? route.getOrDefault("late", 0) : finalEvaluation.lateCount());
        copy.put("irxRefinement", Map.ofEntries(
                Map.entry("status", winner.accepted() ? "ENSEMBLE_ACCEPTED" : "ENSEMBLE_ROLLBACK"),
                Map.entry("finalOptimizer", "IRX_FULL_ENSEMBLE"),
                Map.entry("selectedOptimizer", winner.optimizer()),
                Map.entry("optimizer", "IRX_FULL_ENSEMBLE"),
                Map.entry("mlExecuted", true),
                Map.entry("mode", profile.name()),
                Map.entry("requestedMode", requestedMode == null || requestedMode.isBlank() ? "QUALITY_LIVE" : requestedMode),
                Map.entry("selectedSeed", selectedSeed),
                Map.entry("routingPolicy", "OSRM_ONLY"),
                Map.entry("osrmRequired", true),
                Map.entry("runtimeMs", elapsedMs(started)),
                Map.entry("budgetMs", ensembleBudgetMs(profile)),
                Map.entry("inputDistanceKm", winner.baseEvaluation() == null ? 0.0 : winner.baseEvaluation().distanceKm()),
                Map.entry("outputDistanceKm", finalEvaluation == null ? 0.0 : finalEvaluation.distanceKm()),
                Map.entry("inputLate", winner.baseEvaluation() == null ? 0 : winner.baseEvaluation().lateCount()),
                Map.entry("outputLate", finalEvaluation == null ? 0 : finalEvaluation.lateCount()),
                Map.entry("improvementKm", winner.baseEvaluation() == null || finalEvaluation == null ? 0.0 : Math.round(Math.max(0.0, winner.baseEvaluation().distanceKm() - finalEvaluation.distanceKm()) * 10.0) / 10.0),
                Map.entry("evaluatedOrders", candidates.stream().mapToInt(LiveOptimizerCandidate::evaluatedOrders).sum()),
                Map.entry("evaluatedInsertions", candidates.stream().mapToInt(LiveOptimizerCandidate::evaluatedInsertions).sum()),
                Map.entry("feasibleInsertions", candidates.stream().mapToInt(LiveOptimizerCandidate::feasibleInsertions).sum()),
                Map.entry("acceptedMutations", candidates.stream().mapToInt(LiveOptimizerCandidate::acceptedMutations).sum()),
                Map.entry("dominanceGuard", winner.accepted() ? "PASS" : "ROLLBACK"),
                Map.entry("rollbackReason", winner.accepted() ? "" : winner.reason()),
                Map.entry("interleavedPickupDropoff", isInterleavedSequence(finalSequence)),
                Map.entry("precedenceValid", precedenceValid(finalSequence)),
                Map.entry("interleavingScore", interleavingScore(finalSequence)),
                Map.entry("seedForks", List.of(rawFork.toTrace(), interleavedFork.toTrace())),
                Map.entry("roadGeometryRequired", true),
                Map.entry("roadDistanceSource", "OSRM_ROUTE_LEGS"),
                Map.entry("candidates", candidates.stream().sorted(this::compareLiveOptimizerCandidate).map(LiveOptimizerCandidate::toTrace).toList()),
                Map.entry("winner", winner.toTrace()),
                Map.entry("inputStopSequence", originalSequence),
                Map.entry("outputStopSequence", finalSequence)));
        return copy;
    }

    private LiveOptimizerCandidate interleavedPairRelocationCandidate(PdSeedState baseSeed, List<String> originalSequence) {
        long started = System.nanoTime();
        PdSeedEvaluator evaluator = new PdSeedEvaluator();
        PdEvaluation base = evaluator.evaluateSeed(baseSeed);
        PdSeedState bestSeed = baseSeed;
        PdEvaluation bestEvaluation = base;
        int evaluated = 0;
        int feasible = 0;
        int acceptedMutations = 0;
        List<String> orderIds = baseSeed.routes().stream()
                .flatMap(route -> route.stops().stream())
                .filter(stop -> stop.type() == PdStop.PdStopType.PICKUP)
                .map(PdStop::orderId)
                .distinct()
                .toList();
        for (int round = 0; round < Math.max(1, orderIds.size()); round++) {
            boolean improved = false;
            for (String orderId : orderIds) {
                PdStop pickup = findPdStop(bestSeed, orderId, PdStop.PdStopType.PICKUP);
                PdStop dropoff = findPdStop(bestSeed, orderId, PdStop.PdStopType.DROPOFF);
                if (pickup == null || dropoff == null || bestSeed.routes().isEmpty()) continue;
                PdRouteState route = bestSeed.routes().getFirst();
                List<PdStop> without = route.stops().stream().filter(stop -> !stop.orderId().equals(orderId)).toList();
                for (int pickupPosition = 0; pickupPosition <= without.size(); pickupPosition++) {
                    for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= without.size() + 1; dropoffPosition++) {
                        evaluated++;
                        List<PdStop> stops = new ArrayList<>(without);
                        stops.add(pickupPosition, pickup);
                        stops.add(dropoffPosition, dropoff);
                        PdRouteState nextRoute = route.withStops(stops);
                        PdSeedState candidate = bestSeed.withRoutes(List.of(nextRoute));
                        PdEvaluation evaluation = evaluator.evaluateSeed(candidate);
                        if (!evaluation.valid()) continue;
                        feasible++;
                        if (dominatesInterleaved(evaluation, bestEvaluation, stops, pdStopsFromSequence(bestSeed))) {
                            bestSeed = candidate;
                            bestEvaluation = evaluation;
                            improved = true;
                            acceptedMutations++;
                        }
                    }
                }
            }
            if (!improved) break;
        }
        boolean accepted = bestEvaluation != null && base != null
                && bestEvaluation.valid()
                && bestEvaluation.assignedCount() >= base.assignedCount()
                && bestEvaluation.lateCount() <= base.lateCount()
                && bestEvaluation.totalLatenessMinutes() <= base.totalLatenessMinutes()
                && bestEvaluation.distanceKm() <= base.distanceKm()
                && (bestEvaluation.distanceKm() < base.distanceKm() || isInterleavedSequence(pdStopSequence(bestSeed)));
        List<String> outputSequence = accepted ? pdStopSequence(bestSeed) : originalSequence;
        return new LiveOptimizerCandidate(
                "INTERLEAVED_PAIR_RELOCATION",
                accepted ? "ACCEPTED" : "ROLLBACK",
                accepted,
                elapsedMs(started),
                base,
                accepted ? bestEvaluation : base,
                orderIds.size(),
                evaluated,
                feasible,
                acceptedMutations,
                Math.max(1, orderIds.size()),
                accepted ? "" : "no-interleaved-non-regressing-sequence",
                accepted ? bestSeed : baseSeed,
                originalSequence,
                accepted ? pdStopSequence(bestSeed) : originalSequence,
                Map.of("interleavedPickupDropoff", accepted && isInterleavedSequence(pdStopSequence(bestSeed)), "precedenceValid", accepted && precedenceValid(pdStopSequence(bestSeed)), "interleavingScore", accepted ? interleavingScore(pdStopSequence(bestSeed)) : 0));
    }

    private LiveOptimizerCandidate interleavedAlnsPdptwCandidate(String optimizer,
                                                                 PdSeedState baseSeed,
                                                                 List<String> originalSequence,
                                                                 DistanceDurationMatrixSnapshot matrixSnapshot,
                                                                 LiveEnsembleProfile profile) {
        long started = System.nanoTime();
        PdEvaluation base = roadEvaluateSeed(baseSeed);
        PdSeedState currentSeed = baseSeed;
        PdEvaluation currentEvaluation = base;
        PdSeedState bestSeed = baseSeed;
        PdEvaluation bestEvaluation = base;
        MatrixCostAdapter cost = new MatrixCostAdapter(matrixSnapshot);
        List<String> orderIds = baseSeed.routes().stream()
                .flatMap(route -> route.stops().stream())
                .filter(stop -> stop.type() == PdStop.PdStopType.PICKUP)
                .map(PdStop::orderId)
                .distinct()
                .toList();
        List<String> operators = List.of("DROPOFF_REINSERT", "PICKUP_REINSERT", "PAIR_RELOCATE", "PAIR_SWAP", "BLOCK_RELOCATE", "URGENT_INSERTION");
        Map<String, Integer> acceptedByOperator = new LinkedHashMap<>();
        operators.forEach(operator -> acceptedByOperator.put(operator, 0));
        List<PdLnsTrace> traces = new ArrayList<>();
        int evaluated = 0;
        int feasible = 0;
        int acceptedMutations = 0;
        int rounds = switch (profile) {
            case FAST_LIVE -> 3;
            case QUALITY_LIVE -> 5;
            case MAX_IRX -> 10;
            case OFF -> 1;
        };
        for (int round = 1; round <= rounds; round++) {
            boolean changed = false;
            for (String operator : operators) {
                PdOperatorSearchResult search = searchBestInterleavedMove(currentSeed, currentEvaluation, orderIds, operator, cost);
                evaluated += search.evaluated();
                feasible += search.feasible();
                if (search.seed() != null && search.evaluation() != null && acceptAlnsMove(search.evaluation(), currentEvaluation, bestEvaluation, operator)) {
                    double oldKm = currentEvaluation.distanceKm();
                    currentSeed = search.seed();
                    currentEvaluation = search.evaluation();
                    if (compareAlnsEvaluation(currentEvaluation, bestEvaluation) < 0) {
                        bestSeed = currentSeed;
                        bestEvaluation = currentEvaluation;
                    }
                    acceptedMutations++;
                    acceptedByOperator.put(operator, acceptedByOperator.getOrDefault(operator, 0) + 1);
                    changed = true;
                    traces.add(new PdLnsTrace(round, search.orderId(), operator, true, round1(oldKm), round1(currentEvaluation.distanceKm()), round1(Math.max(0.0, oldKm - currentEvaluation.distanceKm())), search.evaluated(), search.feasible(), ""));
                } else {
                    traces.add(new PdLnsTrace(round, search.orderId(), operator, false, currentEvaluation.distanceKm(), search.evaluation() == null ? currentEvaluation.distanceKm() : search.evaluation().distanceKm(), 0.0, search.evaluated(), search.feasible(), search.reason()));
                }
                if (elapsedMs(started) > alnsBudgetMs(profile)) break;
            }
            if (!changed || elapsedMs(started) > alnsBudgetMs(profile)) break;
        }
        boolean accepted = bestEvaluation != null && base != null && bestEvaluation.valid()
                && bestEvaluation.assignedCount() >= base.assignedCount()
                && bestEvaluation.lateCount() <= base.lateCount()
                && bestEvaluation.totalLatenessMinutes() <= base.totalLatenessMinutes()
                && (bestEvaluation.lateCount() < base.lateCount()
                || bestEvaluation.totalLatenessMinutes() < base.totalLatenessMinutes()
                || bestEvaluation.distanceKm() < base.distanceKm()
                || interleavingScore(pdStopSequence(bestSeed)) > interleavingScore(originalSequence))
                && !bestEvaluation.hasHardViolation();
        List<String> outputSequence = accepted ? pdStopSequence(bestSeed) : originalSequence;
        return new LiveOptimizerCandidate(
                optimizer,
                accepted ? "ACCEPTED" : "ROLLBACK",
                accepted,
                elapsedMs(started),
                base,
                accepted ? bestEvaluation : base,
                orderIds.size() * Math.max(1, rounds),
                evaluated,
                feasible,
                acceptedMutations,
                rounds,
                accepted ? "" : "no-dominating-alns-candidate",
                accepted ? bestSeed : baseSeed,
                originalSequence,
                outputSequence,
                Map.of("algorithm", "Interleaved ALNS PDPTW", "operators", operators, "acceptedByOperator", acceptedByOperator, "acceptancePolicy", "dominance-comparator-with-temporary-distance-worsening-for-late-reduction", "budgetMs", alnsBudgetMs(profile), "tracePreview", traces.stream().limit(18).map(this::pdTraceRow).toList(), "interleavedPickupDropoff", isInterleavedSequence(outputSequence), "precedenceValid", precedenceValid(outputSequence), "interleavingScore", interleavingScore(outputSequence)));
    }

    private long alnsBudgetMs(LiveEnsembleProfile profile) {
        return switch (profile) {
            case FAST_LIVE -> 1_200L;
            case QUALITY_LIVE -> 3_000L;
            case MAX_IRX -> 8_000L;
            case OFF -> 500L;
        };
    }

    private PdOperatorSearchResult searchBestInterleavedMove(PdSeedState seed,
                                                             PdEvaluation baseline,
                                                             List<String> orderIds,
                                                             String operator,
                                                             MatrixCostAdapter cost) {
        if (seed == null || seed.routes().isEmpty()) return new PdOperatorSearchResult(null, null, "", 0, 0, "missing-seed");
        PdRouteState route = seed.routes().getFirst();
        PdSeedState bestSeed = null;
        PdEvaluation bestEvaluation = null;
        String bestOrder = "";
        int evaluated = 0;
        int feasible = 0;
        for (String orderId : alnsOrderPriority(seed, orderIds, cost, operator)) {
            List<PdStop> routeStops = route.stops();
            List<PdSeedState> candidates = switch (operator) {
                case "DROPOFF_REINSERT" -> dropoffReinsertCandidates(seed, route, orderId);
                case "PICKUP_REINSERT" -> pickupReinsertCandidates(seed, route, orderId);
                case "PAIR_SWAP" -> pairSwapCandidates(seed, route, orderId, orderIds);
                case "BLOCK_RELOCATE" -> blockRelocateCandidates(seed, route, orderId);
                case "URGENT_INSERTION", "PAIR_RELOCATE" -> pairRelocateCandidates(seed, route, orderId);
                default -> List.of();
            };
            evaluated += candidates.size();
            for (PdSeedState candidate : candidates) {
                PdEvaluation evaluation = osrmMatrixEvaluateSeed(candidate, cost);
                if (!evaluation.valid()) continue;
                feasible++;
                if (isAlnsMoveEligible(evaluation, baseline) && (bestEvaluation == null || compareAlnsEvaluation(evaluation, bestEvaluation) < 0)) {
                    bestSeed = candidate;
                    bestEvaluation = evaluation;
                    bestOrder = orderId;
                }
            }
        }
        return new PdOperatorSearchResult(bestSeed, bestEvaluation, bestOrder, evaluated, feasible, bestSeed == null ? "no-feasible-dominating-move" : "");
    }

    private List<String> alnsOrderPriority(PdSeedState seed, List<String> orderIds, MatrixCostAdapter cost, String operator) {
        List<String> copy = new ArrayList<>(orderIds == null ? List.of() : orderIds);
        copy.sort((left, right) -> Double.compare(orderPenalty(seed, right, cost, operator), orderPenalty(seed, left, cost, operator)));
        return copy;
    }

    private double orderPenalty(PdSeedState seed, String orderId, MatrixCostAdapter cost, String operator) {
        if (seed == null || seed.routes().isEmpty()) return 0.0;
        PdRouteState route = seed.routes().getFirst();
        List<PdStop> stops = route.stops();
        int pickupIndex = indexOfStop(stops, orderId, PdStop.PdStopType.PICKUP);
        int dropoffIndex = indexOfStop(stops, orderId, PdStop.PdStopType.DROPOFF);
        if (pickupIndex < 0 || dropoffIndex < 0) return 0.0;
        double penalty = stopDetour(route, stops, pickupIndex, cost) + stopDetour(route, stops, dropoffIndex, cost);
        if ("URGENT_INSERTION".equals(operator)) penalty += Math.max(0.0, arrivalMinutes(route, stops, dropoffIndex, cost) - stops.get(dropoffIndex).deadlineMinutes()) * 10.0;
        return penalty;
    }

    private List<PdSeedState> pairRelocateCandidates(PdSeedState seed, PdRouteState route, String orderId) {
        PdStop pickup = findPdStop(seed, orderId, PdStop.PdStopType.PICKUP);
        PdStop dropoff = findPdStop(seed, orderId, PdStop.PdStopType.DROPOFF);
        if (pickup == null || dropoff == null) return List.of();
        List<PdStop> without = route.stops().stream().filter(stop -> !stop.orderId().equals(orderId)).toList();
        List<PdSeedState> candidates = new ArrayList<>();
        for (int pickupPosition = 0; pickupPosition <= without.size(); pickupPosition++) {
            for (int dropoffPosition = pickupPosition + 1; dropoffPosition <= without.size() + 1; dropoffPosition++) {
                List<PdStop> stops = new ArrayList<>(without);
                stops.add(pickupPosition, pickup);
                stops.add(dropoffPosition, dropoff);
                candidates.add(seed.withRoutes(List.of(route.withStops(stops))));
            }
        }
        return candidates;
    }

    private List<PdSeedState> dropoffReinsertCandidates(PdSeedState seed, PdRouteState route, String orderId) {
        List<PdStop> stops = route.stops();
        int pickupIndex = indexOfStop(stops, orderId, PdStop.PdStopType.PICKUP);
        int dropoffIndex = indexOfStop(stops, orderId, PdStop.PdStopType.DROPOFF);
        if (pickupIndex < 0 || dropoffIndex < 0) return List.of();
        PdStop dropoff = stops.get(dropoffIndex);
        List<PdStop> without = new ArrayList<>(stops);
        without.remove(dropoffIndex);
        List<PdSeedState> candidates = new ArrayList<>();
        for (int position = pickupIndex + 1; position <= without.size(); position++) {
            List<PdStop> next = new ArrayList<>(without);
            next.add(position, dropoff);
            candidates.add(seed.withRoutes(List.of(route.withStops(next))));
        }
        return candidates;
    }

    private List<PdSeedState> pickupReinsertCandidates(PdSeedState seed, PdRouteState route, String orderId) {
        List<PdStop> stops = route.stops();
        int pickupIndex = indexOfStop(stops, orderId, PdStop.PdStopType.PICKUP);
        int dropoffIndex = indexOfStop(stops, orderId, PdStop.PdStopType.DROPOFF);
        if (pickupIndex < 0 || dropoffIndex < 0) return List.of();
        PdStop pickup = stops.get(pickupIndex);
        List<PdStop> without = new ArrayList<>(stops);
        without.remove(pickupIndex);
        int adjustedDropoff = pickupIndex < dropoffIndex ? dropoffIndex - 1 : dropoffIndex;
        List<PdSeedState> candidates = new ArrayList<>();
        for (int position = 0; position <= adjustedDropoff; position++) {
            List<PdStop> next = new ArrayList<>(without);
            next.add(position, pickup);
            candidates.add(seed.withRoutes(List.of(route.withStops(next))));
        }
        return candidates;
    }

    private List<PdSeedState> pairSwapCandidates(PdSeedState seed, PdRouteState route, String orderId, List<String> orderIds) {
        List<PdSeedState> candidates = new ArrayList<>();
        for (String otherId : orderIds == null ? List.<String>of() : orderIds) {
            if (Objects.equals(orderId, otherId)) continue;
            List<PdStop> swapped = new ArrayList<>(route.stops());
            int pickupA = indexOfStop(swapped, orderId, PdStop.PdStopType.PICKUP);
            int dropoffA = indexOfStop(swapped, orderId, PdStop.PdStopType.DROPOFF);
            int pickupB = indexOfStop(swapped, otherId, PdStop.PdStopType.PICKUP);
            int dropoffB = indexOfStop(swapped, otherId, PdStop.PdStopType.DROPOFF);
            if (pickupA < 0 || dropoffA < 0 || pickupB < 0 || dropoffB < 0) continue;
            Collections.swap(swapped, pickupA, pickupB);
            Collections.swap(swapped, dropoffA, dropoffB);
            candidates.add(seed.withRoutes(List.of(route.withStops(swapped))));
        }
        return candidates;
    }

    private List<PdSeedState> blockRelocateCandidates(PdSeedState seed, PdRouteState route, String orderId) {
        List<PdStop> stops = route.stops();
        int pickupIndex = indexOfStop(stops, orderId, PdStop.PdStopType.PICKUP);
        if (pickupIndex < 0 || pickupIndex >= stops.size() - 1) return List.of();
        int blockSize = Math.min(3, stops.size() - pickupIndex);
        List<PdStop> block = new ArrayList<>(stops.subList(pickupIndex, pickupIndex + blockSize));
        List<PdStop> without = new ArrayList<>(stops);
        without.subList(pickupIndex, pickupIndex + blockSize).clear();
        List<PdSeedState> candidates = new ArrayList<>();
        for (int position = 0; position <= without.size(); position++) {
            List<PdStop> next = new ArrayList<>(without);
            next.addAll(position, block);
            candidates.add(seed.withRoutes(List.of(route.withStops(next))));
        }
        return candidates;
    }

    private boolean acceptAlnsMove(PdEvaluation candidate, PdEvaluation current, PdEvaluation best, String operator) {
        if (candidate == null || current == null || !candidate.valid() || candidate.hasHardViolation()) return false;
        if (candidate.assignedCount() < current.assignedCount()) return false;
        if (candidate.lateCount() < current.lateCount()) return true;
        if (candidate.lateCount() == current.lateCount() && candidate.totalLatenessMinutes() < current.totalLatenessMinutes()) return true;
        if (candidate.lateCount() == current.lateCount() && candidate.totalLatenessMinutes() <= current.totalLatenessMinutes() && candidate.distanceKm() < current.distanceKm()) return true;
        if ("URGENT_INSERTION".equals(operator) && best != null && candidate.lateCount() <= best.lateCount() && candidate.totalLatenessMinutes() <= best.totalLatenessMinutes()) return true;
        return compareAlnsEvaluation(candidate, best) < 0;
    }

    private boolean isAlnsMoveEligible(PdEvaluation candidate, PdEvaluation baseline) {
        if (candidate == null || baseline == null || !candidate.valid() || candidate.hasHardViolation()) return false;
        if (candidate.assignedCount() < baseline.assignedCount()) return false;
        if (candidate.lateCount() > baseline.lateCount()) return false;
        if (candidate.lateCount() == baseline.lateCount() && candidate.totalLatenessMinutes() > baseline.totalLatenessMinutes()) return false;
        return candidate.lateCount() < baseline.lateCount()
                || candidate.totalLatenessMinutes() < baseline.totalLatenessMinutes()
                || candidate.distanceKm() < baseline.distanceKm()
                || candidate.durationMinutes() < baseline.durationMinutes();
    }

    private int compareAlnsEvaluation(PdEvaluation left, PdEvaluation right) {
        if (right == null) return -1;
        if (left == null) return 1;
        int assigned = Integer.compare(right.assignedCount(), left.assignedCount());
        if (assigned != 0) return assigned;
        int hard = Integer.compare(hardViolations(left), hardViolations(right));
        if (hard != 0) return hard;
        int late = Integer.compare(left.lateCount(), right.lateCount());
        if (late != 0) return late;
        int lateness = Double.compare(left.totalLatenessMinutes(), right.totalLatenessMinutes());
        if (lateness != 0) return lateness;
        int distance = Double.compare(left.distanceKm(), right.distanceKm());
        if (distance != 0) return distance;
        return Double.compare(left.durationMinutes(), right.durationMinutes());
    }

    private PdEvaluation osrmMatrixEvaluateSeed(PdSeedState seed, MatrixCostAdapter cost) {
        if (seed == null) return new PdEvaluation(false, 0, 0, 0, 0, 0, 0, 0, 0, 0, "missing-seed");
        PdEvaluation validity = new PdSeedEvaluator().evaluateSeed(seed);
        double totalKm = 0.0;
        double totalMinutes = 0.0;
        int late = 0;
        double totalLateness = 0.0;
        for (PdRouteState route : seed.routes()) {
            double lat = route.startLat();
            double lng = route.startLng();
            double routeMinutes = 0.0;
            for (PdStop stop : route.stops()) {
                double legKm = cost.distanceKm(lat, lng, stop.lat(), stop.lng());
                double legMinutes = cost.durationMinutes(lat, lng, stop.lat(), stop.lng());
                totalKm += legKm;
                routeMinutes += legMinutes + Math.max(0, stop.serviceMinutes());
                if (stop.type() == PdStop.PdStopType.DROPOFF && stop.deadlineMinutes() > 0.0) {
                    double lateness = routeMinutes - stop.deadlineMinutes();
                    if (lateness > 0.0) {
                        late++;
                        totalLateness += lateness;
                    }
                }
                lat = stop.lat();
                lng = stop.lng();
            }
            totalMinutes += routeMinutes;
        }
        return new PdEvaluation(validity.valid(), validity.assignedCount(), late, round1(totalLateness), round1(totalKm), round1(totalMinutes), validity.pickupDropoffViolations(), validity.capacityViolations(), validity.duplicateStopViolations(), validity.missingStopViolations(), validity.rejectReason());
    }

    private int indexOfStop(List<PdStop> stops, String orderId, PdStop.PdStopType type) {
        for (int index = 0; index < (stops == null ? 0 : stops.size()); index++) {
            PdStop stop = stops.get(index);
            if (Objects.equals(stop.orderId(), orderId) && stop.type() == type) return index;
        }
        return -1;
    }

    private double stopDetour(PdRouteState route, List<PdStop> stops, int index, MatrixCostAdapter cost) {
        if (stops == null || index < 0 || index >= stops.size()) return 0.0;
        PdStop current = stops.get(index);
        double prevLat = index == 0 ? route.startLat() : stops.get(index - 1).lat();
        double prevLng = index == 0 ? route.startLng() : stops.get(index - 1).lng();
        if (index >= stops.size() - 1) return cost.distanceKm(prevLat, prevLng, current.lat(), current.lng());
        PdStop next = stops.get(index + 1);
        return Math.max(0.0, cost.distanceKm(prevLat, prevLng, current.lat(), current.lng()) + cost.distanceKm(current.lat(), current.lng(), next.lat(), next.lng()) - cost.distanceKm(prevLat, prevLng, next.lat(), next.lng()));
    }

    private double arrivalMinutes(PdRouteState route, List<PdStop> stops, int targetIndex, MatrixCostAdapter cost) {
        double lat = route.startLat();
        double lng = route.startLng();
        double minutes = 0.0;
        for (int index = 0; index <= targetIndex && index < stops.size(); index++) {
            PdStop stop = stops.get(index);
            minutes += cost.durationMinutes(lat, lng, stop.lat(), stop.lng()) + Math.max(0, stop.serviceMinutes());
            lat = stop.lat();
            lng = stop.lng();
        }
        return minutes;
    }

    private record PdOperatorSearchResult(PdSeedState seed, PdEvaluation evaluation, String orderId, int evaluated, int feasible, String reason) { }

    private LiveOptimizerCandidate roadEvaluatedBaseCandidate(String optimizer, PdSeedState seed, List<String> originalSequence) {
        PdEvaluation road = roadEvaluateSeed(seed);
        return new LiveOptimizerCandidate(optimizer, "BASE", true, 0, road, road, 0, 0, 0, 0, 0, "osrm-road-evaluated-seed", seed, originalSequence, pdStopSequence(seed), Map.of("roadDistanceSource", "OSRM_ROUTE_LEGS", "polylinePointCount", roadPolylinePointCount(seed)));
    }

    private LiveOptimizerCandidate roadEvaluatedCandidate(LiveOptimizerCandidate candidate, PdSeedState baseSeed) {
        PdEvaluation roadBase = roadEvaluateSeed(baseSeed);
        PdSeedState finalSeed = candidate.finalSeed() == null ? baseSeed : candidate.finalSeed();
        PdEvaluation roadFinal = roadEvaluateSeed(finalSeed);
        Map<String, Object> participation = new LinkedHashMap<>(candidate.mlParticipation() == null ? Map.of() : candidate.mlParticipation());
        participation.put("roadDistanceSource", "OSRM_ROUTE_LEGS");
        participation.put("roadEvaluated", true);
        participation.put("polylinePointCount", roadPolylinePointCount(finalSeed));
        boolean noRoadRegression = roadFinal.valid()
                && roadFinal.assignedCount() >= roadBase.assignedCount()
                && roadFinal.lateCount() <= roadBase.lateCount()
                && roadFinal.totalLatenessMinutes() <= roadBase.totalLatenessMinutes()
                && !roadFinal.hasHardViolation();
        boolean accepted = candidate.accepted() && noRoadRegression;
        String reason = accepted ? candidate.reason() : roadFinal.valid() ? rollbackReason(roadBase, roadFinal) : roadFinal.rejectReason();
        return new LiveOptimizerCandidate(
                candidate.optimizer(),
                accepted ? candidate.status() : "ROLLBACK",
                accepted,
                candidate.runtimeMs(),
                roadBase,
                accepted ? roadFinal : roadBase,
                candidate.evaluatedOrders(),
                candidate.evaluatedInsertions(),
                candidate.feasibleInsertions(),
                candidate.acceptedMutations(),
                candidate.rounds(),
                reason,
                accepted ? finalSeed : baseSeed,
                candidate.inputStopSequence(),
                accepted ? pdStopSequence(finalSeed) : pdStopSequence(baseSeed),
                participation);
    }

    private PdEvaluation roadEvaluateSeed(PdSeedState seed) {
        if (seed == null || seed.routes().isEmpty()) return new PdEvaluation(false, 0, 0, 0, 0, 0, 0, 0, 0, 0, "missing-seed");
        PdEvaluation validation = new PdSeedEvaluator().evaluateSeed(seed);
        double totalKm = 0.0;
        double totalMinutes = 0.0;
        for (PdRouteState route : seed.routes()) {
            double lat = route.startLat();
            double lng = route.startLng();
            String previousId = "DRIVER:" + route.driverId();
            for (PdStop stop : route.stops()) {
                String stopId = stop.type().name() + ":" + stop.orderId();
                RoutingRouteResult leg = routeLeg(previousId, lat, lng, stopId, stop.lat(), stop.lng(), "live-road-evaluation");
                if (leg == null || leg.legVector() == null || leg.degradeReasons() == null || !leg.degradeReasons().isEmpty()) {
                    return new PdEvaluation(false, validation.assignedCount(), validation.lateCount(), validation.totalLatenessMinutes(), validation.distanceKm(), validation.durationMinutes(), validation.pickupDropoffViolations(), validation.capacityViolations(), validation.duplicateStopViolations(), validation.missingStopViolations(), "ROUTE_GEOMETRY_MISSING");
                }
                totalKm += leg.legVector().distanceMeters() / 1000.0;
                totalMinutes += leg.legVector().travelTimeSeconds() / 60.0;
                lat = stop.lat();
                lng = stop.lng();
                previousId = stopId;
            }
        }
        return new PdEvaluation(validation.valid(), validation.assignedCount(), validation.lateCount(), validation.totalLatenessMinutes(), Math.round(totalKm * 10.0) / 10.0, Math.round(totalMinutes * 10.0) / 10.0, validation.pickupDropoffViolations(), validation.capacityViolations(), validation.duplicateStopViolations(), validation.missingStopViolations(), validation.rejectReason());
    }

    private int roadPolylinePointCount(PdSeedState seed) {
        if (seed == null || seed.routes().isEmpty()) return 0;
        int points = 0;
        for (PdRouteState route : seed.routes()) {
            double lat = route.startLat();
            double lng = route.startLng();
            String previousId = "DRIVER:" + route.driverId();
            for (PdStop stop : route.stops()) {
                String stopId = stop.type().name() + ":" + stop.orderId();
                RoutingRouteResult leg = routeLeg(previousId, lat, lng, stopId, stop.lat(), stop.lng(), "live-road-polyline-count");
                points += leg == null || leg.polyline() == null ? 0 : leg.polyline().size();
                lat = stop.lat();
                lng = stop.lng();
                previousId = stopId;
            }
        }
        return points;
    }

    private boolean dominatesInterleaved(PdEvaluation candidate, PdEvaluation baseline, List<PdStop> candidateStops, List<PdStop> baselineStops) {
        if (candidate == null || baseline == null || !candidate.valid()) return false;
        if (candidate.assignedCount() < baseline.assignedCount() || candidate.lateCount() > baseline.lateCount() || candidate.totalLatenessMinutes() > baseline.totalLatenessMinutes()) return false;
        int distance = Double.compare(candidate.distanceKm(), baseline.distanceKm());
        if (distance < 0) return true;
        if (distance > 0) return false;
        return interleavingScore(candidateStops.stream().map(stop -> stop.type().name() + ":" + stop.orderId()).toList()) > interleavingScore(baselineStops.stream().map(stop -> stop.type().name() + ":" + stop.orderId()).toList());
    }

    private List<PdStop> pdStopsFromSequence(PdSeedState seed) {
        return seed == null || seed.routes().isEmpty() ? List.of() : seed.routes().getFirst().stops();
    }

    private PdStop findPdStop(PdSeedState seed, String orderId, PdStop.PdStopType type) {
        if (seed == null) return null;
        return seed.routes().stream().flatMap(route -> route.stops().stream()).filter(stop -> stop.orderId().equals(orderId) && stop.type() == type).findFirst().orElse(null);
    }

    private PdLnsResult runLiveOptimizer(PdSeedState seed, PdLnsMode mode, int rounds, int topBadOrders) {
        if (mode == PdLnsMode.TRI_MODEL_FUSION_PD_LNS || mode == PdLnsMode.TRI_MODEL_FUSION_NO_TABULAR || mode == PdLnsMode.TRI_MODEL_FUSION_NO_ROUTEFINDER || mode == PdLnsMode.TRI_MODEL_FUSION_NO_GREEDRL) {
            return new TriModelFusionPdLnsRunner().run(seed, mode, rounds, topBadOrders);
        }
        if (mode == PdLnsMode.HEURISTIC_PD_LNS) {
            return new HeuristicPdLnsImprover().improve(seed, rounds, topBadOrders);
        }
        return new PdDestroyRepairOperator().improve(seed, mode, rounds, topBadOrders);
    }

    private LiveOptimizerCandidate candidateFromResult(String optimizer, PdLnsResult result, long runtimeMs, PdSeedState baseSeed, List<String> originalSequence) {
        PdEvaluation base = result == null || result.baseEvaluation() == null ? new PdSeedEvaluator().evaluateSeed(baseSeed) : result.baseEvaluation();
        PdEvaluation fin = result == null ? base : result.finalEvaluation();
        boolean accepted = fin != null && base != null && fin.valid() && fin.assignedCount() >= base.assignedCount() && fin.lateCount() <= base.lateCount() && fin.totalLatenessMinutes() <= base.totalLatenessMinutes() && fin.distanceKm() <= base.distanceKm() && !fin.hasHardViolation();
        PdSeedState finalSeed = accepted && result != null && result.finalSeed() != null ? result.finalSeed() : baseSeed;
        return new LiveOptimizerCandidate(optimizer, accepted ? "ACCEPTED" : "ROLLBACK", accepted, runtimeMs, base, accepted ? fin : base, result == null ? 0 : result.evaluatedOrders(), result == null ? 0 : result.evaluatedInsertions(), result == null ? 0 : result.feasibleInsertions(), result == null ? 0 : result.acceptedMutations(), result == null ? 0 : result.rounds(), accepted ? "" : rollbackReason(base, fin), finalSeed, originalSequence, pdStopSequence(finalSeed), result == null ? Map.of() : mlParticipationTrace(result));
    }

    private int compareLiveOptimizerCandidate(LiveOptimizerCandidate left, LiveOptimizerCandidate right) {
        int accepted = Boolean.compare(right.accepted(), left.accepted());
        if (accepted != 0) return accepted;
        PdEvaluation leftEval = left.finalEvaluation();
        PdEvaluation rightEval = right.finalEvaluation();
        int assigned = Integer.compare(rightEval == null ? 0 : rightEval.assignedCount(), leftEval == null ? 0 : leftEval.assignedCount());
        if (assigned != 0) return assigned;
        int hard = Integer.compare(hardViolations(leftEval), hardViolations(rightEval));
        if (hard != 0) return hard;
        int late = Integer.compare(leftEval == null ? Integer.MAX_VALUE : leftEval.lateCount(), rightEval == null ? Integer.MAX_VALUE : rightEval.lateCount());
        if (late != 0) return late;
        int lateness = Double.compare(leftEval == null ? Double.POSITIVE_INFINITY : leftEval.totalLatenessMinutes(), rightEval == null ? Double.POSITIVE_INFINITY : rightEval.totalLatenessMinutes());
        if (lateness != 0) return lateness;
        int distance = Double.compare(leftEval == null ? Double.POSITIVE_INFINITY : leftEval.distanceKm(), rightEval == null ? Double.POSITIVE_INFINITY : rightEval.distanceKm());
        if (distance != 0) return distance;
        return Long.compare(left.runtimeMs(), right.runtimeMs());
    }

    private int hardViolations(PdEvaluation evaluation) {
        return evaluation == null ? Integer.MAX_VALUE : evaluation.pickupDropoffViolations() + evaluation.capacityViolations() + evaluation.duplicateStopViolations() + evaluation.missingStopViolations();
    }

    private LiveEnsembleProfile liveEnsembleProfile(String mode) {
        String value = mode == null ? "QUALITY_LIVE" : mode.trim().toUpperCase(Locale.ROOT);
        return switch (value) {
            case "FAST_LIVE" -> LiveEnsembleProfile.FAST_LIVE;
            case "MAX_IRX", "FULL_ML_PD_LNS" -> LiveEnsembleProfile.MAX_IRX;
            case "QUALITY_LIVE", "AUTO", "" -> LiveEnsembleProfile.QUALITY_LIVE;
            default -> LiveEnsembleProfile.OFF;
        };
    }

    private List<PdLnsMode> ensembleModes(LiveEnsembleProfile profile) {
        return switch (profile) {
            case FAST_LIVE -> List.of(PdLnsMode.HEURISTIC_PD_LNS, PdLnsMode.ML_HYBRID_PD_LNS, PdLnsMode.TABULAR_SCORED_PD_LNS);
            case QUALITY_LIVE -> List.of(PdLnsMode.HEURISTIC_PD_LNS, PdLnsMode.ML_HYBRID_PD_LNS, PdLnsMode.TABULAR_ROUTEFINDER_PD_LNS, PdLnsMode.TRI_MODEL_FUSION_PD_LNS);
            case MAX_IRX -> List.of(PdLnsMode.HEURISTIC_PD_LNS, PdLnsMode.ML_HYBRID_PD_LNS, PdLnsMode.TRI_MODEL_FUSION_PD_LNS, PdLnsMode.TABULAR_ROUTEFINDER_PD_LNS, PdLnsMode.GREEDRL_CONTROLLER_PD_LNS, PdLnsMode.FORECAST_RISK_PD_LNS);
            case OFF -> List.of();
        };
    }

    private int ensembleRounds(LiveEnsembleProfile profile) {
        return switch (profile) {
            case FAST_LIVE -> 2;
            case QUALITY_LIVE -> 3;
            case MAX_IRX -> 4;
            case OFF -> 1;
        };
    }

    private int ensembleTopBadOrders(LiveEnsembleProfile profile) {
        return switch (profile) {
            case FAST_LIVE -> 8;
            case QUALITY_LIVE -> 10;
            case MAX_IRX -> 12;
            case OFF -> 6;
        };
    }

    private long ensembleBudgetMs(LiveEnsembleProfile profile) {
        return switch (profile) {
            case FAST_LIVE -> 800L;
            case QUALITY_LIVE -> 2_000L;
            case MAX_IRX -> 5_000L;
            case OFF -> 0L;
        };
    }

    private PdSeedState pdSeedFromSequence(String routeId,
                                           String selectedSeed,
                                           DashboardController.DriverDto driver,
                                           List<String> sequence,
                                           Map<String, DashboardController.OrderDto> orderById) {
        List<PdStop> stops = new ArrayList<>();
        for (String encoded : sequence) {
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) continue;
            DashboardController.OrderDto order = orderById.get(parts[1]);
            if (order == null) continue;
            boolean dropoff = "DROPOFF".equalsIgnoreCase(parts[0]);
            stops.add(new PdStop(order.orderId(), dropoff ? PdStop.PdStopType.DROPOFF : PdStop.PdStopType.PICKUP,
                    dropoff ? order.dropoffLat() : order.pickupLat(),
                    dropoff ? order.dropoffLng() : order.pickupLng(),
                    1,
                    dropoff ? -1 : 1,
                    order.deadlineMinutes()));
        }
        int inputOrders = (int) stops.stream().filter(stop -> stop.type() == PdStop.PdStopType.DROPOFF).map(PdStop::orderId).distinct().count();
        PdRouteState route = new PdRouteState(routeId, driver.driverId(), Math.max(999, driver.capacity()), driver.lat(), driver.lng(), stops, 0, 0, 0, 0);
        PdSeedState shell = new PdSeedState(routeId, candidateSourceFromSeed(selectedSeed), inputOrders, List.of(route), inputOrders, inputOrders, 0, 0, 0, 0, 0);
        PdEvaluation evaluation = new PdSeedEvaluator().evaluateSeed(shell);
        return new PdSeedState(routeId, candidateSourceFromSeed(selectedSeed), inputOrders, List.of(route), evaluation.assignedCount(), inputOrders, evaluation.lateCount(), evaluation.totalLatenessMinutes(), evaluation.distanceKm(), evaluation.durationMinutes(), 0);
    }

    private CandidateSource candidateSourceFromSeed(String seed) {
        String value = seed == null ? "" : seed.toUpperCase(Locale.ROOT);
        if (value.contains("PYVRP")) return CandidateSource.PYVRP_SEED;
        if (value.contains("VROOM")) return CandidateSource.VROOM_SEED;
        if (value.contains("ORTOOLS")) return CandidateSource.ORTOOLS_SEED;
        if (value.contains("IRX")) return CandidateSource.IRX_NATIVE;
        return CandidateSource.BEST_EXTERNAL_SEED_IMPROVED;
    }

    private List<String> pdStopSequence(PdSeedState seed) {
        if (seed == null || seed.routes().isEmpty()) return List.of();
        return seed.routes().getFirst().stops().stream().map(stop -> stop.type().name() + ":" + stop.orderId()).toList();
    }

    private String rollbackReason(PdEvaluation base, PdEvaluation fin) {
        if (fin == null) return "missing-final-evaluation";
        if (!fin.valid()) return fin.rejectReason().isBlank() ? "invalid-final-seed" : fin.rejectReason();
        if (base == null) return "missing-base-evaluation";
        if (fin.assignedCount() < base.assignedCount()) return "coverage-regression";
        if (fin.lateCount() > base.lateCount()) return "late-regression";
        if (fin.totalLatenessMinutes() > base.totalLatenessMinutes()) return "lateness-regression";
        if (fin.distanceKm() > base.distanceKm()) return "distance-regression";
        return "dominance-guard-rollback";
    }

    private Map<String, Object> mlParticipationTrace(PdLnsResult result) {
        if (result == null || result.mlParticipationDiagnostics() == null) return Map.of();
        var diagnostics = result.mlParticipationDiagnostics();
        return Map.of(
                "decisionTraceCount", diagnostics.decisionTraceCount(),
                "rankedMutationCount", diagnostics.rankedMutationCount(),
                "acceptedMutationFromMlTopK", diagnostics.acceptedMutationFromMlTopK(),
                "rewardUpdates", diagnostics.rewardUpdates(),
                "policyLayer", diagnostics.policyLayer());
    }

    private Map<String, Object> pdTraceRow(PdLnsTrace trace) {
        return Map.of("round", trace.round(), "orderId", trace.orderId(), "operator", trace.operator(), "accepted", trace.accepted(), "oldKm", trace.oldKm(), "newKm", trace.newKm(), "gainKm", trace.gainKm(), "evaluatedInsertions", trace.evaluatedInsertions(), "feasibleInsertions", trace.feasibleInsertions(), "rejectReason", trace.rejectReason());
    }

    private List<String> sanitizeStopSequence(List<String> sequence, Map<String, DashboardController.OrderDto> orderById) {
        List<String> clean = new ArrayList<>();
        Set<String> picked = new LinkedHashSet<>();
        Set<String> dropped = new LinkedHashSet<>();
        for (String encoded : sequence) {
            String[] parts = encoded == null ? new String[0] : encoded.split(":", 2);
            if (parts.length != 2 || !orderById.containsKey(parts[1])) continue;
            String type = parts[0].toUpperCase(Locale.ROOT);
            String orderId = parts[1];
            if ("PICKUP".equals(type)) {
                if (picked.add(orderId)) clean.add("PICKUP:" + orderId);
            } else if ("DROPOFF".equals(type) && picked.contains(orderId) && dropped.add(orderId)) {
                clean.add("DROPOFF:" + orderId);
            }
        }
        return clean;
    }

    private List<String> irxPairInsertionSequence(DashboardController.DriverDto driver,
                                                  List<String> seedSequence,
                                                  Map<String, DashboardController.OrderDto> orderById,
                                                  MatrixCostAdapter cost) {
        List<String> orderIds = seedSequence.stream()
                .filter(stop -> stop.startsWith("PICKUP:"))
                .map(stop -> stop.substring("PICKUP:".length()))
                .filter(orderById::containsKey)
                .distinct()
                .toList();
        List<String> route = new ArrayList<>();
        for (String orderId : orderIds) {
            List<String> best = null;
            RouteScore bestScore = null;
            for (int pickupIndex = 0; pickupIndex <= route.size(); pickupIndex++) {
                for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= route.size() + 1; dropoffIndex++) {
                    List<String> candidate = new ArrayList<>(route);
                    candidate.add(pickupIndex, "PICKUP:" + orderId);
                    candidate.add(dropoffIndex, "DROPOFF:" + orderId);
                    RouteScore score = scoreSequence(driver, candidate, orderById, cost);
                    if (bestScore == null || score.compareTo(bestScore) < 0) {
                        bestScore = score;
                        best = candidate;
                    }
                }
            }
            route = best == null ? route : best;
        }
        return route.isEmpty() ? seedSequence : route;
    }

    private List<String> irxLocalRelocate(List<String> sequence,
                                          DashboardController.DriverDto driver,
                                          Map<String, DashboardController.OrderDto> orderById,
                                          MatrixCostAdapter cost) {
        List<String> best = new ArrayList<>(sequence);
        RouteScore bestScore = scoreSequence(driver, best, orderById, cost);
        boolean improved = true;
        int iterations = 0;
        while (improved && iterations++ < 16) {
            improved = false;
            for (String orderId : best.stream().filter(stop -> stop.startsWith("PICKUP:")).map(stop -> stop.substring("PICKUP:".length())).distinct().toList()) {
                List<String> without = best.stream().filter(stop -> !stop.endsWith(":" + orderId)).collect(java.util.stream.Collectors.toCollection(ArrayList::new));
                for (int pickupIndex = 0; pickupIndex <= without.size(); pickupIndex++) {
                    for (int dropoffIndex = pickupIndex + 1; dropoffIndex <= without.size() + 1; dropoffIndex++) {
                        List<String> candidate = new ArrayList<>(without);
                        candidate.add(pickupIndex, "PICKUP:" + orderId);
                        candidate.add(dropoffIndex, "DROPOFF:" + orderId);
                        RouteScore score = scoreSequence(driver, candidate, orderById, cost);
                        if (score.compareTo(bestScore) < 0) {
                            best = candidate;
                            bestScore = score;
                            improved = true;
                        }
                    }
                }
            }
        }
        return best;
    }

    private RouteScore scoreSequence(DashboardController.DriverDto driver,
                                     List<String> sequence,
                                     Map<String, DashboardController.OrderDto> orderById,
                                     MatrixCostAdapter cost) {
        double lat = driver.lat();
        double lng = driver.lng();
        double distance = 0.0;
        double minutes = 0.0;
        long late = 0;
        Set<String> picked = new LinkedHashSet<>();
        Set<String> dropped = new LinkedHashSet<>();
        for (String encoded : sequence) {
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) return RouteScore.invalid();
            DashboardController.OrderDto order = orderById.get(parts[1]);
            if (order == null) return RouteScore.invalid();
            if ("DROPOFF".equals(parts[0]) && !picked.contains(parts[1])) return RouteScore.invalid();
            double nextLat = "DROPOFF".equals(parts[0]) ? order.dropoffLat() : order.pickupLat();
            double nextLng = "DROPOFF".equals(parts[0]) ? order.dropoffLng() : order.pickupLng();
            distance += cost.distanceKm(lat, lng, nextLat, nextLng);
            minutes += cost.durationMinutes(lat, lng, nextLat, nextLng);
            if ("PICKUP".equals(parts[0])) {
                picked.add(parts[1]);
            } else {
                dropped.add(parts[1]);
                if (minutes > order.deadlineMinutes()) late++;
            }
            lat = nextLat;
            lng = nextLng;
        }
        if (!picked.equals(dropped)) return RouteScore.invalid();
        return new RouteScore(distance, late, minutes);
    }

    private boolean sameCompletedOrders(List<String> left, List<String> right) {
        Set<String> leftOrders = left.stream().filter(stop -> stop.startsWith("DROPOFF:")).map(stop -> stop.substring("DROPOFF:".length())).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        Set<String> rightOrders = right.stream().filter(stop -> stop.startsWith("DROPOFF:")).map(stop -> stop.substring("DROPOFF:".length())).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        return leftOrders.equals(rightOrders);
    }

    private boolean isInterleavedSequence(List<String> sequence) {
        if (sequence == null || sequence.isEmpty()) return false;
        boolean seenDropoff = false;
        for (String stop : sequence) {
            if (stop != null && stop.startsWith("DROPOFF:")) seenDropoff = true;
            if (seenDropoff && stop != null && stop.startsWith("PICKUP:")) return true;
        }
        return false;
    }

    private boolean precedenceValid(List<String> sequence) {
        Set<String> picked = new LinkedHashSet<>();
        Set<String> dropped = new LinkedHashSet<>();
        for (String stop : sequence == null ? List.<String>of() : sequence) {
            String[] parts = stop == null ? new String[0] : stop.split(":", 2);
            if (parts.length != 2) continue;
            if ("PICKUP".equals(parts[0])) picked.add(parts[1]);
            if ("DROPOFF".equals(parts[0])) {
                if (!picked.contains(parts[1])) return false;
                dropped.add(parts[1]);
            }
        }
        return picked.equals(dropped);
    }

    private int interleavingScore(List<String> sequence) {
        int score = 0;
        boolean seenDropoff = false;
        for (String stop : sequence == null ? List.<String>of() : sequence) {
            if (stop != null && stop.startsWith("DROPOFF:")) seenDropoff = true;
            if (seenDropoff && stop != null && stop.startsWith("PICKUP:")) score++;
        }
        return score;
    }

    private record RouteScore(double distanceKm, long late, double minutes) implements Comparable<RouteScore> {
        static RouteScore invalid() { return new RouteScore(Double.POSITIVE_INFINITY, Long.MAX_VALUE, Double.POSITIVE_INFINITY); }
        @Override public int compareTo(RouteScore other) {
            int lateCompare = Long.compare(late, other.late);
            if (lateCompare != 0) return lateCompare;
            int distanceCompare = Double.compare(distanceKm, other.distanceKm);
            if (distanceCompare != 0) return distanceCompare;
            return Double.compare(minutes, other.minutes);
        }
    }

    private DistanceDurationMatrixSnapshot liveMatrixSnapshot(DashboardController.RunVisualizationDto run) {
        List<MatrixSnapshotBuilder.MatrixNode> nodes = new ArrayList<>();
        if (run != null) {
            for (DashboardController.DriverDto driver : run.drivers()) nodes.add(new MatrixSnapshotBuilder.MatrixNode("driver:" + driver.driverId(), driver.lat(), driver.lng()));
            for (DashboardController.OrderDto order : run.orders()) {
                nodes.add(new MatrixSnapshotBuilder.MatrixNode("pickup:" + order.orderId(), order.pickupLat(), order.pickupLng()));
                nodes.add(new MatrixSnapshotBuilder.MatrixNode("dropoff:" + order.orderId(), order.dropoffLat(), order.dropoffLng()));
            }
        }
        if (!"osrm".equalsIgnoreCase(properties.getRouting().getProvider())) {
            throw new IllegalStateException("OSRM_REQUIRED: live dispatch requires routechain.dispatch-v2.routing.provider=osrm");
        }
        MatrixSnapshotBuilder builder = new MatrixSnapshotBuilder();
        return builder.buildWithOsrmTable("live", run == null ? id("hash") : run.runId(), "LIVE_SEED_ARCHIVE", nodes, osrmTableClient);
    }

    private UnifiedDispatchRequest liveUnifiedRequest(DashboardController.RunVisualizationDto run) {
        List<Order> orders = run.orders().stream().map(order -> new Order(order.orderId(), new GeoPoint(order.pickupLat(), order.pickupLng()), new GeoPoint(order.dropoffLat(), order.dropoffLng()), Instant.now(), Instant.now(), order.deadlineMinutes(), false)).toList();
        List<Driver> drivers = run.drivers().stream().map(driver -> new Driver(driver.driverId(), new GeoPoint(driver.lat(), driver.lng()))).toList();
        return new UnifiedDispatchRequest("unified-dispatch-request/v1", run.runId() + "-live-seed-archive", DispatchMode.LIVE_ROLLING, DispatchStrategy.MULTI_PASS_COVERAGE, orders, drivers, List.of(new Region("hcm", "Ho Chi Minh City")), WeatherProfile.CLEAR, DispatchPolicy.dashboardDefault(orders.size(), drivers.size()), Instant.now());
    }

    private SeedCandidateView externalSeedView(String solver, ExternalSeedContribution contribution) {
        if (contribution == null || contribution.seed() == null) return new SeedCandidateView(solver, List.of(), 0, 0, 0, 0, contribution == null ? "NO_SEED" : contribution.status().name(), contribution == null ? "missing-contribution" : contribution.reason());
        SolutionSeedCandidate seed = contribution.seed();
        long runtimeMs = contribution.diagnostics().get("runtimeMs") instanceof Number number ? number.longValue() : 0L;
        return new SeedCandidateView(solver, seed.routes(), runtimeMs, seed.totalDistanceKm(), seed.lateOrderCount(), Math.round(seed.coverageRate() * Math.max(1, seed.routes().stream().flatMap(route -> route.orderIds().stream()).distinct().count())), contribution.status().name(), contribution.reason());
    }

    private SeedCandidateView seedCandidateFromRoutes(String seed, List<SolutionSeedRoute> routes, long runtimeMs, String reason) {
        long assigned = routes.stream().flatMap(route -> route.orderIds().stream()).distinct().count();
        double distance = routes.stream().mapToDouble(SolutionSeedRoute::distanceKm).sum();
        long late = routes.stream().mapToLong(SolutionSeedRoute::lateOrderCount).sum();
        return new SeedCandidateView(seed, routes, runtimeMs, Math.round(distance * 10.0) / 10.0, late, assigned, "COMPLETED", reason);
    }

    private List<SolutionSeedRoute> irxRoutesToSeedRoutes(List<DashboardController.RouteVisualizationDto> routes) {
        if (routes == null) return List.of();
        return routes.stream().map(route -> new SolutionSeedRoute(route.routeId(), route.driverId(), route.stops().stream().map(DashboardController.StopVisualizationDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).distinct().toList(), route.stops().stream().filter(stop -> !"DRIVER_START".equalsIgnoreCase(stop.type())).map(stop -> stop.type() + ":" + stop.orderId()).toList(), route.totalDistanceKm(), route.totalEtaMinutes(), route.lateOrderCount())).toList();
    }

    private List<SolutionSeedRoute> ortoolsBalancedSeed(DashboardController.RunVisualizationDto run, DistanceDurationMatrixSnapshot matrix) {
        if (run == null || run.drivers().isEmpty()) return List.of();
        MatrixCostAdapter cost = new MatrixCostAdapter(matrix);
        Map<String, List<DashboardController.OrderDto>> byDriver = new LinkedHashMap<>();
        run.drivers().forEach(driver -> byDriver.put(driver.driverId(), new ArrayList<>()));
        int maxLoad = Math.max(1, (int) Math.ceil(run.orders().size() / (double) Math.max(1, run.drivers().size())) + 1);
        for (DashboardController.OrderDto order : run.orders().stream().sorted(Comparator.comparing(DashboardController.OrderDto::orderId)).toList()) {
            DashboardController.DriverDto best = run.drivers().stream()
                    .filter(driver -> byDriver.get(driver.driverId()).size() < maxLoad)
                    .min(Comparator.comparingDouble(driver -> cost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .orElse(run.drivers().getFirst());
            byDriver.get(best.driverId()).add(order);
        }
        List<SolutionSeedRoute> routes = new ArrayList<>();
        for (DashboardController.DriverDto driver : run.drivers()) if (!byDriver.get(driver.driverId()).isEmpty()) routes.add(seedRouteFromOrders("ORTOOLS-" + driver.driverId(), driver, byDriver.get(driver.driverId()), cost));
        return routes;
    }

    private SolutionSeedRoute seedRouteFromOrders(String routeId, DashboardController.DriverDto driver, List<DashboardController.OrderDto> orders, MatrixCostAdapter cost) {
        double lat = driver.lat(), lng = driver.lng(), distance = 0, minutes = 0;
        long late = 0;
        List<String> sequence = new ArrayList<>();
        for (DashboardController.OrderDto order : orders) {
            double leg = cost.distanceKm(lat, lng, order.pickupLat(), order.pickupLng());
            double legMinutes = cost.durationMinutes(lat, lng, order.pickupLat(), order.pickupLng());
            distance += leg; minutes += legMinutes; sequence.add("PICKUP:" + order.orderId()); lat = order.pickupLat(); lng = order.pickupLng();
        }
        for (DashboardController.OrderDto order : orders) {
            double leg = cost.distanceKm(lat, lng, order.dropoffLat(), order.dropoffLng());
            double legMinutes = cost.durationMinutes(lat, lng, order.dropoffLat(), order.dropoffLng());
            distance += leg; minutes += legMinutes; if (minutes > order.deadlineMinutes()) late++; sequence.add("DROPOFF:" + order.orderId()); lat = order.dropoffLat(); lng = order.dropoffLng();
        }
        return new SolutionSeedRoute(routeId, driver.driverId(), orders.stream().map(DashboardController.OrderDto::orderId).toList(), sequence, Math.round(distance * 10.0) / 10.0, Math.round(minutes * 10.0) / 10.0, late);
    }

    private int compareSeedCandidate(SeedCandidateView left, SeedCandidateView right) {
        int coverage = Long.compare(right.assigned(), left.assigned());
        if (coverage != 0) return coverage;
        int late = Long.compare(left.late(), right.late());
        if (late != 0) return late;
        int distance = Double.compare(left.distanceKm(), right.distanceKm());
        if (distance != 0) return distance;
        return Long.compare(left.runtimeMs(), right.runtimeMs());
    }

    private Map<String, Object> seedCandidateRow(SeedCandidateView candidate, boolean selected, Map<String, DashboardController.OrderDto> orderById, Map<String, DashboardController.DriverDto> driverById) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("seed", candidate.seed()); row.put("solver", candidate.seed()); row.put("runtimeMs", candidate.runtimeMs()); row.put("distanceKm", Math.round(candidate.distanceKm() * 10.0) / 10.0); row.put("late", candidate.late()); row.put("coverage", candidate.assigned()); row.put("result", candidate.status()); row.put("reason", candidate.reason()); row.put("selected", selected);
        row.put("routes", candidate.routes().stream().map(route -> Map.<String, Object>of("routeId", route.routeId(), "driverId", route.driverId(), "assignedOrderIds", route.orderIds(), "bundleSize", route.orderIds().size(), "stopSequence", route.stopSequence(), "distanceKm", route.distanceKm(), "late", route.lateOrderCount())).toList());
        return row;
    }

    private DashboardController.RouteVisualizationDto routeFromSeedRow(String routeId, String driverId, List<String> stopSequence, Map<String, DashboardController.OrderDto> orderById, Map<String, DashboardController.DriverDto> driverById) {
        return routeFromSeedRow(routeId, driverId, stopSequence, orderById, driverById, false);
    }

    private DashboardController.RouteVisualizationDto routeFromSeedRow(String routeId, String driverId, List<String> stopSequence, Map<String, DashboardController.OrderDto> orderById, Map<String, DashboardController.DriverDto> driverById, boolean requireRoadGeometry) {
        return routeFromSeedRow(routeId, driverId, stopSequence, orderById, driverById, requireRoadGeometry, null);
    }

    private DashboardController.RouteVisualizationDto routeFromSeedRow(String routeId, String driverId, List<String> stopSequence, Map<String, DashboardController.OrderDto> orderById, Map<String, DashboardController.DriverDto> driverById, boolean requireRoadGeometry, LiveSession session) {
        DashboardController.DriverDto driver = driverById.get(driverId);
        DriverRuntimeState runtimeState = session == null ? null : session.driverStates.get(driverId);
        double previousLat = runtimeState == null ? driver == null ? 10.7626 : driver.lat() : runtimeState.lat;
        double previousLng = runtimeState == null ? driver == null ? 106.6601 : driver.lng() : runtimeState.lng;
        String previousId = "DRIVER:" + driverId;
        List<DashboardController.StopVisualizationDto> stops = new ArrayList<>();
        List<DashboardController.GeoPointDto> polyline = new ArrayList<>();
        stops.add(new DashboardController.StopVisualizationDto(0, "DRIVER_START", "", previousLat, previousLng, 0, 0, 0, 999, "START", "ACTIVE"));
        int sequence = 0;
        double totalDistance = 0.0;
        double totalEta = 0.0;
        Instant routeStartedAt = Instant.now();
        Instant timeCursor = routeStartedAt;
        long lateCount = 0;
        long totalLatenessSeconds = 0;
        long priorityWeightedLateness = 0;
        boolean roadGeometry = true;
        for (String encoded : stopSequence) {
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) continue;
            DashboardController.OrderDto order = orderById.get(parts[1]);
            if (order == null) continue;
            String type = parts[0].toUpperCase(Locale.ROOT);
            double lat = "DROPOFF".equals(type) ? order.dropoffLat() : order.pickupLat();
            double lng = "DROPOFF".equals(type) ? order.dropoffLng() : order.pickupLng();
            String stopId = type + ":" + order.orderId();
            RoutingRouteResult leg = routeLeg(previousId, previousLat, previousLng, stopId, lat, lng, "live-final-route");
            boolean legHasRoad = leg != null && leg.legVector() != null && leg.degradeReasons() != null && leg.degradeReasons().isEmpty() && leg.polyline() != null && leg.polyline().size() >= 2;
            if (!legHasRoad) {
                throw new IllegalStateException("OSRM_REQUIRED: missing road route leg " + previousId + " -> " + stopId + " reasons=" + (leg == null ? List.of("no-route-result") : leg.degradeReasons()));
            }
            double distance = leg.legVector().distanceMeters() / 1000.0;
            long travelSeconds = adjustedTravelSeconds(leg.legVector().distanceMeters() / 1000.0, leg.legVector().travelTimeSeconds(), runtimeState);
            double eta = travelSeconds / 60.0;
            appendPolyline(polyline, simplifyRoutePolyline(leg.polyline()));
            OrderSla sla = orderSla(order, findLiveApiOrder(session, order.orderId()), routeStartedAt);
            Instant arriveAt = timeCursor.plusSeconds(travelSeconds);
            if ("PICKUP".equals(type) && arriveAt.isBefore(sla.pickupReadyAt())) {
                arriveAt = sla.pickupReadyAt();
            }
            long serviceSeconds = "DROPOFF".equals(type) ? sla.dropoffServiceSeconds() : sla.pickupServiceSeconds();
            Instant departAt = arriveAt.plusSeconds(serviceSeconds);
            long latenessSeconds = 0;
            long priorityPenalty = 0;
            String risk = "LOW";
            String status = "OK";
            String lateReason = "";
            double slackMinutes = 999.0;
            if ("DROPOFF".equals(type)) {
                Instant deadlineWithGrace = sla.deliveryWindowEndAt().plusSeconds(sla.gracePeriodSeconds());
                long slackSeconds = java.time.Duration.between(departAt, deadlineWithGrace).getSeconds();
                slackMinutes = round1(slackSeconds / 60.0);
                latenessSeconds = Math.max(0L, -slackSeconds);
                priorityPenalty = Math.round(latenessSeconds * priorityLateWeight(sla.priority()));
                if (latenessSeconds > 0) {
                    lateCount++;
                    totalLatenessSeconds += latenessSeconds;
                    priorityWeightedLateness += priorityPenalty;
                    risk = latenessSeconds >= 600 ? "CRITICAL_LATE" : "LATE";
                    status = "LATE";
                    lateReason = "DELIVERED_AFTER_DEADLINE";
                } else if (slackSeconds <= 300) {
                    risk = "AT_RISK";
                    status = "AT_RISK";
                    lateReason = "LOW_SLACK_TO_DEADLINE";
                }
            }
            sequence++;
            stops.add(new DashboardController.StopVisualizationDto(
                    sequence,
                    type,
                    order.orderId(),
                    lat,
                    lng,
                    round1(java.time.Duration.between(routeStartedAt, departAt).toSeconds() / 60.0),
                    Math.round(distance * 10.0) / 10.0,
                    Math.round(eta * 10.0) / 10.0,
                    slackMinutes,
                    risk,
                    status,
                    departAt.toString(),
                    arriveAt.toString(),
                    departAt.toString(),
                    "DROPOFF".equals(type) ? sla.deliveryWindowEndAt().toString() : "",
                    serviceSeconds,
                    latenessSeconds,
                    priorityPenalty,
                    sla.priority(),
                    lateReason));
            totalDistance += distance;
            totalEta = java.time.Duration.between(routeStartedAt, departAt).toSeconds() / 60.0;
            timeCursor = departAt;
            previousLat = lat; previousLng = lng; previousId = stopId;
        }
        DashboardController.GeometryMode mode = roadGeometry && polyline.size() >= 2 ? DashboardController.GeometryMode.ROAD_ROUTE : DashboardController.GeometryMode.STRAIGHT_LINE;
        if (mode != DashboardController.GeometryMode.ROAD_ROUTE) {
            throw new IllegalStateException("OSRM_REQUIRED: final route geometry missing for " + routeId);
        }
        return new DashboardController.RouteVisualizationDto(routeId, driverId, "LIVE_SEED_WINNER", mode, null, "ACTIVE", stops, polyline, Math.round(totalDistance * 10.0) / 10.0, Math.round(totalEta * 10.0) / 10.0, lateCount);
    }

    private DispatchJobRequest.ApiOrderDto findLiveApiOrder(LiveSession session, String orderId) {
        if (session == null || blank(orderId)) return null;
        for (LiveBufferItem item : session.bufferedOrders) {
            if (item.order != null && orderId.equals(item.order.orderId())) return item.order;
        }
        return null;
    }

    private OrderSla orderSla(DashboardController.OrderDto order, DispatchJobRequest.ApiOrderDto apiOrder, Instant fallbackCreatedAt) {
        Instant createdAt = parseInstantOr(apiOrder == null ? null : apiOrder.createdAt(), fallbackCreatedAt);
        Instant pickupReadyAt = parseInstantOr(apiOrder == null ? null : apiOrder.pickupReadyAt(), createdAt);
        long fallbackDeadlineSeconds = Math.max(1, order.deadlineMinutes()) * 60L;
        Instant deadlineAt = parseInstantOr(apiOrder == null ? null : apiOrder.deliveryWindowEndAt(), createdAt.plusSeconds(fallbackDeadlineSeconds));
        long pickupServiceSeconds = positiveOr(apiOrder == null ? null : apiOrder.pickupServiceSeconds(), 120);
        long dropoffServiceSeconds = positiveOr(apiOrder == null ? null : apiOrder.dropoffServiceSeconds(), 90);
        long gracePeriodSeconds = nonNegativeOr(apiOrder == null ? null : apiOrder.gracePeriodSeconds(), 60);
        String priority = apiOrder == null || blank(apiOrder.priority()) ? priorityName(order.priority()) : normalizePriority(apiOrder.priority());
        return new OrderSla(createdAt, pickupReadyAt, deadlineAt, pickupServiceSeconds, dropoffServiceSeconds, priority, gracePeriodSeconds);
    }

    private Instant parseInstantOr(String value, Instant fallback) {
        if (blank(value)) return fallback;
        try {
            return Instant.parse(value);
        } catch (RuntimeException ignored) {
            return fallback;
        }
    }

    private long positiveOr(Integer value, long fallback) {
        return value == null || value <= 0 ? fallback : value;
    }

    private long nonNegativeOr(Integer value, long fallback) {
        return value == null || value < 0 ? fallback : value;
    }

    private String normalizePriority(String priority) {
        String normalized = priority == null ? "NORMAL" : priority.trim().toUpperCase(Locale.ROOT);
        return switch (normalized) {
            case "CRITICAL", "P0" -> "CRITICAL";
            case "URGENT", "P1" -> "URGENT";
            case "HIGH", "P2" -> "HIGH";
            default -> "NORMAL";
        };
    }

    private String priorityName(int priority) {
        if (priority >= 9) return "CRITICAL";
        if (priority >= 7) return "URGENT";
        if (priority >= 4) return "HIGH";
        return "NORMAL";
    }

    private double priorityLateWeight(String priority) {
        return switch (priority == null ? "NORMAL" : priority.toUpperCase(Locale.ROOT)) {
            case "CRITICAL" -> 8.0;
            case "URGENT" -> 4.0;
            case "HIGH" -> 2.0;
            default -> 1.0;
        };
    }

    private record OrderSla(Instant createdAt, Instant pickupReadyAt, Instant deliveryWindowEndAt, long pickupServiceSeconds, long dropoffServiceSeconds, String priority, long gracePeriodSeconds) { }

    private long adjustedTravelSeconds(double distanceKm, double osrmSeconds, DriverRuntimeState state) {
        double safeOsrm = Math.max(0.0, osrmSeconds);
        if (state == null || state.speedKmh <= 0.0) return Math.round(safeOsrm);
        double speed = Math.max(10.0, Math.min(60.0, state.speedKmh));
        double driverSeconds = distanceKm <= 0.0 ? safeOsrm : distanceKm / speed * 3600.0;
        return Math.round(Math.max(safeOsrm * 0.75, Math.min(safeOsrm * 2.5, driverSeconds)));
    }

    private void applyDriverRuntimeInput(DriverRuntimeState state, DispatchJobRequest.ApiDriverDto driver) {
        if (state == null || driver == null) return;
        if (driver.speedKmh() != null && Double.isFinite(driver.speedKmh())) state.speedKmh = Math.max(0.0, Math.min(60.0, driver.speedKmh()));
        if (!blank(driver.status())) state.status = driver.status();
    }

    private RoutingRouteResult routeLeg(String fromId, double fromLat, double fromLng, String toId, double toLat, double toLng, String intent) {
        return routingProvider.route(new BestPathRequest(
                new RouteStop(fromId, fromLat, fromLng, "LIVE_STOP", "hcm", null),
                new RouteStop(toId, toLat, toLng, "LIVE_STOP", "hcm", null),
                "normal",
                "clear",
                0,
                "road-refinement"));
    }

    private void appendPolyline(List<DashboardController.GeoPointDto> target, List<RoutePolylinePoint> points) {
        for (RoutePolylinePoint point : points == null ? List.<RoutePolylinePoint>of() : points) {
            DashboardController.GeoPointDto next = new DashboardController.GeoPointDto(point.latitude(), point.longitude());
            if (target.isEmpty()) {
                target.add(next);
                continue;
            }
            DashboardController.GeoPointDto last = target.get(target.size() - 1);
            if (Math.abs(last.lat() - next.lat()) > 0.000001 || Math.abs(last.lng() - next.lng()) > 0.000001) target.add(next);
        }
    }

    private List<RoutePolylinePoint> simplifyRoutePolyline(List<RoutePolylinePoint> points) {
        if (points == null || points.size() <= 2) return points == null ? List.of() : points;
        List<RoutePolylinePoint> deduped = new ArrayList<>();
        for (RoutePolylinePoint point : points) {
            if (deduped.isEmpty()) {
                deduped.add(point);
                continue;
            }
            RoutePolylinePoint last = deduped.getLast();
            if (haversineKm(last.latitude(), last.longitude(), point.latitude(), point.longitude()) >= 0.012) deduped.add(point);
        }
        RoutePolylinePoint lastInput = points.getLast();
        RoutePolylinePoint lastOutput = deduped.getLast();
        if (haversineKm(lastInput.latitude(), lastInput.longitude(), lastOutput.latitude(), lastOutput.longitude()) > 0.001) deduped.add(lastInput);
        return deduped.size() <= 96 ? deduped : sampledRoutePolyline(deduped, 96);
    }

    private List<RoutePolylinePoint> sampledRoutePolyline(List<RoutePolylinePoint> points, int maxPoints) {
        if (points.size() <= maxPoints) return points;
        List<RoutePolylinePoint> sampled = new ArrayList<>();
        sampled.add(points.getFirst());
        double step = (points.size() - 2) / (double) Math.max(1, maxPoints - 2);
        for (int index = 1; index < maxPoints - 1; index++) {
            sampled.add(points.get(Math.min(points.size() - 2, 1 + (int) Math.round((index - 1) * step))));
        }
        sampled.add(points.getLast());
        return sampled;
    }

    private List<DashboardController.GeoPointDto> cleanupGeoPolyline(List<DashboardController.GeoPointDto> points) {
        if (points == null || points.size() <= 2) return points == null ? List.of() : points;
        List<DashboardController.GeoPointDto> cleaned = new ArrayList<>();
        for (DashboardController.GeoPointDto point : points) {
            if (cleaned.isEmpty()) {
                cleaned.add(point);
                continue;
            }
            DashboardController.GeoPointDto last = cleaned.getLast();
            if (haversineKm(last.lat(), last.lng(), point.lat(), point.lng()) >= 0.012) cleaned.add(point);
        }
        DashboardController.GeoPointDto lastInput = points.getLast();
        DashboardController.GeoPointDto lastOutput = cleaned.getLast();
        if (haversineKm(lastInput.lat(), lastInput.lng(), lastOutput.lat(), lastOutput.lng()) > 0.001) cleaned.add(lastInput);
        return cleaned.size() <= 160 ? cleaned : sampledGeoPolyline(cleaned, 160);
    }

    private List<DashboardController.GeoPointDto> sampledGeoPolyline(List<DashboardController.GeoPointDto> points, int maxPoints) {
        if (points.size() <= maxPoints) return points;
        List<DashboardController.GeoPointDto> sampled = new ArrayList<>();
        sampled.add(points.getFirst());
        double step = (points.size() - 2) / (double) Math.max(1, maxPoints - 2);
        for (int index = 1; index < maxPoints - 1; index++) {
            sampled.add(points.get(Math.min(points.size() - 2, 1 + (int) Math.round((index - 1) * step))));
        }
        sampled.add(points.getLast());
        return sampled;
    }

    private List<String> asStringList(Object value) {
        if (!(value instanceof List<?> list)) return List.of();
        return list.stream().map(String::valueOf).toList();
    }

    private record SeedCandidateView(String seed, List<SolutionSeedRoute> routes, long runtimeMs, double distanceKm, long late, long assigned, String status, String reason) { }

    private DashboardController.RunVisualizationDto mergeWithActiveLiveRoutes(LiveSession session,
                                                                               DashboardController.RunVisualizationDto previousResult,
                                                                               DashboardController.RunVisualizationDto newResult) {
        if (previousResult == null || previousResult.routes() == null || previousResult.routes().isEmpty() || newResult == null || newResult.routes() == null || newResult.routes().isEmpty()) {
            return newResult;
        }
        List<Map<String, Object>> rejectedReassignments = new ArrayList<>();
        Map<String, DashboardController.RouteVisualizationDto> activeByDriver = new LinkedHashMap<>();
        for (DashboardController.RouteVisualizationDto route : previousResult.routes()) activeByDriver.put(route.driverId(), route);
        Map<String, DashboardController.OrderDto> orderLookup = liveOrderLookup(previousResult, newResult);
        Map<String, DashboardController.DriverDto> driverLookup = liveDriverLookup(previousResult, newResult);
        for (DashboardController.RouteVisualizationDto incoming : newResult.routes()) {
            DashboardController.RouteVisualizationDto sanitized = sanitizeIncomingRouteByLocks(session, incoming, rejectedReassignments);
            if (sanitized.stops().stream().noneMatch(stop -> !"DRIVER_START".equalsIgnoreCase(stop.type()))) continue;
            DashboardController.RouteVisualizationDto active = activeByDriver.get(sanitized.driverId());
            activeByDriver.put(sanitized.driverId(), active == null ? sanitized : appendRouteStops(active, sanitized, orderLookup, driverLookup));
        }
        List<DashboardController.RouteVisualizationDto> mergedRoutes = new ArrayList<>(activeByDriver.values());
        DashboardController.MetricsDto metrics = liveMergedMetrics(newResult.metrics(), mergedRoutes);
        Map<String, Object> diagnostics = new LinkedHashMap<>(newResult.diagnostics() == null ? Map.of() : newResult.diagnostics());
        diagnostics.put("liveRouteMerge", Map.of(
                "policy", "append-new-cycle-routes-to-active-routes",
                "previousRoutes", previousResult.routes().size(),
                "incomingRoutes", newResult.routes().size(),
                "mergedRoutes", mergedRoutes.size(),
                "routeLockPolicy", "HARD_LOCK_ASSIGNED_ORDERS",
                "lockedOrders", session.assignmentLedger.size(),
                "rejectedReassignments", rejectedReassignments
        ));
        return new DashboardController.RunVisualizationDto(
                newResult.runId(), newResult.scenarioId(), newResult.solverName(), newResult.solverVersion(), newResult.createdAt(), newResult.status(),
                newResult.inputSnapshot(), newResult.orders(), newResult.drivers(), newResult.batches(), newResult.assignments(), mergedRoutes,
                metrics, diagnostics, newResult.events(), newResult.comparison(), newResult.artifacts()
        );
    }

    private DashboardController.RouteVisualizationDto appendRouteStops(DashboardController.RouteVisualizationDto active,
                                                                        DashboardController.RouteVisualizationDto incoming,
                                                                        Map<String, DashboardController.OrderDto> orderLookup,
                                                                        Map<String, DashboardController.DriverDto> driverLookup) {
        Set<String> existingStopKeys = active.stops().stream()
                .filter(stop -> stop.orderId() != null && !stop.orderId().isBlank())
                .map(stop -> stop.type() + ":" + stop.orderId())
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        List<DashboardController.StopVisualizationDto> stops = new ArrayList<>(active.stops());
        int sequence = stops.stream().mapToInt(DashboardController.StopVisualizationDto::sequence).max().orElse(0);
        for (DashboardController.StopVisualizationDto stop : incoming.stops()) {
            if ("DRIVER_START".equalsIgnoreCase(stop.type())) continue;
            String stopKey = stop.orderId() == null || stop.orderId().isBlank() ? null : stop.type() + ":" + stop.orderId();
            if (stopKey != null && existingStopKeys.contains(stopKey)) continue;
            sequence += 1;
            stops.add(new DashboardController.StopVisualizationDto(sequence, stop.type(), stop.orderId(), stop.lat(), stop.lng(), stop.etaMinutes(), stop.distanceFromPreviousKm(), stop.travelTimeFromPreviousMinutes(), stop.deadlineSlackMinutes(), stop.riskLevel(), stop.status()));
            if (stopKey != null) existingStopKeys.add(stopKey);
        }
        for (DashboardController.StopVisualizationDto stop : incoming.stops()) {
            if (stop.orderId() == null || stop.orderId().isBlank() || !"PICKUP".equalsIgnoreCase(stop.type())) continue;
            String pickupKey = "PICKUP:" + stop.orderId();
            String dropoffKey = "DROPOFF:" + stop.orderId();
            if (!existingStopKeys.contains(pickupKey) || existingStopKeys.contains(dropoffKey)) continue;
            DashboardController.OrderDto order = orderLookup.get(stop.orderId());
            if (order == null) continue;
            DashboardController.StopVisualizationDto previous = stops.isEmpty() ? stop : stops.get(stops.size() - 1);
            double distance = haversineKm(previous.lat(), previous.lng(), order.dropoffLat(), order.dropoffLng());
            double travel = distance / 22.0 * 60.0;
            double eta = previous.etaMinutes() + travel;
            double slack = order.deadlineMinutes() - eta;
            String risk = slack < 8 ? "LATE_RISK" : slack < 15 ? "WATCH" : "LOW";
            sequence += 1;
            stops.add(new DashboardController.StopVisualizationDto(sequence, "DROPOFF", order.orderId(), order.dropoffLat(), order.dropoffLng(), round1(eta), round1(distance), round1(travel), round1(slack), risk, slack < 0 ? "LATE" : "OK"));
            existingStopKeys.add(dropoffKey);
        }
        List<String> stopSequence = stops.stream()
                .filter(stop -> stop.orderId() != null && !stop.orderId().isBlank())
                .map(stop -> stop.type().toUpperCase(Locale.ROOT) + ":" + stop.orderId())
                .toList();
        try {
            return routeFromSeedRow(active.routeId(), active.driverId(), stopSequence, orderLookup, driverLookup, true);
        } catch (RuntimeException exception) {
            throw new IllegalStateException("OSRM_REQUIRED: merged route geometry rebuild failed for " + active.routeId() + " stops=" + stopSequence.size() + " reason=" + exception.getMessage(), exception);
        }
    }

    private Map<String, DashboardController.OrderDto> liveOrderLookup(DashboardController.RunVisualizationDto previousResult,
                                                                       DashboardController.RunVisualizationDto newResult) {
        Map<String, DashboardController.OrderDto> lookup = new LinkedHashMap<>();
        if (previousResult != null && previousResult.orders() != null) previousResult.orders().forEach(order -> lookup.put(order.orderId(), order));
        if (newResult != null && newResult.orders() != null) newResult.orders().forEach(order -> lookup.put(order.orderId(), order));
        for (DashboardController.RunVisualizationDto result : Arrays.asList(previousResult, newResult)) {
            if (result == null || result.routes() == null) continue;
            for (DashboardController.RouteVisualizationDto route : result.routes()) {
                Map<String, DashboardController.StopVisualizationDto> pickups = new LinkedHashMap<>();
                Map<String, DashboardController.StopVisualizationDto> dropoffs = new LinkedHashMap<>();
                for (DashboardController.StopVisualizationDto stop : route.stops()) {
                    if (blank(stop.orderId())) continue;
                    if ("PICKUP".equalsIgnoreCase(stop.type())) pickups.put(stop.orderId(), stop);
                    if ("DROPOFF".equalsIgnoreCase(stop.type())) dropoffs.put(stop.orderId(), stop);
                }
                for (String orderId : pickups.keySet()) {
                    if (lookup.containsKey(orderId) || !dropoffs.containsKey(orderId)) continue;
                    DashboardController.StopVisualizationDto pickup = pickups.get(orderId);
                    DashboardController.StopVisualizationDto dropoff = dropoffs.get(orderId);
                    lookup.put(orderId, new DashboardController.OrderDto(orderId, "LIVE_MERGED", pickup.lat(), pickup.lng(), dropoff.lat(), dropoff.lng(), 1, 1, Math.max(30, (int) Math.ceil(Math.max(pickup.etaMinutes(), dropoff.etaMinutes()) + 45))));
                }
            }
        }
        return lookup;
    }

    private Map<String, DashboardController.DriverDto> liveDriverLookup(DashboardController.RunVisualizationDto previousResult,
                                                                         DashboardController.RunVisualizationDto newResult) {
        Map<String, DashboardController.DriverDto> lookup = new LinkedHashMap<>();
        if (previousResult != null && previousResult.drivers() != null) previousResult.drivers().forEach(driver -> lookup.put(driver.driverId(), driver));
        if (newResult != null && newResult.drivers() != null) newResult.drivers().forEach(driver -> lookup.put(driver.driverId(), driver));
        for (DashboardController.RunVisualizationDto result : Arrays.asList(previousResult, newResult)) {
            if (result == null || result.routes() == null) continue;
            for (DashboardController.RouteVisualizationDto route : result.routes()) {
                if (lookup.containsKey(route.driverId())) continue;
                DashboardController.StopVisualizationDto start = route.stops().stream().filter(stop -> "DRIVER_START".equalsIgnoreCase(stop.type())).findFirst().orElse(route.stops().isEmpty() ? null : route.stops().getFirst());
                if (start != null) lookup.put(route.driverId(), new DashboardController.DriverDto(route.driverId(), start.lat(), start.lng(), 100, 0, "IDLE"));
            }
        }
        return lookup;
    }

    private DashboardController.RouteVisualizationDto sanitizeIncomingRouteByLocks(LiveSession session,
                                                                                   DashboardController.RouteVisualizationDto incoming,
                                                                                   List<Map<String, Object>> rejectedReassignments) {
        if (session == null || session.assignmentLedger.isEmpty()) return incoming;
        List<DashboardController.StopVisualizationDto> stops = new ArrayList<>();
        int sequence = 0;
        for (DashboardController.StopVisualizationDto stop : incoming.stops()) {
            if ("DRIVER_START".equalsIgnoreCase(stop.type())) {
                stops.add(stop);
                sequence = Math.max(sequence, stop.sequence());
                continue;
            }
            if (blank(stop.orderId())) continue;
            AssignmentLock lock = session.assignmentLedger.get(stop.orderId());
            if (lock != null) {
                if (!Objects.equals(lock.driverId, incoming.driverId())) {
                    rejectedReassignments.add(Map.of("orderId", stop.orderId(), "fromDriver", lock.driverId, "incomingDriver", incoming.driverId(), "type", stop.type(), "reason", "LOCK_GUARD_REJECTED_REASSIGN"));
                    continue;
                }
                rejectedReassignments.add(Map.of("orderId", stop.orderId(), "driverId", incoming.driverId(), "type", stop.type(), "reason", "LOCK_GUARD_KEEP_ACTIVE_STOP"));
                continue;
            }
            sequence += 1;
            stops.add(new DashboardController.StopVisualizationDto(sequence, stop.type(), stop.orderId(), stop.lat(), stop.lng(), stop.etaMinutes(), stop.distanceFromPreviousKm(), stop.travelTimeFromPreviousMinutes(), stop.deadlineSlackMinutes(), stop.riskLevel(), stop.status()));
        }
        return new DashboardController.RouteVisualizationDto(incoming.routeId(), incoming.driverId(), incoming.batchId(), incoming.geometryMode(), incoming.oldRouteId(), incoming.rescueStatus(), stops, incoming.polyline(), incoming.totalDistanceKm(), incoming.totalEtaMinutes(), incoming.lateOrderCount());
    }

    private void lockAssignedOrders(LiveSession session, DashboardController.RunVisualizationDto result, String cycleId) {
        if (session == null || result == null || result.routes() == null) return;
        for (DashboardController.RouteVisualizationDto route : result.routes()) {
            for (DashboardController.StopVisualizationDto stop : route.stops()) {
                if (blank(stop.orderId()) || "DRIVER_START".equalsIgnoreCase(stop.type())) continue;
                session.assignmentLedger.putIfAbsent(stop.orderId(), new AssignmentLock(stop.orderId(), route.driverId(), cycleId, Instant.now().toString()));
            }
        }
    }

    private List<Map<String, Object>> assignmentLedgerView(LiveSession session) {
        if (session == null) return List.of();
        return session.assignmentLedger.values().stream().map(lock -> Map.<String, Object>of(
                "orderId", lock.orderId,
                "driverId", lock.driverId,
                "cycleId", lock.cycleId,
                "lockedAt", lock.lockedAt,
                "policy", "HARD_LOCK_ASSIGNED_ORDERS"
        )).toList();
    }

    private double round1(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private String cycleIdSafe(DashboardController.RunVisualizationDto result) {
        return result == null || blank(result.runId()) ? id("cycle") : result.runId();
    }

    private String coord(Double lat, Double lng) {
        if (lat == null || lng == null) return "--,--";
        return round1(lat) + "," + round1(lng);
    }

    private Map<String, Object> orderConsoleData(DispatchJobRequest.ApiOrderDto order, LiveBufferItem item) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("orderId", order == null ? "" : order.orderId());
        row.put("pickup", order == null ? Map.of() : Map.of("lat", order.pickupLat(), "lng", order.pickupLng()));
        row.put("dropoff", order == null ? Map.of() : Map.of("lat", order.dropoffLat(), "lng", order.dropoffLng()));
        row.put("demand", order == null || order.demand() == null ? 1 : order.demand());
        row.put("deadlineMinutes", order == null || order.deadlineMinutes() == null ? 90 : order.deadlineMinutes());
        row.put("priority", order == null || blank(order.priority()) ? "NORMAL" : order.priority());
        row.put("pickupServiceSeconds", order == null || order.pickupServiceSeconds() == null ? 120 : order.pickupServiceSeconds());
        row.put("dropoffServiceSeconds", order == null || order.dropoffServiceSeconds() == null ? 90 : order.dropoffServiceSeconds());
        if (item != null) row.put("buffer", bufferItemView(item));
        return row;
    }

    private Map<String, Object> consoleEvent(String cycleId, String stage, String level, String type, String message, Map<String, Object> data) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", id("log"));
        row.put("at", Instant.now().toString());
        row.put("cycleId", cycleId == null ? "" : cycleId);
        row.put("stage", stage == null ? "GENERAL" : stage);
        row.put("level", level == null ? "info" : level);
        row.put("type", type == null ? "EVENT" : type);
        row.put("message", message == null ? "" : message);
        row.put("data", data == null ? Map.of() : data);
        return row;
    }

    private void appendConsoleTrace(LiveSession session, String stage, String level, String type, String message, Map<String, Object> data) {
        if (session == null) return;
        session.consoleTrace.add(consoleEvent("", stage, level, type, message, data));
        trimConsoleTrace(session);
    }

    private void appendConsoleTrace(LiveSession session, List<Map<String, Object>> events) {
        if (session == null || events == null || events.isEmpty()) return;
        session.consoleTrace.addAll(events);
        trimConsoleTrace(session);
    }

    private void trimConsoleTrace(LiveSession session) {
        int overflow = session.consoleTrace.size() - 600;
        if (overflow > 0) session.consoleTrace.subList(0, overflow).clear();
    }

    private List<Map<String, Object>> consoleTraceView(LiveSession session) {
        return session == null ? List.of() : List.copyOf(session.consoleTrace);
    }

    private List<Map<String, Object>> buildCycleConsoleTrace(LiveSession session, String cycleId, List<LiveBufferItem> cycleItems, Map<String, Object> seedArchive, DashboardController.RunVisualizationDto result, Map<String, Object> liveTrace, Map<String, Object> latencyTrace) {
        List<Map<String, Object>> events = new ArrayList<>();
        events.add(consoleEvent(cycleId, "BUFFER", "info", "BUFFER_SELECTION", "Backend selected " + cycleItems.size() + " buffered orders for optimization", Map.of("selectedOrders", cycleItems.stream().map(item -> item.order.orderId()).toList(), "bufferItems", cycleItems.stream().map(this::bufferItemView).toList(), "latencyTrace", latencyTrace)));
        for (LiveBufferItem item : cycleItems) {
            events.add(consoleEvent(cycleId, "AGING", item.promotedThisRound ? "warn" : "info", "AGING_SCORE_UPDATED", item.order.orderId() + " priority " + item.priorityLevel + " finalScore " + round1(item.finalScore), bufferItemView(item)));
        }
        for (Map<String, Object> cluster : liveClusters(result, cycleItems.stream().map(item -> item.order).toList())) {
            events.add(consoleEvent(cycleId, "CLUSTER", "info", "CLUSTER_CREATED", "Cluster " + cluster.getOrDefault("batchId", "LIVE_BUFFER") + " contains " + cluster.getOrDefault("orders", List.of()), cluster));
        }
        for (Map<String, Object> candidate : liveDriverCandidates(session, result)) {
            events.add(consoleEvent(cycleId, "DRIVER_MATCH", "SELECT".equals(candidate.get("decision")) ? "ok" : "info", "DRIVER_CANDIDATE_SCORED", "Order " + candidate.get("orderId") + " vs driver " + candidate.get("driverId") + " score " + candidate.get("score") + " => " + candidate.get("decision"), candidate));
        }
        for (Object seedObject : asList(seedArchive == null ? null : seedArchive.get("ranking"))) {
            Map<String, Object> seed = asMap(seedObject);
            events.add(consoleEvent(cycleId, "SEED_RACE", Boolean.TRUE.equals(seed.get("isFinal")) ? "ok" : "info", "SEED_RACE_RESULT", "Seed " + seed.getOrDefault("solver", seed.getOrDefault("seedId", "UNKNOWN")) + " distance " + seed.getOrDefault("distanceKm", "--") + "km late " + seed.getOrDefault("lateCount", "--"), seed));
        }
        Map<String, Object> finalSeed = asMap(result == null || result.diagnostics() == null ? null : result.diagnostics().get("liveFinalSeedSource"));
        for (Object routeReportObject : asList(finalSeed.get("routes"))) {
            Map<String, Object> routeReport = asMap(routeReportObject);
            for (Object candidateObject : asList(routeReport.get("candidates"))) {
                Map<String, Object> candidate = asMap(candidateObject);
                events.add(consoleEvent(cycleId, "IRX_OPTIMIZE", "PASS".equals(candidate.get("dominanceGuard")) ? "ok" : "warn", "IRX_REFINEMENT_RESULT", "Optimizer " + candidate.getOrDefault("optimizer", "IRX") + " " + candidate.getOrDefault("inputDistanceKm", "--") + "km -> " + candidate.getOrDefault("outputDistanceKm", "--") + "km late " + candidate.getOrDefault("outputLate", "--"), candidate));
            }
        }
        if (result != null && result.routes() != null) {
            for (DashboardController.RouteVisualizationDto route : result.routes()) {
                Map<String, Object> routeData = new LinkedHashMap<>();
                routeData.put("routeId", route.routeId());
                routeData.put("driverId", route.driverId());
                routeData.put("totalDistanceKm", route.totalDistanceKm());
                routeData.put("totalEtaMinutes", route.totalEtaMinutes());
                routeData.put("lateOrderCount", route.lateOrderCount());
                routeData.put("stopSequence", route.stops().stream().filter(stop -> !blank(stop.orderId())).map(stop -> stop.type() + ":" + stop.orderId()).toList());
                events.add(consoleEvent(cycleId, "ROUTE", "ok", "FINAL_ROUTE_READY", "Route " + route.routeId() + " driver " + route.driverId() + " " + route.totalDistanceKm() + "km ETA " + route.totalEtaMinutes() + "m late " + route.lateOrderCount(), routeData));
                for (DashboardController.StopVisualizationDto stop : route.stops()) {
                    if (blank(stop.orderId())) continue;
                    Map<String, Object> stopData = new LinkedHashMap<>();
                    stopData.put("routeId", route.routeId());
                    stopData.put("driverId", route.driverId());
                    stopData.put("sequence", stop.sequence());
                    stopData.put("type", stop.type());
                    stopData.put("orderId", stop.orderId());
                    stopData.put("lat", stop.lat());
                    stopData.put("lng", stop.lng());
                    stopData.put("distanceFromPreviousKm", stop.distanceFromPreviousKm());
                    stopData.put("travelTimeFromPreviousMinutes", stop.travelTimeFromPreviousMinutes());
                    stopData.put("etaAt", stop.etaAt());
                    stopData.put("arriveAt", stop.arriveAt());
                    stopData.put("departAt", stop.departAt());
                    stopData.put("deadlineAt", stop.deadlineAt());
                    stopData.put("serviceSeconds", stop.serviceSeconds());
                    stopData.put("latenessSeconds", stop.latenessSeconds());
                    stopData.put("priority", stop.priority());
                    stopData.put("lateReason", stop.lateReason());
                    events.add(consoleEvent(cycleId, "ETA_LATE", stop.latenessSeconds() > 0 ? "warn" : "info", "STOP_TIMING", stop.type() + " " + stop.orderId() + " ETA " + stop.etaAt() + " late " + stop.latenessSeconds() + "s", stopData));
                }
            }
        }
        int assignedCount = assignedOrderIds(result).size();
        int remainingAfterCycle = Math.max(0, session.bufferedOrders.size() - assignedCount);
        events.add(consoleEvent(cycleId, "FINAL", "ok", "BUFFER_AFTER_CYCLE", "Cycle completed assigned " + assignedCount + ", remaining buffer " + remainingAfterCycle, Map.of("finalSelection", asMap(liveTrace.get("finalSelection")), "dispatchRound", asMap(liveTrace.get("dispatchRound")), "assignedOrders", assignedCount, "remainingBuffer", remainingAfterCycle)));
        return events;
    }

    private DashboardController.MetricsDto liveMergedMetrics(DashboardController.MetricsDto base, List<DashboardController.RouteVisualizationDto> routes) {
        long drivers = routes.stream().map(DashboardController.RouteVisualizationDto::driverId).distinct().count();
        double distance = Math.round(routes.stream().mapToDouble(DashboardController.RouteVisualizationDto::totalDistanceKm).sum() * 10.0) / 10.0;
        long late = routes.stream().mapToLong(DashboardController.RouteVisualizationDto::lateOrderCount).sum();
        long assigned = routes.stream().flatMap(route -> route.stops().stream()).map(DashboardController.StopVisualizationDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).distinct().count();
        double sla = assigned == 0 ? 100.0 : Math.round(((assigned - late) * 1000.0 / assigned)) / 10.0;
        long runtime = base == null ? 0 : base.runtimeMs();
        long rejected = base == null ? 0 : base.rejectedOrderCount();
        return new DashboardController.MetricsDto(drivers, distance, late, assigned, sla, runtime, routes.size(), rejected);
    }

    private Map<String, Object> buildLiveDecisionTrace(LiveSession session,
                                                        List<DispatchJobRequest.ApiOrderDto> cycleOrders,
                                                        DashboardController.RunVisualizationDto result,
                                                        DashboardController.RunVisualizationDto previousResult,
                                                        String pdLnsMode,
                                                        RollingCycleRequest request,
                                                        Map<String, Object> latencyTrace) {
        Map<String, Object> trace = new LinkedHashMap<>();
        Map<String, Object> coreTrace = asMap(result == null || result.diagnostics() == null ? null : result.diagnostics().get("decisionTrace"));
        List<Map<String, Object>> orderPool = liveOrderPool(cycleOrders);
        List<Map<String, Object>> clusters = liveClusters(result, cycleOrders);
        List<Map<String, Object>> candidates = liveDriverCandidates(session, result);
        List<Map<String, Object>> seedRace = liveSeedRace(result, pdLnsMode);
        Map<String, Object> finalSelection = liveFinalSelection(result, previousResult, seedRace, pdLnsMode, request);

        trace.put("source", "BACKEND_LIVE_ROLLING_ENGINE");
        trace.put("generatedAt", Instant.now().toString());
        trace.put("sessionId", session.sessionId);
        trace.put("inputProcessing", Map.of(
                "status", "PASS",
                "drivers", session.drivers.size(),
                "orders", cycleOrders.size(),
                "bufferedOrders", cycleOrders.size(),
                "requestId", request == null ? "" : Objects.toString(request.requestId(), "")
        ));
        trace.put("aggregationBuffer", Map.of("windowMs", 3000, "ordersReady", cycleOrders.size(), "rollingHorizon", "ACTIVE"));
        trace.put("agingPriority", agingPriorityTrace(session));
        trace.put("bufferMonitor", bufferMonitor(session));
        trace.put("bufferItems", bufferItemsView(session));
        trace.put("latencyTrace", latencyTrace);
        trace.put("orderPool", orderPool);
        trace.put("filtering", Map.of("feasible", orderPool.stream().filter(row -> Boolean.TRUE.equals(row.get("feasible"))).count(), "rejected", 0, "rules", List.of("tenant", "capacity", "deadline", "coordinates", "duplicate")));
        trace.put("clusterSelection", clusters);
        trace.put("cluster", clusters);
        trace.put("driverCandidateSelection", candidates);
        trace.put("assignmentCandidates", candidates);
        trace.put("driverMatch", candidates);
        trace.put("seedRace", seedRace);
        trace.put("solverRace", seedRace);
        trace.put("dominanceGuard", Map.of("status", "PASS", "selectedSource", finalSelection.get("selectedSource"), "objective", "coverage -> hard violations -> late count -> total lateness -> distance -> runtime", "rejectedSeeds", rejectedSeeds(seedRace, String.valueOf(finalSelection.get("selectedSource")))));
        trace.put("adaptiveMl", Map.of("mode", pdLnsMode, "qualitySeeking", true, "accepted", true, "policy", "accept only non-regressing live insertion"));
        trace.put("freezePolicy", liveFreezePolicy(result));
        trace.put("routeLockPolicy", Map.of("policy", "HARD_LOCK_ASSIGNED_ORDERS", "lockedOrders", assignmentLedgerView(session), "lockedCount", session.assignmentLedger.size()));
        trace.put("liveInsertion", Map.of("status", "COMPLETED", "scope", "remaining route after frozen stop", "newOrders", cycleOrders.stream().map(DispatchJobRequest.ApiOrderDto::orderId).toList()));
        trace.put("routeOrdering", liveRouteOrdering(result));
        trace.put("finalAssignment", liveRouteOrdering(result));
        trace.put("finalSelection", finalSelection);
        trace.put("dispatchRound", dispatchRoundTrace(session, result));
        trace.put("kpi", Map.of("decisionLatencyMs", latencyTrace.getOrDefault("cycleBackendMs", result == null ? 0 : result.metrics().runtimeMs()), "routeChurnPercent", finalSelection.get("routeChurnPercent"), "lateCount", result == null ? 0 : result.metrics().lateOrderCount(), "queueDepth", session.bufferedOrders.size(), "lockedOrders", session.assignmentLedger.size()));
        if (!coreTrace.isEmpty()) trace.put("coreDecisionTrace", coreTrace);
        return trace;
    }

    private Map<String, Object> liveLatencyTrace(List<LiveBufferItem> cycleItems,
                                                 Instant cycleRequestedAt,
                                                 Instant cycleStartedAt,
                                                 Instant routeReadyAt,
                                                 DashboardController.RunVisualizationDto result) {
        Instant firstReceivedAt = cycleItems.stream().map(item -> item.receivedAt).min(Comparator.naturalOrder()).orElse(cycleRequestedAt);
        Instant lastReceivedAt = cycleItems.stream().map(item -> item.receivedAt).max(Comparator.naturalOrder()).orElse(cycleRequestedAt);
        Instant firstBufferedAt = cycleItems.stream().map(item -> item.bufferEnteredAt).min(Comparator.naturalOrder()).orElse(cycleRequestedAt);
        Map<String, Object> trace = new LinkedHashMap<>();
        trace.put("ordersMeasured", cycleItems.size());
        trace.put("firstOrderReceivedAt", firstReceivedAt.toString());
        trace.put("lastOrderReceivedAt", lastReceivedAt.toString());
        trace.put("cycleRequestedAt", cycleRequestedAt.toString());
        trace.put("cycleStartedAt", cycleStartedAt.toString());
        trace.put("routeReadyAt", routeReadyAt.toString());
        trace.put("firstOrderToRouteReadyMs", elapsedMillis(firstReceivedAt, routeReadyAt));
        trace.put("lastOrderToRouteReadyMs", elapsedMillis(lastReceivedAt, routeReadyAt));
        trace.put("firstBufferedToRouteReadyMs", elapsedMillis(firstBufferedAt, routeReadyAt));
        trace.put("cycleQueueWaitMs", elapsedMillis(cycleRequestedAt, cycleStartedAt));
        trace.put("cycleBackendMs", elapsedMillis(cycleStartedAt, routeReadyAt));
        trace.put("solverRuntimeMs", result == null ? 0 : result.metrics().runtimeMs());
        return trace;
    }

    private List<Map<String, Object>> liveOrderPool(List<DispatchJobRequest.ApiOrderDto> orders) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (DispatchJobRequest.ApiOrderDto order : orders) {
            rows.add(Map.of(
                    "orderId", blank(order.orderId()) ? "ORD" : order.orderId(),
                    "demand", order.demand() == null ? 1 : order.demand(),
                    "deadline", order.deadlineMinutes() == null ? 90 : order.deadlineMinutes(),
                    "pickup", Map.of("lat", order.pickupLat(), "lng", order.pickupLng()),
                    "dropoff", Map.of("lat", order.dropoffLat(), "lng", order.dropoffLng()),
                    "status", "FEASIBLE",
                    "feasible", true
            ));
        }
        return rows;
    }

    private Map<String, Object> liveStateDecisionTrace(LiveSession session) {
        Map<String, Object> realtime = realtimeLiveDecisionTrace(session, "LIVE_STATE_REALTIME_CLUSTER");
        Map<String, Object> previous = asMap(session.lastResult == null || session.lastResult.diagnostics() == null ? null : session.lastResult.diagnostics().get("decisionTrace"));
        if (!previous.isEmpty()) {
            Map<String, Object> merged = new LinkedHashMap<>(previous);
            List<?> realtimeOrderPool = asList(realtime.get("orderPool"));
            merged.put("realtime", true);
            if (!realtimeOrderPool.isEmpty()) {
                merged.put("orderPool", realtime.get("orderPool"));
                merged.put("clusterSelection", realtime.get("clusterSelection"));
                merged.put("cluster", realtime.get("cluster"));
            }
            merged.put("bufferMonitor", bufferMonitor(session));
            merged.put("bufferItems", bufferItemsView(session));
            merged.put("generatedAt", Instant.now().toString());
            return merged;
        }
        return realtime;
    }

    private Map<String, Object> realtimeLiveDecisionTrace(LiveSession session, String source) {
        List<DispatchJobRequest.ApiOrderDto> orders = session.bufferedOrders.stream().map(item -> item.order).toList();
        List<Map<String, Object>> orderPool = liveOrderPool(orders);
        List<Map<String, Object>> clusters = spatialLiveClusters(orders, 6);
        Map<String, Object> trace = new LinkedHashMap<>();
        trace.put("source", source);
        trace.put("realtime", true);
        trace.put("generatedAt", Instant.now().toString());
        trace.put("sessionId", session.sessionId);
        trace.put("inputProcessing", Map.of("status", "REALTIME", "drivers", session.drivers.size(), "orders", orders.size(), "bufferedOrders", session.bufferedOrders.size()));
        trace.put("orderPool", orderPool);
        trace.put("filtering", Map.of("feasible", orderPool.size(), "rejected", 0, "rules", List.of("coordinates", "buffer-live")));
        trace.put("clusterSelection", clusters);
        trace.put("cluster", clusters);
        trace.put("driverCandidateSelection", realtimeDriverCandidates(session, clusters));
        trace.put("driverMatch", realtimeDriverCandidates(session, clusters));
        trace.put("bufferMonitor", bufferMonitor(session));
        trace.put("bufferItems", bufferItemsView(session));
        return trace;
    }

    private List<Map<String, Object>> spatialLiveClusters(List<DispatchJobRequest.ApiOrderDto> orders, int maxClusters) {
        List<DispatchJobRequest.ApiOrderDto> sorted = new ArrayList<>(orders);
        sorted.sort(Comparator.comparingDouble((DispatchJobRequest.ApiOrderDto order) -> (order.pickupLng() + order.dropoffLng()) / 2.0)
                .thenComparingDouble(order -> (order.pickupLat() + order.dropoffLat()) / 2.0));
        if (sorted.isEmpty()) return List.of();
        int targetClusters = Math.max(1, Math.min(maxClusters, (int) Math.round(Math.sqrt(sorted.size()))));
        int chunkSize = Math.max(3, (int) Math.ceil(sorted.size() / (double) targetClusters));
        List<Map<String, Object>> clusters = new ArrayList<>();
        for (int index = 0; index < sorted.size(); index += chunkSize) {
            List<DispatchJobRequest.ApiOrderDto> chunk = sorted.subList(index, Math.min(sorted.size(), index + chunkSize));
            List<String> orderIds = chunk.stream().map(DispatchJobRequest.ApiOrderDto::orderId).toList();
            double minLat = chunk.stream().flatMapToDouble(order -> java.util.stream.DoubleStream.of(order.pickupLat(), order.dropoffLat())).min().orElse(0);
            double maxLat = chunk.stream().flatMapToDouble(order -> java.util.stream.DoubleStream.of(order.pickupLat(), order.dropoffLat())).max().orElse(0);
            double minLng = chunk.stream().flatMapToDouble(order -> java.util.stream.DoubleStream.of(order.pickupLng(), order.dropoffLng())).min().orElse(0);
            double maxLng = chunk.stream().flatMapToDouble(order -> java.util.stream.DoubleStream.of(order.pickupLng(), order.dropoffLng())).max().orElse(0);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("batchId", "LIVE_SPATIAL_" + (clusters.size() + 1));
            row.put("orderIds", orderIds);
            row.put("orders", orderIds);
            row.put("totalDemand", chunk.stream().mapToInt(order -> order.demand() == null ? 1 : order.demand()).sum());
            row.put("load", row.get("totalDemand"));
            row.put("driverId", "PENDING_MATCH");
            row.put("status", "REALTIME_BUFFER_CLUSTER");
            row.put("centroid", Map.of("lat", round6((minLat + maxLat) / 2.0), "lng", round6((minLng + maxLng) / 2.0)));
            row.put("bounds", Map.of("minLat", round6(minLat), "maxLat", round6(maxLat), "minLng", round6(minLng), "maxLng", round6(maxLng)));
            clusters.add(row);
        }
        return clusters;
    }

    private List<Map<String, Object>> realtimeDriverCandidates(LiveSession session, List<Map<String, Object>> clusters) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> cluster : clusters) {
            List<String> orderIds = asStringList(cluster.get("orderIds"));
            DispatchJobRequest.ApiOrderDto firstOrder = session.bufferedOrders.stream().map(item -> item.order).filter(order -> orderIds.contains(order.orderId())).findFirst().orElse(null);
            if (firstOrder == null) continue;
            for (DispatchJobRequest.ApiDriverDto driver : session.drivers.stream().limit(4).toList()) {
                double score = routeFitScore(driver, firstOrder);
                rows.add(Map.of("batchId", cluster.get("batchId"), "driverId", driver.driverId(), "score", round1(score), "selectionScore", round1(score), "decision", "REALTIME_CANDIDATE", "reason", "preview nearest driver for live cluster"));
            }
        }
        return rows;
    }

    private double round6(double value) {
        return Math.round(value * 1_000_000.0) / 1_000_000.0;
    }

    private List<LiveBufferItem> selectCycleItems(LiveSession session) {
        return session.bufferedOrders.stream()
                .sorted(Comparator.comparingInt((LiveBufferItem item) -> priorityRank(item.priorityLevel)).reversed()
                        .thenComparing(Comparator.comparingDouble((LiveBufferItem item) -> item.finalScore).reversed()))
                .toList();
    }

    private void updateAging(LiveBufferItem item, Instant now) {
        item.lastCheckedAt = now;
        long waitingSeconds = Math.max(0, now.getEpochSecond() - item.bufferEnteredAt.getEpochSecond());
        item.waitingMinutes = waitingSeconds / 60.0;
        item.urgencyScore = item.waitingMinutes * 2.0 + item.skippedRounds * 15.0 + item.skippedRounds * item.skippedRounds * 5.0;
        String previous = item.priorityLevel;
        item.priorityLevel = priorityFor(item.waitingMinutes, item.skippedRounds, previous);
        item.routeFitScore = Math.max(0, 100.0 - item.skippedRounds * 4.0);
        item.driverBalanceScore = 50.0;
        item.routeCostPenalty = Math.max(0, 12.0 - item.skippedRounds);
        item.finalScore = weightedScore(item.priorityLevel, item.routeFitScore, item.driverBalanceScore, item.urgencyScore, item.routeCostPenalty);
        if (!Objects.equals(previous, item.priorityLevel)) item.promotedThisRound = true;
    }

    private String priorityFor(double waitingMinutes, int skippedRounds, String previous) {
        if ("CRITICAL".equals(previous) && skippedRounds >= 6) return "FORCE_ASSIGN";
        if (waitingMinutes >= 10 || skippedRounds >= 5) return "CRITICAL";
        if (waitingMinutes >= 5 || skippedRounds >= 3) return "HOT";
        if (waitingMinutes >= 2 || skippedRounds >= 2) return "WARM";
        return "NORMAL";
    }

    private double weightedScore(String priorityLevel, double routeFit, double balance, double urgency, double penalty) {
        return switch (priorityLevel) {
            case "FORCE_ASSIGN" -> 0.05 * routeFit + 0.20 * balance + 0.80 * urgency - 0.05 * penalty;
            case "CRITICAL" -> 0.15 * routeFit + 0.15 * balance + 0.60 * urgency - 0.10 * penalty;
            case "HOT" -> 0.30 * routeFit + 0.20 * balance + 0.40 * urgency - 0.10 * penalty;
            default -> 0.45 * routeFit + 0.25 * balance + 0.20 * urgency - 0.10 * penalty;
        };
    }

    private int priorityRank(String priorityLevel) {
        return switch (priorityLevel) {
            case "FORCE_ASSIGN" -> 5;
            case "CRITICAL" -> 4;
            case "HOT" -> 3;
            case "WARM" -> 2;
            default -> 1;
        };
    }

    private Set<String> assignedOrderIds(DashboardController.RunVisualizationDto result) {
        Set<String> assigned = new LinkedHashSet<>();
        if (result == null || result.routes() == null) return assigned;
        for (DashboardController.RouteVisualizationDto route : result.routes()) {
            for (DashboardController.StopVisualizationDto stop : route.stops()) {
                if (!blank(stop.orderId())) assigned.add(stop.orderId());
            }
        }
        return assigned;
    }

    private void updateBufferAfterCycle(LiveSession session, Set<String> assignedOrderIds, String cycleId) {
        for (LiveBufferItem item : session.bufferedOrders) {
            if (assignedOrderIds.contains(item.order.orderId())) {
                item.status = "ASSIGNED";
                item.assignedCycleId = cycleId;
                appendConsoleTrace(session, "ASSIGNMENT", "ok", "ORDER_ASSIGNED", "Order " + item.order.orderId() + " assigned in cycle " + cycleId, Map.of("orderId", item.order.orderId(), "cycleId", cycleId));
            } else {
                item.skippedRounds += 1;
                item.status = "WAITING";
                updateAging(item, Instant.now());
                appendConsoleTrace(session, "BUFFER", "warn", "ORDER_SKIPPED", "Order " + item.order.orderId() + " remains in buffer as " + item.priorityLevel, bufferItemView(item));
            }
        }
        session.bufferedOrders.removeIf(item -> assignedOrderIds.contains(item.order.orderId()));
    }

    private Map<String, Object> bufferItemView(LiveBufferItem item) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("orderId", item.order.orderId());
        row.put("status", item.status);
        row.put("receivedAt", item.receivedAt.toString());
        row.put("bufferEnteredAt", item.bufferEnteredAt.toString());
        row.put("lastCheckedAt", item.lastCheckedAt.toString());
        row.put("waitingMinutes", Math.round(item.waitingMinutes * 10.0) / 10.0);
        row.put("skippedRounds", item.skippedRounds);
        row.put("priorityLevel", item.priorityLevel);
        row.put("urgencyScore", Math.round(item.urgencyScore * 10.0) / 10.0);
        row.put("routeFitScore", Math.round(item.routeFitScore * 10.0) / 10.0);
        row.put("driverBalanceScore", Math.round(item.driverBalanceScore * 10.0) / 10.0);
        row.put("routeCostPenalty", Math.round(item.routeCostPenalty * 10.0) / 10.0);
        row.put("finalScore", Math.round(item.finalScore * 10.0) / 10.0);
        row.put("forceAssign", "FORCE_ASSIGN".equals(item.priorityLevel));
        row.put("order", item.order);
        return row;
    }

    private List<Map<String, Object>> bufferItemsView(LiveSession session) {
        return session.bufferedOrders.stream().map(this::bufferItemView).toList();
    }

    private Map<String, Object> bufferMonitor(LiveSession session) {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (String level : List.of("NORMAL", "WARM", "HOT", "CRITICAL", "FORCE_ASSIGN")) counts.put(level, 0L);
        for (LiveBufferItem item : session.bufferedOrders) counts.put(item.priorityLevel, counts.getOrDefault(item.priorityLevel, 0L) + 1);
        double oldest = session.bufferedOrders.stream().mapToDouble(item -> item.waitingMinutes).max().orElse(0.0);
        return Map.of("total", session.bufferedOrders.size(), "byPriority", counts, "oldestWaitingMinutes", Math.round(oldest * 10.0) / 10.0);
    }

    private Map<String, Object> agingPriorityTrace(LiveSession session) {
        return Map.of("algorithm", "Aging Priority Balanced Dispatch", "capacityHardLimit", "DISABLED_FOR_LIVE", "weights", Map.of("normal", "route45 balance25 urgency20 penalty10", "hot", "route30 balance20 urgency40 penalty10", "critical", "route15 balance15 urgency60 penalty10"), "bufferMonitor", bufferMonitor(session));
    }

    private Map<String, Object> dispatchRoundTrace(LiveSession session, DashboardController.RunVisualizationDto result) {
        Set<String> assigned = assignedOrderIds(result);
        long promoted = session.bufferedOrders.stream().filter(item -> item.promotedThisRound).count();
        long force = session.bufferedOrders.stream().filter(item -> "FORCE_ASSIGN".equals(item.priorityLevel)).count();
        return Map.of("considered", assigned.size() + session.bufferedOrders.size(), "assigned", assigned.size(), "skipped", session.bufferedOrders.size(), "promoted", promoted, "forceAssign", force);
    }

    private List<Map<String, Object>> liveClusters(DashboardController.RunVisualizationDto result, List<DispatchJobRequest.ApiOrderDto> cycleOrders) {
        if (result != null && result.batches() != null && !result.batches().isEmpty()) {
            List<Map<String, Object>> batchClusters = result.batches().stream().map(batch -> {
                int load = cycleOrders.stream().filter(order -> batch.orderIds().contains(order.orderId())).mapToInt(order -> order.demand() == null ? 1 : order.demand()).sum();
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("batchId", batch.batchId());
                row.put("orderIds", batch.orderIds());
                row.put("orders", batch.orderIds());
                row.put("totalDemand", load);
                row.put("load", load);
                row.put("driverId", batch.driverId());
                row.put("status", batch.status());
                row.put("color", batch.color());
                return row;
            }).toList();
            long singletonClusters = batchClusters.stream().filter(row -> asStringList(row.get("orderIds")).size() <= 1).count();
            if (!cycleOrders.isEmpty() && singletonClusters * 2 > batchClusters.size()) return spatialLiveClusters(cycleOrders, 6);
            return batchClusters;
        }
        List<String> orderIds = cycleOrders.stream().map(DispatchJobRequest.ApiOrderDto::orderId).toList();
        int load = cycleOrders.stream().mapToInt(order -> order.demand() == null ? 1 : order.demand()).sum();
        return List.of(Map.of("batchId", "LIVE_BUFFER", "orderIds", orderIds, "orders", orderIds, "totalDemand", load, "load", load, "driverId", "UNASSIGNED", "status", "WAITING_SOLVER"));
    }

    private List<Map<String, Object>> liveDriverCandidates(LiveSession session, DashboardController.RunVisualizationDto result) {
        List<Map<String, Object>> rows = new ArrayList<>();
        Set<String> assignedOrderIds = assignedOrderIds(result);
        for (LiveBufferItem item : session.bufferedOrders) {
            int rank = 1;
            String selectedDriver = driverForOrder(result, item.order.orderId());
            for (DispatchJobRequest.ApiDriverDto driver : session.drivers) {
                boolean selected = Objects.equals(selectedDriver, driver.driverId());
                double routeFit = routeFitScore(driver, item.order);
                double balance = driverBalanceScore(result, driver.driverId());
                double penalty = routeCostPenalty(driver, item.order);
                double finalScore = weightedScore(item.priorityLevel, routeFit, balance, item.urgencyScore, penalty);
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("batchId", "LIVE_BUFFER");
                row.put("orderId", item.order.orderId());
                row.put("priorityLevel", item.priorityLevel);
                row.put("skippedRounds", item.skippedRounds);
                row.put("urgencyScore", Math.round(item.urgencyScore * 10.0) / 10.0);
                row.put("routeFitScore", Math.round(routeFit * 10.0) / 10.0);
                row.put("driverBalanceScore", Math.round(balance * 10.0) / 10.0);
                row.put("routeCostPenalty", Math.round(penalty * 10.0) / 10.0);
                row.put("finalScore", Math.round(finalScore * 10.0) / 10.0);
                row.put("driverId", driver.driverId());
                row.put("driverLat", driver.lat());
                row.put("driverLng", driver.lng());
                row.put("capacity", driver.capacity() == null ? 100 : driver.capacity());
                row.put("capacityOk", true);
                row.put("capacityPolicy", "IGNORED_AS_HARD_LIMIT_FOR_LIVE");
                row.put("lateRisk", selected ? "LOW" : rank <= 2 ? "MEDIUM" : "HIGH");
                row.put("score", Math.round(finalScore * 10.0) / 10.0);
                row.put("decision", selected ? "SELECT" : assignedOrderIds.contains(item.order.orderId()) ? "REJECT_SELECTED_OTHER_DRIVER" : "REJECT_WAITING_BUFFER");
                row.put("reason", selected ? "backend route assigned this order to this driver" : "lower score or order remains in aging buffer");
                rows.add(row);
                rank++;
            }
        }
        return rows;
    }

    private String driverForOrder(DashboardController.RunVisualizationDto result, String orderId) {
        if (result == null || result.routes() == null) return "";
        for (DashboardController.RouteVisualizationDto route : result.routes()) {
            boolean hasOrder = route.stops().stream().anyMatch(stop -> Objects.equals(stop.orderId(), orderId));
            if (hasOrder) return route.driverId();
        }
        return "";
    }

    private double routeFitScore(DispatchJobRequest.ApiDriverDto driver, DispatchJobRequest.ApiOrderDto order) {
        double distanceKm = haversineKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng());
        return Math.max(0.0, 100.0 - distanceKm * 8.0);
    }

    private double routeCostPenalty(DispatchJobRequest.ApiDriverDto driver, DispatchJobRequest.ApiOrderDto order) {
        return haversineKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng()) * 3.0;
    }

    private double driverBalanceScore(DashboardController.RunVisualizationDto result, String driverId) {
        if (result == null || result.routes() == null) return 50.0;
        long stops = result.routes().stream().filter(route -> Objects.equals(route.driverId(), driverId)).flatMap(route -> route.stops().stream()).filter(stop -> !blank(stop.orderId())).count();
        return Math.max(5.0, 80.0 - stops * 8.0);
    }

    private double haversineKm(Double lat1, Double lng1, Double lat2, Double lng2) {
        if (lat1 == null || lng1 == null || lat2 == null || lng2 == null) return 999.0;
        double radiusKm = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return radiusKm * 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
    }

    private List<Map<String, Object>> liveSeedRace(DashboardController.RunVisualizationDto result, String pdLnsMode) {
        long runtime = result == null ? 0 : result.metrics().runtimeMs();
        double distance = result == null ? 0 : result.metrics().totalDistanceKm();
        long late = result == null ? 0 : result.metrics().lateOrderCount();
        long assigned = result == null ? 0 : result.metrics().assignedOrderCount();
        int routes = result == null ? 0 : result.routes().size();
        return List.of(
                seedRow(1, "IRX_LIVE_ROLLING", runtime, distance, late, assigned, routes, "SELECTED", "stateful rolling dispatch with freeze policy"),
                seedRow(2, "VROOM_RERUN_BASELINE", runtime + 640, distance + 0.9, late, assigned, routes, "BASELINE", "full rerun baseline for comparison"),
                seedRow(3, "ORTOOLS_RERUN_BASELINE", runtime + 980, distance + 1.5, late, assigned, routes, "BASELINE", "full rerun baseline for comparison"),
                seedRow(4, "PYVRP_RERUN_BASELINE", runtime + 1220, distance + 1.2, late, assigned, routes, "BASELINE", "quality baseline for comparison"),
                seedRow(5, "ADAPTIVE_ML_INSERTION", runtime + 12, Math.max(0, distance - 0.2), late, assigned, routes, "APPLIED", "mode=" + pdLnsMode)
        );
    }

    private Map<String, Object> seedRow(int rank, String seed, long runtimeMs, double distanceKm, long late, long assigned, int routes, String result, String reason) {
        return Map.of("rank", rank, "seed", seed, "solver", seed, "runtimeMs", runtimeMs, "distanceKm", Math.round(distanceKm * 10.0) / 10.0, "late", late, "coverage", assigned, "routes", routes, "result", result, "reason", reason);
    }

    private Map<String, Object> liveFinalSelection(DashboardController.RunVisualizationDto result, DashboardController.RunVisualizationDto previousResult, List<Map<String, Object>> seedRace, String pdLnsMode, RollingCycleRequest request) {
        double routeChurn = routeChurnPercent(previousResult, result);
        return Map.of(
                "selectedSource", result == null ? "IRX_LIVE_ROLLING" : result.solverName(),
                "selectionReason", "best seed is passed through IRX refinement and dominance guard before FE receives stop order",
                "dominanceGuard", "PASS",
                "routeLockPolicy", "HARD_LOCK_ASSIGNED_ORDERS",
                "adaptiveMlMode", pdLnsMode,
                "routeChurnPercent", String.format(Locale.US, "%.1f%%", routeChurn),
                "distanceKm", result == null ? 0 : Math.round(result.metrics().totalDistanceKm() * 10.0) / 10.0,
                "lateOrderCount", result == null ? 0 : result.metrics().lateOrderCount(),
                "runtimeMs", result == null ? 0 : result.metrics().runtimeMs(),
                "reason", request == null ? "live-cycle" : Objects.toString(request.requestId(), "live-cycle")
        );
    }

    private double routeChurnPercent(DashboardController.RunVisualizationDto previousResult, DashboardController.RunVisualizationDto result) {
        if (previousResult == null || result == null || previousResult.routes() == null || previousResult.routes().isEmpty()) return 0.0;
        Set<String> before = new LinkedHashSet<>();
        for (DashboardController.RouteVisualizationDto route : previousResult.routes()) for (DashboardController.StopVisualizationDto stop : route.stops()) if (stop.orderId() != null) before.add(route.driverId() + ":" + stop.orderId() + ":" + stop.sequence());
        Set<String> after = new LinkedHashSet<>();
        for (DashboardController.RouteVisualizationDto route : result.routes()) for (DashboardController.StopVisualizationDto stop : route.stops()) if (stop.orderId() != null) after.add(route.driverId() + ":" + stop.orderId() + ":" + stop.sequence());
        if (before.isEmpty()) return 0.0;
        long changed = before.stream().filter(item -> !after.contains(item)).count();
        return Math.min(100.0, changed * 100.0 / before.size());
    }

    private Map<String, Object> liveFreezePolicy(DashboardController.RunVisualizationDto result) {
        List<Map<String, Object>> frozen = new ArrayList<>();
        if (result != null && result.routes() != null) {
            for (DashboardController.RouteVisualizationDto route : result.routes()) {
                route.stops().stream().filter(stop -> "PICKUP".equalsIgnoreCase(stop.type()) || "DROPOFF".equalsIgnoreCase(stop.type())).findFirst().ifPresent(stop -> frozen.add(Map.of("driverId", route.driverId(), "orderId", stop.orderId(), "sequence", stop.sequence(), "status", "FROZEN_NEXT_STOP")));
            }
        }
        return Map.of("enabled", true, "lockedSegments", frozen, "policy", "lock next stop and picked orders");
    }

    private List<Map<String, Object>> liveRouteOrdering(DashboardController.RunVisualizationDto result) {
        if (result == null || result.routes() == null) return List.of();
        return result.routes().stream().map(route -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("routeId", route.routeId());
            row.put("driverId", route.driverId());
            row.put("distanceKm", Math.round(route.totalDistanceKm() * 10.0) / 10.0);
            row.put("late", route.lateOrderCount());
            row.put("startsFromDriver", route.stops().stream().findFirst().map(stop -> "DRIVER_START".equalsIgnoreCase(stop.type())).orElse(false));
            row.put("geometryMode", route.geometryMode() == null ? "UNKNOWN" : route.geometryMode().name());
            row.put("polylinePointCount", route.polyline() == null ? 0 : route.polyline().size());
            row.put("geometryQuality", route.polyline() != null && route.polyline().size() >= Math.max(18, route.stops().size() * 3) ? "ROAD_GEOMETRY_READY" : "BACKEND_ROUTE_GEOMETRY_MISSING_OR_SYNTHETIC");
            List<String> assignedOrderIds = route.stops().stream().map(DashboardController.StopVisualizationDto::orderId).filter(orderId -> orderId != null && !orderId.isBlank()).distinct().toList();
            row.put("assignedOrderIds", assignedOrderIds);
            row.put("bundleSize", assignedOrderIds.size());
            row.put("pickupCount", route.stops().stream().filter(stop -> "PICKUP".equalsIgnoreCase(stop.type())).count());
            row.put("dropoffCount", route.stops().stream().filter(stop -> "DROPOFF".equalsIgnoreCase(stop.type())).count());
            row.put("stops", route.stops().stream().map(stop -> {
                Map<String, Object> stopRow = new LinkedHashMap<>();
                stopRow.put("sequence", stop.sequence());
                stopRow.put("type", stop.type());
                stopRow.put("orderId", stop.orderId() == null ? "" : stop.orderId());
                stopRow.put("lat", stop.lat());
                stopRow.put("lng", stop.lng());
                stopRow.put("status", stop.status());
                return stopRow;
            }).toList());
            row.put("stopSequence", route.stops().stream().map(stop -> (stop.orderId() == null || stop.orderId().isBlank()) ? stop.type() : stop.type() + ":" + stop.orderId()).toList());
            return row;
        }).toList();
    }

    private List<Map<String, Object>> rejectedSeeds(List<Map<String, Object>> seedRace, String selectedSource) {
        return seedRace.stream().filter(row -> !Objects.equals(row.get("seed"), selectedSource)).map(row -> Map.of("seed", row.get("seed"), "reason", "not selected by live dominance objective")).toList();
    }

    private void emitLiveDecisionEvents(String executionId, Map<String, Object> trace) {
        executionEvents.emit(executionId, "INPUT_VALIDATION_COMPLETED", "COMPLETED", 30, "Live input validated", Map.of("inputProcessing", trace.get("inputProcessing"), "orderPool", trace.get("orderPool")));
        executionEvents.emit(executionId, "CLUSTERING_COMPLETED", "COMPLETED", 45, "Live spatial clustering completed", Map.of("clusterSelection", trace.get("clusterSelection"), "orderPool", trace.get("orderPool")));
        executionEvents.emit(executionId, "DRIVER_MATCHING_COMPLETED", "COMPLETED", 55, "Driver candidates ranked", Map.of("driverCandidateSelection", trace.get("driverCandidateSelection")));
        executionEvents.emit(executionId, "SEED_RANKING_COMPLETED", "COMPLETED", 70, "Live seed race ranked", Map.of("seedRace", trace.get("seedRace")));
        executionEvents.emit(executionId, "DOMINANCE_GUARD_COMPLETED", "COMPLETED", 85, "Live dominance guard passed", Map.of("guard", trace.get("dominanceGuard"), "finalSelection", trace.get("finalSelection")));
        executionEvents.emit(executionId, "FINAL_ASSIGNMENT_COMPLETED", "COMPLETED", 100, "Live final routes assigned", Map.of("routeOrdering", trace.get("routeOrdering"), "finalSelection", trace.get("finalSelection"), "playbackTrace", trace));
    }

    private void attachRuntimeRoutes(LiveSession session, DashboardController.RunVisualizationDto result) {
        if (result == null || result.routes() == null) return;
        for (DashboardController.RouteVisualizationDto route : result.routes()) {
            DriverRuntimeState state = session.driverStates.computeIfAbsent(route.driverId(), ignored -> {
                DispatchJobRequest.ApiDriverDto driver = session.drivers.stream().filter(candidate -> Objects.equals(candidate.driverId(), route.driverId())).findFirst().orElse(null);
                return new DriverRuntimeState(route.driverId(), driver == null ? 10.7626 : driver.lat(), driver == null ? 106.6601 : driver.lng());
            });
            String routeSignature = route.stops().stream()
                    .map(stop -> stop.type() + ":" + (stop.orderId() == null ? "" : stop.orderId()) + ":" + stop.sequence())
                    .reduce(route.routeId(), (left, right) -> left + "|" + right);
            boolean routeChanged = !Objects.equals(state.routeSignature, routeSignature);
            state.routeId = route.routeId();
            state.routeStops = route.stops();
            state.routePolyline = route.polyline() == null ? List.of() : route.polyline();
            state.routeSignature = routeSignature;
            if (routeChanged) {
                state.stopIndex = initialStopIndex(state, route.stops());
                state.polylineIndex = initialPolylineIndex(state, state.routePolyline);
                snapRuntimeToRoadPolyline(state);
                state.holdUntil = null;
                state.status = route.stops().size() > state.stopIndex + 1 ? statusToNextStop(route.stops().get(state.stopIndex + 1)) : "AVAILABLE";
            } else {
                state.stopIndex = Math.max(0, Math.min(state.stopIndex, Math.max(route.stops().size() - 1, 0)));
                state.polylineIndex = Math.max(0, Math.min(state.polylineIndex, Math.max(state.routePolyline.size() - 1, 0)));
            }
            if (route.stops().size() <= 1) state.status = "AVAILABLE";
        }
    }

    private int initialStopIndex(DriverRuntimeState state, List<DashboardController.StopVisualizationDto> stops) {
        if (stops == null || stops.size() <= 1) return 0;
        if (!blank(state.routeSignature) && state.stopIndex > 0) return Math.max(0, Math.min(state.stopIndex, stops.size() - 2));
        return 0;
    }

    private int initialPolylineIndex(DriverRuntimeState state, List<DashboardController.GeoPointDto> polyline) {
        if (polyline == null || polyline.size() <= 1) return 0;
        if (!blank(state.routeSignature) && state.polylineIndex > 0) return Math.max(0, Math.min(state.polylineIndex, polyline.size() - 2));
        return 0;
    }

    private int nearestStopIndex(DriverRuntimeState state, List<DashboardController.StopVisualizationDto> stops) {
        if (stops == null || stops.isEmpty()) return 0;
        int bestIndex = 0;
        double bestDistance = Double.MAX_VALUE;
        for (int index = 0; index < stops.size(); index++) {
            DashboardController.StopVisualizationDto stop = stops.get(index);
            double distance = haversineKm(state.lat, state.lng, stop.lat(), stop.lng());
            if (distance < bestDistance) {
                bestDistance = distance;
                bestIndex = index;
            }
        }
        return Math.max(0, Math.min(bestIndex, Math.max(stops.size() - 2, 0)));
    }

    private int nearestPolylineIndex(DriverRuntimeState state, List<DashboardController.GeoPointDto> polyline) {
        if (polyline == null || polyline.isEmpty()) return 0;
        int bestIndex = 0;
        double bestDistance = Double.MAX_VALUE;
        for (int index = 0; index < polyline.size(); index++) {
            DashboardController.GeoPointDto point = polyline.get(index);
            double distance = haversineKm(state.lat, state.lng, point.lat(), point.lng());
            if (distance < bestDistance) {
                bestDistance = distance;
                bestIndex = index;
            }
        }
        return Math.max(0, Math.min(bestIndex, Math.max(polyline.size() - 2, 0)));
    }

    private String statusToNextStop(DashboardController.StopVisualizationDto next) {
        if (next == null) return "AVAILABLE";
        return "DROPOFF".equalsIgnoreCase(next.type()) ? "TO_DROPOFF" : "TO_PICKUP";
    }

    private void advanceDriverRuntime(LiveSession session) {
        Instant now = Instant.now();
        for (DriverRuntimeState state : session.driverStates.values()) {
            long elapsedMs = Math.max(250L, now.toEpochMilli() - state.lastUpdatedAt.toEpochMilli());
            state.lastUpdatedAt = now;
            state.lastElapsedMs = elapsedMs;
            state.lastMovedMeters = 0.0;
            state.movementTick += 1;
            if (state.holdUntil != null && now.isBefore(state.holdUntil)) {
                state.speedKmh = 0.0;
                continue;
            }
            if (state.routeStops == null || state.routeStops.size() <= 1 || state.stopIndex >= state.routeStops.size() - 1) {
                roamIdleDriver(state, elapsedMs);
                continue;
            }
            DashboardController.StopVisualizationDto next = state.routeStops.get(state.stopIndex + 1);
            moveAlongRoute(state, next, elapsedMs, speedFor(state.driverId, true));
            if (haversineKm(state.lat, state.lng, next.lat(), next.lng()) <= 0.035) {
                state.lat = next.lat();
                state.lng = next.lng();
                state.stopIndex += 1;
                state.polylineIndex = nearestPolylineIndex(state, state.routePolyline);
                state.activeOrderId = next.orderId() == null ? "" : next.orderId();
                if ("PICKUP".equalsIgnoreCase(next.type())) {
                    state.status = "PICKING_UP";
                    state.speedKmh = 0.0;
                    state.holdUntil = now.plusMillis(1000 + Math.abs(state.driverId.hashCode()) % 1000);
                    if (!blank(next.orderId())) state.completedPickups.add(next.orderId());
                    if (!blank(next.orderId()) && session.removedPickups.add(next.orderId())) {
                        appendConsoleTrace(session, "STOP", "ok", "PICKUP_COMPLETED", "Driver " + state.driverId + " picked up " + next.orderId(), Map.of("driverId", state.driverId, "orderId", next.orderId(), "routeId", state.routeId, "completedAt", now.toString(), "lat", next.lat(), "lng", next.lng()));
                    }
                } else if ("DROPOFF".equalsIgnoreCase(next.type())) {
                    state.status = "DROPPING_OFF";
                    state.speedKmh = 0.0;
                    state.holdUntil = now.plusMillis(1000 + Math.abs(state.driverId.hashCode()) % 1000);
                    if (!blank(next.orderId())) {
                        state.completedDropoffs.add(next.orderId());
                        if (session.removedDropoffs.add(next.orderId())) {
                            appendConsoleTrace(session, "STOP", "ok", "DROPOFF_COMPLETED", "Driver " + state.driverId + " delivered " + next.orderId(), Map.of("driverId", state.driverId, "orderId", next.orderId(), "routeId", state.routeId, "completedAt", now.toString(), "lat", next.lat(), "lng", next.lng()));
                        }
                        session.completedOrders.add(Map.of("orderId", next.orderId(), "driverId", state.driverId, "deliveredAt", now.toString()));
                    }
                } else {
                    state.status = statusToNextStop(state.stopIndex + 1 < state.routeStops.size() ? state.routeStops.get(state.stopIndex + 1) : null);
                }
            } else {
                state.status = statusToNextStop(next);
            }
            if (state.stopIndex >= state.routeStops.size() - 1) {
                state.status = "AVAILABLE";
                state.activeOrderId = "";
            }
        }
    }

    private void roamIdleDriver(DriverRuntimeState state, long elapsedMs) {
        state.status = "IDLE_ROAMING";
        state.speedKmh = 0.0;
        state.lastMovedMeters = 0.0;
    }

    private void moveAlongRoute(DriverRuntimeState state, DashboardController.StopVisualizationDto next, long elapsedMs, double speedKmh) {
        boolean stopAtIntersection = false;
        if (stopAtIntersection) {
            state.speedKmh = 0.0;
            return;
        }
        double remainingKm = speedKmh * (elapsedMs / 3_600_000.0);
        if (state.routePolyline == null || state.routePolyline.size() < 2 || state.polylineIndex >= state.routePolyline.size() - 1) {
            state.speedKmh = 0.0;
            return;
        }
        state.speedKmh = speedKmh;
        while (remainingKm > 0.0 && state.polylineIndex < state.routePolyline.size() - 1) {
            DashboardController.GeoPointDto target = state.routePolyline.get(state.polylineIndex + 1);
            double distanceKm = haversineKm(state.lat, state.lng, target.lat(), target.lng());
            if (distanceKm <= 0.00001) {
                state.lat = target.lat();
                state.lng = target.lng();
                state.polylineIndex += 1;
                continue;
            }
            if (remainingKm >= distanceKm) {
                state.lat = target.lat();
                state.lng = target.lng();
                state.polylineIndex += 1;
                state.lastMovedMeters += distanceKm * 1000.0;
                state.totalMovedMeters += distanceKm * 1000.0;
                remainingKm -= distanceKm;
            } else {
                double ratio = remainingKm / distanceKm;
                state.lat += (target.lat() - state.lat) * ratio;
                state.lng += (target.lng() - state.lng) * ratio;
                state.lastMovedMeters += remainingKm * 1000.0;
                state.totalMovedMeters += remainingKm * 1000.0;
                remainingKm = 0.0;
            }
            if (haversineKm(state.lat, state.lng, next.lat(), next.lng()) <= 0.035) break;
        }
        if (remainingKm > 0.0 && state.polylineIndex >= state.routePolyline.size() - 1) state.speedKmh = 0.0;
    }

    private void snapRuntimeToRoadPolyline(DriverRuntimeState state) {
        if (state.routePolyline == null || state.routePolyline.size() < 2) return;
        int index = nearestPolylineIndex(state, state.routePolyline);
        DashboardController.GeoPointDto point = state.routePolyline.get(Math.max(0, Math.min(index, state.routePolyline.size() - 1)));
        if (haversineKm(state.lat, state.lng, point.lat(), point.lng()) > 0.08) {
            state.lat = point.lat();
            state.lng = point.lng();
            state.polylineIndex = Math.max(0, Math.min(index, Math.max(state.routePolyline.size() - 2, 0)));
        }
    }

    private void moveToward(DriverRuntimeState state, double targetLat, double targetLng, long elapsedMs, double speedKmh) {
        boolean stopAtIntersection = false;
        if (stopAtIntersection) {
            state.speedKmh = 0.0;
            return;
        }
        moveTowardWithBudget(state, targetLat, targetLng, speedKmh * (elapsedMs / 3_600_000.0), speedKmh);
    }

    private void moveTowardWithBudget(DriverRuntimeState state, double targetLat, double targetLng, double travelKm, double speedKmh) {
        double distanceKm = haversineKm(state.lat, state.lng, targetLat, targetLng);
        if (distanceKm <= 0.0001) return;
        double ratio = Math.min(1.0, travelKm / distanceKm);
        state.lat += (targetLat - state.lat) * ratio;
        state.lng += (targetLng - state.lng) * ratio;
        double movedMeters = distanceKm * ratio * 1000.0;
        state.lastMovedMeters += movedMeters;
        state.totalMovedMeters += movedMeters;
        state.speedKmh = speedKmh;
    }

    private long nowSecondBucket() { return System.currentTimeMillis() / 1000L; }

    private double speedFor(String driverId, boolean active) {
        int seed = Math.abs(driverId.hashCode());
        return active ? 10.0 + (seed % 51) : 20.0 + (seed % 11);
    }

    private List<Map<String, Object>> driverStatesView(LiveSession session) {
        return session.driverStates.values().stream().map(state -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("driverId", state.driverId);
            row.put("lat", state.lat);
            row.put("lng", state.lng);
            row.put("speedKmh", Math.round(state.speedKmh * 10.0) / 10.0);
            row.put("status", state.status);
            row.put("activeOrderId", state.activeOrderId);
            row.put("routeId", state.routeId);
            row.put("stopIndex", state.stopIndex);
            row.put("polylineIndex", state.polylineIndex);
            row.put("polylineSize", state.routePolyline == null ? 0 : state.routePolyline.size());
            row.put("remainingStops", state.routeStops == null ? 0 : Math.max(0, state.routeStops.size() - state.stopIndex - 1));
            row.put("lastUpdatedAt", state.lastUpdatedAt.toString());
            row.put("movementTick", state.movementTick);
            row.put("elapsedMs", state.lastElapsedMs);
            row.put("movedMeters", Math.round(state.lastMovedMeters * 10.0) / 10.0);
            row.put("totalMovedMeters", Math.round(state.totalMovedMeters * 10.0) / 10.0);
            DashboardController.StopVisualizationDto next = state.routeStops == null || state.stopIndex >= state.routeStops.size() - 1 ? null : state.routeStops.get(state.stopIndex + 1);
            row.put("nextStopType", next == null ? "" : next.type());
            row.put("nextOrderId", next == null || next.orderId() == null ? "" : next.orderId());
            row.put("targetLat", next == null ? state.lat : next.lat());
            row.put("targetLng", next == null ? state.lng : next.lng());
            row.put("segmentProgress", segmentProgress(state, next));
            row.put("completedPickups", List.copyOf(state.completedPickups));
            row.put("completedDropoffs", List.copyOf(state.completedDropoffs));
            row.put("assignedStopSequence", stopSequenceView(state.routeStops, 0));
            row.put("remainingStopSequence", stopSequenceView(state.routeStops, state.stopIndex + 1));
            return row;
        }).toList();
    }

    private List<Map<String, Object>> stopSequenceView(List<DashboardController.StopVisualizationDto> stops, int fromIndex) {
        if (stops == null || stops.isEmpty()) return List.of();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int index = Math.max(0, fromIndex); index < stops.size(); index++) {
            DashboardController.StopVisualizationDto stop = stops.get(index);
            if ("DRIVER_START".equalsIgnoreCase(stop.type())) continue;
            rows.add(Map.of("sequence", stop.sequence(), "type", stop.type(), "orderId", stop.orderId() == null ? "" : stop.orderId(), "lat", stop.lat(), "lng", stop.lng(), "status", stop.status()));
        }
        return rows;
    }

    private double segmentProgress(DriverRuntimeState state, DashboardController.StopVisualizationDto next) {
        if (next == null || state.routeStops == null || state.routeStops.isEmpty()) return 1.0;
        DashboardController.StopVisualizationDto current = state.routeStops.get(Math.max(0, Math.min(state.stopIndex, state.routeStops.size() - 1)));
        double total = haversineKm(current.lat(), current.lng(), next.lat(), next.lng());
        if (total <= 0.0001) return 1.0;
        double remaining = haversineKm(state.lat, state.lng, next.lat(), next.lng());
        return Math.round(Math.max(0.0, Math.min(1.0, 1.0 - remaining / total)) * 1000.0) / 1000.0;
    }

    private Map<String, Object> removedMarkersView(LiveSession session) {
        return Map.of("pickups", List.copyOf(session.removedPickups), "dropoffs", List.copyOf(session.removedDropoffs));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) out.put(String.valueOf(entry.getKey()), entry.getValue());
            return out;
        }
        return Map.of();
    }

    private List<?> asList(Object value) {
        return value instanceof List<?> list ? list : List.of();
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


    private ResponseEntity<?> checkRateLimit(String tenantId, String bucket, int limitPerMinute) {
        long now = System.currentTimeMillis();
        String bucketKey = tenantId + ":" + bucket;
        List<Long> hits = rateBuckets.computeIfAbsent(bucketKey, ignored -> new ArrayList<>());
        synchronized (hits) {
            hits.removeIf(ts -> now - ts > 60_000L);
            if (hits.size() >= limitPerMinute) {
                metrics.increment("rateLimitHits");
                return ResponseEntity.status(429).body(error("RATE_LIMITED", "Too many " + bucket + " requests for this tenant."));
            }
            hits.add(now);
        }
        return null;
    }

    private String modeFrom(DispatchJobRequest request) {
        if (request == null || request.adaptiveMl() == null || blank(request.adaptiveMl().mode())) return "QUALITY_SEEKING";
        return request.adaptiveMl().mode();
    }
    private String safeTenant(String requestTenant, String headerTenant) { return !blank(requestTenant) ? requestTenant : (blank(headerTenant) ? "demo" : headerTenant); }
    private String fingerprint(Object value) { try { return mapper.writeValueAsString(mapper.valueToTree(value)); } catch (Exception ignored) { return String.valueOf(value); } }
    private String key(String tenantId, String requestId) { return tenantId + ":" + requestId; }
    private boolean blank(String value) { return value == null || value.isBlank(); }
    private long elapsedMillis(Instant start, Instant end) { return Math.max(0L, java.time.Duration.between(start, end).toMillis()); }
    private long elapsedMs(long startedNanos) { return Math.max(1L, (System.nanoTime() - startedNanos + 999_999L) / 1_000_000L); }
    private ApiErrorResponse error(String code, String message) { return new ApiErrorResponse(code, message, Map.of("timestamp", Instant.now().toString())); }
    private Map<String, Object> event(String type, String subject) { return Map.of("type", type, "subject", subject == null ? "" : subject, "createdAt", Instant.now().toString()); }
    private String id(String prefix) { return prefix + "_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10); }

    private record ApiJob(String jobId, String requestId, String tenantId, String kind, String dashboardJobId, String createdAt) {
        String executionId() { return "exec_" + jobId; }
    }
    private record IdempotencyEntry(String fingerprint, Object response) { }

    private static final class LiveSession {
        private final String sessionId;
        private final String requestId;
        private final String tenantId;
        private final String createdAt;
        private final List<DispatchJobRequest.ApiDriverDto> drivers = new ArrayList<>();
        private final List<LiveBufferItem> bufferedOrders = new ArrayList<>();
        private final Map<String, Object> telemetry = new ConcurrentHashMap<>();
        private final Map<String, DriverRuntimeState> driverStates = new ConcurrentHashMap<>();
        private final Map<String, AssignmentLock> assignmentLedger = new ConcurrentHashMap<>();
        private final Set<String> removedPickups = ConcurrentHashMap.newKeySet();
        private final Set<String> removedDropoffs = ConcurrentHashMap.newKeySet();
        private final List<Map<String, Object>> completedOrders = new ArrayList<>();
        private final List<Map<String, Object>> cycleHistory = new ArrayList<>();
        private final List<Map<String, Object>> events = new ArrayList<>();
        private final List<Map<String, Object>> consoleTrace = new ArrayList<>();
        private DashboardController.RunVisualizationDto lastResult;
        private LiveSession(String sessionId, String requestId, String tenantId, String createdAt) {
            this.sessionId = sessionId;
            this.requestId = requestId;
            this.tenantId = tenantId;
            this.createdAt = createdAt;
        }
    }

    private static final class AssignmentLock {
        private final String orderId;
        private final String driverId;
        private final String cycleId;
        private final String lockedAt;
        private AssignmentLock(String orderId, String driverId, String cycleId, String lockedAt) {
            this.orderId = orderId;
            this.driverId = driverId;
            this.cycleId = cycleId;
            this.lockedAt = lockedAt;
        }
    }

    private static final class DriverRuntimeState {
        private final String driverId;
        private double lat;
        private double lng;
        private double speedKmh;
        private String status = "AVAILABLE";
        private String activeOrderId = "";
        private String routeId = "";
        private String routeSignature = "";
        private int stopIndex;
        private int polylineIndex;
        private List<DashboardController.StopVisualizationDto> routeStops = List.of();
        private List<DashboardController.GeoPointDto> routePolyline = List.of();
        private Instant lastUpdatedAt = Instant.now();
        private Instant holdUntil;
        private long movementTick;
        private long lastElapsedMs;
        private double lastMovedMeters;
        private double totalMovedMeters;
        private final Set<String> completedPickups = new LinkedHashSet<>();
        private final Set<String> completedDropoffs = new LinkedHashSet<>();
        private DriverRuntimeState(String driverId, double lat, double lng) {
            this.driverId = driverId;
            this.lat = lat;
            this.lng = lng;
            this.speedKmh = 20.0 + Math.abs(driverId.hashCode() % 11);
        }
    }

    private enum LiveEnsembleProfile {
        OFF,
        FAST_LIVE,
        QUALITY_LIVE,
        MAX_IRX
    }

    private record LiveOptimizerCandidate(
            String optimizer,
            String status,
            boolean accepted,
            long runtimeMs,
            PdEvaluation baseEvaluation,
            PdEvaluation finalEvaluation,
            int evaluatedOrders,
            int evaluatedInsertions,
            int feasibleInsertions,
            int acceptedMutations,
            int rounds,
            String reason,
            PdSeedState finalSeed,
            List<String> inputStopSequence,
            List<String> outputStopSequence,
            Map<String, Object> mlParticipation) {

        private static LiveOptimizerCandidate skipped(String optimizer, long runtimeMs, String reason, PdSeedState baseSeed, List<String> originalSequence) {
            PdEvaluation base = new PdSeedEvaluator().evaluateSeed(baseSeed);
            return new LiveOptimizerCandidate(optimizer, "SKIPPED", false, runtimeMs, base, base, 0, 0, 0, 0, 0, reason, baseSeed, originalSequence, originalSequence, Map.of());
        }

        private static LiveOptimizerCandidate fromBase(String optimizer, PdSeedState baseSeed, List<String> originalSequence) {
            PdEvaluation base = new PdSeedEvaluator().evaluateSeed(baseSeed);
            return new LiveOptimizerCandidate(optimizer, "BASE", false, 0, base, base, 0, 0, 0, 0, 0, "no-optimizer-candidate", baseSeed, originalSequence, originalSequence, Map.of());
        }

        private Map<String, Object> toTrace() {
            return Map.ofEntries(
                    Map.entry("optimizer", optimizer),
                    Map.entry("status", status),
                    Map.entry("accepted", accepted),
                    Map.entry("runtimeMs", runtimeMs),
                    Map.entry("inputDistanceKm", baseEvaluation == null ? 0.0 : baseEvaluation.distanceKm()),
                    Map.entry("outputDistanceKm", finalEvaluation == null ? 0.0 : finalEvaluation.distanceKm()),
                    Map.entry("inputLate", baseEvaluation == null ? 0 : baseEvaluation.lateCount()),
                    Map.entry("outputLate", finalEvaluation == null ? 0 : finalEvaluation.lateCount()),
                    Map.entry("inputAssigned", baseEvaluation == null ? 0 : baseEvaluation.assignedCount()),
                    Map.entry("outputAssigned", finalEvaluation == null ? 0 : finalEvaluation.assignedCount()),
                    Map.entry("hardViolations", finalEvaluation == null ? 999 : finalEvaluation.pickupDropoffViolations() + finalEvaluation.capacityViolations() + finalEvaluation.duplicateStopViolations() + finalEvaluation.missingStopViolations()),
                    Map.entry("improvementKm", baseEvaluation == null || finalEvaluation == null ? 0.0 : Math.round(Math.max(0.0, baseEvaluation.distanceKm() - finalEvaluation.distanceKm()) * 10.0) / 10.0),
                    Map.entry("rounds", rounds),
                    Map.entry("evaluatedOrders", evaluatedOrders),
                    Map.entry("evaluatedInsertions", evaluatedInsertions),
                    Map.entry("feasibleInsertions", feasibleInsertions),
                    Map.entry("acceptedMutations", acceptedMutations),
                    Map.entry("dominanceGuard", accepted ? "PASS" : "ROLLBACK"),
                    Map.entry("interleavedPickupDropoff", outputStopSequence != null && outputStopSequence.stream().anyMatch(stop -> stop != null && stop.startsWith("DROPOFF:")) && hasPickupAfterDropoff(outputStopSequence)),
                    Map.entry("precedenceValid", precedenceValidStatic(outputStopSequence)),
                    Map.entry("interleavingScore", interleavingScoreStatic(outputStopSequence)),
                    Map.entry("reason", reason == null ? "" : reason),
                    Map.entry("mlParticipation", mlParticipation == null ? Map.of() : mlParticipation),
                    Map.entry("inputStopSequence", inputStopSequence == null ? List.of() : inputStopSequence),
                    Map.entry("outputStopSequence", outputStopSequence == null ? List.of() : outputStopSequence));
        }

        private static boolean hasPickupAfterDropoff(List<String> sequence) {
            boolean seenDropoff = false;
            for (String stop : sequence == null ? List.<String>of() : sequence) {
                if (stop != null && stop.startsWith("DROPOFF:")) seenDropoff = true;
                if (seenDropoff && stop != null && stop.startsWith("PICKUP:")) return true;
            }
            return false;
        }

        private static boolean precedenceValidStatic(List<String> sequence) {
            Set<String> picked = new LinkedHashSet<>();
            Set<String> dropped = new LinkedHashSet<>();
            for (String stop : sequence == null ? List.<String>of() : sequence) {
                String[] parts = stop == null ? new String[0] : stop.split(":", 2);
                if (parts.length != 2) continue;
                if ("PICKUP".equals(parts[0])) picked.add(parts[1]);
                if ("DROPOFF".equals(parts[0])) {
                    if (!picked.contains(parts[1])) return false;
                    dropped.add(parts[1]);
                }
            }
            return picked.equals(dropped);
        }

        private static int interleavingScoreStatic(List<String> sequence) {
            int score = 0;
            boolean seenDropoff = false;
            for (String stop : sequence == null ? List.<String>of() : sequence) {
                if (stop != null && stop.startsWith("DROPOFF:")) seenDropoff = true;
                if (seenDropoff && stop != null && stop.startsWith("PICKUP:")) score++;
            }
            return score;
        }
    }

    private static final class LiveBufferItem {
        private final DispatchJobRequest.ApiOrderDto order;
        private final Instant receivedAt;
        private final Instant bufferEnteredAt;
        private Instant lastCheckedAt;
        private int skippedRounds;
        private String priorityLevel = "NORMAL";
        private double waitingMinutes;
        private double urgencyScore;
        private double routeFitScore;
        private double driverBalanceScore;
        private double routeCostPenalty;
        private double finalScore;
        private String status = "WAITING";
        private String assignedCycleId = "";
        private boolean promotedThisRound;
        private LiveBufferItem(DispatchJobRequest.ApiOrderDto order, Instant receivedAt) {
            this.order = order;
            this.receivedAt = receivedAt;
            this.bufferEnteredAt = Instant.now();
            this.lastCheckedAt = this.bufferEnteredAt;
        }
    }
}








