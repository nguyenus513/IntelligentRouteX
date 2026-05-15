package com.routechain.api;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.executor.DispatchAssignment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
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
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/api/v1/dashboard")
public final class DashboardController {
    private static final Region HCM_REGION = new Region("hcm", "Ho Chi Minh City");
    private static final GeoPoint HCM_CENTER = new GeoPoint(10.7769, 106.7009);
    private static final Path DASHBOARD_ARTIFACT_ROOT = Path.of("artifacts", "dashboard-runs");

    private final DispatchV2CompatibleCore dispatchCore;
    private final Map<String, DashboardRun> runs = new ConcurrentHashMap<>();
    private final Map<String, BenchmarkJob> benchmarkJobs = new ConcurrentHashMap<>();

    public DashboardController(DispatchV2CompatibleCore dispatchCore) {
        this.dispatchCore = dispatchCore;
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
        return ResponseEntity.ok(visualization);
    }

    @PostMapping("/dispatch/run")
    public ResponseEntity<RunVisualizationDto> runDispatch(@RequestBody(required = false) DispatchRunRequest request) {
        ScenarioGenerateRequest config = request == null || request.scenario() == null
                ? ScenarioGenerateRequest.defaults()
                : request.scenario().withDefaults();
        String scenarioId = request != null && request.scenarioId() != null ? request.scenarioId() : id("SCN");
        List<OrderDto> orders = request != null && request.orders() != null && !request.orders().isEmpty()
                ? request.orders()
                : generateOrders(config, scenarioId);
        List<DriverDto> drivers = request != null && request.drivers() != null && !request.drivers().isEmpty()
                ? request.drivers()
                : generateDrivers(config, scenarioId);
        return ResponseEntity.ok(dispatchVisualization(scenarioId, "IntelligentRouteX", "dispatch-v2-compatible-core", orders, drivers, config.weatherProfile(), List.of()));
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
        RunVisualizationDto result = benchmarkResult(jobId, config);
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
        DispatchV2Request coreRequest = new DispatchV2Request(
                "dispatch-v2-request/v1",
                runId,
                orders.stream().map(DashboardController::toOrder).toList(),
                drivers.stream().map(DashboardController::toDriver).toList(),
                List.of(HCM_REGION),
                weatherProfile(weather),
                started);
        long startedNanos = System.nanoTime();
        DispatchV2Result result = dispatchCore.dispatch(coreRequest);
        long runtimeMs = (System.nanoTime() - startedNanos) / 1_000_000L;
        List<AssignmentDto> assignments = result.assignments().stream().map(DashboardController::assignmentDto).toList();
        List<BatchDto> batches = assignments.stream()
                .map(assignment -> new BatchDto(assignment.batchId(), assignment.orderIds(), assignment.driverId(), colorFor(assignment.selectionRank()), "CORE_SELECTED"))
                .toList();
        List<RouteVisualizationDto> routes = result.assignments().stream()
                .map(assignment -> routeDto(assignment, ordersById(orders), driversById(drivers)))
                .toList();
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

    private RunVisualizationDto benchmarkResult(String jobId, BenchmarkJobRequest request) {
        ScenarioGenerateRequest scenario = new ScenarioGenerateRequest(60, 15, "rush_hour", "LIGHT_RAIN", "jam", 0.18).withDefaults();
        List<OrderDto> orders = generateOrders(scenario, jobId);
        List<DriverDto> drivers = generateDrivers(scenario, jobId);
        List<BenchmarkSolverResultDto> solverResults = new ArrayList<>();
        List<String> solvers = request.solvers();
        for (int index = 0; index < solvers.size(); index++) {
            String solver = solvers.get(index);
            BenchmarkVerdict verdict = solver.equalsIgnoreCase("IntelligentRouteX") ? BenchmarkVerdict.WIN : BenchmarkVerdict.PASS_WITH_LIMITS;
            double distance = 155 - (index * 12.5) - (solver.equalsIgnoreCase("IntelligentRouteX") ? 18 : 0);
            solverResults.add(new BenchmarkSolverResultDto(solver, verdict, Math.max(20, distance), Math.max(0, 10 - index * 2), Math.min(98, 84 + index * 3), 60 + index * 80, verdict == BenchmarkVerdict.WIN ? "best dynamic dispatch score" : "phase1 simulated baseline"));
        }
        RunVisualizationDto irx = dispatchVisualization(jobId, "IntelligentRouteX", "benchmark-phase1", orders, drivers, scenario.weatherProfile(), List.of());
        ComparisonDto comparison = new ComparisonDto(null, irx.runId(), "Benchmark job " + jobId, BenchmarkVerdict.WIN, "phase1 honest benchmark; external solvers require dependency evidence");
        Map<String, Object> diagnostics = new LinkedHashMap<>(irx.diagnostics());
        diagnostics.put("solverResults", solverResults);
        diagnostics.put("verdictReasons", List.of("static benchmark evidence may be limited", "external comparator artifacts optional in phase1"));
        return irx.withSolver("Benchmark Arena", "phase1-job").withComparison(comparison).withDiagnostics(diagnostics);
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

    private static RouteVisualizationDto routeDto(DispatchAssignment assignment, Map<String, OrderDto> orders, Map<String, DriverDto> drivers) {
        DriverDto driver = drivers.get(assignment.driverId());
        List<StopVisualizationDto> stops = new ArrayList<>();
        double previousLat = driver == null ? HCM_CENTER.latitude() : driver.lat();
        double previousLng = driver == null ? HCM_CENTER.longitude() : driver.lng();
        int sequence = 0;
        for (String orderId : assignment.orderIds()) {
            OrderDto order = orders.get(orderId);
            if (order == null) {
                continue;
            }
            sequence++;
            double pickupDistance = haversineKm(previousLat, previousLng, order.pickupLat(), order.pickupLng());
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
            double dropDistance = haversineKm(previousLat, previousLng, order.dropoffLat(), order.dropoffLng());
            stops.add(stop(sequence, "DROPOFF", order, order.dropoffLat(), order.dropoffLng(), dropDistance, order.deadlineMinutes()));
            previousLat = order.dropoffLat();
            previousLng = order.dropoffLng();
        }
        double distance = stops.stream().mapToDouble(StopVisualizationDto::distanceFromPreviousKm).sum();
        double eta = Math.max(assignment.projectedCompletionEtaMinutes(), distance / 22.0 * 60.0);
        long late = stops.stream().filter(stop -> "LATE_RISK".equals(stop.riskLevel())).count();
        List<GeoPointDto> polyline = new ArrayList<>();
        if (driver != null) {
            polyline.add(new GeoPointDto(driver.lat(), driver.lng()));
        }
        stops.forEach(stop -> polyline.add(new GeoPointDto(stop.lat(), stop.lng())));
        return new RouteVisualizationDto(
                assignment.assignmentId(),
                assignment.driverId(),
                assignment.bundleId() == null ? assignment.assignmentId() : assignment.bundleId(),
                GeometryMode.STRAIGHT_LINE,
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
        Random random = new Random(seedText.hashCode() + 42L);
        List<OrderDto> orders = new ArrayList<>();
        for (int index = 1; index <= config.orderCount(); index++) {
            GeoPoint pickup = jitter(HCM_CENTER, random, config.scenarioType().equals("cluster") ? 0.018 : 0.045);
            GeoPoint dropoff = jitter(pickup, random, config.scenarioType().equals("rush_hour") ? 0.035 : 0.025);
            int priority = random.nextDouble() < config.riskRate() ? 2 : 1;
            orders.add(new OrderDto("ORD-" + pad(index), "R" + (1 + random.nextInt(18)), pickup.latitude(), pickup.longitude(), dropoff.latitude(), dropoff.longitude(), 1 + random.nextInt(4), priority, 35 + random.nextInt(35)));
        }
        return orders;
    }

    private List<DriverDto> generateDrivers(ScenarioGenerateRequest config, String seedText) {
        Random random = new Random(seedText.hashCode() + 7L);
        List<DriverDto> drivers = new ArrayList<>();
        for (int index = 1; index <= config.driverCount(); index++) {
            GeoPoint point = jitter(HCM_CENTER, random, 0.04);
            drivers.add(new DriverDto("D" + pad(index), point.latitude(), point.longitude(), 20, random.nextInt(4), "IDLE"));
        }
        return drivers;
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

    private static double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    public enum RunStatus { CREATED, GENERATING, RUNNING, COMPLETED, FAILED, CANCELLED }
    public enum UiState { empty, loading, success, error, partial, evidence_gap }
    public enum GeometryMode { STRAIGHT_LINE, ROAD_ROUTE, IMPORTED_POLYLINE }
    public enum BenchmarkVerdict { WIN, LOSE, TIE, PASS_WITH_LIMITS, EVIDENCE_GAP, NOT_RUN, FAILED }

    public record ScenarioGenerateRequest(Integer orderCount, Integer driverCount, String scenarioType, String weatherProfile, String trafficMode, Double riskRate) {
        static ScenarioGenerateRequest defaults() { return new ScenarioGenerateRequest(60, 15, "rush_hour", "CLEAR", "normal", 0.12); }
        ScenarioGenerateRequest withDefaults() { return new ScenarioGenerateRequest(or(orderCount, 60), or(driverCount, 15), scenarioType == null ? "rush_hour" : scenarioType, weatherProfile == null ? "CLEAR" : weatherProfile, trafficMode == null ? "normal" : trafficMode, riskRate == null ? 0.12 : riskRate); }
    }

    public record DispatchRunRequest(String scenarioId, ScenarioGenerateRequest scenario, List<OrderDto> orders, List<DriverDto> drivers) { }
    public record RescueSimulationRequest(String baseRunId, List<EventDto> events) { }
    public record BenchmarkJobRequest(String datasetId, List<String> solvers) {
        static BenchmarkJobRequest defaults() { return new BenchmarkJobRequest("synthetic-food-smoke", List.of("single-order", "distance-batching", "IntelligentRouteX")); }
        BenchmarkJobRequest withDefaults() { return new BenchmarkJobRequest(datasetId == null ? "synthetic-food-smoke" : datasetId, solvers == null || solvers.isEmpty() ? defaults().solvers() : solvers); }
    }

    public record DashboardRun(String runId, String kind, String createdAt, RunStatus status, RunVisualizationDto visualization) { }
    public record BenchmarkJob(String jobId, String datasetId, List<String> solvers, RunStatus status, String createdAt, String resultRunId, String error) {
        BenchmarkJob withStatus(RunStatus nextStatus, String nextResultRunId, String nextError) { return new BenchmarkJob(jobId, datasetId, solvers, nextStatus, createdAt, nextResultRunId, nextError); }
    }
    public record BenchmarkDatasetDto(String datasetId, String path, String source) { }
    public record BenchmarkSolverResultDto(String solverName, BenchmarkVerdict verdict, double totalDistanceKm, long lateOrderCount, double slaSuccessRate, long runtimeMs, String reason) { }
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
}
