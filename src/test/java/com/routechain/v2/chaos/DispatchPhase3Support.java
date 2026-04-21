package com.routechain.v2.chaos;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.TestDispatchV2Factory;
import com.routechain.v2.benchmark.DispatchQualityMetrics;
import com.routechain.v2.certification.DispatchHotStartCertificationHarness;
import com.routechain.v2.context.TrafficRefineMapper;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.HttpForecastClient;
import com.routechain.v2.integration.HttpGreedRlClient;
import com.routechain.v2.integration.HttpOpenMeteoClient;
import com.routechain.v2.integration.HttpRouteFinderClient;
import com.routechain.v2.integration.HttpTabularScoringClient;
import com.routechain.v2.integration.HttpTomTomTrafficRefineClient;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.OpenMeteoClient;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.TestForecastClient;
import com.routechain.v2.integration.TestGreedRlClient;
import com.routechain.v2.integration.TestOpenMeteoClient;
import com.routechain.v2.integration.TestRouteFinderClient;
import com.routechain.v2.integration.TestTabularScoringClient;
import com.routechain.v2.integration.TestTomTomTrafficRefineClient;
import com.routechain.v2.integration.TomTomTrafficRefineClient;
import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import com.routechain.v2.perf.DispatchPerfNumericStats;
import com.routechain.v2.perf.DispatchPerfStageLatencyStats;
import com.routechain.v2.perf.DispatchPerfWorkloadFactory;
import com.routechain.v2.route.RouteProposalSource;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

