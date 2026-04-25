package com.routechain.v2.perf;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.GeoPoint;
import com.routechain.v2.BootMode;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import com.routechain.v2.cluster.PairFeatureVector;
import com.routechain.v2.context.EtaEstimateRequest;
import com.routechain.v2.context.EtaFeatureVector;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.integration.DemandShiftFeatureVector;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.ForecastResult;
import com.routechain.v2.integration.GreedRlBundleFeatureVector;
import com.routechain.v2.integration.GreedRlBundleResult;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.GreedRlSequenceFeatureVector;
import com.routechain.v2.integration.GreedRlSequenceResult;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.OpenMeteoClient;
import com.routechain.v2.integration.OpenMeteoSnapshot;
import com.routechain.v2.integration.PostDropShiftFeatureVector;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.RouteFinderFeatureVector;
import com.routechain.v2.integration.RouteFinderResult;
import com.routechain.v2.integration.TabularScoreResult;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.TestForecastClient;
import com.routechain.v2.integration.TestGreedRlClient;
import com.routechain.v2.integration.TestOpenMeteoClient;
import com.routechain.v2.integration.TestRouteFinderClient;
import com.routechain.v2.integration.TestTabularScoringClient;
import com.routechain.v2.integration.TestTomTomTrafficRefineClient;
import com.routechain.v2.integration.TomTomTrafficRefineClient;
import com.routechain.v2.integration.TomTomTrafficRefineResult;
import com.routechain.v2.integration.WorkerReadyState;
import com.routechain.v2.integration.ZoneBurstFeatureVector;
import com.routechain.v2.route.DriverFitFeatureVector;
import com.routechain.v2.route.RouteValueFeatureVector;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class DispatchPerfBenchmarkHarness {
    public static final int DEFAULT_WARMUP_RUNS = 2;
    public static final int DEFAULT_MEASURED_RUNS = 5;
    public static final String DEFAULT_MACHINE_LABEL = "dispatch-v2-benchmark-authority-v1";
    private static final List<String> CANONICAL_STAGES = List.of(
            "eta/context",
            "order-buffer",
            "pair-graph",
            "micro-cluster",
            "boundary-expansion",
            "bundle-pool",
            "pickup-anchor",
            "driver-shortlist/rerank",
            "route-proposal-pool",
            "scenario-evaluation",
            "global-selector",
            "dispatch-executor");

    public DispatchPerfBenchmarkResult run(BenchmarkRequest request) {
        if (request.workloadSize() == WorkloadSize.XL && !request.runDeferredXl()) {
            return deferredResult(request, "deferred-on-current-machine");
        }

        List<DispatchV2Result> measuredResults = new ArrayList<>();
        CountingDependencies counters = countingDependencies(request.baselineId());
        for (int runIndex = 0; runIndex < request.warmupRuns() + request.measuredRuns(); runIndex++) {
            DispatchV2Result result = executeRun(request, counters, runIndex);
            if (runIndex >= request.warmupRuns()) {
                measuredResults.add(result);
            }
        }

        List<Long> totalLatencies = measuredResults.stream()
                .map(result -> result.latencyBudgetSummary().totalDispatchLatencyMs())
                .toList();
        Map<String, List<Long>> stageSamples = new LinkedHashMap<>();
        CANONICAL_STAGES.forEach(stage -> stageSamples.put(stage, new ArrayList<>()));
        for (DispatchV2Result result : measuredResults) {
            for (DispatchStageLatency stageLatency : result.stageLatencies()) {
                stageSamples.computeIfAbsent(stageLatency.stageName(), ignored -> new ArrayList<>()).add(stageLatency.elapsedMs());
            }
        }

        List<DispatchPerfStageLatencyStats> stageLatencyStats = stageSamples.entrySet().stream()
                .map(entry -> new DispatchPerfStageLatencyStats(
                        "dispatch-perf-stage-latency-stats/v1",
                        entry.getKey(),
                        DispatchPerfNumericStats.fromSamples(entry.getValue())))
                .toList();

        long budgetBreaches = measuredResults.stream()
                .filter(result -> result.latencyBudgetSummary().totalBudgetBreached()
                        || result.stageLatencies().stream().anyMatch(DispatchStageLatency::budgetBreached))
                .count();
        Map<String, Integer> reusedStageNames = frequencyMap(measuredResults.stream()
                .flatMap(result -> result.hotStartState().reusedStageNames().stream())
                .toList());
        List<Long> savedMsSamples = measuredResults.stream()
                .map(result -> result.hotStartState().estimatedSavedMs())
                .toList();
        long usedMemoryMb = (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024L * 1024L);

        return new DispatchPerfBenchmarkResult(
                "dispatch-perf-benchmark-result/v1",
                Instant.now(),
                gitCommit(),
                DispatchPerfMachineProfile.capture(request.machineLabel()),
                request.baselineId().name(),
                request.workloadSize().name(),
                request.runMode().name().toLowerCase(Locale.ROOT),
                selectorMode(request.baselineId()),
                request.workloadSize().orderCount(),
                request.workloadSize().driverCount(),
                request.workloadSize().seed(),
                request.warmupRuns(),
                request.measuredRuns(),
                measuredResults.size(),
                false,
                DispatchPerfNumericStats.fromSamples(totalLatencies),
                stageLatencyStats,
                measuredResults.isEmpty() ? 0.0 : (double) budgetBreaches / measuredResults.size(),
                reusedStageNames,
                DispatchPerfNumericStats.fromSamples(savedMsSamples),
                counters.workerCallCounts(),
                counters.liveSourceCallCounts(),
                usedMemoryMb,
                request.runMode() == RunMode.WARM ? warmNotes(measuredResults) : List.of());
    }

    private DispatchPerfBenchmarkResult deferredResult(BenchmarkRequest request, String note) {
        return new DispatchPerfBenchmarkResult(
                "dispatch-perf-benchmark-result/v1",
                Instant.now(),
                gitCommit(),
                DispatchPerfMachineProfile.capture(request.machineLabel()),
                request.baselineId().name(),
                request.workloadSize().name(),
                request.runMode().name().toLowerCase(Locale.ROOT),
                selectorMode(request.baselineId()),
                request.workloadSize().orderCount(),
                request.workloadSize().driverCount(),
                request.workloadSize().seed(),
                request.warmupRuns(),
                request.measuredRuns(),
                0,
                true,
                DispatchPerfNumericStats.empty(),
                List.of(),
                0.0,
                Map.of(),
                DispatchPerfNumericStats.empty(),
                Map.of(),
                Map.of(),
                null,
                List.of(note));
    }

    private List<String> warmNotes(List<DispatchV2Result> measuredResults) {
        LinkedHashSet<String> notes = new LinkedHashSet<>();
        boolean allWarm = measuredResults.stream()
                .allMatch(result -> result.warmStartState().bootMode() == BootMode.WARM);
        notes.add(allWarm ? "warm-boot-recoverability-observed" : "warm-boot-recoverability-missing");
        return List.copyOf(notes);
    }

    private DispatchV2Result executeRun(BenchmarkRequest request, CountingDependencies counters, int runIndex) {
        return switch (request.runMode()) {
            case COLD -> coldDispatch(request, counters, runIndex);
            case WARM -> warmDispatch(request, counters, runIndex);
            case HOT -> hotDispatch(request, counters, runIndex);
        };
    }

    private DispatchV2Result coldDispatch(BenchmarkRequest request, CountingDependencies counters, int runIndex) {
        RouteChainDispatchV2Properties properties = baseProperties(request.baselineId(), null);
        properties.setHotStartEnabled(false);
        properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(
                properties,
                counters.tabularClient(),
                counters.routeFinderClient(),
                counters.greedRlClient(),
                counters.forecastClient(),
                counters.openMeteoClient(),
                counters.tomTomClient());
        return harness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "cold")));
    }

    private DispatchV2Result warmDispatch(BenchmarkRequest request, CountingDependencies counters, int runIndex) {
        Path feedbackDirectory = feedbackDirectory(request, runIndex);
        RouteChainDispatchV2Properties properties = baseProperties(request.baselineId(), feedbackDirectory);
        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = TestDispatchV2Factory.harness(
                properties,
                counters.tabularClient(),
                counters.routeFinderClient(),
                counters.greedRlClient(),
                counters.forecastClient(),
                counters.openMeteoClient(),
                counters.tomTomClient());
        seedHarness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "seed")));

        TestDispatchV2Factory.TestDispatchRuntimeHarness warmHarness = TestDispatchV2Factory.harness(
                properties,
                counters.tabularClient(),
                counters.routeFinderClient(),
                counters.greedRlClient(),
                counters.forecastClient(),
                counters.openMeteoClient(),
                counters.tomTomClient());
        return warmHarness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "warm")));
    }

    private DispatchV2Result hotDispatch(BenchmarkRequest request, CountingDependencies counters, int runIndex) {
        Path feedbackDirectory = feedbackDirectory(request, runIndex);
        RouteChainDispatchV2Properties properties = baseProperties(request.baselineId(), feedbackDirectory);
        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = TestDispatchV2Factory.harness(
                properties,
                counters.tabularClient(),
                counters.routeFinderClient(),
                counters.greedRlClient(),
                counters.forecastClient(),
                counters.openMeteoClient(),
                counters.tomTomClient());
        seedHarness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "seed")));

        TestDispatchV2Factory.TestDispatchRuntimeHarness hotHarness = TestDispatchV2Factory.harness(
                properties,
                counters.tabularClient(),
                counters.routeFinderClient(),
                counters.greedRlClient(),
                counters.forecastClient(),
                counters.openMeteoClient(),
                counters.tomTomClient());
        hotHarness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "warm")));
        return hotHarness.core().dispatch(DispatchPerfWorkloadFactory.request(request.workloadSize(), traceId(request, runIndex, "hot")));
    }

    private Path feedbackDirectory(BenchmarkRequest request, int runIndex) {
        return request.feedbackRoot()
                .resolve(request.baselineId().name().toLowerCase(Locale.ROOT))
                .resolve(request.workloadSize().name().toLowerCase(Locale.ROOT))
                .resolve(request.runMode().name().toLowerCase(Locale.ROOT))
                .resolve("run-" + runIndex);
    }

    private RouteChainDispatchV2Properties baseProperties(BaselineId baselineId, Path feedbackDirectory) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setEnabled(true);
        properties.getPerformance().setTelemetryEnabled(true);
        if (feedbackDirectory == null) {
            properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
        } else {
            properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
            properties.getFeedback().setBaseDir(feedbackDirectory.toString());
            properties.getWarmHotStart().setLoadLatestSnapshotOnBoot(true);
        }
        switch (baselineId) {
            case A -> {
                properties.setMlEnabled(false);
                properties.setSelectorOrtoolsEnabled(false);
                properties.setHotStartEnabled(false);
                properties.setTomtomEnabled(false);
                properties.setOpenMeteoEnabled(false);
                properties.getWeather().setEnabled(false);
                properties.getTraffic().setEnabled(false);
                properties.getMl().getForecast().setEnabled(false);
            }
            case B -> {
                properties.setMlEnabled(false);
                properties.setSelectorOrtoolsEnabled(true);
                properties.setHotStartEnabled(false);
                properties.setTomtomEnabled(false);
                properties.setOpenMeteoEnabled(false);
                properties.getWeather().setEnabled(false);
                properties.getTraffic().setEnabled(false);
                properties.getMl().getForecast().setEnabled(false);
            }
            case C -> {
                properties.setMlEnabled(true);
                properties.setSelectorOrtoolsEnabled(true);
                properties.setTomtomEnabled(true);
                properties.setOpenMeteoEnabled(true);
                properties.getWeather().setEnabled(true);
                properties.getTraffic().setEnabled(true);
                properties.getMl().getTabular().setEnabled(true);
                properties.getMl().getRoutefinder().setEnabled(true);
                properties.getMl().getGreedrl().setEnabled(true);
                properties.getMl().getForecast().setEnabled(true);
            }
        }
        return properties;
    }

    private CountingDependencies countingDependencies(BaselineId baselineId) {
        return switch (baselineId) {
            case A, B -> CountingDependencies.noOp();
            case C -> CountingDependencies.full();
        };
    }

    private String selectorMode(BaselineId baselineId) {
        return baselineId == BaselineId.B || baselineId == BaselineId.C ? "ortools" : "greedy";
    }

    private String traceId(BenchmarkRequest request, int runIndex, String suffix) {
        return "perf-%s-%s-%s-%s-%d".formatted(
                request.baselineId().name().toLowerCase(Locale.ROOT),
                request.workloadSize().name().toLowerCase(Locale.ROOT),
                request.runMode().name().toLowerCase(Locale.ROOT),
                suffix,
                runIndex);
    }

    private Map<String, Integer> frequencyMap(List<String> values) {
        Map<String, Integer> frequency = new LinkedHashMap<>();
        for (String value : values) {
            frequency.merge(value, 1, Integer::sum);
        }
        return Map.copyOf(frequency);
    }

    private String gitCommit() {
        try {
            Process process = new ProcessBuilder("git", "rev-parse", "--short", "HEAD")
                    .redirectErrorStream(true)
                    .start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                String line = reader.readLine();
                int exit = process.waitFor();
                if (exit == 0 && line != null && !line.isBlank()) {
                    return line.trim();
                }
            }
        } catch (IOException exception) {
            return "workspace";
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return "workspace";
        }
        return "workspace";
    }

    public record BenchmarkRequest(
            BaselineId baselineId,
            WorkloadSize workloadSize,
            RunMode runMode,
            int warmupRuns,
            int measuredRuns,
            String machineLabel,
            boolean runDeferredXl,
            Path feedbackRoot) {

        public BenchmarkRequest {
            if (warmupRuns < 0) {
                throw new IllegalArgumentException("warmupRuns must be >= 0");
            }
            if (measuredRuns <= 0) {
                throw new IllegalArgumentException("measuredRuns must be > 0");
            }
        }
    }

    public enum BaselineId {
        A,
        B,
        C
    }

    public enum RunMode {
        COLD,
        WARM,
        HOT
    }

    public enum WorkloadSize {
        XS(20, 5, 77L),
        S(50, 20, 101L),
        M(200, 80, 202L),
        L(1000, 400, 303L),
        XL(5000, 2000, 404L);

        private final int orderCount;
        private final int driverCount;
        private final long seed;

        WorkloadSize(int orderCount, int driverCount, long seed) {
            this.orderCount = orderCount;
            this.driverCount = driverCount;
            this.seed = seed;
        }

        public int orderCount() {
            return orderCount;
        }

        public int driverCount() {
            return driverCount;
        }

        public long seed() {
            return seed;
        }
    }

    private record CountingDependencies(
            CountingTabularClient tabularClient,
            CountingRouteFinderClient routeFinderClient,
            CountingGreedRlClient greedRlClient,
            CountingForecastClient forecastClient,
            CountingOpenMeteoClient openMeteoClient,
            CountingTomTomClient tomTomClient) {

        static CountingDependencies noOp() {
            Map<String, Integer> workerCalls = new LinkedHashMap<>();
            Map<String, Integer> liveSourceCalls = new LinkedHashMap<>();
            return new CountingDependencies(
                    new CountingTabularClient(new NoOpTabularScoringClient(), workerCalls),
                    new CountingRouteFinderClient(new NoOpRouteFinderClient(), workerCalls),
                    new CountingGreedRlClient(new NoOpGreedRlClient(), workerCalls),
                    new CountingForecastClient(new NoOpForecastClient(), workerCalls),
                    new CountingOpenMeteoClient(new NoOpOpenMeteoClient(), liveSourceCalls),
                    new CountingTomTomClient(new NoOpTomTomTrafficRefineClient(), liveSourceCalls));
        }

        static CountingDependencies full() {
            Map<String, Integer> workerCalls = new LinkedHashMap<>();
            Map<String, Integer> liveSourceCalls = new LinkedHashMap<>();
            return new CountingDependencies(
                    new CountingTabularClient(TestTabularScoringClient.applied(0.15), workerCalls),
                    new CountingRouteFinderClient(TestRouteFinderClient.applied(), workerCalls),
                    new CountingGreedRlClient(TestGreedRlClient.applied(), workerCalls),
                    new CountingForecastClient(TestForecastClient.applied(), workerCalls),
                    new CountingOpenMeteoClient(TestOpenMeteoClient.freshHeavyRain(), liveSourceCalls),
                    new CountingTomTomClient(TestTomTomTrafficRefineClient.applied(1.22, true), liveSourceCalls));
        }

        Map<String, Integer> workerCallCounts() {
            Map<String, Integer> merged = new LinkedHashMap<>();
            mergeCounts(merged, tabularClient.stageCalls());
            mergeCounts(merged, routeFinderClient.stageCalls());
            mergeCounts(merged, greedRlClient.stageCalls());
            mergeCounts(merged, forecastClient.stageCalls());
            return Map.copyOf(merged);
        }

        Map<String, Integer> liveSourceCallCounts() {
            Map<String, Integer> merged = new LinkedHashMap<>();
            mergeCounts(merged, openMeteoClient.calls());
            mergeCounts(merged, tomTomClient.calls());
            return Map.copyOf(merged);
        }

        private static void mergeCounts(Map<String, Integer> target, Map<String, Integer> source) {
            for (Map.Entry<String, Integer> entry : source.entrySet()) {
                target.merge(entry.getKey(), entry.getValue(), Integer::sum);
            }
        }
    }

    private static final class CountingTabularClient implements TabularScoringClient {
        private final TabularScoringClient delegate;
        private final Map<String, Integer> stageCalls;

        private CountingTabularClient(TabularScoringClient delegate, Map<String, Integer> stageCalls) {
            this.delegate = delegate;
            this.stageCalls = stageCalls;
        }

        @Override
        public TabularScoreResult scoreEtaResidual(EtaFeatureVector etaFeatureVector, long timeoutBudgetMs) {
            increment("eta/context");
            return delegate.scoreEtaResidual(etaFeatureVector, timeoutBudgetMs);
        }

        @Override
        public TabularScoreResult scorePair(PairFeatureVector pairFeatureVector, long timeoutBudgetMs) {
            increment("pair-graph");
            return delegate.scorePair(pairFeatureVector, timeoutBudgetMs);
        }

        @Override
        public TabularScoreResult scoreDriverFit(DriverFitFeatureVector driverFitFeatureVector, long timeoutBudgetMs) {
            increment("driver-shortlist/rerank");
            return delegate.scoreDriverFit(driverFitFeatureVector, timeoutBudgetMs);
        }

        @Override
        public TabularScoreResult scoreRouteValue(RouteValueFeatureVector routeValueFeatureVector, long timeoutBudgetMs) {
            increment("route-proposal-pool");
            return delegate.scoreRouteValue(routeValueFeatureVector, timeoutBudgetMs);
        }

        @Override
        public WorkerReadyState readyState() {
            return delegate.readyState();
        }

        Map<String, Integer> stageCalls() {
            return Map.copyOf(stageCalls);
        }

        private void increment(String stageName) {
            stageCalls.merge(stageName, 1, Integer::sum);
        }
    }

    private static final class CountingRouteFinderClient implements RouteFinderClient {
        private final RouteFinderClient delegate;
        private final Map<String, Integer> stageCalls;

        private CountingRouteFinderClient(RouteFinderClient delegate, Map<String, Integer> stageCalls) {
            this.delegate = delegate;
            this.stageCalls = stageCalls;
        }

        @Override
        public RouteFinderResult refineRoute(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
            increment("route-proposal-pool");
            return delegate.refineRoute(featureVector, timeoutBudgetMs);
        }

        @Override
        public RouteFinderResult generateAlternatives(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
            increment("route-proposal-pool");
            return delegate.generateAlternatives(featureVector, timeoutBudgetMs);
        }

        @Override
        public WorkerReadyState readyState() {
            return delegate.readyState();
        }

        Map<String, Integer> stageCalls() {
            return Map.copyOf(stageCalls);
        }

        private void increment(String stageName) {
            stageCalls.merge(stageName, 1, Integer::sum);
        }
    }

    private static final class CountingGreedRlClient implements GreedRlClient {
        private final GreedRlClient delegate;
        private final Map<String, Integer> stageCalls;

        private CountingGreedRlClient(GreedRlClient delegate, Map<String, Integer> stageCalls) {
            this.delegate = delegate;
            this.stageCalls = stageCalls;
        }

        @Override
        public GreedRlBundleResult proposeBundles(GreedRlBundleFeatureVector featureVector, long timeoutBudgetMs) {
            increment("bundle-pool");
            return delegate.proposeBundles(featureVector, timeoutBudgetMs);
        }

        @Override
        public GreedRlSequenceResult proposeSequence(GreedRlSequenceFeatureVector featureVector, long timeoutBudgetMs) {
            increment("bundle-pool");
            return delegate.proposeSequence(featureVector, timeoutBudgetMs);
        }

        @Override
        public WorkerReadyState readyState() {
            return delegate.readyState();
        }

        Map<String, Integer> stageCalls() {
            return Map.copyOf(stageCalls);
        }

        private void increment(String stageName) {
            stageCalls.merge(stageName, 1, Integer::sum);
        }
    }

    private static final class CountingForecastClient implements ForecastClient {
        private final ForecastClient delegate;
        private final Map<String, Integer> stageCalls;

        private CountingForecastClient(ForecastClient delegate, Map<String, Integer> stageCalls) {
            this.delegate = delegate;
            this.stageCalls = stageCalls;
        }

        @Override
        public ForecastResult forecastDemandShift(DemandShiftFeatureVector featureVector, long timeoutBudgetMs) {
            increment("scenario-evaluation");
            return delegate.forecastDemandShift(featureVector, timeoutBudgetMs);
        }

        @Override
        public ForecastResult forecastZoneBurst(ZoneBurstFeatureVector featureVector, long timeoutBudgetMs) {
            increment("scenario-evaluation");
            return delegate.forecastZoneBurst(featureVector, timeoutBudgetMs);
        }

        @Override
        public ForecastResult forecastPostDropShift(PostDropShiftFeatureVector featureVector, long timeoutBudgetMs) {
            increment("scenario-evaluation");
            return delegate.forecastPostDropShift(featureVector, timeoutBudgetMs);
        }

        @Override
        public WorkerReadyState readyState() {
            return delegate.readyState();
        }

        Map<String, Integer> stageCalls() {
            return Map.copyOf(stageCalls);
        }

        private void increment(String stageName) {
            stageCalls.merge(stageName, 1, Integer::sum);
        }
    }

    private static final class CountingOpenMeteoClient implements OpenMeteoClient {
        private final OpenMeteoClient delegate;
        private final Map<String, Integer> calls;

        private CountingOpenMeteoClient(OpenMeteoClient delegate, Map<String, Integer> calls) {
            this.delegate = delegate;
            this.calls = calls;
        }

        @Override
        public OpenMeteoSnapshot fetchForecast(GeoPoint point, Instant decisionTime) {
            calls.merge("open-meteo", 1, Integer::sum);
            return delegate.fetchForecast(point, decisionTime);
        }

        @Override
        public OpenMeteoSnapshot fetchHistorical(GeoPoint point, Instant decisionTime) {
            calls.merge("open-meteo", 1, Integer::sum);
            return delegate.fetchHistorical(point, decisionTime);
        }

        Map<String, Integer> calls() {
            return Map.copyOf(calls);
        }
    }

    private static final class CountingTomTomClient implements TomTomTrafficRefineClient {
        private final TomTomTrafficRefineClient delegate;
        private final Map<String, Integer> calls;

        private CountingTomTomClient(TomTomTrafficRefineClient delegate, Map<String, Integer> calls) {
            this.delegate = delegate;
            this.calls = calls;
        }

        @Override
        public TomTomTrafficRefineResult refine(EtaEstimateRequest request, double baselineMinutes, double distanceKm) {
            calls.merge("tomtom-traffic", 1, Integer::sum);
            return delegate.refine(request, baselineMinutes, distanceKm);
        }

        Map<String, Integer> calls() {
            return Map.copyOf(calls);
        }
    }
}
