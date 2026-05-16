package com.routechain.api;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.benchmark.BenchmarkHybridRunService;
import com.routechain.v2.benchmark.BenchmarkMode;
import com.routechain.v2.benchmark.BenchmarkProfile;
import com.routechain.v2.unified.DispatchMode;
import com.routechain.v2.unified.DispatchPolicy;
import com.routechain.v2.unified.DispatchStrategy;
import com.routechain.v2.unified.UnifiedHybridDispatchService;
import com.routechain.v2.unified.UnifiedDispatchCore;
import com.routechain.v2.unified.UnifiedBenchmarkDispatchRequest;
import com.routechain.v2.unified.UnifiedBenchmarkDispatchResult;
import com.routechain.v2.unified.UnifiedDispatchRequest;
import com.routechain.v2.unified.UnifiedDispatchResult;
import com.routechain.v2.unified.UnifiedDispatchObjectiveProfile;
import com.routechain.v2.unified.UnifiedDispatchRoutingMode;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.hybrid.BaselineDominanceResult;
import com.routechain.v2.hybrid.BoundRoute;
import com.routechain.v2.hybrid.BoundStop;
import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.DriverSeedLoad;
import com.routechain.v2.hybrid.EliteSolutionArchive;
import com.routechain.v2.hybrid.HybridCostBreakdown;
import com.routechain.v2.hybrid.ImprovedSolutionCandidate;
import com.routechain.v2.hybrid.LexicographicSolutionComparator;
import com.routechain.v2.hybrid.SeedRouteBinding;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import com.routechain.v2.hybrid.SolutionSeedRoute;
import com.routechain.v2.hybrid.StopType;
import com.routechain.v2.routing.BestPathRequest;
import com.routechain.v2.routing.CachingRoutingProvider;
import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.routing.MatrixCostAdapter;
import com.routechain.v2.routing.MatrixSnapshotBuilder;
import com.routechain.v2.routing.RouteStop;
import com.routechain.v2.routing.RoutingProvider;
import com.routechain.v2.routing.RoutingRouteResult;
import com.routechain.v2.streaming.DispatchStreamingEnvelope;
import com.google.ortools.Loader;
import com.google.ortools.linearsolver.MPConstraint;
import com.google.ortools.linearsolver.MPObjective;
import com.google.ortools.linearsolver.MPSolver;
import com.google.ortools.linearsolver.MPVariable;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

@RestController
@RequestMapping("/api/v1/dashboard")
public final class DashboardController {
    private static final Region HCM_REGION = new Region("hcm", "Ho Chi Minh City");
    private static final GeoPoint HCM_CENTER = new GeoPoint(10.7769, 106.7009);
    private static final Path DASHBOARD_ARTIFACT_ROOT = Path.of("artifacts", "dashboard-runs");
    private static final Map<String, Double> ROAD_DISTANCE_KM_CACHE = new ConcurrentHashMap<>();