final class DispatchPhase3Support {
    static final List<String> CANONICAL_STAGES = List.of(
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
    private static final Path MODEL_MANIFEST_PATH = Path.of("services", "models", "model-manifest.yaml");

    private DispatchPhase3Support() {
    }

    static RouteChainDispatchV2Properties baseProperties(DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                         ExecutionMode executionMode,
                                                         Path feedbackDirectory) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setEnabled(true);
        properties.getPerformance().setTelemetryEnabled(true);
        properties.setMlEnabled(false);
        properties.setSelectorOrtoolsEnabled(false);
        properties.setHotStartEnabled(false);
        properties.setTomtomEnabled(false);
        properties.setOpenMeteoEnabled(false);
        properties.getWeather().setEnabled(false);
        properties.getTraffic().setEnabled(false);
        properties.getMl().getTabular().setEnabled(false);
        properties.getMl().getRoutefinder().setEnabled(false);
        properties.getMl().getGreedrl().setEnabled(false);
        properties.getMl().getForecast().setEnabled(false);
        if (feedbackDirectory != null && (executionMode == ExecutionMode.LOCAL_REAL || baselineId == DispatchPerfBenchmarkHarness.BaselineId.C)) {
            properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
            properties.getFeedback().setBaseDir(feedbackDirectory.toString());
            properties.getWarmHotStart().setLoadLatestSnapshotOnBoot(true);
        } else {
            properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
        }
        if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.B || baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
            properties.setSelectorOrtoolsEnabled(true);
        }
        if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
            properties.setMlEnabled(true);
            properties.setHotStartEnabled(true);
            properties.getMl().getTabular().setEnabled(true);
            properties.getMl().getRoutefinder().setEnabled(true);
            properties.getMl().getGreedrl().setEnabled(true);
            properties.getMl().getForecast().setEnabled(true);
        }
        return properties;
    }

    static TestDispatchV2Factory.TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                                    ScenarioDependencies dependencies) {
        return TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
    }

    static ScenarioDependencies noOps() {
        return new ScenarioDependencies(
                new NoOpTabularScoringClient(),
                new NoOpRouteFinderClient(),
                new NoOpGreedRlClient(),
                new NoOpForecastClient(),
                new NoOpOpenMeteoClient(),
                new NoOpTomTomTrafficRefineClient());
    }

    static ScenarioDependencies appliedMlOnly() {
        return new ScenarioDependencies(
                TestTabularScoringClient.applied(0.15),
                TestRouteFinderClient.applied(),
                TestGreedRlClient.applied(),
                TestForecastClient.applied(),
                new NoOpOpenMeteoClient(),
                new NoOpTomTomTrafficRefineClient());
    }

    static ScenarioDependencies localRealDependencies(RouteChainDispatchV2Properties properties) {
        if (!Files.exists(MODEL_MANIFEST_PATH)) {
            return noOps();
        }
        String apiKey = System.getenv("TOMTOM_API_KEY");
        return new ScenarioDependencies(
                new HttpTabularScoringClient(
                        properties.getMl().getTabular().getBaseUrl(),
                        properties.getMl().getTabular().getConnectTimeout(),
                        properties.getMl().getTabular().getReadTimeout(),
                        MODEL_MANIFEST_PATH),
                new HttpRouteFinderClient(
                        properties.getMl().getRoutefinder().getBaseUrl(),
                        properties.getMl().getRoutefinder().getConnectTimeout(),
                        properties.getMl().getRoutefinder().getReadTimeout(),
                        MODEL_MANIFEST_PATH),
                new HttpGreedRlClient(
                        properties.getMl().getGreedrl().getBaseUrl(),
                        properties.getMl().getGreedrl().getConnectTimeout(),
                        properties.getMl().getGreedrl().getReadTimeout(),
                        MODEL_MANIFEST_PATH),
                new HttpForecastClient(
                        properties.getMl().getForecast().getBaseUrl(),
                        properties.getMl().getForecast().getConnectTimeout(),
                        properties.getMl().getForecast().getReadTimeout(),
                        MODEL_MANIFEST_PATH),
                new HttpOpenMeteoClient(
                        properties.getWeather().getBaseUrl(),
                        properties.getWeather().getConnectTimeout(),
                        properties.getWeather().getReadTimeout(),
                        properties),
                new HttpTomTomTrafficRefineClient(
                        properties.getTraffic().getBaseUrl(),
                        (apiKey == null || apiKey.isBlank()) ? properties.getTraffic().getApiKey() : apiKey,
                        properties.getTraffic().getConnectTimeout(),
                        properties.getTraffic().getReadTimeout(),
                        new TrafficRefineMapper()));
    }

    static ScenarioDefinition scenarioDefinition(ScenarioPack scenarioPack) {
        return switch (scenarioPack) {
            case NORMAL_CLEAR -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        properties.getMl().getForecast().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return baselineId == DispatchPerfBenchmarkHarness.BaselineId.C ? appliedMlOnly() : noOps();
                }
            };
            case HEAVY_RAIN -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId != DispatchPerfBenchmarkHarness.BaselineId.A) {
                        properties.setOpenMeteoEnabled(true);
                        properties.getWeather().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    DispatchV2Request request = DispatchPerfWorkloadFactory.request(workloadSize, traceId);
                    return new DispatchV2Request(
                            request.schemaVersion(),
                            traceId,
                            request.openOrders(),
                            request.availableDrivers(),
                            request.regions(),
                            WeatherProfile.HEAVY_RAIN,
                            request.decisionTime());
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        return appliedMlOnly().withOpenMeteoClient(TestOpenMeteoClient.freshHeavyRain());
                    }
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.B) {
                        return noOps().withOpenMeteoClient(TestOpenMeteoClient.freshHeavyRain());
                    }
                    return noOps();
                }
            };
            case TRAFFIC_SHOCK -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId != DispatchPerfBenchmarkHarness.BaselineId.A) {
                        properties.setTomtomEnabled(true);
                        properties.getTraffic().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchHotStartCertificationHarness.copyWithDecisionTime(
                            DispatchPerfWorkloadFactory.request(workloadSize, traceId),
                            traceId,
                            Instant.parse("2026-04-16T08:00:00Z"));
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        return appliedMlOnly().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.applied(1.35, true));
                    }
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.B) {
                        return noOps().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.applied(1.35, true));
                    }
                    return noOps();
                }
            };
            case FORECAST_HEAVY -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        properties.getMl().getForecast().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return baselineId == DispatchPerfBenchmarkHarness.BaselineId.C
                            ? appliedMlOnly().withForecastClient(TestForecastClient.applied())
                            : noOps();
                }
            };
            case WORKER_DEGRADATION -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        properties.getMl().getForecast().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return baselineId == DispatchPerfBenchmarkHarness.BaselineId.C
                            ? appliedMlOnly().withTabularClient(TestTabularScoringClient.notApplied("tabular-unavailable"))
                            : noOps();
                }
            };
            case LIVE_SOURCE_DEGRADATION -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId != DispatchPerfBenchmarkHarness.BaselineId.A) {
                        properties.setOpenMeteoEnabled(true);
                        properties.getWeather().setEnabled(true);
                        properties.setTomtomEnabled(true);
                        properties.getTraffic().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                                 String traceId,
                                                 DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        return appliedMlOnly()
                                .withOpenMeteoClient(TestOpenMeteoClient.unavailable("open-meteo-unavailable"))
                                .withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.unavailable("tomtom-unavailable"));
                    }
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.B) {
                        return noOps()
                                .withOpenMeteoClient(TestOpenMeteoClient.unavailable("open-meteo-unavailable"))
                                .withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.unavailable("tomtom-unavailable"));
                    }
                    return noOps();
                }
            };
        };
    }

    static DispatchQualityMetrics metricsFrom(DispatchV2Result result) {
        int executedAssignmentCount = result.dispatchExecutionSummary().executedAssignmentCount();
        long bundledAssignments = result.assignments().stream()
                .filter(assignment -> assignment.orderIds().size() > 1)
                .count();
        double averageBundleSize = result.assignments().stream()
                .filter(assignment -> assignment.orderIds().size() > 1)
                .mapToInt(assignment -> assignment.orderIds().size())
                .average()
                .orElse(0.0);
        double averagePickupEta = result.assignments().stream()
                .mapToDouble(assignment -> assignment.projectedPickupEtaMinutes())
                .average()
                .orElse(0.0);
        double averageCompletionEta = result.assignments().stream()
                .mapToDouble(assignment -> assignment.projectedCompletionEtaMinutes())
                .average()
                .orElse(0.0);
        double landingValueAverage = result.robustUtilities().stream()
                .mapToDouble(robustUtility -> robustUtility.landingValue())
                .average()
                .orElse(0.0);
        double robustUtilityAverage = result.robustUtilities().stream()
                .mapToDouble(robustUtility -> robustUtility.robustUtility())
                .average()
                .orElse(0.0);
        return new DispatchQualityMetrics(
                "dispatch-quality-metrics/v1",
                result.globalSelectionResult().selectedCount(),
                executedAssignmentCount,
                conflictFreeAssignments(result),
                executedAssignmentCount <= result.globalSelectionResult().selectedCount(),
                executedAssignmentCount == 0 ? 0.0 : bundledAssignments / (double) executedAssignmentCount,
                averageBundleSize,
                routeFallbackRate(result),
                averagePickupEta,
                averageCompletionEta,
                landingValueAverage,
                robustUtilityAverage,
                result.globalSelectionResult().objectiveValue(),
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                distinctDegrades(result).isEmpty() ? 0.0 : 1.0,
                fallbackRate(result.mlStageMetadata().stream().map(MlStageMetadata::fallbackUsed).toList()),
                fallbackRate(result.liveStageMetadata().stream().map(LiveStageMetadata::fallbackUsed).toList()));
    }

    static DispatchQualityMetrics aggregateMetrics(List<DispatchQualityMetrics> samples) {
        if (samples.isEmpty()) {
            return new DispatchQualityMetrics("dispatch-quality-metrics/v1", 0, 0, true, true, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        }
        return new DispatchQualityMetrics(
                "dispatch-quality-metrics/v1",
                (int) Math.round(samples.stream().mapToInt(DispatchQualityMetrics::selectedProposalCount).average().orElse(0.0)),
                (int) Math.round(samples.stream().mapToInt(DispatchQualityMetrics::executedAssignmentCount).average().orElse(0.0)),
                samples.stream().allMatch(DispatchQualityMetrics::conflictFreeAssignments),
                samples.stream().allMatch(DispatchQualityMetrics::executionValid),
                samples.stream().mapToDouble(DispatchQualityMetrics::bundleRate).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::averageBundleSize).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::routeFallbackRate).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::averageProjectedPickupEtaMinutes).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::averageProjectedCompletionEtaMinutes).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::landingValueAverage).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::robustUtilityAverage).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::selectorObjectiveValue).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::routeCostQuality).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::driverEntryQuality).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::burstRobustness).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::dispatchRegretAverage).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::courierUtilizationEstimate).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::degradeRate).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::workerFallbackRate).average().orElse(0.0),
                samples.stream().mapToDouble(DispatchQualityMetrics::liveSourceFallbackRate).average().orElse(0.0));
    }

    static List<DispatchPerfStageLatencyStats> stageLatencyStats(List<DispatchV2Result> results) {
        Map<String, List<Long>> stageSamples = new LinkedHashMap<>();
        CANONICAL_STAGES.forEach(stage -> stageSamples.put(stage, new ArrayList<>()));
        for (DispatchV2Result result : results) {
            for (DispatchStageLatency stageLatency : result.stageLatencies()) {
                stageSamples.computeIfAbsent(stageLatency.stageName(), ignored -> new ArrayList<>()).add(stageLatency.elapsedMs());
            }
        }
        return stageSamples.entrySet().stream()
                .map(entry -> new DispatchPerfStageLatencyStats(
                        "dispatch-perf-stage-latency-stats/v1",
                        entry.getKey(),
                        DispatchPerfNumericStats.fromSamples(entry.getValue())))
                .toList();
    }

    static List<String> distinctDegrades(DispatchV2Result result) {
        return distinctStrings(java.util.stream.Stream.of(
                        result.degradeReasons().stream(),
                        result.liveStageMetadata().stream()
                                .map(LiveStageMetadata::degradeReason)
                                .filter(reason -> reason != null && !reason.isBlank()),
                        result.routeProposalSummary().degradeReasons().stream(),
                        result.scenarioEvaluationSummary().degradeReasons().stream(),
                        result.globalSelectionResult().degradeReasons().stream(),
                        result.dispatchExecutionSummary().degradeReasons().stream())
                .flatMap(stream -> stream)
                .toList());
    }

    static List<String> distinctStrings(List<String> values) {
        return values.stream()
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .sorted(Comparator.naturalOrder())
                .toList();
    }

    static boolean conflictFreeAssignments(DispatchV2Result result) {
        Set<String> seenDrivers = new LinkedHashSet<>();
        Set<String> seenOrders = new LinkedHashSet<>();
        for (var assignment : result.assignments()) {
            if (!seenDrivers.add(assignment.driverId())) {
                return false;
            }
            for (String orderId : assignment.orderIds()) {
                if (!seenOrders.add(orderId)) {
                    return false;
                }
            }
        }
        return true;
    }

    static Map<String, Integer> frequencyMap(List<String> values) {
        Map<String, Integer> frequency = new LinkedHashMap<>();
        for (String value : values) {
            frequency.merge(value, 1, Integer::sum);
        }
        return Map.copyOf(frequency);
    }

    static String gitCommit() {
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

    private static double routeFallbackRate(DispatchV2Result result) {
        int executedAssignmentCount = result.dispatchExecutionSummary().executedAssignmentCount();
        long fallbackAssignments = result.assignments().stream()
                .filter(assignment -> assignment.routeSource() == RouteProposalSource.FALLBACK_SIMPLE
                        || containsFallbackSignal(assignment.reasons())
                        || containsFallbackSignal(assignment.degradeReasons()))
                .count();
        if (executedAssignmentCount > 0) {
            return fallbackAssignments / (double) executedAssignmentCount;
        }
        Integer fallbackProposals = result.routeProposalSummary().sourceCounts().get(RouteProposalSource.FALLBACK_SIMPLE);
        if (result.routeProposalSummary().proposalCount() <= 0 || fallbackProposals == null) {
            return 0.0;
        }
        return fallbackProposals / (double) result.routeProposalSummary().proposalCount();
    }

    private static boolean containsFallbackSignal(List<String> reasons) {
        return reasons.stream()
                .filter(reason -> reason != null)
                .map(reason -> reason.toLowerCase(Locale.ROOT))
                .anyMatch(reason -> reason.contains("fallback"));
    }

    private static double fallbackRate(List<Boolean> fallbackFlags) {
        if (fallbackFlags.isEmpty()) {
            return 0.0;
        }
        long fallbacks = fallbackFlags.stream().filter(Boolean::booleanValue).count();
        return fallbacks / (double) fallbackFlags.size();
    }

    enum ExecutionMode {
        CONTROLLED("controlled"),
        LOCAL_REAL("local-real");

        private final String wireName;

        ExecutionMode(String wireName) {
            this.wireName = wireName;
        }

        String wireName() {
            return wireName;
        }

        static ExecutionMode fromWire(String value) {
            return EnumSet.allOf(ExecutionMode.class).stream()
                    .filter(mode -> mode.wireName.equals(value))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("Unknown execution mode: " + value));
        }
    }

    enum ScenarioPack {
        NORMAL_CLEAR("normal-clear"),
        HEAVY_RAIN("heavy-rain"),
        TRAFFIC_SHOCK("traffic-shock"),
        FORECAST_HEAVY("forecast-heavy"),
        WORKER_DEGRADATION("worker-degradation"),
        LIVE_SOURCE_DEGRADATION("live-source-degradation");

        private final String wireName;

        ScenarioPack(String wireName) {
            this.wireName = wireName;
        }

        String wireName() {
            return wireName;
        }

        static ScenarioPack fromWire(String value) {
            return EnumSet.allOf(ScenarioPack.class).stream()
                    .filter(pack -> pack.wireName.equals(value))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("Unknown scenario pack: " + value));
        }
    }

    enum ChaosFaultType {
        TABULAR_UNAVAILABLE("tabular-unavailable"),
        ROUTEFINDER_UNAVAILABLE("routefinder-unavailable"),
        GREEDRL_UNAVAILABLE("greedrl-unavailable"),
        FORECAST_UNAVAILABLE("forecast-unavailable"),
        WORKER_READY_FALSE_OPTIONAL_PATH("worker-ready-false-optional-path"),
        WORKER_MALFORMED_RESPONSE("worker-malformed-response"),
        WORKER_FINGERPRINT_MISMATCH("worker-fingerprint-mismatch"),
        OPEN_METEO_STALE("open-meteo-stale"),
        OPEN_METEO_UNAVAILABLE("open-meteo-unavailable"),
        TOMTOM_TIMEOUT("tomtom-timeout"),
        TOMTOM_AUTH_OR_QUOTA("tomtom-auth-or-quota"),
        TOMTOM_HTTP_ERROR("tomtom-http-error"),
        TOMTOM_MISSING_API_KEY("tomtom-missing-api-key"),
        WARM_BOOT_INVALID_SNAPSHOT("warm-boot-invalid-snapshot"),
        REUSE_STATE_LOAD_MISSING_OR_INVALID("reuse-state-load-missing-or-invalid"),
        PARTIAL_HOT_START_DRIFT("partial-hot-start-drift");

        private final String wireName;

        ChaosFaultType(String wireName) {
            this.wireName = wireName;
        }

        String wireName() {
            return wireName;
        }

        static ChaosFaultType fromWire(String value) {
            return EnumSet.allOf(ChaosFaultType.class).stream()
                    .filter(type -> type.wireName.equals(value))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("Unknown fault type: " + value));
        }
    }

    interface ScenarioDefinition {
        void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId);

        DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                  String traceId,
                                  DispatchPerfBenchmarkHarness.BaselineId baselineId);

        ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId);

        default ScenarioDependencies dependencies(ExecutionMode executionMode,
                                                  DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                  RouteChainDispatchV2Properties properties) {
            if (executionMode == ExecutionMode.LOCAL_REAL) {
                ScenarioDependencies realDependencies = localRealDependencies(properties);
                if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                    return realDependencies;
                }
                return noOps()
                        .withOpenMeteoClient(realDependencies.openMeteoClient())
                        .withTomTomTrafficRefineClient(realDependencies.tomTomTrafficRefineClient());
            }
            return controlledDependencies(baselineId);
        }
    }

    record ScenarioDependencies(
            TabularScoringClient tabularScoringClient,
            RouteFinderClient routeFinderClient,
            GreedRlClient greedRlClient,
            ForecastClient forecastClient,
            OpenMeteoClient openMeteoClient,
            TomTomTrafficRefineClient tomTomTrafficRefineClient) {

        ScenarioDependencies withTabularClient(TabularScoringClient client) {
            return new ScenarioDependencies(client, routeFinderClient, greedRlClient, forecastClient, openMeteoClient, tomTomTrafficRefineClient);
        }

        ScenarioDependencies withRouteFinderClient(RouteFinderClient client) {
            return new ScenarioDependencies(tabularScoringClient, client, greedRlClient, forecastClient, openMeteoClient, tomTomTrafficRefineClient);
        }

        ScenarioDependencies withGreedRlClient(GreedRlClient client) {
            return new ScenarioDependencies(tabularScoringClient, routeFinderClient, client, forecastClient, openMeteoClient, tomTomTrafficRefineClient);
        }

        ScenarioDependencies withForecastClient(ForecastClient client) {
            return new ScenarioDependencies(tabularScoringClient, routeFinderClient, greedRlClient, client, openMeteoClient, tomTomTrafficRefineClient);
        }

        ScenarioDependencies withOpenMeteoClient(OpenMeteoClient client) {
            return new ScenarioDependencies(tabularScoringClient, routeFinderClient, greedRlClient, forecastClient, client, tomTomTrafficRefineClient);
        }

        ScenarioDependencies withTomTomTrafficRefineClient(TomTomTrafficRefineClient client) {
            return new ScenarioDependencies(tabularScoringClient, routeFinderClient, greedRlClient, forecastClient, openMeteoClient, client);
        }
    }
}