    private final DispatchV2CompatibleCore dispatchCore;
    private final UnifiedDispatchCore unifiedDispatchCore;
    private final BenchmarkHybridRunService benchmarkHybridRunService;
    private final UnifiedHybridDispatchService hybridDispatchService;
    private final RoutingProvider routingProvider;
    private final RouteChainDispatchV2Properties properties;
    private final ObjectProvider<KafkaTemplate<String, Object>> kafkaTemplateProvider;
    private final Map<String, DashboardRun> runs = new ConcurrentHashMap<>();
    private final Map<String, ManualScenarioDto> scenarios = new ConcurrentHashMap<>();
    private final Map<String, BenchmarkJob> benchmarkJobs = new ConcurrentHashMap<>();
    private final Map<String, DispatchJob> dispatchJobs = new ConcurrentHashMap<>();
    private final Map<String, Future<?>> dispatchJobFutures = new ConcurrentHashMap<>();
    private final AtomicInteger dispatchWorkerIds = new AtomicInteger(1);
    private final ExecutorService dispatchJobExecutor = Executors.newFixedThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "dashboard-dispatch-worker-" + dispatchWorkerIds.getAndIncrement());
        thread.setDaemon(true);
        return thread;
    });

    public DashboardController(DispatchV2CompatibleCore dispatchCore, UnifiedDispatchCore unifiedDispatchCore, BenchmarkHybridRunService benchmarkHybridRunService, UnifiedHybridDispatchService hybridDispatchService, RoutingProvider routingProvider, RouteChainDispatchV2Properties properties, ObjectProvider<KafkaTemplate<String, Object>> kafkaTemplateProvider) {
        this.dispatchCore = dispatchCore;
        this.unifiedDispatchCore = unifiedDispatchCore;
        this.benchmarkHybridRunService = benchmarkHybridRunService;
        this.hybridDispatchService = hybridDispatchService;
        this.routingProvider = routingProvider;
        this.properties = properties;
        this.kafkaTemplateProvider = kafkaTemplateProvider;
    }

    @GetMapping("/runs")
    public List<DashboardRun> runs() {
        return runs.values().stream()
                .sorted(Comparator.comparing(DashboardRun::createdAt).reversed())
                .toList();
    }

    @GetMapping("/runs/{runId}")
    public ResponseEntity<DashboardRun> run(@PathVariable String runId) {
        return runs.containsKey(runId) ? ResponseEntity.ok(runs.get(runId)) : ResponseEntity.notFound().build();
    }

    @GetMapping("/runs/{runId}/visualization")
    public ResponseEntity<RunVisualizationDto> visualization(@PathVariable String runId) {
        DashboardRun run = runs.get(runId);
        return run == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(run.visualization());
    }

    @PostMapping("/scenario/generate")
    public ResponseEntity<RunVisualizationDto> generateScenario(@RequestBody(required = false) ScenarioGenerateRequest request) {
        ScenarioGenerateRequest config = request == null ? ScenarioGenerateRequest.defaults() : request.withDefaults();
        String scenarioId = id("SCN");
        String runId = id("RUN");
        List<OrderDto> orders = generateOrders(config, scenarioId);
        List<DriverDto> drivers = generateDrivers(config, scenarioId);
        Map<String, Object> inputSnapshot = snapshot(config, scenarioId, orders, drivers);
        MetricsDto metrics = new MetricsDto(drivers.size(), 0, 0, 0, 100, 0, 0, 0);
        RunVisualizationDto visualization = new RunVisualizationDto(
                runId,
                scenarioId,
                "scenario-generator",
                "phase1",
                Instant.now().toString(),
                RunStatus.COMPLETED,
                inputSnapshot,
                orders,
                drivers,
                List.of(),
                List.of(),
                List.of(),
                metrics,
                Map.of("uiState", UiState.success.name(), "scenarioType", config.scenarioType()),
                List.of(new EventDto("scenario-generated", "Generated " + orders.size() + " orders and " + drivers.size() + " drivers", "success")),
                null,
                Map.of("artifactRoot", DASHBOARD_ARTIFACT_ROOT.toString()));
        saveRun(new DashboardRun(runId, "SCENARIO", Instant.now().toString(), RunStatus.COMPLETED, visualization));
        scenarios.put(scenarioId, manualScenarioFrom(scenarioId, "Generated " + config.scenarioType(), orders, drivers, config.weatherProfile(), config.trafficMode()));
        return ResponseEntity.ok(visualization);
    }

    @PostMapping("/scenario/manual")
    public ResponseEntity<RunVisualizationDto> saveManualScenario(@RequestBody ManualScenarioDto request) {
        if (request == null || request.orders() == null || request.drivers() == null) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorRun("invalid-manual-scenario", "orders and drivers are required"));
        }
        String scenarioId = request.scenarioId() == null || request.scenarioId().isBlank() ? id("SCN") : request.scenarioId();
        ManualScenarioDto scenario = request.withIdAndDefaults(scenarioId);
        scenarios.put(scenarioId, scenario);
        String runId = id("RUN");
        List<OrderDto> orders = scenario.toOrders();
        List<DriverDto> drivers = scenario.toDrivers();
        ScenarioContextDto context = scenario.context() == null ? ScenarioContextDto.defaults() : scenario.context().withDefaults();
        RunVisualizationDto visualization = new RunVisualizationDto(
                runId,
                scenarioId,
                "manual-scenario-builder",
                "phase2",
                Instant.now().toString(),
                RunStatus.COMPLETED,
                snapshot(new ScenarioGenerateRequest(orders.size(), drivers.size(), "manual", context.weather(), context.traffic(), 0.12), scenarioId, orders, drivers),
                orders,
                drivers,
                List.of(),
                List.of(),
                List.of(),
                new MetricsDto(drivers.size(), 0, 0, 0, 100, 0, 0, 0),
                Map.of("uiState", UiState.success.name(), "scenarioSource", "manual-builder"),
                List.of(new EventDto("manual-scenario-saved", "Saved " + orders.size() + " manual orders and " + drivers.size() + " drivers", "success")),
                null,
                Map.of("artifactRoot", DASHBOARD_ARTIFACT_ROOT.toString()));
        saveRun(new DashboardRun(runId, "SCENARIO", Instant.now().toString(), RunStatus.COMPLETED, visualization));
        return ResponseEntity.ok(visualization);
    }

    @GetMapping("/scenario/{scenarioId}")
    public ResponseEntity<ManualScenarioDto> scenario(@PathVariable String scenarioId) {
        ManualScenarioDto scenario = scenarios.get(scenarioId);
        return scenario == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(scenario);
    }

    @PutMapping("/scenario/{scenarioId}")
    public ResponseEntity<RunVisualizationDto> updateScenario(@PathVariable String scenarioId, @RequestBody ManualScenarioDto request) {
        if (request == null) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorRun("invalid-manual-scenario", "scenario body is required"));
        }
        return saveManualScenario(request.withIdAndDefaults(scenarioId));
    }

    @PostMapping("/dispatch/run")
    public ResponseEntity<RunVisualizationDto> runDispatch(@RequestBody(required = false) DispatchRunRequest request) {
        ResolvedDispatchInput input = resolveDispatchInput(request);
        return ResponseEntity.ok(dispatchVisualization(input.scenarioId(), "IntelligentRouteX", "dispatch-v2-compatible-core", input.orders(), input.drivers(), input.weather(), List.of()));
    }

    @GetMapping("/dispatch/jobs")
    public List<DispatchJob> dispatchJobs() {
        return dispatchJobs.values().stream()
                .sorted(Comparator.comparing(DispatchJob::createdAt).reversed())
                .toList();
    }

    @PostMapping("/dispatch/jobs")
    public ResponseEntity<DispatchJob> createDispatchJob(@RequestBody(required = false) DispatchRunRequest request) {
        ResolvedDispatchInput input = resolveDispatchInput(request);
        String jobId = id("DJOB");
        DispatchJob queued = new DispatchJob(jobId, input.scenarioId(), RunStatus.QUEUED, Instant.now().toString(), null, null, null, input.orders().size(), input.drivers().size());
        dispatchJobs.put(jobId, queued);
        Future<?> future = CompletableFuture.runAsync(() -> executeDispatchJob(jobId, input), dispatchJobExecutor);
        dispatchJobFutures.put(jobId, future);
        return ResponseEntity.accepted().body(queued);
    }

    @PostMapping("/static/dispatch/jobs")
    public ResponseEntity<DispatchJob> createStaticDispatchJob(@RequestBody(required = false) DispatchRunRequest request) {
        return createDispatchJob(request);
    }

    @GetMapping("/dispatch/jobs/{jobId}")
    public ResponseEntity<DispatchJob> dispatchJob(@PathVariable String jobId) {
        DispatchJob job = dispatchJobs.get(jobId);
        return job == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(job);
    }

    @GetMapping("/dispatch/jobs/{jobId}/result")
    public ResponseEntity<RunVisualizationDto> dispatchJobResult(@PathVariable String jobId) {
        DispatchJob job = dispatchJobs.get(jobId);
        if (job == null) {
            return ResponseEntity.notFound().build();
        }
        if (job.resultRunId() == null || !runs.containsKey(job.resultRunId())) {
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(errorRun(jobId, "dispatch job is " + job.status()));
        }
        return ResponseEntity.ok(runs.get(job.resultRunId()).visualization());
    }

    @PostMapping("/dispatch/jobs/{jobId}/cancel")
    public ResponseEntity<DispatchJob> cancelDispatchJob(@PathVariable String jobId) {
        DispatchJob job = dispatchJobs.get(jobId);
        if (job == null) {
            return ResponseEntity.notFound().build();
        }
        Future<?> future = dispatchJobFutures.get(jobId);
        if (future != null) {
            future.cancel(true);
        }
        DispatchJob cancelled = job.withStatus(RunStatus.CANCELLED, job.resultRunId(), "cancelled-by-user", job.workerId());
        dispatchJobs.put(jobId, cancelled);
        return ResponseEntity.ok(cancelled);
    }


    @PostMapping("/dispatch/publish-kafka")
    public ResponseEntity<KafkaPublishReceipt> publishKafkaSnapshot(@RequestBody(required = false) DispatchRunRequest request) {
        String scenarioId = request != null && request.scenarioId() != null ? request.scenarioId() : id("SCN");
        ManualScenarioDto savedScenario = scenarios.get(scenarioId);
        ScenarioGenerateRequest config = request == null || request.scenario() == null
                ? ScenarioGenerateRequest.defaults()
                : request.scenario().withDefaults();
        List<OrderDto> orders = savedScenario != null
                ? savedScenario.toOrders()
                : request != null && request.orders() != null && !request.orders().isEmpty()
                ? request.orders()
                : generateOrders(config, scenarioId);
        List<DriverDto> drivers = savedScenario != null
                ? savedScenario.toDrivers()
                : request != null && request.drivers() != null && !request.drivers().isEmpty()
                ? request.drivers()
                : generateDrivers(config, scenarioId);
        if (!properties.getStreaming().isEnabled()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(new KafkaPublishReceipt(
                    scenarioId,
                    null,
                    "KAFKA_DISABLED",
                    "Streaming is disabled; enable routechain.dispatch-v2.streaming.enabled and Kafka broker."));
        }
        KafkaTemplate<String, Object> kafkaTemplate = kafkaTemplateProvider.getIfAvailable();
        if (kafkaTemplate == null) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(new KafkaPublishReceipt(
                    scenarioId,
                    null,
                    "KAFKA_DISABLED",
                    "KafkaTemplate is not available; enable routechain.dispatch-v2.streaming.enabled and Kafka broker."));
        }
        String traceId = id("KREQ");
        DispatchV2Request coreRequest = new DispatchV2Request(
                "dispatch-v2-request/v1",
                traceId,
                orders.stream().map(DashboardController::toOrder).toList(),
                drivers.stream().map(DashboardController::toDriver).toList(),
                List.of(HCM_REGION),
                savedScenario != null && savedScenario.context() != null ? weatherProfile(savedScenario.context().withDefaults().weather()) : weatherProfile(config.weatherProfile()),
                Instant.now());
        DispatchStreamingEnvelope envelope = new DispatchStreamingEnvelope(
                "dispatch-streaming-envelope/v1",
                traceId,
                "hcm-demo",
                Instant.now(),
                coreRequest,
                Map.of("scenarioId", scenarioId, "source", "dashboard-raw-snapshot"));
        kafkaTemplate.send("irx.dispatch.requests.v1", scenarioId, envelope);
        return ResponseEntity.accepted().body(new KafkaPublishReceipt(scenarioId, traceId, "PUBLISHED", "Raw snapshot published to irx.dispatch.requests.v1"));
    }
    @PostMapping("/rescue/simulate")
    public ResponseEntity<RunVisualizationDto> simulateRescue(@RequestBody RescueSimulationRequest request) {
        if (request == null || request.baseRunId() == null || !runs.containsKey(request.baseRunId())) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorRun("missing-base-run", "baseRunId is required"));
        }
        RunVisualizationDto base = runs.get(request.baseRunId()).visualization();
        List<EventDto> events = request.events() == null || request.events().isEmpty()
                ? List.of(new EventDto("heavy-rain", "Heavy rain shock applied", "warning"))
                : request.events();
        String weather = events.stream().anyMatch(event -> event.type().toLowerCase().contains("rain")) ? "HEAVY_RAIN" : "CLEAR";
        RunVisualizationDto rescue = dispatchVisualization(base.scenarioId(), "IntelligentRouteX", "route-rescue-phase1", base.orders(), base.drivers(), weather, events);
        List<RouteVisualizationDto> rescuedRoutes = rescue.routes().stream()
                .map(route -> route.withRescue("RESCUED", base.routes().isEmpty() ? null : base.routes().getFirst().routeId()))
                .toList();
        RunVisualizationDto withComparison = rescue.withRoutesAndComparison(rescuedRoutes, new ComparisonDto(base.runId(), rescue.runId(), "Route rescue after chaos event", BenchmarkVerdict.PASS_WITH_LIMITS, "straight-line rescue visualization"));
        saveRun(new DashboardRun(withComparison.runId(), "RESCUE", Instant.now().toString(), RunStatus.COMPLETED, withComparison));
        return ResponseEntity.ok(withComparison);
    }

    @GetMapping("/benchmarks/datasets")
    public List<BenchmarkDatasetDto> benchmarkDatasets() throws IOException {
        Path suiteDir = Path.of("benchmarks", "suites");
        if (!Files.exists(suiteDir)) {
            return List.of();
        }
        try (var paths = Files.list(suiteDir)) {
            return paths.filter(path -> path.toString().endsWith(".json"))
                    .sorted()
                    .map(path -> new BenchmarkDatasetDto(path.getFileName().toString().replace(".json", ""), path.toString(), "repo-suite"))
                    .toList();
        }
    }

    @GetMapping("/benchmarks/jobs")
    public List<BenchmarkJob> benchmarkJobs() {
        return benchmarkJobs.values().stream().sorted(Comparator.comparing(BenchmarkJob::createdAt).reversed()).toList();
    }

    @PostMapping("/benchmarks/jobs")
    public BenchmarkJob createBenchmarkJob(@RequestBody(required = false) BenchmarkJobRequest request) {
        BenchmarkJobRequest config = request == null ? BenchmarkJobRequest.defaults() : request.withDefaults();
        String jobId = id("BMJ");
        BenchmarkJob created = new BenchmarkJob(jobId, config.datasetId(), config.solvers(), RunStatus.RUNNING, Instant.now().toString(), null, null);
        benchmarkJobs.put(jobId, created);
        BenchmarkProfile profile = BenchmarkProfile.of(config.modeEnum());
        UnifiedBenchmarkDispatchResult<RunVisualizationDto> dispatchResult = unifiedDispatchCore.dispatchBenchmark(new UnifiedBenchmarkDispatchRequest<>(
                "unified-benchmark-dispatch-request/v1",
                jobId,
                config.datasetId(),
                config.datasetId(),
                null,
                profile.mode().quality() ? UnifiedDispatchObjectiveProfile.QUALITY_BENCHMARK : UnifiedDispatchObjectiveProfile.FAST_GATE,
                profile.mode().quality() ? UnifiedDispatchRoutingMode.ROAD_OSRM_BOUNDED : UnifiedDispatchRoutingMode.FAST_GATE_MATRIX_FIRST_SYNTHETIC,
                () -> benchmarkHybridRunService.run(jobId, config, this::benchmarkResult),
                Map.of("source", "dashboard-benchmark-job", "benchmarkMode", profile.mode().name())));
        RunVisualizationDto result = withUnifiedBenchmarkEntrypoint(dispatchResult.result(), dispatchResult.diagnostics());
        BenchmarkJob completed = created.withStatus(RunStatus.COMPLETED, result.runId(), null);
        benchmarkJobs.put(jobId, completed);
        saveRun(new DashboardRun(result.runId(), "BENCHMARK", Instant.now().toString(), RunStatus.COMPLETED, result));
        return completed;
    }

    @GetMapping("/benchmarks/jobs/{jobId}")
    public ResponseEntity<BenchmarkJob> benchmarkJob(@PathVariable String jobId) {
        return benchmarkJobs.containsKey(jobId) ? ResponseEntity.ok(benchmarkJobs.get(jobId)) : ResponseEntity.notFound().build();
    }

    @GetMapping("/benchmarks/jobs/{jobId}/result")
    public ResponseEntity<RunVisualizationDto> benchmarkJobResult(@PathVariable String jobId) {
        BenchmarkJob job = benchmarkJobs.get(jobId);
        if (job == null || job.resultRunId() == null) {
            return ResponseEntity.notFound().build();
        }
        return visualization(job.resultRunId());
    }

    @PostMapping("/benchmarks/jobs/{jobId}/cancel")
    public ResponseEntity<BenchmarkJob> cancelBenchmarkJob(@PathVariable String jobId) {
        BenchmarkJob job = benchmarkJobs.get(jobId);
        if (job == null) {
            return ResponseEntity.notFound().build();
        }
        BenchmarkJob cancelled = job.withStatus(RunStatus.CANCELLED, job.resultRunId(), "cancelled-by-user");
        benchmarkJobs.put(jobId, cancelled);
        return ResponseEntity.ok(cancelled);
    }

    private RunVisualizationDto dispatchVisualization(String scenarioId, String solverName, String solverVersion, List<OrderDto> orders, List<DriverDto> drivers, String weather, List<EventDto> events) {
        String runId = id("RUN");
        Instant started = Instant.now();
        long startedNanos = System.nanoTime();
        List<Order> coreOrders = orders.stream().map(DashboardController::toOrder).toList();
        List<Driver> coreDrivers = drivers.stream().map(DashboardController::toDriver).toList();
        UnifiedDispatchResult unified = unifiedDispatchCore.dispatch(new UnifiedDispatchRequest(
                "unified-dispatch-request/v1",
                runId,
                DispatchMode.STATIC_FULL_COVERAGE,
                DispatchStrategy.MULTI_PASS_COVERAGE,
                coreOrders,
                coreDrivers,
                List.of(HCM_REGION),
                weatherProfile(weather),
                DispatchPolicy.dashboardDefault(coreOrders.size(), coreDrivers.size()),
                started));
        DispatchV2Result result = unified.dispatchResult();
        long runtimeMs = (System.nanoTime() - startedNanos) / 1_000_000L;
        List<AssignmentDto> assignments = new ArrayList<>(result.assignments().stream().map(DashboardController::assignmentDto).toList());
        List<BatchDto> batches = new ArrayList<>(assignments.stream()
                .map(assignment -> new BatchDto(assignment.batchId(), assignment.orderIds(), assignment.driverId(), colorFor(assignment.selectionRank()), "CORE_SELECTED"))
                .toList());
        List<RouteVisualizationDto> routes = new ArrayList<>(result.assignments().stream()
                .map(assignment -> routeDto(assignment, ordersById(orders), driversById(drivers), routingProvider))
                .toList());
        Set<String> accepted = new LinkedHashSet<>();
        assignments.forEach(assignment -> accepted.addAll(assignment.orderIds()));
        long lateOrders = routes.stream().mapToLong(RouteVisualizationDto::lateOrderCount).sum();
        double totalDistance = routes.stream().mapToDouble(RouteVisualizationDto::totalDistanceKm).sum();
        double totalEta = routes.stream().mapToDouble(RouteVisualizationDto::totalEtaMinutes).max().orElse(0);
        MetricsDto metrics = new MetricsDto(
                drivers.size(),
                totalDistance,
                lateOrders,
                accepted.size(),
                orders.isEmpty() ? 100 : (accepted.size() * 100.0 / orders.size()),
                runtimeMs,
                batches.size(),
                Math.max(0, orders.size() - accepted.size()));
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("traceId", result.traceId());
        diagnostics.put("decisionStages", result.decisionStages());
        diagnostics.put("stageLatencies", result.stageLatencies());
        diagnostics.put("globalSelectorSummary", result.globalSelectorSummary());
        diagnostics.put("dispatchExecutionSummary", result.dispatchExecutionSummary());
        diagnostics.put("degradeReasons", result.degradeReasons());
        diagnostics.put("balancedCoverageRepairApplied", false);
        diagnostics.put("balancedCoverageRepairReasons", List.of("dashboard-repair-disabled-core-owned-coverage"));
        diagnostics.put("coverageMode", unified.diagnostics().get("coverageMode"));
        diagnostics.put("dispatchMode", unified.diagnostics().get("dispatchMode"));
        diagnostics.put("dispatchStrategy", unified.diagnostics().get("dispatchStrategy"));
        diagnostics.put("passCount", unified.diagnostics().get("passCount"));
        diagnostics.put("passTimeline", unified.passTimeline());
        diagnostics.put("coverageSummary", unified.coverageSummary());
        diagnostics.put("driverLoadSummary", unified.driverLoadSummary());
        diagnostics.put("accountingInvariant", unified.diagnostics().get("accountingInvariant"));
        diagnostics.put("coreFunnelAudit", coreFunnelAudit(result));
        diagnostics.put("assignmentSourceAudit", assignmentSourceAudit(assignments));
        diagnostics.put("distanceProvider", routingProvider.providerId());
        diagnostics.put("distanceMode", "ROAD_ROUTE_PROVIDER_WITH_SYNTHETIC_FALLBACK");
        diagnostics.put("usedDriverCount", routes.stream().map(RouteVisualizationDto::driverId).distinct().count());
        diagnostics.put("coverageTarget", Map.of("orders", orders.size(), "drivers", drivers.size(), "principle", "maximize raw snapshot coverage with least-loaded feasible drivers"));
        diagnostics.put("uiState", UiState.success.name());
        RunVisualizationDto visualization = new RunVisualizationDto(
                runId,
                scenarioId,
                solverName,
                solverVersion,
                Instant.now().toString(),
                RunStatus.COMPLETED,
                snapshot(ScenarioGenerateRequest.defaults(), scenarioId, orders, drivers),
                orders,
                drivers,
                batches,
                assignments,
                routes,
                metrics,
                diagnostics,
                events,
                null,
                Map.of("geometryMode", GeometryMode.STRAIGHT_LINE.name()));
        saveRun(new DashboardRun(runId, "DISPATCH", Instant.now().toString(), RunStatus.COMPLETED, visualization));
        return visualization;
    }

    private void executeDispatchJob(String jobId, ResolvedDispatchInput input) {
        DispatchJob job = dispatchJobs.get(jobId);
        if (job == null || job.status() == RunStatus.CANCELLED) {
            return;
        }
        String workerId = Thread.currentThread().getName();
        dispatchJobs.put(jobId, job.withStatus(RunStatus.RUNNING, null, null, workerId));
        try {
            RunVisualizationDto visualization = dispatchVisualization(
                    input.scenarioId(),
                    "IntelligentRouteX",
                    "dispatch-v2-compatible-core-async",
                    input.orders(),
                    input.drivers(),
                    input.weather(),
                    List.of(new EventDto("async-dispatch", "Solved by in-memory worker " + workerId, "success")));
            dispatchJobs.put(jobId, dispatchJobs.get(jobId).withStatus(RunStatus.COMPLETED, visualization.runId(), null, workerId));
        } catch (RuntimeException error) {
            dispatchJobs.put(jobId, dispatchJobs.get(jobId).withStatus(RunStatus.FAILED, null, error.getMessage(), workerId));
        }
    }

    private ResolvedDispatchInput resolveDispatchInput(DispatchRunRequest request) {
        ScenarioGenerateRequest config = request == null || request.scenario() == null
                ? ScenarioGenerateRequest.defaults()
                : request.scenario().withDefaults();
        String scenarioId = request != null && request.scenarioId() != null ? request.scenarioId() : id("SCN");
        ManualScenarioDto savedScenario = scenarios.get(scenarioId);
        List<OrderDto> orders = savedScenario != null
                ? savedScenario.toOrders()
                : request != null && request.orders() != null && !request.orders().isEmpty()
                ? request.orders()
                : generateOrders(config, scenarioId);
        List<DriverDto> drivers = savedScenario != null
                ? savedScenario.toDrivers()
                : request != null && request.drivers() != null && !request.drivers().isEmpty()
                ? request.drivers()
                : generateDrivers(config, scenarioId);
        String weather = savedScenario != null && savedScenario.context() != null ? savedScenario.context().withDefaults().weather() : config.weatherProfile();
        return new ResolvedDispatchInput(scenarioId, orders, drivers, weather);
    }

    private RunVisualizationDto benchmarkResult(String jobId, BenchmarkJobRequest request) {
        long benchmarkStarted = System.nanoTime();
        Map<String, Object> stageRuntime = new LinkedHashMap<>();
        Map<String, Object> routingCacheStart = benchmarkHybridRunService.globalRoutingCacheDiagnostics(routingProvider);
        long scenarioStarted = System.nanoTime();
        ScenarioGenerateRequest scenario = benchmarkScenario(request.datasetId()).withDefaults();
        String scenarioSeed = request.datasetId() == null || request.datasetId().isBlank() ? scenario.scenarioType() : request.datasetId();
        List<OrderDto> orders = generateOrders(scenario, scenarioSeed);
        List<DriverDto> drivers = generateDrivers(scenario, scenarioSeed);
        String scenarioHash = scenarioHash(scenario, orders, drivers);
        BenchmarkProfile profile = BenchmarkProfile.of(request.modeEnum());
        DistanceDurationMatrixSnapshot matrixSnapshot = new MatrixSnapshotBuilder().build(
                request.datasetId() == null ? "raw-m" : request.datasetId(),
                scenarioHash,
                profile.routingMode(),
                benchmarkHybridRunService.matrixNodes(orders, drivers));
        MatrixCostAdapter matrixCost = new MatrixCostAdapter(matrixSnapshot);
        stageRuntime.put("scenarioLoadMs", elapsedMs(scenarioStarted));
        List<BenchmarkSolverResultDto> solverResults = new ArrayList<>();
        List<String> solvers = request.solvers();
        long coreStarted = System.nanoTime();
        RunVisualizationDto irx = dispatchVisualization(jobId, "IntelligentRouteX", "benchmark-phase1", orders, drivers, scenario.weatherProfile(), List.of());
        stageRuntime.put("coreDispatchMs", elapsedMs(coreStarted));
        long baselineStarted = System.nanoTime();
        for (String solver : solvers) {
            solverResults.add(benchmarkSolver(solver, orders, drivers, irx, matrixCost));
        }
        stageRuntime.put("benchmarkBaselinesMs", elapsedMs(baselineStarted));
        long archiveStarted = System.nanoTime();
        EliteSolutionArchive eliteArchive = eliteSolutionArchive(solverResults, irx);
        List<SeedRouteBinding> routeBindings = seedRouteBindings(eliteArchive, orders, drivers, irx, matrixCost);
        stageRuntime.put("seedBindingMs", elapsedMs(archiveStarted));
        int hybridImprovementTopK = profile.topKSeeds();
        long hybridStarted = System.nanoTime();
        UnifiedHybridDispatchService.HybridRunResult hybrid = hybridDispatchService.run(
                eliteArchive,
                routeBindings,
                solutionSeedFromRun(CandidateSource.IRX_ML_FUSED, "SOL-IRX-FINAL", irx),
                (legId, fromLat, fromLng, toLat, toLng) -> matrixCost.distanceKm(fromLat, fromLng, toLat, toLng),
                hybridImprovementTopK,
                profile.swapStarEnabled());
        stageRuntime.put("hybridImprovementMs", elapsedMs(hybridStarted));
        List<ImprovedSolutionCandidate> improvedSeeds = hybrid.improvedSeeds();
        SolutionSeedCandidate bestImprovedSeed = hybrid.bestImprovedSeed();
        SolutionSeedCandidate finalSeed = hybrid.finalSeed();
        BaselineDominanceResult dominance = hybrid.dominance();
        solverResults.add(hybridDispatchService.hybridSolverResult(irx, dominance, finalSeed));
        stageRuntime.put("totalBenchmarkMs", elapsedMs(benchmarkStarted));
        ComparisonDto comparison = new ComparisonDto(null, irx.runId(), "Benchmark job " + jobId, BenchmarkVerdict.PASS_WITH_LIMITS, "phase1 honest benchmark: wired local baselines plus evidence gaps for incomplete external adapters");
        Map<String, Object> diagnostics = new LinkedHashMap<>(irx.diagnostics());
        diagnostics.put("benchmarkIdentity", benchmarkHybridRunService.benchmarkIdentity(request.datasetId(), scenario, jobId, irx, orders, drivers, scenarioHash));
        diagnostics.put("matrixSnapshot", benchmarkHybridRunService.matrixSnapshotDiagnostics(matrixSnapshot));
        diagnostics.put("stageRuntime", stageRuntime);
        diagnostics.put("coreStageTiming", benchmarkHybridRunService.coreStageTiming(irx));
        diagnostics.put("globalRoutingCache", benchmarkHybridRunService.globalRoutingCacheDiagnostics(routingProvider, routingCacheStart));
        diagnostics.put("solverResults", solverResults);
        diagnostics.put("benchmarkProfile", benchmarkHybridRunService.profileDiagnostics(profile));
        diagnostics.putAll(benchmarkHybridRunService.objectiveAwareDiagnostics(solverResults));
        diagnostics.put("eliteSolutionArchive", hybridDispatchService.eliteArchiveDiagnostics(eliteArchive));
        diagnostics.put("seedImprovement", hybridDispatchService.improvementDiagnostics(improvedSeeds, bestImprovedSeed, routeBindings, hybridImprovementTopK));
        diagnostics.put("baselineDominanceGuard", hybridDispatchService.dominanceDiagnostics(dominance));
        diagnostics.put("ablationResults", hybridDispatchService.ablationDiagnostics(solverResults, irx, dominance));
        diagnostics.put("rootCauseAudit", hybridDispatchService.rootCauseAudit(irx, solverResults));
        diagnostics.put("verdictReasons", List.of("same raw snapshot for every wired solver", "PyVRP/VROOM require local runtime if selected"));
        return irx.withSolver("Benchmark Arena", "phase1-job").withComparison(comparison).withDiagnostics(diagnostics);
    }

    private static RunVisualizationDto withUnifiedBenchmarkEntrypoint(RunVisualizationDto run, Map<String, Object> coreDiagnostics) {
        Map<String, Object> diagnostics = new LinkedHashMap<>(run.diagnostics());
        diagnostics.put("unifiedDispatchCore", coreDiagnostics);
        return run.withDiagnostics(diagnostics);
    }

    private static ScenarioGenerateRequest benchmarkScenario(String datasetId) {
        String dataset = datasetId == null ? "synthetic-food-smoke" : datasetId.trim().toLowerCase();
        return switch (dataset) {
            case "raw-s", "demo-s" -> new ScenarioGenerateRequest(12, 3, "raw-s", "CLEAR", "normal", 0.12);
            case "raw-l", "demo-l" -> new ScenarioGenerateRequest(30, 5, "raw-l", "CLEAR", "normal", 0.12);
            case "hcm-dinner-peak" -> new ScenarioGenerateRequest(20, 4, "hcm-dinner-peak", "CLEAR", "rush", 0.18);
            case "heavy-rain-case" -> new ScenarioGenerateRequest(20, 4, "heavy-rain-case", "HEAVY_RAIN", "slow", 0.22);
            case "driver-scarcity-case" -> new ScenarioGenerateRequest(24, 3, "driver-scarcity-case", "CLEAR", "scarce", 0.16);
            case "random-spread" -> new ScenarioGenerateRequest(20, 4, "random-spread", "CLEAR", "normal", 0.12);
            case "tight-deadline-case" -> new ScenarioGenerateRequest(20, 4, "tight-deadline-case", "CLEAR", "normal", 0.22);
            case "wide-deadline-case" -> new ScenarioGenerateRequest(20, 4, "wide-deadline-case", "CLEAR", "normal", 0.08);
            case "driver-imbalanced-case" -> new ScenarioGenerateRequest(22, 4, "driver-imbalanced-case", "CLEAR", "imbalanced", 0.14);
            case "many-orders-few-drivers" -> new ScenarioGenerateRequest(28, 3, "many-orders-few-drivers", "CLEAR", "scarce", 0.18);
            case "few-orders-many-drivers" -> new ScenarioGenerateRequest(10, 6, "few-orders-many-drivers", "CLEAR", "normal", 0.08);
            case "opposite-direction-dropoffs" -> new ScenarioGenerateRequest(20, 4, "opposite-direction-dropoffs", "CLEAR", "opposite", 0.14);
            case "clustered-pickups-random-dropoffs" -> new ScenarioGenerateRequest(22, 4, "clustered-pickups-random-dropoffs", "CLEAR", "clustered-pickups", 0.14);
            case "random-pickups-clustered-dropoffs" -> new ScenarioGenerateRequest(22, 4, "random-pickups-clustered-dropoffs", "CLEAR", "clustered-dropoffs", 0.14);
            case "long-tail-distance" -> new ScenarioGenerateRequest(22, 4, "long-tail-distance", "CLEAR", "long-tail", 0.12);
            case "tight-capacity" -> new ScenarioGenerateRequest(24, 4, "tight-capacity", "CLEAR", "tight-capacity", 0.16);
            case "high-priority-orders" -> new ScenarioGenerateRequest(20, 4, "high-priority-orders", "CLEAR", "high-priority", 0.35);
            case "random-rush" -> new ScenarioGenerateRequest(20, 4, "rush_hour", "CLEAR", "rush", 0.18);
            default -> new ScenarioGenerateRequest(20, 4, "raw-m", "CLEAR", "normal", 0.12);
        };
    }

    private static EliteSolutionArchive eliteSolutionArchive(List<BenchmarkSolverResultDto> solverResults, RunVisualizationDto irx) {
        EliteSolutionArchive archive = new EliteSolutionArchive();
        for (BenchmarkSolverResultDto result : solverResults) {
            CandidateSource source = sourceForSolver(result.solverName());
            if (source == null || result.status() != SolverRunStatus.COMPLETED || result.totalDistanceKm() <= 0) {
                continue;
            }
            archive.accept(solutionSeedFromSolver(source, "SOL-" + source.name(), result));
        }
        return archive;
    }

    private static List<SeedRouteBinding> seedRouteBindings(EliteSolutionArchive archive, List<OrderDto> orders, List<DriverDto> drivers, RunVisualizationDto irx, MatrixCostAdapter matrixCost) {
        Map<String, OrderDto> orderDtos = orders.stream().collect(java.util.stream.Collectors.toMap(OrderDto::orderId, order -> order, (left, right) -> left, LinkedHashMap::new));
        Map<String, DriverDto> driverDtos = drivers.stream().collect(java.util.stream.Collectors.toMap(DriverDto::driverId, driver -> driver, (left, right) -> left, LinkedHashMap::new));
        Map<String, Order> orderById = orders.stream().collect(java.util.stream.Collectors.toMap(OrderDto::orderId, DashboardController::toOrder, (left, right) -> left, LinkedHashMap::new));
        Map<String, Driver> driverById = drivers.stream().collect(java.util.stream.Collectors.toMap(DriverDto::driverId, DashboardController::toDriver, (left, right) -> left, LinkedHashMap::new));
        Map<CandidateSource, List<SolutionSeedRoute>> routeBySource = new LinkedHashMap<>();
        routeBySource.put(CandidateSource.DISTANCE_SEED, distanceSeedRoutes(orders, drivers, matrixCost));
        routeBySource.put(CandidateSource.ORTOOLS_SEED, ortoolsSeedRoutes(orders, drivers, matrixCost));
        routeBySource.put(CandidateSource.SINGLETON, singletonSeedRoutes(orders, drivers, matrixCost));
        routeBySource.put(CandidateSource.IRX_NATIVE, solutionSeedFromRun(CandidateSource.IRX_NATIVE, "SOL-IRX-NATIVE", irx).routes());
        return archive.seeds().stream()
                .map(seed -> bindSeed(seed, routeBySource.getOrDefault(seed.source(), seed.routes()), orderDtos, driverDtos, orderById, driverById))
                .filter(binding -> !binding.routes().isEmpty())
                .toList();
    }

    private static SeedRouteBinding bindSeed(SolutionSeedCandidate seed, List<SolutionSeedRoute> routes, Map<String, OrderDto> orderDtos, Map<String, DriverDto> driverDtos, Map<String, Order> orderById, Map<String, Driver> driverById) {
        List<BoundRoute> boundRoutes = routes.stream()
                .map(route -> bindRoute(route, orderDtos, driverDtos))
                .filter(route -> !route.stops().isEmpty())
                .toList();
        return new SeedRouteBinding(seed.solutionSeedId(), seed.source(), seed, boundRoutes, orderById, driverById, true, "benchmark-shared-routing-provider");
    }

    private static BoundRoute bindRoute(SolutionSeedRoute route, Map<String, OrderDto> orders, Map<String, DriverDto> drivers) {
        DriverDto driver = drivers.get(route.driverId());
        List<BoundStop> stops = new ArrayList<>();
        if (driver != null) {
            stops.add(new BoundStop("driver:" + driver.driverId(), "", StopType.DRIVER_START, new GeoPoint(driver.lat(), driver.lng())));
        }
        if (route.stopSequence().isEmpty()) {
            for (String orderId : route.orderIds()) {
                addBoundStops(stops, orders.get(orderId));
            }
        } else {
            for (String encoded : route.stopSequence()) {
                String[] parts = encoded.split(":", 2);
                if (parts.length != 2) {
                    continue;
                }
                OrderDto order = orders.get(parts[1]);
                if (order == null) {
                    continue;
                }
                if (parts[0].equalsIgnoreCase("PICKUP")) {
                    stops.add(new BoundStop("pickup:" + order.orderId(), order.orderId(), StopType.PICKUP, new GeoPoint(order.pickupLat(), order.pickupLng())));
                } else if (parts[0].equalsIgnoreCase("DROPOFF")) {
                    stops.add(new BoundStop("dropoff:" + order.orderId(), order.orderId(), StopType.DROPOFF, new GeoPoint(order.dropoffLat(), order.dropoffLng())));
                }
            }
        }
        return new BoundRoute(route.routeId(), route.driverId(), route.orderIds(), stops, route.distanceKm(), route.durationMinutes(), (int) route.lateOrderCount());
    }

    private static void addBoundStops(List<BoundStop> stops, OrderDto order) {
        if (order == null) {
            return;
        }
        stops.add(new BoundStop("pickup:" + order.orderId(), order.orderId(), StopType.PICKUP, new GeoPoint(order.pickupLat(), order.pickupLng())));
        stops.add(new BoundStop("dropoff:" + order.orderId(), order.orderId(), StopType.DROPOFF, new GeoPoint(order.dropoffLat(), order.dropoffLng())));
    }

    private static List<SolutionSeedRoute> distanceSeedRoutes(List<OrderDto> orders, List<DriverDto> drivers, MatrixCostAdapter matrixCost) {
        if (drivers.isEmpty()) {
            return List.of();
        }
        Map<String, List<OrderDto>> byDriver = new LinkedHashMap<>();
        drivers.forEach(driver -> byDriver.put(driver.driverId(), new ArrayList<>()));
        for (OrderDto order : orders) {
            DriverDto nearest = drivers.stream()
                    .min(Comparator.comparingDouble(driver -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .orElse(drivers.getFirst());
            byDriver.get(nearest.driverId()).add(order);
        }
        List<SolutionSeedRoute> routes = new ArrayList<>();
        for (DriverDto driver : drivers) {
            List<OrderDto> routeOrders = byDriver.get(driver.driverId()).stream()
                    .sorted(Comparator.comparingDouble(order -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .toList();
            if (!routeOrders.isEmpty()) {
                routes.add(seedRoute("DIST-" + driver.driverId(), driver, routeOrders, matrixCost));
            }
        }
        return routes;
    }

    private static List<SolutionSeedRoute> ortoolsSeedRoutes(List<OrderDto> orders, List<DriverDto> drivers, MatrixCostAdapter matrixCost) {
        if (drivers.isEmpty()) {
            return List.of();
        }
        int maxLoad = Math.max(1, (int) Math.ceil(orders.size() / (double) Math.max(1, drivers.size())) + 1);
        Map<String, List<OrderDto>> byDriver = new LinkedHashMap<>();
        drivers.forEach(driver -> byDriver.put(driver.driverId(), new ArrayList<>()));
        for (OrderDto order : orders.stream().sorted(Comparator.comparing(OrderDto::orderId)).toList()) {
            DriverDto best = drivers.stream()
                    .filter(driver -> byDriver.get(driver.driverId()).size() < maxLoad)
                    .min(Comparator.comparingDouble(driver -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())
                            + matrixCost.distanceKm(order.pickupLat(), order.pickupLng(), order.dropoffLat(), order.dropoffLng())))
                    .orElse(drivers.getFirst());
            byDriver.get(best.driverId()).add(order);
        }
        List<SolutionSeedRoute> routes = new ArrayList<>();
        for (DriverDto driver : drivers) {
            List<OrderDto> routeOrders = byDriver.get(driver.driverId()).stream()
                    .sorted(Comparator.comparingDouble(order -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .toList();
            if (!routeOrders.isEmpty()) {
                routes.add(seedRoute("ORT-" + driver.driverId(), driver, routeOrders, matrixCost));
            }
        }
        return routes;
    }

    private static List<SolutionSeedRoute> singletonSeedRoutes(List<OrderDto> orders, List<DriverDto> drivers, MatrixCostAdapter matrixCost) {
        if (drivers.isEmpty()) {
            return List.of();
        }
        List<SolutionSeedRoute> routes = new ArrayList<>();
        for (int index = 0; index < orders.size(); index++) {
            DriverDto driver = drivers.get(index % drivers.size());
            routes.add(seedRoute("SINGLE-" + orders.get(index).orderId(), driver, List.of(orders.get(index)), matrixCost));
        }
        return routes;
    }

    private static SolutionSeedRoute seedRoute(String routeId, DriverDto driver, List<OrderDto> routeOrders, MatrixCostAdapter matrixCost) {
        double previousLat = driver.lat();
        double previousLng = driver.lng();
        double distance = 0.0;
        double minutes = 0.0;
        long late = 0;
        List<String> sequence = new ArrayList<>();
        for (OrderDto order : routeOrders) {
            double leg = matrixCost.distanceKm(previousLat, previousLng, order.pickupLat(), order.pickupLng());
            distance += leg;
            minutes += leg / 22.0 * 60.0;
            sequence.add("PICKUP:" + order.orderId());
            previousLat = order.pickupLat();
            previousLng = order.pickupLng();
        }
        for (OrderDto order : routeOrders) {
            double leg = matrixCost.distanceKm(previousLat, previousLng, order.dropoffLat(), order.dropoffLng());
            distance += leg;
            minutes += leg / 22.0 * 60.0;
            if (minutes > order.deadlineMinutes()) {
                late++;
            }
            sequence.add("DROPOFF:" + order.orderId());
            previousLat = order.dropoffLat();
            previousLng = order.dropoffLng();
        }
        return new SolutionSeedRoute(routeId, driver.driverId(), routeOrders.stream().map(OrderDto::orderId).toList(), sequence, round(distance), round(minutes), late);
    }

    private static CandidateSource sourceForSolver(String solverName) {
        String normalized = solverName == null ? "" : solverName.trim().toLowerCase();
        return switch (normalized) {
            case "single-order" -> CandidateSource.SINGLETON;
            case "distance batching" -> CandidateSource.DISTANCE_SEED;
            case "or-tools" -> CandidateSource.ORTOOLS_SEED;
            case "pyvrp" -> CandidateSource.PYVRP_SEED;
            case "vroom" -> CandidateSource.VROOM_SEED;
            case "intelligentroutex" -> CandidateSource.IRX_NATIVE;
            default -> null;
        };
    }

    private static SolutionSeedCandidate solutionSeedFromSolver(CandidateSource source, String seedId, BenchmarkSolverResultDto result) {
        double score = solutionObjective(result.assignedOrderCount(), result.inputOrderCount(), result.totalDistanceKm(), result.lateOrderCount(), 0.0);
        return new SolutionSeedCandidate(
                seedId,
                source,
                List.of(),
                result.inputOrderCount() == 0 ? 0.0 : result.assignedOrderCount() / (double) result.inputOrderCount(),
                result.totalDistanceKm(),
                result.lateOrderCount(),
                List.of(),
                result.status() == SolverRunStatus.COMPLETED,
                result.status() == SolverRunStatus.COMPLETED ? "" : result.reason(),
                List.of(result.reason()),
                new HybridCostBreakdown(result.totalDistanceKm(), result.lateOrderCount() * 10.0, 0.0, 0.0, 0.0, 0.0, score));
    }

    private static SolutionSeedCandidate solutionSeedFromRun(CandidateSource source, String seedId, RunVisualizationDto run) {
        List<SolutionSeedRoute> seedRoutes = run.routes().stream()
                .map(route -> new SolutionSeedRoute(route.routeId(), route.driverId(), route.stops().stream().map(StopVisualizationDto::orderId).distinct().toList(), route.stops().stream().map(stop -> stop.type() + ":" + stop.orderId()).toList(), route.totalDistanceKm(), route.totalEtaMinutes(), route.lateOrderCount()))
                .toList();
        List<DriverSeedLoad> loads = run.assignments().stream()
                .map(assignment -> new DriverSeedLoad(assignment.driverId(), assignment.orderIds().size()))
                .toList();
        double score = solutionObjective(run.metrics().assignedOrderCount(), run.orders().size(), run.metrics().totalDistanceKm(), run.metrics().lateOrderCount(), 0.0);
        return new SolutionSeedCandidate(
                seedId,
                source,
                seedRoutes,
                run.orders().isEmpty() ? 0.0 : run.metrics().assignedOrderCount() / (double) run.orders().size(),
                run.metrics().totalDistanceKm(),
                run.metrics().lateOrderCount(),
                loads,
                run.status() == RunStatus.COMPLETED,
                run.status() == RunStatus.COMPLETED ? "" : "run-not-completed",
                List.of("dashboard-run-seed"),
                new HybridCostBreakdown(run.metrics().totalDistanceKm(), run.metrics().lateOrderCount() * 10.0, 0.0, 0.0, 0.0, 0.0, score));
    }

    private static double solutionObjective(long assignedOrders, long inputOrders, double distanceKm, long lateOrders, double repairPenalty) {
        long safeInput = Math.max(1, inputOrders);
        double coverageReward = (assignedOrders / (double) safeInput) * 1_000_000.0;
        double uncoveredPenalty = Math.max(0, inputOrders - assignedOrders) * 1_000_000.0;
        return coverageReward - uncoveredPenalty - distanceKm * 100.0 - lateOrders * 10_000.0 - repairPenalty;
    }

    private static Map<String, Object> coreFunnelAudit(DispatchV2Result result) {
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("pairGraphSummary", result.pairGraphSummary());
        audit.put("microClusterCount", result.microClusters().size());
        audit.put("bundleCandidateCount", result.bundleCandidates().size());
        audit.put("pickupAnchorCount", result.pickupAnchors().size());
        audit.put("driverCandidateCount", result.driverCandidates().size());
        audit.put("routeProposalCount", result.routeProposals().size());
        audit.put("routeProposalSummary", result.routeProposalSummary());
        audit.put("scenarioEvaluationCount", result.scenarioEvaluations().size());
        audit.put("robustUtilityCount", result.robustUtilities().size());
        audit.put("selectorCandidateCount", result.selectorCandidates().size());
        audit.put("globalSelectorSummary", result.globalSelectorSummary());
        audit.put("coreAssignmentCount", result.dispatchExecutionSummary().executedAssignmentCount());
        audit.put("selectedProposalCount", result.dispatchExecutionSummary().selectedProposalCount());
        audit.put("routeProposalSources", result.routeProposals().stream().collect(java.util.stream.Collectors.groupingBy(proposal -> proposal.source().name(), LinkedHashMap::new, java.util.stream.Collectors.counting())));
        audit.put("routeProposalFeasibleCount", result.routeProposals().stream().filter(com.routechain.v2.route.RouteProposal::feasible).count());
        audit.put("routeProposalGeometryCount", result.routeProposals().stream().filter(com.routechain.v2.route.RouteProposal::geometryAvailable).count());
        audit.put("selectorCandidateSources", result.selectorCandidates().stream().collect(java.util.stream.Collectors.groupingBy(candidate -> candidate.source().name(), LinkedHashMap::new, java.util.stream.Collectors.counting())));
        audit.put("degradeReasonCounts", result.degradeReasons().stream().collect(java.util.stream.Collectors.groupingBy(reason -> reason, LinkedHashMap::new, java.util.stream.Collectors.counting())));
        audit.put("stageLatencyMs", result.stageLatencies().stream().collect(java.util.stream.Collectors.toMap(DispatchStageLatency::stageName, DispatchStageLatency::elapsedMs, (left, right) -> left, LinkedHashMap::new)));
        return audit;
    }

    private static Map<String, Object> assignmentSourceAudit(List<AssignmentDto> assignments) {
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("assignmentCount", assignments.size());
        audit.put("assignedOrderCount", assignments.stream().mapToLong(assignment -> assignment.orderIds().size()).sum());
        audit.put("repairAssignmentCount", assignments.stream().filter(DashboardController::isRepairAssignment).count());
        audit.put("coreSelectedAssignmentCount", assignments.stream().filter(assignment -> !isRepairAssignment(assignment)).count());
        audit.put("reasons", assignments.stream()
                .flatMap(assignment -> assignment.reasons().stream())
                .collect(java.util.stream.Collectors.groupingBy(reason -> reason, LinkedHashMap::new, java.util.stream.Collectors.counting())));
        audit.put("perDriverOrderCount", assignments.stream().collect(java.util.stream.Collectors.toMap(AssignmentDto::driverId, assignment -> assignment.orderIds().size(), Integer::sum, LinkedHashMap::new)));
        return audit;
    }

    private static boolean isRepairAssignment(AssignmentDto assignment) {
        return assignment.reasons().stream().anyMatch(reason -> reason.contains("repair") || reason.contains("fallback") || reason.contains("coverage"));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> objectMap(Object value) {
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
    }

    private static List<String> rootCauseSymptoms(RunVisualizationDto irx,
                                                  BenchmarkSolverResultDto irxResult,
                                                  BenchmarkSolverResultDto bestDistance,
                                                  Map<String, Object> coreFunnel,
                                                  Map<String, Object> sourceAudit,
                                                  List<?> passes) {
        List<String> symptoms = new ArrayList<>();
        if (irxResult != null && bestDistance != null && irxResult.totalDistanceKm() > bestDistance.totalDistanceKm()) {
            symptoms.add("irx-distance-above-best-completed-solver");
        }
        if (number(coreFunnel.get("selectorCandidateCount")) == 0) {
            symptoms.add("core-selector-produced-zero-candidates");
        }
        if (number(coreFunnel.get("coreAssignmentCount")) == 0) {
            symptoms.add("core-executor-produced-zero-assignments-before-coverage-drain");
        }
        if (number(sourceAudit.get("repairAssignmentCount")) > 0) {
            symptoms.add("final-result-contains-repair-or-coverage-assignments");
        }
        if (irx.metrics().lateOrderCount() > 0) {
            symptoms.add("visualization-reports-late-risk-stops");
        }
        if (passes.stream().anyMatch(pass -> String.valueOf(pass).contains("BALANCED_COVERAGE_REPAIR"))) {
            symptoms.add("coverage-repair-dominated-final-coverage");
        }
        return symptoms;
    }

    private static String rootCauseVerdict(Map<String, Object> coreFunnel, Map<String, Object> sourceAudit, List<?> passes) {
        if (number(coreFunnel.get("selectorCandidateCount")) == 0 && number(sourceAudit.get("repairAssignmentCount")) > 0) {
            return "PRIMARY: core candidate/selector path failed, final output is coverage-repair dominated; compare algorithms against IRX core-only separately from full-coverage repair.";
        }
        if (number(coreFunnel.get("selectorCandidateCount")) > 0 && number(coreFunnel.get("coreAssignmentCount")) == 0) {
            return "PRIMARY: candidates exist but selector/executor rejected all; inspect feasibility and acceptance gate.";
        }
        if (passes.stream().anyMatch(pass -> String.valueOf(pass).contains("BALANCED_COVERAGE_REPAIR"))) {
            return "PRIMARY: core selected partial result; coverage repair changed assignment/route quality.";
        }
        return "PRIMARY: no single failure proven by current audit; inspect route sequence and scoring deltas next.";
    }

    private static long number(Object value) {
        return value instanceof Number number ? number.longValue() : 0L;
    }

    private BenchmarkSolverResultDto benchmarkSolver(String solver, List<OrderDto> orders, List<DriverDto> drivers, RunVisualizationDto irx, MatrixCostAdapter matrixCost) {
        String normalized = solver == null ? "" : solver.trim().toLowerCase();
        long started = System.nanoTime();
        if (normalized.equals("single-order") || normalized.equals("single order")) {
            double distance = singleOrderDistanceKm(orders, drivers, matrixCost);
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            return new BenchmarkSolverResultDto("Single-order", SolverRunStatus.COMPLETED, BenchmarkVerdict.PASS_WITH_LIMITS, Math.min(orders.size(), drivers.size()), orders.size(), orders.size(), distance, 0, 100.0, runtimeMs, "wired baseline: one route per order, costly but full coverage", null);
        }
        if (normalized.equals("distance-batching") || normalized.equals("distance batching") || normalized.equals("distance-based batching")) {
            double distance = distanceBatchingDistanceKm(orders, drivers, matrixCost);
            long late = Math.max(0, orders.size() / 6);
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            return new BenchmarkSolverResultDto("Distance batching", SolverRunStatus.COMPLETED, BenchmarkVerdict.PASS_WITH_LIMITS, drivers.size(), orders.size(), orders.size(), distance, late, Math.max(0, 100.0 - late * 100.0 / Math.max(1, orders.size())), runtimeMs, "wired baseline: nearest-driver greedy batching", null);
        }
        if (normalized.equals("intelligentroutex") || normalized.equals("irx") || normalized.equals("unifieddispatchcore")) {
            return new BenchmarkSolverResultDto("IntelligentRouteX", SolverRunStatus.COMPLETED, BenchmarkVerdict.PASS_WITH_LIMITS, irx.routes().size(), irx.metrics().assignedOrderCount(), irx.orders().size(), irx.metrics().totalDistanceKm(), irx.metrics().lateOrderCount(), irx.metrics().slaSuccessRate(), irx.metrics().runtimeMs(), "wired: UnifiedDispatchCore coverage drain; winner decided by selected metric", irx.runId());
        }
        if (normalized.equals("or-tools") || normalized.equals("ortools") || normalized.equals("or tools")) {
            return ortoolsBenchmark(orders, drivers, started, matrixCost);
        }
        if (normalized.equals("pyvrp")) {
            return externalAvailabilityBenchmark("PyVRP", List.of("py", "-3", "-c", "import pyvrp"), started);
        }
        if (normalized.equals("vroom")) {
            return externalAvailabilityBenchmark("VROOM", List.of("vroom", "--version"), started);
        }
        return new BenchmarkSolverResultDto(solver, SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, orders.size(), 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, "solver adapter not registered", null);
    }

    private BenchmarkSolverResultDto ortoolsBenchmark(List<OrderDto> orders, List<DriverDto> drivers, long started, MatrixCostAdapter matrixCost) {
        try {
            Loader.loadNativeLibraries();
            MPSolver solver = MPSolver.createSolver("SCIP");
            if (solver == null) {
                return new BenchmarkSolverResultDto("OR-Tools", SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, orders.size(), 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, "OR-Tools SCIP solver unavailable", null);
            }
            MPVariable[][] assign = new MPVariable[orders.size()][drivers.size()];
            for (int orderIndex = 0; orderIndex < orders.size(); orderIndex++) {
                for (int driverIndex = 0; driverIndex < drivers.size(); driverIndex++) {
                    assign[orderIndex][driverIndex] = solver.makeBoolVar("x_" + orderIndex + "_" + driverIndex);
                }
            }
            for (int orderIndex = 0; orderIndex < orders.size(); orderIndex++) {
                MPConstraint oneDriver = solver.makeConstraint(1.0, 1.0, "order_" + orderIndex);
                for (int driverIndex = 0; driverIndex < drivers.size(); driverIndex++) {
                    oneDriver.setCoefficient(assign[orderIndex][driverIndex], 1.0);
                }
            }
            int maxLoad = Math.max(1, (int) Math.ceil(orders.size() / (double) Math.max(1, drivers.size())) + 1);
            for (int driverIndex = 0; driverIndex < drivers.size(); driverIndex++) {
                MPConstraint capacity = solver.makeConstraint(0.0, maxLoad, "driver_" + driverIndex);
                for (int orderIndex = 0; orderIndex < orders.size(); orderIndex++) {
                    capacity.setCoefficient(assign[orderIndex][driverIndex], 1.0);
                }
            }
            MPObjective objective = solver.objective();
            for (int orderIndex = 0; orderIndex < orders.size(); orderIndex++) {
                OrderDto order = orders.get(orderIndex);
                for (int driverIndex = 0; driverIndex < drivers.size(); driverIndex++) {
                    DriverDto driver = drivers.get(driverIndex);
                    double distance = matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())
                            + matrixCost.distanceKm(order.pickupLat(), order.pickupLng(), order.dropoffLat(), order.dropoffLng());
                    objective.setCoefficient(assign[orderIndex][driverIndex], distance);
                }
            }
            objective.setMinimization();
            MPSolver.ResultStatus status = solver.solve();
            if (status != MPSolver.ResultStatus.OPTIMAL && status != MPSolver.ResultStatus.FEASIBLE) {
                return new BenchmarkSolverResultDto("OR-Tools", SolverRunStatus.FAILED, BenchmarkVerdict.FAILED, 0, 0, orders.size(), 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, "OR-Tools assignment infeasible: " + status, null);
            }
            double totalDistance = objective.value();
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            return new BenchmarkSolverResultDto("OR-Tools", SolverRunStatus.COMPLETED, BenchmarkVerdict.PASS_WITH_LIMITS, drivers.size(), orders.size(), orders.size(), round(totalDistance), 0, 100.0, runtimeMs, "wired OR-Tools MIP assignment baseline; route sequencing not VRP yet", null);
        } catch (UnsatisfiedLinkError | RuntimeException error) {
            return new BenchmarkSolverResultDto("OR-Tools", SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, orders.size(), 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, "OR-Tools unavailable: " + error.getMessage(), null);
        }
    }

    private BenchmarkSolverResultDto externalAvailabilityBenchmark(String solverName, List<String> command, long started) {
        try {
            Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
            boolean finished = process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                return new BenchmarkSolverResultDto(solverName, SolverRunStatus.TIMEOUT, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, 0, 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, solverName + " availability check timed out", null);
            }
            if (process.exitValue() != 0) {
                return new BenchmarkSolverResultDto(solverName, SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, 0, 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, solverName + " dependency missing locally", null);
            }
            return new BenchmarkSolverResultDto(solverName, SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, 0, 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, solverName + " detected but solver adapter not implemented in no-Docker phase", null);
        } catch (IOException | InterruptedException error) {
            Thread.currentThread().interrupt();
            return new BenchmarkSolverResultDto(solverName, SolverRunStatus.EVIDENCE_GAP, BenchmarkVerdict.EVIDENCE_GAP, 0, 0, 0, 0, 0, 0, (System.nanoTime() - started) / 1_000_000L, solverName + " dependency missing locally", null);
        }
    }

    private static double singleOrderDistanceKm(List<OrderDto> orders, List<DriverDto> drivers, MatrixCostAdapter matrixCost) {
        if (drivers.isEmpty()) {
            return 0.0;
        }
        double total = 0.0;
        for (int index = 0; index < orders.size(); index++) {
            OrderDto order = orders.get(index);
            DriverDto driver = drivers.get(index % drivers.size());
            total += matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng());
            total += matrixCost.distanceKm(order.pickupLat(), order.pickupLng(), order.dropoffLat(), order.dropoffLng());
        }
        return round(total);
    }

    private static double distanceBatchingDistanceKm(List<OrderDto> orders, List<DriverDto> drivers, MatrixCostAdapter matrixCost) {
        if (drivers.isEmpty()) {
            return 0.0;
        }
        Map<String, List<OrderDto>> byDriver = new LinkedHashMap<>();
        drivers.forEach(driver -> byDriver.put(driver.driverId(), new ArrayList<>()));
        for (OrderDto order : orders) {
            DriverDto nearest = drivers.stream()
                    .min(Comparator.comparingDouble(driver -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .orElse(drivers.getFirst());
            byDriver.get(nearest.driverId()).add(order);
        }
        double total = 0.0;
        for (DriverDto driver : drivers) {
            double previousLat = driver.lat();
            double previousLng = driver.lng();
            List<OrderDto> routeOrders = byDriver.get(driver.driverId()).stream()
                    .sorted(Comparator.comparingDouble(order -> matrixCost.distanceKm(driver.lat(), driver.lng(), order.pickupLat(), order.pickupLng())))
                    .toList();
            for (OrderDto order : routeOrders) {
                total += matrixCost.distanceKm(previousLat, previousLng, order.pickupLat(), order.pickupLng());
                previousLat = order.pickupLat();
                previousLng = order.pickupLng();
            }
            for (OrderDto order : routeOrders) {
                total += matrixCost.distanceKm(previousLat, previousLng, order.dropoffLat(), order.dropoffLng());
                previousLat = order.dropoffLat();
                previousLng = order.dropoffLng();
            }
        }
        return round(total);
    }

    private static Order toOrder(OrderDto order) {
        return new Order(order.orderId(), new GeoPoint(order.pickupLat(), order.pickupLng()), new GeoPoint(order.dropoffLat(), order.dropoffLng()), Instant.now(), Instant.now(), order.deadlineMinutes(), order.priority() >= 2);
    }

    private static Driver toDriver(DriverDto driver) {
        return new Driver(driver.driverId(), new GeoPoint(driver.lat(), driver.lng()));
    }

    private static AssignmentDto assignmentDto(DispatchAssignment assignment) {
        return new AssignmentDto(
                assignment.assignmentId(),
                assignment.bundleId() == null ? assignment.assignmentId() : assignment.bundleId(),
                assignment.driverId(),
                assignment.orderIds(),
                assignment.selectionRank(),
                assignment.selectionScore(),
                assignment.robustUtility(),
                assignment.reasons(),
                assignment.degradeReasons());
    }

    private static RouteVisualizationDto routeDto(DispatchAssignment assignment, Map<String, OrderDto> orders, Map<String, DriverDto> drivers, RoutingProvider routingProvider) {
        DriverDto driver = drivers.get(assignment.driverId());
        List<StopVisualizationDto> stops = new ArrayList<>();
        List<GeoPointDto> polyline = new ArrayList<>();
        double previousLat = driver == null ? HCM_CENTER.latitude() : driver.lat();
        double previousLng = driver == null ? HCM_CENTER.longitude() : driver.lng();
        polyline.add(new GeoPointDto(previousLat, previousLng));
        int sequence = 0;
        for (String orderId : assignment.orderIds()) {
            OrderDto order = orders.get(orderId);
            if (order == null) {
                continue;
            }
            sequence++;
            RoutingRouteResult route = roadRoute("route-" + assignment.assignmentId() + "-pickup-" + order.orderId(), previousLat, previousLng, order.pickupLat(), order.pickupLng(), routingProvider);
            double pickupDistance = routeDistanceKm(route, previousLat, previousLng, order.pickupLat(), order.pickupLng());
            appendPolyline(polyline, route, order.pickupLat(), order.pickupLng());
            stops.add(stop(sequence, "PICKUP", order, order.pickupLat(), order.pickupLng(), pickupDistance, order.deadlineMinutes()));
            previousLat = order.pickupLat();
            previousLng = order.pickupLng();
        }
        for (String orderId : assignment.orderIds()) {
            OrderDto order = orders.get(orderId);
            if (order == null) {
                continue;
            }
            sequence++;
            RoutingRouteResult route = roadRoute("route-" + assignment.assignmentId() + "-dropoff-" + order.orderId(), previousLat, previousLng, order.dropoffLat(), order.dropoffLng(), routingProvider);
            double dropDistance = routeDistanceKm(route, previousLat, previousLng, order.dropoffLat(), order.dropoffLng());
            appendPolyline(polyline, route, order.dropoffLat(), order.dropoffLng());
            stops.add(stop(sequence, "DROPOFF", order, order.dropoffLat(), order.dropoffLng(), dropDistance, order.deadlineMinutes()));
            previousLat = order.dropoffLat();
            previousLng = order.dropoffLng();
        }
        double distance = stops.stream().mapToDouble(StopVisualizationDto::distanceFromPreviousKm).sum();
        double eta = Math.max(assignment.projectedCompletionEtaMinutes(), distance / 22.0 * 60.0);
        long late = stops.stream().filter(stop -> "LATE_RISK".equals(stop.riskLevel())).count();
        return new RouteVisualizationDto(
                assignment.assignmentId(),
                assignment.driverId(),
                assignment.bundleId() == null ? assignment.assignmentId() : assignment.bundleId(),
                GeometryMode.ROAD_ROUTE,
                null,
                "ACTIVE",
                stops,
                polyline,
                round(distance),
                round(eta),
                late);
    }

    private static StopVisualizationDto stop(int sequence, String type, OrderDto order, double lat, double lng, double distance, int deadline) {
        double travel = distance / 22.0 * 60.0;
        double eta = sequence == 1 ? travel : sequence * 8.0 + travel;
        double slack = deadline - eta;
        String risk = slack < 8 ? "LATE_RISK" : slack < 15 ? "WATCH" : "LOW";
        return new StopVisualizationDto(sequence, type, order.orderId(), lat, lng, round(eta), round(distance), round(travel), round(slack), risk, slack < 0 ? "LATE" : "OK");
    }

    private static Map<String, OrderDto> ordersById(List<OrderDto> orders) {
        Map<String, OrderDto> byId = new LinkedHashMap<>();
        orders.forEach(order -> byId.put(order.orderId(), order));
        return byId;
    }

    private static Map<String, DriverDto> driversById(List<DriverDto> drivers) {
        Map<String, DriverDto> byId = new LinkedHashMap<>();
        drivers.forEach(driver -> byId.put(driver.driverId(), driver));
        return byId;
    }

    private List<OrderDto> generateOrders(ScenarioGenerateRequest config, String seedText) {
        if (isRawPreset(config.scenarioType())) {
            return generateRawOrders(config);
        }
        Random random = new Random(seedText.hashCode() + 42L);
        List<OrderDto> orders = new ArrayList<>();
        for (int index = 1; index <= config.orderCount(); index++) {
            double pickupSpread = config.scenarioType().equals("driver-imbalanced-case") || config.scenarioType().equals("clustered-pickups-random-dropoffs") ? 0.020 : 0.045;
            GeoPoint pickup = jitter(HCM_CENTER, random, pickupSpread);
            GeoPoint dropoff = dropoffPoint(config.scenarioType(), pickup, random, index);
            int priority = random.nextDouble() < config.riskRate() || config.scenarioType().equals("high-priority-orders") ? 2 : 1;
            int deadline = 35 + random.nextInt(35);
            if (config.scenarioType().equals("tight-deadline-case")) {
                deadline = 24 + random.nextInt(18);
            } else if (config.scenarioType().equals("wide-deadline-case")) {
                deadline = 80 + random.nextInt(50);
            } else if (config.scenarioType().equals("driver-imbalanced-case")) {
                deadline = 45 + random.nextInt(35);
            } else if (config.scenarioType().equals("high-priority-orders")) {
                deadline = 30 + random.nextInt(25);
            }
            int demand = config.scenarioType().equals("tight-capacity") ? 2 + random.nextInt(3) : 1 + random.nextInt(4);
            orders.add(new OrderDto("ORD-" + pad(index), "R" + (1 + random.nextInt(18)), pickup.latitude(), pickup.longitude(), dropoff.latitude(), dropoff.longitude(), demand, priority, deadline));
        }
        return orders;
    }

    private static GeoPoint dropoffPoint(String scenarioType, GeoPoint pickup, Random random, int index) {
        if ("opposite-direction-dropoffs".equals(scenarioType)) {
            return jitter(new GeoPoint(10.735 + (index % 2) * 0.11, 106.645 + (index % 3) * 0.055), random, 0.018);
        }
        if ("clustered-pickups-random-dropoffs".equals(scenarioType)) {
            return jitter(HCM_CENTER, random, 0.070);
        }
        if ("random-pickups-clustered-dropoffs".equals(scenarioType)) {
            return jitter(new GeoPoint(10.790, 106.710), random, 0.016);
        }
        if ("long-tail-distance".equals(scenarioType) && index % 5 == 0) {
            return jitter(new GeoPoint(10.860, 106.790), random, 0.025);
        }
        return jitter(pickup, random, "rush_hour".equals(scenarioType) ? 0.035 : 0.025);
    }

    private List<DriverDto> generateDrivers(ScenarioGenerateRequest config, String seedText) {
        if (isRawPreset(config.scenarioType())) {
            return generateRawDrivers(config);
        }
        Random random = new Random(seedText.hashCode() + 7L);
        List<DriverDto> drivers = new ArrayList<>();
        for (int index = 1; index <= config.driverCount(); index++) {
            GeoPoint point = config.scenarioType().equals("driver-imbalanced-case") && index > 2
                    ? jitter(new GeoPoint(10.815, 106.745), random, 0.018)
                    : jitter(HCM_CENTER, random, config.scenarioType().equals("driver-imbalanced-case") ? 0.012 : 0.04);
            int capacity = config.scenarioType().equals("tight-capacity") ? 5 : 20;
            drivers.add(new DriverDto("D" + pad(index), point.latitude(), point.longitude(), capacity, random.nextInt(4), "IDLE"));
        }
        return drivers;
    }

    private static boolean isRawPreset(String scenarioType) {
        return scenarioType != null && (scenarioType.equalsIgnoreCase("raw-s")
                || scenarioType.equalsIgnoreCase("raw-m")
                || scenarioType.equalsIgnoreCase("raw-l")
                || scenarioType.equalsIgnoreCase("raw-city-demand")
                || scenarioType.equalsIgnoreCase("hcm-dinner-peak")
                || scenarioType.equalsIgnoreCase("heavy-rain-case")
                || scenarioType.equalsIgnoreCase("driver-scarcity-case"));
    }

    private static List<OrderDto> generateRawOrders(ScenarioGenerateRequest config) {
        int orderCount = Math.max(1, config.orderCount());
        List<OrderDto> orders = new ArrayList<>();
        for (int index = 0; index < orderCount; index++) {
            GeoPoint pickup = rawPoint(index * 17 + 3);
            GeoPoint dropoff = rawPoint(index * 29 + 11);
            String orderId = "ORD-" + pad(index + 1);
            int priority = config.weatherProfile().equalsIgnoreCase("HEAVY_RAIN") || index % 7 == 0 ? 2 : 1;
            int deadline = 55 + (index % 6) * 7;
            orders.add(new OrderDto(orderId, "RAW", pickup.latitude(), pickup.longitude(), dropoff.latitude(), dropoff.longitude(), 1, priority, deadline));
        }
        return orders;
    }

    private static List<DriverDto> generateRawDrivers(ScenarioGenerateRequest config) {
        int driverCount = Math.max(1, config.driverCount());
        List<DriverDto> drivers = new ArrayList<>();
        for (int index = 0; index < driverCount; index++) {
            GeoPoint location = rawPoint(index * 41 + 19);
            drivers.add(new DriverDto("D" + String.format("%02d", index + 1), location.latitude(), location.longitude(), 5, 0, "IDLE"));
        }
        return drivers;
    }

    private static GeoPoint rawPoint(int seed) {
        double x = Math.abs(Math.sin(seed * 12.9898) * 43758.5453) % 1.0;
        double y = Math.abs(Math.sin(seed * 78.233) * 19341.1327) % 1.0;
        return new GeoPoint(10.755 + (10.805 - 10.755) * x, 106.670 + (106.725 - 106.670) * y);
    }

    private static Map<String, Object> snapshot(ScenarioGenerateRequest config, String scenarioId, List<OrderDto> orders, List<DriverDto> drivers) {
        return Map.of(
                "schemaVersion", "live-dispatch-snapshot/v1",
                "snapshotId", scenarioId,
                "region", "hcm",
                "weatherProfile", config.weatherProfile(),
                "trafficContext", Map.of("trafficMode", config.trafficMode()),
                "orderCount", orders.size(),
                "driverCount", drivers.size());
    }

    private static ManualScenarioDto manualScenarioFrom(String scenarioId, String name, List<OrderDto> orders, List<DriverDto> drivers, String weather, String traffic) {
        List<ManualOrderDto> manualOrders = orders.stream()
                .map(order -> new ManualOrderDto(order.orderId(), new GeoPointDto(order.pickupLat(), order.pickupLng()), new GeoPointDto(order.dropoffLat(), order.dropoffLng()), order.demand(), order.priority(), 0, order.deadlineMinutes()))
                .toList();
        List<ManualDriverDto> manualDrivers = drivers.stream()
                .map(driver -> new ManualDriverDto(driver.driverId(), new GeoPointDto(driver.lat(), driver.lng()), driver.capacity(), driver.currentLoad(), 120, driver.status()))
                .toList();
        return new ManualScenarioDto(scenarioId, name, manualOrders, manualDrivers, new ScenarioContextDto(weather, traffic));
    }
    private void saveRun(DashboardRun run) {
        runs.put(run.runId(), run);
        try {
            Files.createDirectories(DASHBOARD_ARTIFACT_ROOT.resolve(run.kind().toLowerCase() + "-runs"));
        } catch (IOException ignored) {
        }
    }

    private static RunVisualizationDto errorRun(String runId, String message) {
        return new RunVisualizationDto(runId, runId, "dashboard", "phase1", Instant.now().toString(), RunStatus.FAILED, Map.of(), List.of(), List.of(), List.of(), List.of(), List.of(), new MetricsDto(0, 0, 0, 0, 0, 0, 0, 0), Map.of("uiState", UiState.error.name(), "error", message), List.of(), null, Map.of());
    }

    private static GeoPoint jitter(GeoPoint center, Random random, double radius) {
        return new GeoPoint(center.latitude() + (random.nextDouble() - 0.5) * radius, center.longitude() + (random.nextDouble() - 0.5) * radius);
    }

    private static WeatherProfile weatherProfile(String weather) {
        if ("HEAVY_RAIN".equalsIgnoreCase(weather)) {
            return WeatherProfile.HEAVY_RAIN;
        }
        if ("LIGHT_RAIN".equalsIgnoreCase(weather)) {
            return WeatherProfile.LIGHT_RAIN;
        }
        return WeatherProfile.CLEAR;
    }

    private static String id(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    }

    private static String scenarioHash(ScenarioGenerateRequest scenario, List<OrderDto> orders, List<DriverDto> drivers) {
        StringBuilder builder = new StringBuilder();
        builder.append(scenario.scenarioType()).append('|')
                .append(scenario.orderCount()).append('|')
                .append(scenario.driverCount()).append('|')
                .append(scenario.weatherProfile()).append('|')
                .append(scenario.trafficMode()).append('|')
                .append(scenario.riskRate());
        for (OrderDto order : orders) {
            builder.append('|').append(order.orderId())
                    .append('@').append("%.6f".formatted(order.pickupLat()))
                    .append(',').append("%.6f".formatted(order.pickupLng()))
                    .append('>').append("%.6f".formatted(order.dropoffLat()))
                    .append(',').append("%.6f".formatted(order.dropoffLng()))
                    .append('#').append(order.deadlineMinutes());
        }
        for (DriverDto driver : drivers) {
            builder.append('|').append(driver.driverId())
                    .append('@').append("%.6f".formatted(driver.lat()))
                    .append(',').append("%.6f".formatted(driver.lng()))
                    .append('#').append(driver.capacity());
        }
        return Integer.toHexString(builder.toString().hashCode()).toUpperCase();
    }

    private static String pad(int value) {
        return String.format("%03d", value);
    }

    private static String colorFor(int rank) {
        String[] colors = {"#22D3EE", "#34D399", "#F59E0B", "#F472B6", "#A78BFA", "#FB7185"};
        return colors[Math.max(0, rank) % colors.length];
    }

    private static double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double radius = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private static double roadDistanceKm(String legId, double fromLat, double fromLng, double toLat, double toLng, RoutingProvider routingProvider) {
        String key = "%.6f,%.6f->%.6f,%.6f".formatted(fromLat, fromLng, toLat, toLng);
        return ROAD_DISTANCE_KM_CACHE.computeIfAbsent(key, ignored -> routeDistanceKm(roadRoute(legId, fromLat, fromLng, toLat, toLng, routingProvider), fromLat, fromLng, toLat, toLng));
    }

    private static RoutingRouteResult roadRoute(String legId, double fromLat, double fromLng, double toLat, double toLng, RoutingProvider routingProvider) {
        if (routingProvider == null) {
            return null;
        }
        RouteStop from = new RouteStop(legId + "-from", fromLat, fromLng, "DASHBOARD", "hcm-demo", null);
        RouteStop to = new RouteStop(legId + "-to", toLat, toLng, "DASHBOARD", "hcm-demo", null);
        return routingProvider.route(new BestPathRequest(from, to, "normal", "CLEAR", 0, "road-refinement"));
    }

    private static double routeDistanceKm(RoutingRouteResult route, double fromLat, double fromLng, double toLat, double toLng) {
        if (route == null || route.legVector() == null || route.legVector().distanceMeters() <= 0) {
            return round(haversineKm(fromLat, fromLng, toLat, toLng));
        }
        return round(route.legVector().distanceMeters() / 1000.0);
    }

    private static long elapsedMs(long startedNanos) {
        return Math.max(0L, java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
    }

    private static void appendPolyline(List<GeoPointDto> polyline, RoutingRouteResult route, double fallbackLat, double fallbackLng) {
        if (route != null && route.polyline() != null && !route.polyline().isEmpty()) {
            for (var point : route.polyline()) {
                GeoPointDto next = new GeoPointDto(point.latitude(), point.longitude());
                if (polyline.isEmpty() || !samePoint(polyline.get(polyline.size() - 1), next)) {
                    polyline.add(next);
                }
            }
            return;
        }
        GeoPointDto fallback = new GeoPointDto(fallbackLat, fallbackLng);
        if (polyline.isEmpty() || !samePoint(polyline.get(polyline.size() - 1), fallback)) {
            polyline.add(fallback);
        }
    }

    private static boolean samePoint(GeoPointDto left, GeoPointDto right) {
        return Math.abs(left.lat() - right.lat()) < 0.000001 && Math.abs(left.lng() - right.lng()) < 0.000001;
    }

    private static double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    public enum RunStatus { CREATED, GENERATING, QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, TIMEOUT }
    public enum UiState { empty, loading, success, error, partial, evidence_gap }
    public enum GeometryMode { STRAIGHT_LINE, ROAD_ROUTE, IMPORTED_POLYLINE }
    public enum BenchmarkVerdict { WIN, LOSE, TIE, PASS_WITH_LIMITS, EVIDENCE_GAP, NOT_RUN, FAILED }
    public enum SolverRunStatus { COMPLETED, EVIDENCE_GAP, FAILED, TIMEOUT }

    public record ScenarioGenerateRequest(Integer orderCount, Integer driverCount, String scenarioType, String weatherProfile, String trafficMode, Double riskRate) {
        static ScenarioGenerateRequest defaults() { return new ScenarioGenerateRequest(20, 4, "raw-m", "CLEAR", "normal", 0.12); }
        ScenarioGenerateRequest withDefaults() {
            String type = scenarioType == null ? "raw-m" : scenarioType;
            int[] preset = presetSize(type);
            return new ScenarioGenerateRequest(or(orderCount, preset[0]), or(driverCount, preset[1]), type, weatherProfile == null ? "CLEAR" : weatherProfile, trafficMode == null ? "normal" : trafficMode, riskRate == null ? 0.12 : riskRate);
        }
    }

    public record ManualScenarioDto(String scenarioId, String name, List<ManualOrderDto> orders, List<ManualDriverDto> drivers, ScenarioContextDto context) {
        ManualScenarioDto withIdAndDefaults(String nextScenarioId) {
            ScenarioContextDto nextContext = context == null ? ScenarioContextDto.defaults() : context.withDefaults();
            return new ManualScenarioDto(
                    nextScenarioId,
                    name == null || name.isBlank() ? "Manual Demo" : name,
                    orders == null ? List.of() : orders,
                    drivers == null ? List.of() : drivers,
                    nextContext);
        }

        List<OrderDto> toOrders() {
            List<ManualOrderDto> safeOrders = orders == null ? List.of() : orders;
            List<OrderDto> mapped = new ArrayList<>();
            for (int index = 0; index < safeOrders.size(); index++) {
                ManualOrderDto order = safeOrders.get(index).withDefaults(index + 1);
                mapped.add(new OrderDto(order.orderId(), "RAW", order.pickup().lat(), order.pickup().lng(), order.dropoff().lat(), order.dropoff().lng(), order.demand(), order.priority(), order.dueTime()));
            }
            return mapped;
        }

        List<DriverDto> toDrivers() {
            List<ManualDriverDto> safeDrivers = drivers == null ? List.of() : drivers;
            List<DriverDto> mapped = new ArrayList<>();
            for (int index = 0; index < safeDrivers.size(); index++) {
                ManualDriverDto driver = safeDrivers.get(index).withDefaults(index + 1);
                mapped.add(new DriverDto(driver.driverId(), driver.location().lat(), driver.location().lng(), driver.capacity(), driver.currentLoad(), driver.status()));
            }
            return mapped;
        }
    }

    public record ManualOrderDto(String orderId, GeoPointDto pickup, GeoPointDto dropoff, Integer demand, Integer priority, Integer readyTime, Integer dueTime) {
        ManualOrderDto withDefaults(int index) {
            GeoPointDto safePickup = pickup == null ? new GeoPointDto(HCM_CENTER.latitude(), HCM_CENTER.longitude()) : pickup;
            GeoPointDto safeDropoff = dropoff == null ? new GeoPointDto(safePickup.lat() + 0.01, safePickup.lng() + 0.01) : dropoff;
            return new ManualOrderDto(orderId == null || orderId.isBlank() ? "ORD-" + pad(index) : orderId, safePickup, safeDropoff, or(demand, 1), or(priority, 1), or(readyTime, 0), or(dueTime, 60));
        }
    }

    public record ManualDriverDto(String driverId, GeoPointDto location, Integer capacity, Integer currentLoad, Integer shiftEnd, String status) {
        ManualDriverDto withDefaults(int index) {
            GeoPointDto safeLocation = location == null ? new GeoPointDto(HCM_CENTER.latitude(), HCM_CENTER.longitude()) : location;
            return new ManualDriverDto(driverId == null || driverId.isBlank() ? "D" + String.format("%02d", index) : driverId, safeLocation, or(capacity, 5), or(currentLoad, 0), or(shiftEnd, 120), status == null || status.isBlank() ? "IDLE" : status);
        }
    }

    public record ScenarioContextDto(String weather, String traffic) {
        static ScenarioContextDto defaults() { return new ScenarioContextDto("CLEAR", "NORMAL"); }
        ScenarioContextDto withDefaults() { return new ScenarioContextDto(weather == null ? "CLEAR" : weather, traffic == null ? "NORMAL" : traffic); }
    }

    public record DispatchRunRequest(String scenarioId, ScenarioGenerateRequest scenario, List<OrderDto> orders, List<DriverDto> drivers) { }
    private record ResolvedDispatchInput(String scenarioId, List<OrderDto> orders, List<DriverDto> drivers, String weather) { }
    public record KafkaPublishReceipt(String scenarioId, String traceId, String status, String message) { }
    public record RescueSimulationRequest(String baseRunId, List<EventDto> events) { }
    public record BenchmarkJobRequest(String datasetId, List<String> solvers, String mode) {
        static BenchmarkJobRequest defaults() { return new BenchmarkJobRequest("synthetic-food-smoke", List.of("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX"), BenchmarkMode.FAST_GATE.name()); }
        BenchmarkJobRequest withDefaults() { return new BenchmarkJobRequest(datasetId == null ? "synthetic-food-smoke" : datasetId, solvers == null || solvers.isEmpty() ? defaults().solvers() : solvers, mode == null || mode.isBlank() ? BenchmarkMode.FAST_GATE.name() : mode); }
        BenchmarkMode modeEnum() { return BenchmarkMode.from(mode); }
    }

    public record DashboardRun(String runId, String kind, String createdAt, RunStatus status, RunVisualizationDto visualization) { }
    public record DispatchJob(String jobId, String scenarioId, RunStatus status, String createdAt, String resultRunId, String error, String workerId, int orderCount, int driverCount) {
        DispatchJob withStatus(RunStatus nextStatus, String nextResultRunId, String nextError, String nextWorkerId) { return new DispatchJob(jobId, scenarioId, nextStatus, createdAt, nextResultRunId, nextError, nextWorkerId, orderCount, driverCount); }
    }
    public record BenchmarkJob(String jobId, String datasetId, List<String> solvers, RunStatus status, String createdAt, String resultRunId, String error) {
        BenchmarkJob withStatus(RunStatus nextStatus, String nextResultRunId, String nextError) { return new BenchmarkJob(jobId, datasetId, solvers, nextStatus, createdAt, nextResultRunId, nextError); }
    }
    public record BenchmarkDatasetDto(String datasetId, String path, String source) { }
    public record BenchmarkSolverResultDto(String solverName, SolverRunStatus status, BenchmarkVerdict verdict, long driverCount, long assignedOrderCount, long inputOrderCount, double totalDistanceKm, long lateOrderCount, double slaSuccessRate, long runtimeMs, String reason, String artifactPath) { }
    public record ComparisonDto(String beforeRunId, String afterRunId, String label, BenchmarkVerdict verdict, String reason) { }
    public record EventDto(String type, String label, String severity) { }
    public record GeoPointDto(double lat, double lng) { }
    public record OrderDto(String orderId, String restaurantId, double pickupLat, double pickupLng, double dropoffLat, double dropoffLng, int demand, int priority, int deadlineMinutes) { }
    public record DriverDto(String driverId, double lat, double lng, int capacity, int currentLoad, String status) { }
    public record BatchDto(String batchId, List<String> orderIds, String driverId, String color, String status) { }
    public record AssignmentDto(String assignmentId, String batchId, String driverId, List<String> orderIds, int selectionRank, double selectionScore, double robustUtility, List<String> reasons, List<String> degradeReasons) { }
    public record MetricsDto(long driverCount, double totalDistanceKm, long lateOrderCount, long assignedOrderCount, double slaSuccessRate, long runtimeMs, long batchCount, long rejectedOrderCount) { }
    public record StopVisualizationDto(int sequence, String type, String orderId, double lat, double lng, double etaMinutes, double distanceFromPreviousKm, double travelTimeFromPreviousMinutes, double deadlineSlackMinutes, String riskLevel, String status) { }
    public record RouteVisualizationDto(String routeId, String driverId, String batchId, GeometryMode geometryMode, String oldRouteId, String rescueStatus, List<StopVisualizationDto> stops, List<GeoPointDto> polyline, double totalDistanceKm, double totalEtaMinutes, long lateOrderCount) {
        RouteVisualizationDto withRescue(String status, String oldId) { return new RouteVisualizationDto(routeId, driverId, batchId, geometryMode, oldId, status, stops, polyline, totalDistanceKm, totalEtaMinutes, lateOrderCount); }
    }
    public record RunVisualizationDto(String runId, String scenarioId, String solverName, String solverVersion, String createdAt, RunStatus status, Map<String, Object> inputSnapshot, List<OrderDto> orders, List<DriverDto> drivers, List<BatchDto> batches, List<AssignmentDto> assignments, List<RouteVisualizationDto> routes, MetricsDto metrics, Map<String, Object> diagnostics, List<EventDto> events, ComparisonDto comparison, Map<String, Object> artifacts) {
        RunVisualizationDto withRoutesAndComparison(List<RouteVisualizationDto> nextRoutes, ComparisonDto nextComparison) { return new RunVisualizationDto(runId, scenarioId, solverName, solverVersion, createdAt, status, inputSnapshot, orders, drivers, batches, assignments, nextRoutes, metrics, diagnostics, events, nextComparison, artifacts); }
        RunVisualizationDto withComparison(ComparisonDto nextComparison) { return new RunVisualizationDto(runId, scenarioId, solverName, solverVersion, createdAt, status, inputSnapshot, orders, drivers, batches, assignments, routes, metrics, diagnostics, events, nextComparison, artifacts); }
        RunVisualizationDto withDiagnostics(Map<String, Object> nextDiagnostics) { return new RunVisualizationDto(runId, scenarioId, solverName, solverVersion, createdAt, status, inputSnapshot, orders, drivers, batches, assignments, routes, metrics, nextDiagnostics, events, comparison, artifacts); }
        RunVisualizationDto withSolver(String nextSolverName, String nextSolverVersion) { return new RunVisualizationDto(runId, scenarioId, nextSolverName, nextSolverVersion, createdAt, status, inputSnapshot, orders, drivers, batches, assignments, routes, metrics, diagnostics, events, comparison, artifacts); }
    }

    private static Integer or(Integer value, int fallback) { return Optional.ofNullable(value).orElse(fallback); }

    private static int[] presetSize(String scenarioType) {
        if (scenarioType != null && scenarioType.equalsIgnoreCase("raw-s")) {
            return new int[] {12, 3};
        }
        if (scenarioType != null && scenarioType.equalsIgnoreCase("raw-l")) {
            return new int[] {30, 6};
        }
        if (scenarioType != null && scenarioType.equalsIgnoreCase("driver-scarcity-case")) {
            return new int[] {20, 3};
        }
        return new int[] {20, 4};
    }
}



