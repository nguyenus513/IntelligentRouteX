package com.routechain.v2.benchmark;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.TestDispatchV2Factory;
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
import com.routechain.v2.integration.MlWorkerMetadata;
import com.routechain.v2.integration.MlWorkerAuditSupport;
import com.routechain.v2.integration.ModelManifestLoader;
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
import com.routechain.v2.integration.WorkerManifest;
import com.routechain.v2.integration.WorkerReadyState;
import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import com.routechain.v2.perf.DispatchPerfMachineProfile;
import com.routechain.v2.perf.DispatchPerfWorkloadFactory;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectedProposal;
import com.routechain.v2.decision.DecisionStageName;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.InvalidPathException;
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

public final class DispatchQualityBenchmarkHarness {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper().findAndRegisterModules();
    private static final String TABULAR_WORKER = "ml-tabular-worker";
    private static final String ROUTEFINDER_WORKER = "ml-routefinder-worker";
    private static final String GREEDRL_WORKER = "ml-greedrl-worker";
    private static final String FORECAST_WORKER = "ml-forecast-worker";
    private static final List<String> PROMOTION_BLOCKER_STAGES = List.of(
            DecisionStageName.DRIVER.wireName(),
            DecisionStageName.ROUTE_CRITIQUE.wireName(),
            DecisionStageName.SCENARIO.wireName(),
            DecisionStageName.ROUTE_GENERATION.wireName());

    public DispatchQualityBenchmarkRun benchmark(BenchmarkRequest request) {
        DispatchQualityExecutionPolicy executionPolicy = executionPolicy(request);
        List<DispatchQualityBenchmarkResult> results = request.baselines().stream()
                .map(baseline -> request.workloadSize() == DispatchPerfBenchmarkHarness.WorkloadSize.XL && !request.runDeferredXl()
                        ? deferredResult(request, baseline, executionPolicy, "deferred-on-current-machine")
                        : runScenario(request, baseline, executionPolicy))
                .toList();
        DispatchQualityComparisonReport comparisonReport = request.baselines().containsAll(List.of(
                DispatchPerfBenchmarkHarness.BaselineId.A,
                DispatchPerfBenchmarkHarness.BaselineId.B,
                DispatchPerfBenchmarkHarness.BaselineId.C))
                ? comparisonReport(request, results)
                : null;
        return new DispatchQualityBenchmarkRun(results, comparisonReport);
    }

    public DispatchAblationResult ablate(AblationRequest request) {
        if (request.workloadSize() == DispatchPerfBenchmarkHarness.WorkloadSize.XL && !request.runDeferredXl()) {
            DispatchQualityMetrics emptyMetrics = emptyMetrics();
            return new DispatchAblationResult(
                    "dispatch-ablation-result/v1",
                    request.scenarioPack().wireName(),
                    request.scenarioPack().wireName(),
                    request.workloadSize().name(),
                    request.executionMode().wireName(),
                    request.component().wireName(),
                    Map.of("deferred", "false"),
                    Map.of("deferred", "true"),
                    emptyMetrics,
                    emptyMetrics,
                    List.of("deferred-on-current-machine"));
        }

        DispatchV2Result controlResult = executeAblationRun(request, true);
        DispatchV2Result variantResult = executeAblationRun(request, false);
        DispatchQualityMetrics controlMetrics = metricsFrom(controlResult);
        DispatchQualityMetrics variantMetrics = metricsFrom(variantResult);
        return new DispatchAblationResult(
                "dispatch-ablation-result/v1",
                request.scenarioPack().wireName(),
                request.scenarioPack().wireName(),
                request.workloadSize().name(),
                request.executionMode().wireName(),
                request.component().wireName(),
                controlConfig(request.component(), true),
                controlConfig(request.component(), false),
                controlMetrics,
                variantMetrics,
                deltaSummary(controlMetrics, variantMetrics));
    }

    private DispatchQualityBenchmarkResult runScenario(BenchmarkRequest request,
                                                       DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                       DispatchQualityExecutionPolicy executionPolicy) {
        Instant cellStartedAt = Instant.now();
        try {
            ScenarioExecution execution = executeDispatch(request, baselineId);
            Instant dispatchCompletedAt = Instant.now();
            DispatchV2Result result = execution.result();
            DispatchQualityFeedbackSummary feedbackSummary = feedbackSummary(feedbackDirectory(request, baselineId, executionPolicy));
            List<DispatchStagePromotionBlocker> promotionBlockers = promotionBlockers(
                    request,
                    execution.authoritativeStages(),
                    execution.attachDiagnostics(),
                    feedbackSummary,
                    routeVectorMetrics(result));
            List<String> notes = new ArrayList<>();
            if (!request.authorityRun() && request.executionMode() == ExecutionMode.LOCAL_REAL) {
                notes.add("non-authoritative-local-real-run");
            }
            if (request.decisionMode() == DispatchBenchmarkDecisionMode.LLM_AUTHORITATIVE) {
                notes.add("authoritative-stage-intent-from-benchmark-mode");
            }
            if (execution.attachDiagnostics().mlAttachStatus() == DispatchQualityMlAttachStatus.ML_ATTACH_FAIL) {
                notes.add("ML_ATTACH_FAIL");
            }
            String runAuthorityClass = request.authorityRun() ? "AUTHORITY_REAL" : "LOCAL_NON_AUTHORITY";
            boolean authorityEligible = request.authorityRun() && notes.stream().noneMatch("non-authoritative-local-real-run"::equals);
            Instant cellCompletedAt = Instant.now();
            return new DispatchQualityBenchmarkResult(
                    "dispatch-quality-benchmark-result/v1",
                    cellStartedAt,
                    gitCommit(),
                    DispatchPerfMachineProfile.capture(request.machineLabel()),
                    request.decisionMode().wireName(),
                    request.promptFamily(),
                    runtimeClassification(request.decisionMode(), execution.authoritativeStages()),
                    execution.authoritativeStages(),
                    request.executionMode().wireName(),
                    runAuthorityClass,
                    request.authorityRun(),
                    authorityEligible,
                    false,
                    execution.attachDiagnostics().resolvedModelManifestPath(),
                    execution.attachDiagnostics().manifestExists(),
                    execution.attachDiagnostics().workerBaseUrls(),
                    execution.attachDiagnostics().activeMlFlags(),
                    execution.attachDiagnostics().workerStatusSnapshot(),
                    execution.attachDiagnostics().mlAttachStatus(),
                    execution.attachDiagnostics().mlAttachmentFailureReasons(),
                    baselineId.name(),
                    request.scenarioPack().wireName(),
                    request.scenarioPack().wireName(),
                    request.workloadSize().name(),
                    traceFamilyId(request, baselineId),
                    result.decisionStages(),
                    executionPolicy,
                    osProfile(),
                    cellStartedAt,
                    dispatchCompletedAt,
                    cellCompletedAt,
                    null,
                    DispatchQualityTimeoutPhase.NONE,
                    promotionBlockers,
                    false,
                    metricsFrom(result),
                    intelligenceMetrics(result, feedbackSummary, request.scenarioPack()),
                    feedbackSummary.llmShadowAgreement(),
                    routeVectorMetrics(result),
                    feedbackSummary.tokenUsageSummary(),
                    feedbackSummary.stageFallbackSummary(),
                    distinctDegrades(result),
                    distinctSources(result.mlStageMetadata().stream()
                            .filter(MlStageMetadata::applied)
                            .map(MlStageMetadata::sourceModel)
                            .toList()),
                    distinctSources(result.liveStageMetadata().stream()
                            .filter(LiveStageMetadata::applied)
                            .map(LiveStageMetadata::sourceName)
                            .toList()),
                    List.copyOf(notes));
        } catch (RuntimeException exception) {
            if (!isTimeoutFailure(exception)) {
                throw exception;
            }
            return timeoutResult(request, baselineId, executionPolicy, cellStartedAt, classifyTimeoutPhase(exception), exception);
        }
    }

    private DispatchQualityBenchmarkResult timeoutResult(BenchmarkRequest request,
                                                         DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                         DispatchQualityExecutionPolicy executionPolicy,
                                                         Instant cellStartedAt,
                                                         DispatchQualityTimeoutPhase timeoutPhase,
                                                         RuntimeException exception) {
        List<String> notes = new ArrayList<>();
        notes.add(timeoutPhase.wireName());
        String message = blankToEmpty(exception.getMessage());
        if (!message.isBlank()) {
            notes.add("timeout-message:" + message);
        }
        return new DispatchQualityBenchmarkResult(
                "dispatch-quality-benchmark-result/v1",
                cellStartedAt,
                gitCommit(),
                DispatchPerfMachineProfile.capture(request.machineLabel()),
                request.decisionMode().wireName(),
                request.promptFamily(),
                runtimeClassification(request.decisionMode(), request.decisionMode().authoritativeStages()),
                request.decisionMode().authoritativeStages(),
                request.executionMode().wireName(),
                request.authorityRun() ? "AUTHORITY_REAL" : "LOCAL_NON_AUTHORITY",
                false,
                false,
                false,
                "",
                false,
                Map.of(),
                Map.of(),
                List.of(),
                DispatchQualityMlAttachStatus.ATTACHED,
                List.of(timeoutPhase.wireName()),
                baselineId.name(),
                request.scenarioPack().wireName(),
                request.scenarioPack().wireName(),
                request.workloadSize().name(),
                traceFamilyId(request, baselineId),
                List.of(),
                executionPolicy,
                osProfile(),
                cellStartedAt,
                null,
                Instant.now(),
                null,
                timeoutPhase,
                List.of(),
                false,
                emptyMetrics(),
                DispatchIntelligenceMetrics.empty(),
                DispatchLlmShadowAgreementSummary.empty(),
                DispatchRouteVectorMetrics.empty(),
                DispatchTokenUsageSummary.empty(),
                DispatchStageFallbackSummary.empty(),
                List.of(),
                List.of(),
                List.of(),
                List.copyOf(notes));
    }

    private DispatchQualityBenchmarkResult deferredResult(BenchmarkRequest request,
                                                          DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                          DispatchQualityExecutionPolicy executionPolicy,
                                                          String note) {
        Instant cellStartedAt = Instant.now();
        Instant cellCompletedAt = Instant.now();
        return new DispatchQualityBenchmarkResult(
                "dispatch-quality-benchmark-result/v1",
                cellStartedAt,
                gitCommit(),
                DispatchPerfMachineProfile.capture(request.machineLabel()),
                request.decisionMode().wireName(),
                request.promptFamily(),
                runtimeClassification(request.decisionMode(), request.decisionMode().authoritativeStages()),
                request.decisionMode().authoritativeStages(),
                request.executionMode().wireName(),
                request.authorityRun() ? "AUTHORITY_REAL" : "LOCAL_NON_AUTHORITY",
                request.authorityRun(),
                false,
                false,
                "",
                false,
                Map.of(),
                Map.of(),
                List.of(),
                DispatchQualityMlAttachStatus.ML_ATTACH_FAIL,
                List.of("deferred-on-current-machine"),
                baselineId.name(),
                request.scenarioPack().wireName(),
                request.scenarioPack().wireName(),
                request.workloadSize().name(),
                traceFamilyId(request, baselineId),
                List.of(),
                executionPolicy,
                osProfile(),
                cellStartedAt,
                null,
                cellCompletedAt,
                null,
                DispatchQualityTimeoutPhase.NONE,
                List.of(),
                true,
                emptyMetrics(),
                DispatchIntelligenceMetrics.empty(),
                DispatchLlmShadowAgreementSummary.empty(),
                DispatchRouteVectorMetrics.empty(),
                DispatchTokenUsageSummary.empty(),
                DispatchStageFallbackSummary.empty(),
                List.of(),
                List.of(),
                List.of(),
                List.of(note));
    }

    private ScenarioExecution executeDispatch(BenchmarkRequest request, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
        DispatchQualityExecutionPolicy executionPolicy = executionPolicy(request);
        ScenarioDefinition scenario = scenarioDefinition(request.scenarioPack());
        RouteChainDispatchV2Properties properties = baseProperties(
                baselineId,
                request.decisionMode(),
                request.promptFamily(),
                request.executionMode(),
                feedbackDirectory(request, baselineId, executionPolicy));
        scenario.configureProperties(properties, baselineId);
        ScenarioDependencies dependencies = request.executionMode() == ExecutionMode.CONTROLLED
                ? scenario.controlledDependencies(baselineId)
                : scenario.localRealDependencies(baselineId, properties);
        MlAttachDiagnostics attachDiagnostics = collectAttachDiagnostics(properties, dependencies);
        DispatchV2Request dispatchRequest = scenario.request(
                request.workloadSize(),
                traceFamilyId(request, baselineId),
                baselineId);
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
        DispatchV2Result result = harness.core().dispatch(dispatchRequest);
        return new ScenarioExecution(
                result,
                finalizeAttachDiagnostics(properties, baselineId, request.authorityRun(), attachDiagnostics, result),
                List.copyOf(properties.getDecision().getAuthoritativeStages()));
    }

    private DispatchV2Result executeAblationRun(AblationRequest request, boolean control) {
        ScenarioDefinition scenario = scenarioDefinition(request.scenarioPack());
        RouteChainDispatchV2Properties properties = baseProperties(
                DispatchPerfBenchmarkHarness.BaselineId.C,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                request.executionMode(),
                feedbackDirectory(request, control));
        scenario.configureProperties(properties, DispatchPerfBenchmarkHarness.BaselineId.C);
        ScenarioDependencies dependencies = request.executionMode() == ExecutionMode.CONTROLLED
                ? scenario.controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId.C)
                : scenario.localRealDependencies(DispatchPerfBenchmarkHarness.BaselineId.C, properties);
        if (!control) {
            dependencies = applyAblation(request.component(), properties, dependencies);
        } else if (request.component() == AblationComponent.HOT_START) {
            properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
            properties.getFeedback().setBaseDir(feedbackDirectory(request, true).toString());
            properties.setHotStartEnabled(true);
            properties.getWarmHotStart().setLoadLatestSnapshotOnBoot(true);
        }

        DispatchV2Request requestPayload = scenario.request(
                request.workloadSize(),
                "ablation-%s-%s-%s".formatted(request.component().wireName(), control ? "control" : "variant", request.scenarioPack().wireName()),
                DispatchPerfBenchmarkHarness.BaselineId.C);
        if (request.component() == AblationComponent.HOT_START) {
            return executeHotStartAblation(properties, dependencies, requestPayload, control);
        }
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
        return harness.core().dispatch(requestPayload);
    }

    private DispatchV2Result executeHotStartAblation(RouteChainDispatchV2Properties properties,
                                                     ScenarioDependencies dependencies,
                                                     DispatchV2Request requestPayload,
                                                     boolean control) {
        if (!control) {
            properties.setHotStartEnabled(false);
            properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
            TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(
                    properties,
                    dependencies.tabularScoringClient(),
                    dependencies.routeFinderClient(),
                    dependencies.greedRlClient(),
                    dependencies.forecastClient(),
                    dependencies.openMeteoClient(),
                    dependencies.tomTomTrafficRefineClient());
            return harness.core().dispatch(requestPayload);
        }

        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
        seedHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(requestPayload, requestPayload.traceId() + "-seed"));

        TestDispatchV2Factory.TestDispatchRuntimeHarness hotHarness = TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
        hotHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(requestPayload, requestPayload.traceId() + "-warm"));
        return hotHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(requestPayload, requestPayload.traceId() + "-hot"));
    }

    private ScenarioDependencies applyAblation(AblationComponent component,
                                               RouteChainDispatchV2Properties properties,
                                               ScenarioDependencies dependencies) {
        return switch (component) {
            case TABULAR -> {
                properties.getMl().getTabular().setEnabled(false);
                yield dependencies.withTabularClient(new NoOpTabularScoringClient());
            }
            case ROUTEFINDER -> {
                properties.getMl().getRoutefinder().setEnabled(false);
                yield dependencies.withRouteFinderClient(new NoOpRouteFinderClient());
            }
            case GREEDRL -> {
                properties.getMl().getGreedrl().setEnabled(false);
                yield dependencies.withGreedRlClient(new NoOpGreedRlClient());
            }
            case FORECAST -> {
                properties.getMl().getForecast().setEnabled(false);
                yield dependencies.withForecastClient(new NoOpForecastClient());
            }
            case TOMTOM -> {
                properties.setTomtomEnabled(false);
                properties.getTraffic().setEnabled(false);
                yield dependencies.withTomTomTrafficRefineClient(new NoOpTomTomTrafficRefineClient());
            }
            case OPEN_METEO -> {
                properties.setOpenMeteoEnabled(false);
                properties.getWeather().setEnabled(false);
                yield dependencies.withOpenMeteoClient(new NoOpOpenMeteoClient());
            }
            case ORTOOLS -> {
                properties.setSelectorOrtoolsEnabled(false);
                yield dependencies;
            }
            case HOT_START -> {
                properties.setHotStartEnabled(false);
                properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
                yield dependencies;
            }
        };
    }

    private Map<String, String> controlConfig(AblationComponent component, boolean control) {
        return switch (component) {
            case TABULAR -> Map.of("tabular", control ? "on" : "off");
            case ROUTEFINDER -> Map.of("routefinder", control ? "on" : "off");
            case GREEDRL -> Map.of("greedrl", control ? "on" : "off");
            case FORECAST -> Map.of("forecast", control ? "on" : "off");
            case TOMTOM -> Map.of("tomtom", control ? "on" : "off");
            case OPEN_METEO -> Map.of("open-meteo", control ? "on" : "off");
            case ORTOOLS -> Map.of("selector-mode", control ? "ortools" : "degraded-greedy");
            case HOT_START -> Map.of("hot-start", control ? "on" : "off");
        };
    }

    private DispatchQualityComparisonReport comparisonReport(BenchmarkRequest request, List<DispatchQualityBenchmarkResult> results) {
        Map<String, DispatchQualityBenchmarkResult> byBaseline = new LinkedHashMap<>();
        for (DispatchQualityBenchmarkResult result : results) {
            byBaseline.put(result.baselineId(), result);
        }
        DispatchQualityBenchmarkResult baselineA = byBaseline.get("A");
        DispatchQualityBenchmarkResult baselineB = byBaseline.get("B");
        DispatchQualityBenchmarkResult baselineC = byBaseline.get("C");
        List<String> advantages = new ArrayList<>();
        List<String> regressions = new ArrayList<>();
        if (baselineC != null && baselineA != null) {
            compareAgainst("A", baselineC.metrics(), baselineA.metrics(), advantages, regressions);
        }
        if (baselineC != null && baselineB != null) {
            compareAgainst("B", baselineC.metrics(), baselineB.metrics(), advantages, regressions);
        }
        String summary = "Full V2 has %d advantages and %d regressions against selected baselines".formatted(
                advantages.size(),
                regressions.size());
        return new DispatchQualityComparisonReport(
                "dispatch-quality-comparison-report/v1",
                request.scenarioPack().wireName(),
                request.scenarioPack().wireName(),
                request.workloadSize().name(),
                request.decisionMode().wireName(),
                request.decisionMode().authoritativeStages(),
                request.executionMode().wireName(),
                request.authorityRun() ? "AUTHORITY_REAL" : "LOCAL_NON_AUTHORITY",
                request.authorityRun(),
                results.stream().allMatch(DispatchQualityBenchmarkResult::authorityEligible),
                false,
                List.copyOf(results),
                List.copyOf(advantages),
                List.copyOf(regressions),
                summary);
    }

    private void compareAgainst(String baselineName,
                                DispatchQualityMetrics full,
                                DispatchQualityMetrics baseline,
                                List<String> advantages,
                                List<String> regressions) {
        compareHigherBetter("selectedProposalCount", full.selectedProposalCount(), baseline.selectedProposalCount(), baselineName, advantages, regressions);
        compareHigherBetter("executedAssignmentCount", full.executedAssignmentCount(), baseline.executedAssignmentCount(), baselineName, advantages, regressions);
        compareHigherBetter("bundleRate", full.bundleRate(), baseline.bundleRate(), baselineName, advantages, regressions);
        compareHigherBetter("averageBundleSize", full.averageBundleSize(), baseline.averageBundleSize(), baselineName, advantages, regressions);
        compareLowerBetter("routeFallbackRate", full.routeFallbackRate(), baseline.routeFallbackRate(), baselineName, advantages, regressions);
        compareLowerBetter("averageProjectedPickupEtaMinutes", full.averageProjectedPickupEtaMinutes(), baseline.averageProjectedPickupEtaMinutes(), baselineName, advantages, regressions);
        compareLowerBetter("averageProjectedCompletionEtaMinutes", full.averageProjectedCompletionEtaMinutes(), baseline.averageProjectedCompletionEtaMinutes(), baselineName, advantages, regressions);
        compareHigherBetter("landingValueAverage", full.landingValueAverage(), baseline.landingValueAverage(), baselineName, advantages, regressions);
        compareHigherBetter("robustUtilityAverage", full.robustUtilityAverage(), baseline.robustUtilityAverage(), baselineName, advantages, regressions);
        compareHigherBetter("selectorObjectiveValue", full.selectorObjectiveValue(), baseline.selectorObjectiveValue(), baselineName, advantages, regressions);
        compareLowerBetter("degradeRate", full.degradeRate(), baseline.degradeRate(), baselineName, advantages, regressions);
        compareLowerBetter("workerFallbackRate", full.workerFallbackRate(), baseline.workerFallbackRate(), baselineName, advantages, regressions);
        compareLowerBetter("liveSourceFallbackRate", full.liveSourceFallbackRate(), baseline.liveSourceFallbackRate(), baselineName, advantages, regressions);
        if (full.conflictFreeAssignments() && !baseline.conflictFreeAssignments()) {
            advantages.add("conflictFreeAssignments better than %s".formatted(baselineName));
        } else if (!full.conflictFreeAssignments() && baseline.conflictFreeAssignments()) {
            regressions.add("conflictFreeAssignments worse than %s".formatted(baselineName));
        }
    }

    private void compareHigherBetter(String metric,
                                     double fullValue,
                                     double baselineValue,
                                     String baselineName,
                                     List<String> advantages,
                                     List<String> regressions) {
        if (Double.compare(fullValue, baselineValue) > 0) {
            advantages.add("%s better than %s (%s > %s)".formatted(metric, baselineName, fullValue, baselineValue));
        } else if (Double.compare(fullValue, baselineValue) < 0) {
            regressions.add("%s worse than %s (%s < %s)".formatted(metric, baselineName, fullValue, baselineValue));
        }
    }

    private void compareLowerBetter(String metric,
                                    double fullValue,
                                    double baselineValue,
                                    String baselineName,
                                    List<String> advantages,
                                    List<String> regressions) {
        if (Double.compare(fullValue, baselineValue) < 0) {
            advantages.add("%s better than %s (%s < %s)".formatted(metric, baselineName, fullValue, baselineValue));
        } else if (Double.compare(fullValue, baselineValue) > 0) {
            regressions.add("%s worse than %s (%s > %s)".formatted(metric, baselineName, fullValue, baselineValue));
        }
    }

    private List<String> deltaSummary(DispatchQualityMetrics control, DispatchQualityMetrics variant) {
        List<String> lines = new ArrayList<>();
        lines.add("selectedProposalCount delta=" + (variant.selectedProposalCount() - control.selectedProposalCount()));
        lines.add("executedAssignmentCount delta=" + (variant.executedAssignmentCount() - control.executedAssignmentCount()));
        lines.add("bundleRate delta=" + (variant.bundleRate() - control.bundleRate()));
        lines.add("robustUtilityAverage delta=" + (variant.robustUtilityAverage() - control.robustUtilityAverage()));
        lines.add("selectorObjectiveValue delta=" + (variant.selectorObjectiveValue() - control.selectorObjectiveValue()));
        return List.copyOf(lines);
    }

    private DispatchQualityMetrics metricsFrom(DispatchV2Result result) {
        int executedAssignmentCount = result.dispatchExecutionSummary().executedAssignmentCount();
        int selectedProposalCount = result.globalSelectionResult().selectedCount();
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
        boolean conflictFree = conflictFreeAssignments(result);
        boolean executionValid = executedAssignmentCount <= selectedProposalCount
                && result.dispatchExecutionSummary().resolvedButRejectedCount() <= result.dispatchExecutionSummary().skippedProposalCount();
        return new DispatchQualityMetrics(
                "dispatch-quality-metrics/v1",
                selectedProposalCount,
                executedAssignmentCount,
                conflictFree,
                executionValid,
                executedAssignmentCount == 0 ? 0.0 : bundledAssignments / (double) executedAssignmentCount,
                averageBundleSize,
                routeFallbackRate(result),
                averagePickupEta,
                averageCompletionEta,
                landingValueAverage,
                robustUtilityAverage,
                result.globalSelectionResult().objectiveValue(),
                routeCostQuality(result),
                driverEntryQuality(result),
                burstRobustness(result),
                dispatchRegretAverage(result),
                courierUtilizationEstimate(result),
                distinctDegrades(result).isEmpty() ? 0.0 : 1.0,
                fallbackRate(result.mlStageMetadata().stream().map(MlStageMetadata::fallbackUsed).toList()),
                fallbackRate(result.liveStageMetadata().stream().map(LiveStageMetadata::fallbackUsed).toList()));
    }

    private double routeFallbackRate(DispatchV2Result result) {
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

    private boolean containsFallbackSignal(List<String> reasons) {
        return reasons.stream()
                .filter(reason -> reason != null)
                .map(reason -> reason.toLowerCase(Locale.ROOT))
                .anyMatch(reason -> reason.contains("fallback"));
    }

    private double fallbackRate(List<Boolean> fallbackFlags) {
        if (fallbackFlags.isEmpty()) {
            return 0.0;
        }
        long fallbacks = fallbackFlags.stream().filter(Boolean::booleanValue).count();
        return fallbacks / (double) fallbackFlags.size();
    }

    private boolean conflictFreeAssignments(DispatchV2Result result) {
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

    private List<String> distinctDegrades(DispatchV2Result result) {
        return distinctSources(java.util.stream.Stream.of(
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

    private List<String> distinctSources(List<String> values) {
        return values.stream()
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .sorted(Comparator.naturalOrder())
                .toList();
    }

    private DispatchQualityMetrics emptyMetrics() {
        return new DispatchQualityMetrics(
                "dispatch-quality-metrics/v1",
                0,
                0,
                true,
                true,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0);
    }

    static DispatchQualityTimeoutPhase classifyTimeoutPhase(Throwable throwable) {
        String joinedMessage = flattenThrowableMessages(throwable).toLowerCase(Locale.ROOT);
        if (joinedMessage.contains("task output") || joinedMessage.contains("task lock") || joinedMessage.contains("lock")) {
            return DispatchQualityTimeoutPhase.TASK_LOCK_TIMEOUT;
        }
        if (joinedMessage.contains("artifact") || joinedMessage.contains("markdown") || joinedMessage.contains("json write")) {
            return DispatchQualityTimeoutPhase.ARTIFACT_WRITE_TIMEOUT;
        }
        if (joinedMessage.contains("dispatch") || joinedMessage.contains("stage")) {
            return DispatchQualityTimeoutPhase.DISPATCH_TIMEOUT;
        }
        return DispatchQualityTimeoutPhase.UNKNOWN_TIMEOUT;
    }

    private static boolean isTimeoutFailure(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof java.util.concurrent.TimeoutException || current instanceof InterruptedException) {
                return true;
            }
            String message = blankToEmpty(current.getMessage()).toLowerCase(Locale.ROOT);
            if (message.contains("timeout") || message.contains("timed out")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static String flattenThrowableMessages(Throwable throwable) {
        List<String> messages = new ArrayList<>();
        Throwable current = throwable;
        while (current != null) {
            String message = blankToEmpty(current.getMessage());
            if (!message.isBlank()) {
                messages.add(message);
            }
            current = current.getCause();
        }
        return String.join(" | ", messages);
    }

    private DispatchQualityExecutionPolicy executionPolicy(BenchmarkRequest request) {
        boolean windows = isWindows();
        boolean heavyMode = windows
                && (request.authorityRun()
                || request.executionMode() == ExecutionMode.LOCAL_REAL
                || request.workloadSize() != DispatchPerfBenchmarkHarness.WorkloadSize.S);
        long perCellTimeoutMillis = switch (request.workloadSize()) {
            case S -> heavyMode ? 90_000L : 45_000L;
            case M -> heavyMode ? 180_000L : 120_000L;
            case L -> heavyMode ? 300_000L : 240_000L;
            case XL -> heavyMode ? 480_000L : 360_000L;
        };
        long totalHarnessTimeoutMillis = perCellTimeoutMillis * Math.max(1, request.baselines().size());
        return new DispatchQualityExecutionPolicy(
                heavyMode ? "windows-sequential-heavy" : "default-quality-harness",
                true,
                heavyMode,
                heavyMode,
                heavyMode,
                !request.runDeferredXl(),
                perCellTimeoutMillis,
                totalHarnessTimeoutMillis);
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win");
    }

    private static String osProfile() {
        return "%s %s (%s)".formatted(
                System.getProperty("os.name", "unknown-os"),
                System.getProperty("os.version", "unknown-version"),
                System.getProperty("os.arch", "unknown-arch"));
    }

    private RouteChainDispatchV2Properties baseProperties(DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                          DispatchBenchmarkDecisionMode decisionMode,
                                                          String promptFamily,
                                                          ExecutionMode executionMode,
                                                          Path feedbackDirectory) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        applyBenchmarkProfile(properties, configuredValue(
                "dispatchQuality.profile",
                "DISPATCH_QUALITY_PROFILE",
                ""));
        properties.getDecision().setMode(decisionMode.runtimeMode());
        properties.getDecision().setAuthoritativeStages(parseStages(configuredValue(
                "routechain.dispatch-v2.decision.authoritative-stages",
                "DISPATCH_QUALITY_AUTHORITATIVE_STAGES",
                String.join(",", decisionMode.authoritativeStages()))));
        properties.getDecision().getLlm().setBaseUrl(configuredValue(
                "routechain.dispatch-v2.decision.llm.base-url",
                "ROUTECHAIN_DECISION_LLM_BASE_URL",
                properties.getDecision().getLlm().getBaseUrl()));
        properties.getDecision().getLlm().setModel(configuredValue(
                "routechain.dispatch-v2.decision.llm.model",
                "ROUTECHAIN_DECISION_LLM_MODEL",
                properties.getDecision().getLlm().getModel()));
        properties.getDecision().getLlm().setPromptFamily(configuredValue(
                "routechain.dispatch-v2.decision.llm.prompt-family",
                "DISPATCH_QUALITY_PROMPT_FAMILY",
                promptFamily));
        properties.getMl().setModelManifestPath(configuredValue(
                "dispatchV2.ml.modelManifestPath",
                "IRX_MODEL_MANIFEST_PATH",
                properties.getMl().getModelManifestPath()));
        properties.getMl().getTabular().setBaseUrl(configuredValue(
                "dispatchV2.ml.tabular.baseUrl",
                "IRX_TABULAR_BASE_URL",
                properties.getMl().getTabular().getBaseUrl()));
        properties.getMl().getRoutefinder().setBaseUrl(configuredValue(
                "dispatchV2.ml.routefinder.baseUrl",
                "IRX_ROUTEFINDER_BASE_URL",
                properties.getMl().getRoutefinder().getBaseUrl()));
        properties.getMl().getGreedrl().setBaseUrl(configuredValue(
                "dispatchV2.ml.greedrl.baseUrl",
                "IRX_GREEDRL_BASE_URL",
                properties.getMl().getGreedrl().getBaseUrl()));
        properties.getMl().getForecast().setBaseUrl(configuredValue(
                "dispatchV2.ml.forecast.baseUrl",
                "IRX_FORECAST_BASE_URL",
                properties.getMl().getForecast().getBaseUrl()));
        properties.getWeather().setBaseUrl(configuredValue(
                "dispatchV2.weather.baseUrl",
                "IRX_OPEN_METEO_BASE_URL",
                properties.getWeather().getBaseUrl()));
        properties.getTraffic().setBaseUrl(configuredValue(
                "dispatchV2.traffic.baseUrl",
                "IRX_TOMTOM_BASE_URL",
                properties.getTraffic().getBaseUrl()));
        properties.getTraffic().setApiKey(configuredValue(
                "dispatchV2.traffic.apiKey",
                "IRX_TOMTOM_API_KEY",
                properties.getTraffic().getApiKey()));
        properties.setEnabled(true);
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
        if (feedbackDirectory != null) {
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

    private void applyBenchmarkProfile(RouteChainDispatchV2Properties properties, String profileName) {
        if (!"dispatch-v2-full-adaptive".equalsIgnoreCase(blankToEmpty(profileName))) {
            return;
        }
        properties.setEnabled(true);
        properties.setMlEnabled(true);
        properties.setSelectorOrtoolsEnabled(true);
        properties.setWarmStartEnabled(true);
        properties.setHotStartEnabled(true);
        properties.setTomtomEnabled(true);
        properties.setOpenMeteoEnabled(true);
        properties.getWeather().setEnabled(true);
        properties.getTraffic().setEnabled(true);
        properties.getMl().getTabular().setEnabled(true);
        properties.getMl().getRoutefinder().setEnabled(true);
        properties.getMl().getGreedrl().setEnabled(true);
        properties.getMl().getForecast().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setProfileName("dispatch-v2-full-adaptive");
        properties.getCompute().getAdaptive().setMachineProfile("local");
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(true);
        properties.getCompute().getAdaptive().setFailOpenWhenWorkerMetadataMissing(false);
        properties.getCompute().getAdaptive().setRoutefinderMaxTuplesPerDispatch(4);
        properties.getCompute().getAdaptive().setRoutefinderEtaAmbiguityThresholdMinutes(1.5);
        properties.getCompute().getAdaptive().setRoutefinderStopCountThreshold(3);
        properties.getCompute().getAdaptive().setRoutefinderWeatherEscalationEnabled(true);
        properties.getCompute().getAdaptive().setRoutefinderTrafficEscalationEnabled(true);
        properties.getCompute().getAdaptive().setRoutefinderBoundaryCrossEscalationEnabled(true);
        properties.getCompute().getAdaptive().setGreedrlMinWorkingOrders(4);
        properties.getCompute().getAdaptive().setGreedrlMinAcceptedBoundaryOrders(1);
        properties.getCompute().getAdaptive().setGreedrlSupportSpreadThreshold(0.12);
        properties.getCompute().getAdaptive().setForecastEnabledInHotPathByDefault(false);
        properties.getCompute().getAdaptive().setForecastAmbiguityThresholdMinutes(1.8);
        properties.getCompute().getAdaptive().setForecastMinProposalCount(2);
        properties.getCompute().getAdaptive().setForecastWeatherEscalationEnabled(true);
        properties.getCompute().getAdaptive().setForecastTrafficEscalationEnabled(true);
        properties.getDecision().getLlm().setBaseUrl("https://r8cp2m4.9router.com/v1");
    }

    private Path feedbackDirectory(BenchmarkRequest request,
                                   DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                   DispatchQualityExecutionPolicy executionPolicy) {
        Path root = executionPolicy.isolatedOutputRoots()
                ? request.outputRoot().resolve("cells").resolve(cellKey(request, baselineId))
                : request.outputRoot();
        return root
                .resolve("feedback")
                .resolve(request.scenarioPack().wireName())
                .resolve(request.workloadSize().name().toLowerCase(Locale.ROOT))
                .resolve(request.executionMode().wireName())
                .resolve(request.decisionMode().wireName())
                .resolve(request.promptFamily().toLowerCase(Locale.ROOT))
                .resolve(baselineId.name().toLowerCase(Locale.ROOT));
    }

    private Path feedbackDirectory(AblationRequest request, boolean control) {
        return request.outputRoot()
                .resolve("feedback")
                .resolve("ablation")
                .resolve(request.component().wireName())
                .resolve(request.scenarioPack().wireName())
                .resolve(control ? "control" : "variant");
    }

    private String traceFamilyId(BenchmarkRequest request, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
        return "quality-%s-%s-%s-%s-%s".formatted(
                request.scenarioPack().wireName(),
                request.workloadSize().name().toLowerCase(Locale.ROOT),
                request.decisionMode().wireName(),
                request.promptFamily().toLowerCase(Locale.ROOT),
                baselineId.name().toLowerCase(Locale.ROOT));
    }

    private String cellKey(BenchmarkRequest request, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
        return "%s-%s-%s-%s-%s-%s".formatted(
                request.scenarioPack().wireName(),
                request.workloadSize().name().toLowerCase(Locale.ROOT),
                request.executionMode().wireName(),
                request.decisionMode().wireName(),
                request.promptFamily().toLowerCase(Locale.ROOT),
                baselineId.name().toLowerCase(Locale.ROOT));
    }

    private DispatchQualityFeedbackSummary feedbackSummary(Path feedbackDirectory) {
        if (feedbackDirectory == null || !Files.exists(feedbackDirectory)) {
            return DispatchQualityFeedbackSummary.empty();
        }
        Path decisionStageRoot = feedbackDirectory.resolve("decision-stage");
        if (!Files.exists(decisionStageRoot)) {
            return DispatchQualityFeedbackSummary.empty();
        }
        List<JsonNode> joins = readFamily(decisionStageRoot, "decision_stage_join");
        List<JsonNode> outputs = readFamily(decisionStageRoot, "decision_stage_output");
        return new DispatchQualityFeedbackSummary(
                agreementSummary(joins),
                tokenUsageSummary(outputs),
                fallbackSummary(outputs));
    }

    private List<JsonNode> readFamily(Path decisionStageRoot, String family) {
        Path familyRoot = decisionStageRoot.resolve(family);
        if (!Files.exists(familyRoot)) {
            return List.of();
        }
        try (var stream = Files.list(familyRoot)) {
            return stream
                    .filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .map(this::readJson)
                    .filter(node -> node != null)
                    .toList();
        } catch (IOException exception) {
            return List.of();
        }
    }

    private JsonNode readJson(Path path) {
        try {
            return OBJECT_MAPPER.readTree(path.toFile());
        } catch (IOException exception) {
            return null;
        }
    }

    private DispatchLlmShadowAgreementSummary agreementSummary(List<JsonNode> joins) {
        if (joins.isEmpty()) {
            return DispatchLlmShadowAgreementSummary.empty();
        }
        Map<String, DispatchStageAgreementAccumulator> byStage = new LinkedHashMap<>();
        for (JsonNode join : joins) {
            String stageName = join.path("stageName").isTextual()
                    ? join.path("stageName").asText()
                    : join.path("stageName").path("wireName").asText("");
            if (stageName.isBlank()) {
                continue;
            }
            DispatchStageAgreementAccumulator accumulator = byStage.computeIfAbsent(stageName, ignored -> new DispatchStageAgreementAccumulator());
            boolean available = join.path("agreementAvailable").asBoolean(false);
            if (!available) {
                continue;
            }
            List<String> selectedIds = jsonTextList(join.path("selectedIds"));
            List<String> actualSelectedIds = jsonTextList(join.path("actualSelectedIds"));
            accumulator.comparisonCount++;
            if (selectedIds.equals(actualSelectedIds)) {
                accumulator.exactMatchCount++;
            }
        }
        List<DispatchDecisionStageAgreement> stageAgreements = byStage.entrySet().stream()
                .map(entry -> entry.getValue().toSummary(entry.getKey()))
                .toList();
        int comparedStages = stageAgreements.stream().mapToInt(DispatchDecisionStageAgreement::comparisonCount).sum();
        int exactMatches = stageAgreements.stream().mapToInt(DispatchDecisionStageAgreement::exactMatchCount).sum();
        double overallRate = comparedStages == 0 ? 0.0 : exactMatches / (double) comparedStages;
        return new DispatchLlmShadowAgreementSummary(
                "dispatch-llm-shadow-agreement-summary/v1",
                comparedStages,
                exactMatches,
                overallRate,
                stageAgreements);
    }

    private DispatchTokenUsageSummary tokenUsageSummary(List<JsonNode> outputs) {
        if (outputs.isEmpty()) {
            return DispatchTokenUsageSummary.empty();
        }
        long inputTokens = 0L;
        long outputTokens = 0L;
        long totalTokens = 0L;
        int requestCount = 0;
        for (JsonNode output : outputs) {
            JsonNode tokenUsage = output.path("meta").path("tokenUsage");
            if (tokenUsage.isMissingNode() || tokenUsage.isNull() || tokenUsage.isEmpty()) {
                continue;
            }
            requestCount++;
            long prompt = firstLong(tokenUsage, "inputTokens", "input_tokens", "promptTokens", "prompt_tokens");
            long completion = firstLong(tokenUsage, "outputTokens", "output_tokens", "completionTokens", "completion_tokens");
            long total = firstLong(tokenUsage, "totalTokens", "total_tokens");
            inputTokens += prompt;
            outputTokens += completion;
            totalTokens += total > 0 ? total : prompt + completion;
        }
        if (requestCount == 0) {
            return DispatchTokenUsageSummary.empty();
        }
        return new DispatchTokenUsageSummary(
                "dispatch-token-usage-summary/v1",
                requestCount,
                inputTokens,
                outputTokens,
                totalTokens);
    }

    private DispatchStageFallbackSummary fallbackSummary(List<JsonNode> outputs) {
        if (outputs.isEmpty()) {
            return DispatchStageFallbackSummary.empty();
        }
        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, String> reasons = new LinkedHashMap<>();
        int totalFallbacks = 0;
        for (JsonNode output : outputs) {
            JsonNode meta = output.path("meta");
            if (!meta.path("fallbackUsed").asBoolean(false)) {
                continue;
            }
            String stageName = output.path("stageName").isTextual()
                    ? output.path("stageName").asText()
                    : output.path("stageName").path("wireName").asText("");
            if (stageName.isBlank()) {
                continue;
            }
            totalFallbacks++;
            counts.merge(stageName, 1, Integer::sum);
            String reason = meta.path("fallbackReason").asText("");
            if (!reason.isBlank()) {
                reasons.put(stageName, reason);
            }
        }
        return new DispatchStageFallbackSummary(
                "dispatch-stage-fallback-summary/v1",
                outputs.size(),
                totalFallbacks,
                counts,
                reasons);
    }

    private List<DispatchStagePromotionBlocker> promotionBlockers(BenchmarkRequest request,
                                                                  List<String> authoritativeStages,
                                                                  MlAttachDiagnostics diagnostics,
                                                                  DispatchQualityFeedbackSummary feedbackSummary,
                                                                  DispatchRouteVectorMetrics routeVectorMetrics) {
        return PROMOTION_BLOCKER_STAGES.stream()
                .map(stageName -> promotionBlocker(request, authoritativeStages, diagnostics, feedbackSummary, routeVectorMetrics, stageName))
                .toList();
    }

    private DispatchStagePromotionBlocker promotionBlocker(BenchmarkRequest request,
                                                           List<String> authoritativeStages,
                                                           MlAttachDiagnostics diagnostics,
                                                           DispatchQualityFeedbackSummary feedbackSummary,
                                                           DispatchRouteVectorMetrics routeVectorMetrics,
                                                           String stageName) {
        int fallbackCount = feedbackSummary.stageFallbackSummary().fallbackCountsByStage().getOrDefault(stageName, 0);
        String fallbackReason = feedbackSummary.stageFallbackSummary().latestFallbackReasonByStage().getOrDefault(stageName, "");
        int providerErrorCount = fallbackReason.contains("provider-http-error") ? 1 : 0;
        double routeCoverage = requiresRouteVectorCoverage(stageName) ? routeVectorMetrics.geometryCoverage() : 1.0;
        boolean tokenUsagePresent = feedbackSummary.tokenUsageSummary().requestCount() > 0;
        boolean authoritativeCandidate = authoritativeStages.contains(stageName)
                || request.decisionMode().authoritativeStages().contains(stageName);
        List<String> blockerReasons = new ArrayList<>();
        if (!authoritativeCandidate && request.decisionMode() == DispatchBenchmarkDecisionMode.LLM_AUTHORITATIVE) {
            blockerReasons.add("not-in-authoritative-stage-set");
        }
        if (fallbackCount > 0) {
            blockerReasons.add("fallback-count:" + fallbackCount);
        }
        if (providerErrorCount > 0) {
            blockerReasons.add("provider-http-error");
        }
        if (requiresRouteVectorCoverage(stageName) && routeCoverage < 1.0) {
            blockerReasons.add("route-vector-coverage-below-1.0");
        }
        if (request.decisionMode() != DispatchBenchmarkDecisionMode.LEGACY && !tokenUsagePresent) {
            blockerReasons.add("token-usage-missing");
        }
        if (diagnostics.mlAttachStatus() != DispatchQualityMlAttachStatus.ATTACHED) {
            blockerReasons.add("ml-attach-" + diagnostics.mlAttachStatus().name().toLowerCase(Locale.ROOT));
        }
        return new DispatchStagePromotionBlocker(
                stageName,
                authoritativeCandidate,
                fallbackCount,
                providerErrorCount,
                routeCoverage,
                tokenUsagePresent,
                diagnostics.mlAttachStatus(),
                blockerReasons.isEmpty(),
                List.copyOf(blockerReasons));
    }

    private boolean requiresRouteVectorCoverage(String stageName) {
        return DecisionStageName.ROUTE_CRITIQUE.wireName().equals(stageName)
                || DecisionStageName.ROUTE_GENERATION.wireName().equals(stageName);
    }

    private List<String> jsonTextList(JsonNode node) {
        if (node == null || !node.isArray()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode child : node) {
            if (child.isTextual()) {
                values.add(child.asText());
            }
        }
        return List.copyOf(values);
    }

    private long firstLong(JsonNode node, String... fieldNames) {
        for (String fieldName : fieldNames) {
            JsonNode field = node.get(fieldName);
            if (field != null && field.isNumber()) {
                return field.asLong();
            }
        }
        return 0L;
    }

    private DispatchRouteVectorMetrics routeVectorMetrics(DispatchV2Result result) {
        List<RouteProposal> proposals = result.routeProposals();
        if (proposals == null || proposals.isEmpty()) {
            return DispatchRouteVectorMetrics.empty();
        }
        long geometryAvailable = proposals.stream().filter(RouteProposal::geometryAvailable).count();
        double bestTravelTime = proposals.stream().mapToDouble(RouteProposal::totalTravelTimeSeconds).filter(value -> value > 0.0).min().orElse(0.0);
        double bestRouteCost = proposals.stream().mapToDouble(RouteProposal::routeCost).filter(value -> value > 0.0).min().orElse(0.0);
        return new DispatchRouteVectorMetrics(
                "dispatch-route-vector-metrics/v1",
                proposals.size(),
                geometryAvailable / (double) proposals.size(),
                proposals.stream().mapToDouble(RouteProposal::totalDistanceMeters).average().orElse(0.0),
                proposals.stream().mapToDouble(RouteProposal::totalTravelTimeSeconds).average().orElse(0.0),
                proposals.stream().mapToDouble(RouteProposal::routeCost).average().orElse(0.0),
                proposals.stream().mapToDouble(RouteProposal::congestionScore).average().orElse(0.0),
                proposals.stream().mapToDouble(RouteProposal::majorRoadRatio).average().orElse(0.0),
                proposals.stream().mapToDouble(RouteProposal::straightnessScore).average().orElse(0.0),
                proposals.stream().mapToInt(RouteProposal::turnCount).average().orElse(0.0),
                routeDominanceRate(proposals, bestTravelTime, bestRouteCost),
                averageRouteRegret(result, bestRouteCost),
                proposals.stream().mapToDouble(RouteProposal::straightnessScore).average().orElse(0.0),
                averageEtaDominanceScore(proposals, bestTravelTime));
    }

    private double dispatchRegretAverage(DispatchV2Result result) {
        List<RouteProposal> proposals = result.routeProposals();
        if (proposals.isEmpty()) {
            return 0.0;
        }
        double bestRouteValue = proposals.stream().mapToDouble(RouteProposal::routeValue).max().orElse(0.0);
        if (bestRouteValue <= 0.0) {
            return 0.0;
        }
        return selectedRouteProposals(result).stream()
                .mapToDouble(proposal -> Math.max(0.0, bestRouteValue - proposal.routeValue()))
                .average()
                .orElse(0.0);
    }

    private double routeCostQuality(DispatchV2Result result) {
        List<RouteProposal> selected = selectedRouteProposals(result);
        if (selected.isEmpty()) {
            return 0.0;
        }
        double bestRouteCost = result.routeProposals().stream().mapToDouble(RouteProposal::routeCost).filter(value -> value > 0.0).min().orElse(0.0);
        if (bestRouteCost <= 0.0) {
            return 0.0;
        }
        return selected.stream()
                .mapToDouble(proposal -> Math.max(0.0, 1.0 - ((proposal.routeCost() - bestRouteCost) / bestRouteCost)))
                .average()
                .orElse(0.0);
    }

    private double driverEntryQuality(DispatchV2Result result) {
        if (result.driverCandidates().isEmpty()) {
            return 0.0;
        }
        Set<String> selectedIds = result.globalSelectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .collect(java.util.stream.Collectors.toSet());
        Map<String, Double> driverFitByProposal = result.routeProposals().stream()
                .collect(java.util.stream.Collectors.toMap(
                        RouteProposal::proposalId,
                        proposal -> result.driverCandidates().stream()
                                .filter(candidate -> candidate.driverId().equals(proposal.driverId())
                                        && candidate.bundleId().equals(proposal.bundleId())
                                        && candidate.anchorOrderId().equals(proposal.anchorOrderId()))
                                .mapToDouble(DriverCandidate::driverFitScore)
                                .max()
                                .orElse(0.0),
                        (left, right) -> left));
        return selectedIds.stream()
                .mapToDouble(proposalId -> driverFitByProposal.getOrDefault(proposalId, 0.0))
                .average()
                .orElse(0.0);
    }

    private double burstRobustness(DispatchV2Result result) {
        if (result.robustUtilities().isEmpty()) {
            return 0.0;
        }
        return result.robustUtilities().stream()
                .mapToDouble(utility -> {
                    if (utility.expectedValue() == 0.0) {
                        return utility.stabilityScore();
                    }
                    return Math.max(0.0, Math.min(1.0, utility.worstCaseValue() / Math.max(1.0, utility.expectedValue())));
                })
                .average()
                .orElse(0.0);
    }

    private double courierUtilizationEstimate(DispatchV2Result result) {
        long driverCount = result.driverCandidates().stream().map(candidate -> candidate.driverId()).distinct().count();
        if (driverCount <= 0) {
            return 0.0;
        }
        return result.dispatchExecutionSummary().executedAssignmentCount() / (double) driverCount;
    }

    private double routeDominanceRate(List<RouteProposal> proposals, double bestTravelTime, double bestRouteCost) {
        if (proposals.isEmpty() || bestTravelTime <= 0.0 || bestRouteCost <= 0.0) {
            return 0.0;
        }
        long dominated = proposals.stream()
                .filter(proposal -> proposal.totalTravelTimeSeconds() > bestTravelTime * 1.15
                        && proposal.routeCost() > bestRouteCost * 1.10)
                .count();
        return dominated / (double) proposals.size();
    }

    private double averageRouteRegret(DispatchV2Result result, double bestRouteCost) {
        if (bestRouteCost <= 0.0) {
            return 0.0;
        }
        return selectedRouteProposals(result).stream()
                .mapToDouble(proposal -> Math.max(0.0, proposal.routeCost() - bestRouteCost))
                .average()
                .orElse(0.0);
    }

    private double averageEtaDominanceScore(List<RouteProposal> proposals, double bestTravelTime) {
        if (proposals.isEmpty() || bestTravelTime <= 0.0) {
            return 0.0;
        }
        return proposals.stream()
                .filter(proposal -> proposal.totalTravelTimeSeconds() > 0.0)
                .mapToDouble(proposal -> bestTravelTime / proposal.totalTravelTimeSeconds())
                .average()
                .orElse(0.0);
    }

    private List<RouteProposal> selectedRouteProposals(DispatchV2Result result) {
        Set<String> selectedIds = result.globalSelectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .collect(java.util.stream.Collectors.toSet());
        return result.routeProposals().stream()
                .filter(proposal -> selectedIds.contains(proposal.proposalId()))
                .toList();
    }

    private DispatchIntelligenceMetrics intelligenceMetrics(DispatchV2Result result,
                                                            DispatchQualityFeedbackSummary feedbackSummary,
                                                            ScenarioPack scenarioPack) {
        int tokenTotal = (int) feedbackSummary.tokenUsageSummary().totalTokens();
        int goodDecisionCount = Math.max(1, result.dispatchExecutionSummary().executedAssignmentCount());
        double contextEfficiency = goodDecisionCount / (double) Math.max(1, tokenTotal);
        double stageCoherence = feedbackSummary.llmShadowAgreement().overallExactMatchRate();
        if (stageCoherence == 0.0 && !result.decisionStages().isEmpty()) {
            stageCoherence = 1.0 - routeFallbackRate(result);
        }
        double fallbackRecoveryQuality = 1.0 - fallbackRate(result.mlStageMetadata().stream().map(MlStageMetadata::fallbackUsed).toList());
        double adaptationQuality = switch (scenarioPack) {
            case HEAVY_RAIN, TRAFFIC_SHOCK, LIVE_SOURCE_DEGRADATION -> 1.0 - Math.min(1.0, routeFallbackRate(result));
            default -> 1.0;
        };
        double consistencyVariance = result.fallbackUsed() ? 1.0 : 0.0;
        return new DispatchIntelligenceMetrics(
                "dispatch-intelligence-metrics/v1",
                contextEfficiency,
                stageCoherence,
                fallbackRecoveryQuality,
                adaptationQuality,
                consistencyVariance,
                feedbackSummary.tokenUsageSummary().requestCount());
    }

    private String runtimeClassification(DispatchBenchmarkDecisionMode decisionMode, List<String> authoritativeStages) {
        return switch (decisionMode) {
            case LEGACY -> "legacy-baseline";
            case LLM_SHADOW -> "llm-shadow";
            case LLM_AUTHORITATIVE -> authoritativeStages.contains(DecisionStageName.ROUTE_GENERATION.wireName())
                    ? "llm-full-primary"
                    : "llm-guarded-primary";
        };
    }

    private ScenarioDefinition scenarioDefinition(ScenarioPack scenarioPack) {
        return switch (scenarioPack) {
            case NORMAL_CLEAR -> new ScenarioDefinition() {
                @Override
                public void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        properties.getMl().getForecast().setEnabled(true);
                    }
                }

                @Override
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.NORMAL_CLEAR);
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
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    DispatchV2Request request = DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.HEAVY_RAIN);
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
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    DispatchV2Request request = DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.TRAFFIC_SHOCK);
                    return DispatchHotStartCertificationHarness.copyWithDecisionTime(
                            request,
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
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.DENSE_HOTSPOT);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        return appliedMlOnly().withForecastClient(TestForecastClient.applied());
                    }
                    return noOps();
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
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.LUNCH_PEAK);
                }

                @Override
                public ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                        return appliedMlOnly().withTabularClient(TestTabularScoringClient.notApplied("tabular-unavailable"));
                    }
                    return noOps();
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
                public DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId, DispatchPerfBenchmarkHarness.BaselineId baselineId) {
                    return DispatchPerfWorkloadFactory.request(workloadSize, traceId, DispatchPerfWorkloadFactory.ScenarioWorldProfile.DINNER_PEAK);
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

    private static ScenarioDependencies noOps() {
        return new ScenarioDependencies(
                new NoOpTabularScoringClient(),
                new NoOpRouteFinderClient(),
                new NoOpGreedRlClient(),
                new NoOpForecastClient(),
                new NoOpOpenMeteoClient(),
                new NoOpTomTomTrafficRefineClient());
    }

    private static ScenarioDependencies appliedMlOnly() {
        return new ScenarioDependencies(
                TestTabularScoringClient.applied(0.15),
                TestRouteFinderClient.applied(),
                TestGreedRlClient.applied(),
                TestForecastClient.applied(),
                new NoOpOpenMeteoClient(),
                new NoOpTomTomTrafficRefineClient());
    }

    private static ScenarioDependencies localRealDependencies(RouteChainDispatchV2Properties properties) {
        ManifestResolution manifestResolution = resolveManifest(properties);
        if (!manifestResolution.valid()) {
            return noOps();
        }
        String apiKey = System.getenv("TOMTOM_API_KEY");
        return new ScenarioDependencies(
                new HttpTabularScoringClient(
                        properties.getMl().getTabular().getBaseUrl(),
                        properties.getMl().getTabular().getConnectTimeout(),
                        properties.getMl().getTabular().getReadTimeout(),
                        manifestResolution.path()),
                new HttpRouteFinderClient(
                        properties.getMl().getRoutefinder().getBaseUrl(),
                        properties.getMl().getRoutefinder().getConnectTimeout(),
                        properties.getMl().getRoutefinder().getReadTimeout(),
                        manifestResolution.path()),
                new HttpGreedRlClient(
                        properties.getMl().getGreedrl().getBaseUrl(),
                        properties.getMl().getGreedrl().getConnectTimeout(),
                        properties.getMl().getGreedrl().getReadTimeout(),
                        manifestResolution.path()),
                new HttpForecastClient(
                        properties.getMl().getForecast().getBaseUrl(),
                        properties.getMl().getForecast().getConnectTimeout(),
                        properties.getMl().getForecast().getReadTimeout(),
                        manifestResolution.path()),
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

    private MlAttachDiagnostics collectAttachDiagnostics(RouteChainDispatchV2Properties properties,
                                                         ScenarioDependencies dependencies) {
        ManifestResolution manifestResolution = resolveManifest(properties);
        Map<String, WorkerManifest.WorkerManifestEntry> manifestEntries = loadManifestEntries(manifestResolution);
        List<DispatchQualityWorkerStatus> workers = List.of(
                workerStatus(TABULAR_WORKER, properties.isMlEnabled() && properties.getMl().getTabular().isEnabled(), properties.getMl().getTabular().getBaseUrl(), dependencies.tabularScoringClient().readyState(), manifestEntries.get(TABULAR_WORKER)),
                workerStatus(ROUTEFINDER_WORKER, properties.isMlEnabled() && properties.getMl().getRoutefinder().isEnabled(), properties.getMl().getRoutefinder().getBaseUrl(), dependencies.routeFinderClient().readyState(), manifestEntries.get(ROUTEFINDER_WORKER)),
                workerStatus(GREEDRL_WORKER, properties.isMlEnabled() && properties.getMl().getGreedrl().isEnabled(), properties.getMl().getGreedrl().getBaseUrl(), dependencies.greedRlClient().readyState(), manifestEntries.get(GREEDRL_WORKER)),
                workerStatus(FORECAST_WORKER, properties.isMlEnabled() && properties.getMl().getForecast().isEnabled(), properties.getMl().getForecast().getBaseUrl(), dependencies.forecastClient().readyState(), manifestEntries.get(FORECAST_WORKER)));
        List<String> failureReasons = new ArrayList<>();
        failureReasons.addAll(manifestResolution.failureReasons());
        workers.stream()
                .filter(DispatchQualityWorkerStatus::enabled)
                .filter(worker -> !worker.ready())
                .map(worker -> worker.workerName() + ":" + blankToEmpty(worker.readyReason()))
                .forEach(failureReasons::add);
        return new MlAttachDiagnostics(
                manifestResolution.displayPath(),
                manifestResolution.exists(),
                workerBaseUrls(properties),
                activeMlFlags(properties),
                workers,
                DispatchQualityMlAttachStatus.ATTACHED,
                List.copyOf(distinctSources(failureReasons)));
    }

    private MlAttachDiagnostics finalizeAttachDiagnostics(RouteChainDispatchV2Properties properties,
                                                          DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                          boolean authorityRun,
                                                          MlAttachDiagnostics diagnostics,
                                                          DispatchV2Result result) {
        List<String> workerAppliedSources = distinctSources(result.mlStageMetadata().stream()
                .filter(MlStageMetadata::applied)
                .map(MlStageMetadata::sourceModel)
                .toList());
        List<DispatchQualityWorkerStatus> updatedWorkers = diagnostics.workerStatusSnapshot().stream()
                .map(worker -> applyRunObservation(worker, workerAppliedSources))
                .toList();
        List<String> failureReasons = new ArrayList<>(diagnostics.mlAttachmentFailureReasons());
        if (properties.isMlEnabled() && authorityRun && baselineId == DispatchPerfBenchmarkHarness.BaselineId.C && workerAppliedSources.isEmpty()) {
            failureReasons.add("worker-applied-sources-empty");
        }
        DispatchQualityMlAttachStatus status = classifyAttachStatus(properties, baselineId, authorityRun, updatedWorkers, workerAppliedSources);
        return new MlAttachDiagnostics(
                diagnostics.resolvedModelManifestPath(),
                diagnostics.manifestExists(),
                diagnostics.workerBaseUrls(),
                diagnostics.activeMlFlags(),
                updatedWorkers,
                status,
                List.copyOf(distinctSources(failureReasons)));
    }

    private static DispatchQualityWorkerStatus applyRunObservation(DispatchQualityWorkerStatus worker, List<String> workerAppliedSources) {
        boolean applied = !blankToEmpty(worker.sourceModel()).isBlank() && workerAppliedSources.contains(worker.sourceModel());
        String notAppliedReason = applied ? "" : (worker.ready() ? "worker-not-observed-in-run" : worker.readyReason());
        return new DispatchQualityWorkerStatus(
                worker.workerName(),
                worker.enabled(),
                worker.baseUrl(),
                worker.reachable(),
                worker.ready(),
                worker.readyReason(),
                worker.sourceModel(),
                worker.modelVersion(),
                worker.artifactDigest(),
                worker.loadedFromLocal(),
                worker.expectedFingerprint(),
                worker.fingerprintMatch(),
                worker.device(),
                worker.dtype(),
                worker.gpuMemoryAllocatedMb(),
                worker.batchSize(),
                worker.compileMode(),
                worker.modelLoaded(),
                worker.warmupDone(),
                worker.workerAuditPresent(),
                worker.workerAuditSource(),
                worker.workerAuditMissingFields(),
                applied,
                blankToEmpty(notAppliedReason));
    }

    private static DispatchQualityMlAttachStatus classifyAttachStatus(RouteChainDispatchV2Properties properties,
                                                                      DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                                      boolean authorityRun,
                                                                      List<DispatchQualityWorkerStatus> workers,
                                                                      List<String> workerAppliedSources) {
        long enabledWorkers = workers.stream().filter(DispatchQualityWorkerStatus::enabled).count();
        long readyWorkers = workers.stream().filter(DispatchQualityWorkerStatus::enabled).filter(DispatchQualityWorkerStatus::ready).count();
        long appliedWorkers = workers.stream().filter(DispatchQualityWorkerStatus::enabled).filter(DispatchQualityWorkerStatus::applied).count();
        if (!properties.isMlEnabled() || enabledWorkers == 0) {
            return DispatchQualityMlAttachStatus.ATTACHED;
        }
        if (authorityRun
                && baselineId == DispatchPerfBenchmarkHarness.BaselineId.C
                && workerAppliedSources.isEmpty()) {
            return readyWorkers > 0 ? DispatchQualityMlAttachStatus.PARTIAL_ATTACH : DispatchQualityMlAttachStatus.ML_ATTACH_FAIL;
        }
        if (appliedWorkers == 0 && workerAppliedSources.isEmpty()) {
            return readyWorkers > 0 ? DispatchQualityMlAttachStatus.PARTIAL_ATTACH : DispatchQualityMlAttachStatus.ML_ATTACH_FAIL;
        }
        return appliedWorkers < enabledWorkers ? DispatchQualityMlAttachStatus.PARTIAL_ATTACH : DispatchQualityMlAttachStatus.ATTACHED;
    }

    private static DispatchQualityWorkerStatus workerStatus(String workerName,
                                                            boolean enabled,
                                                            String baseUrl,
                                                            WorkerReadyState readyState,
                                                            WorkerManifest.WorkerManifestEntry manifestEntry) {
        MlWorkerMetadata metadata = readyState == null ? MlWorkerMetadata.empty() : readyState.workerMetadata();
        boolean ready = enabled && readyState != null && readyState.ready();
        String readyReason = enabled
                ? (ready ? "" : readyState == null ? "worker-state-missing" : blankToEmpty(readyState.reason()))
                : "worker-disabled";
        return new DispatchQualityWorkerStatus(
                workerName,
                enabled,
                blankToEmpty(baseUrl),
                enabled && isReachable(readyReason),
                ready,
                blankToEmpty(readyReason),
                firstNonBlank(metadata.sourceModel(), manifestEntry == null ? "" : manifestEntry.modelName()),
                firstNonBlank(metadata.modelVersion(), manifestEntry == null ? "" : manifestEntry.modelVersion()),
                firstNonBlank(metadata.artifactDigest(), manifestEntry == null ? "" : manifestEntry.artifactDigest()),
                loadedFromLocal(manifestEntry, readyState),
                manifestEntry == null ? "" : blankToEmpty(manifestEntry.loadedModelFingerprint()),
                fingerprintMatch(manifestEntry, readyState),
                blankToEmpty(metadata.device()),
                blankToEmpty(metadata.dtype()),
                metadata.gpuMemoryAllocatedMb(),
                metadata.batchSize(),
                blankToEmpty(metadata.compileMode()),
                metadata.modelLoaded(),
                metadata.warmupDone(),
                MlWorkerAuditSupport.auditPresent(metadata),
                MlWorkerAuditSupport.auditSource(metadata),
                MlWorkerAuditSupport.missingFields(metadata),
                false,
                ready ? "" : blankToEmpty(readyReason));
    }

    private static Map<String, String> workerBaseUrls(RouteChainDispatchV2Properties properties) {
        return Map.of(
                TABULAR_WORKER, properties.getMl().getTabular().getBaseUrl(),
                ROUTEFINDER_WORKER, properties.getMl().getRoutefinder().getBaseUrl(),
                GREEDRL_WORKER, properties.getMl().getGreedrl().getBaseUrl(),
                FORECAST_WORKER, properties.getMl().getForecast().getBaseUrl());
    }

    private static Map<String, Boolean> activeMlFlags(RouteChainDispatchV2Properties properties) {
        return Map.of(
                "mlEnabled", properties.isMlEnabled(),
                "sidecarRequired", properties.isSidecarRequired(),
                "tabularEnabled", properties.getMl().getTabular().isEnabled(),
                "routefinderEnabled", properties.getMl().getRoutefinder().isEnabled(),
                "greedrlEnabled", properties.getMl().getGreedrl().isEnabled(),
                "forecastEnabled", properties.getMl().getForecast().isEnabled());
    }

    private static Map<String, WorkerManifest.WorkerManifestEntry> loadManifestEntries(ManifestResolution manifestResolution) {
        if (!manifestResolution.valid()) {
            return Map.of();
        }
        try {
            WorkerManifest manifest = new ModelManifestLoader().load(manifestResolution.path());
            Map<String, WorkerManifest.WorkerManifestEntry> entries = new LinkedHashMap<>();
            for (WorkerManifest.WorkerManifestEntry entry : manifest.workers()) {
                entries.put(entry.workerName(), entry);
            }
            return Map.copyOf(entries);
        } catch (RuntimeException exception) {
            return Map.of();
        }
    }

    private static ManifestResolution resolveManifest(RouteChainDispatchV2Properties properties) {
        String configuredPath = blankToEmpty(properties.getMl().getModelManifestPath());
        if (configuredPath.isBlank()) {
            return new ManifestResolution(null, "", false, List.of("model-manifest-path-blank"));
        }
        try {
            Path resolved = Path.of(configuredPath).toAbsolutePath().normalize();
            if (!Files.exists(resolved)) {
                return new ManifestResolution(resolved, resolved.toString(), false, List.of("model-manifest-missing"));
            }
            return new ManifestResolution(resolved, resolved.toString(), true, List.of());
        } catch (InvalidPathException exception) {
            return new ManifestResolution(null, configuredPath, false, List.of("model-manifest-path-invalid"));
        }
    }

    private static String configuredValue(String propertyName, String envName, String defaultValue) {
        String propertyValue = System.getProperty(propertyName);
        if (propertyValue != null && !propertyValue.isBlank()) {
            return propertyValue;
        }
        String envValue = System.getenv(envName);
        if (envValue != null && !envValue.isBlank()) {
            return envValue;
        }
        return defaultValue;
    }

    private static List<String> parseStages(String rawValue) {
        if (rawValue == null || rawValue.isBlank()) {
            return List.of();
        }
        return java.util.Arrays.stream(rawValue.split(","))
                .map(String::trim)
                .filter(token -> !token.isBlank())
                .toList();
    }

    private static boolean isReachable(String readyReason) {
        String normalized = blankToEmpty(readyReason).toLowerCase(Locale.ROOT);
        return !(normalized.contains("client-disabled")
                || normalized.contains("worker-unreachable")
                || normalized.contains("manifest-worker-missing")
                || normalized.contains("model-manifest"));
    }

    private static Boolean loadedFromLocal(WorkerManifest.WorkerManifestEntry manifestEntry, WorkerReadyState readyState) {
        if (manifestEntry == null || !Boolean.TRUE.equals(manifestEntry.readyRequiresLocalLoad()) || readyState == null) {
            return null;
        }
        if (readyState.ready()) {
            return true;
        }
        if ("local-model-not-loaded".equals(readyState.reason())) {
            return false;
        }
        if ("loaded-model-fingerprint-mismatch".equals(readyState.reason())) {
            return true;
        }
        return null;
    }

    private static Boolean fingerprintMatch(WorkerManifest.WorkerManifestEntry manifestEntry, WorkerReadyState readyState) {
        if (manifestEntry == null || blankToEmpty(manifestEntry.loadedModelFingerprint()).isBlank() || readyState == null) {
            return null;
        }
        if (readyState.ready()) {
            return true;
        }
        if ("loaded-model-fingerprint-mismatch".equals(readyState.reason())) {
            return false;
        }
        return null;
    }

    private static String firstNonBlank(String first, String second) {
        return !blankToEmpty(first).isBlank() ? blankToEmpty(first) : blankToEmpty(second);
    }

    private static String blankToEmpty(String value) {
        return value == null ? "" : value;
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
            List<DispatchPerfBenchmarkHarness.BaselineId> baselines,
            DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
            ScenarioPack scenarioPack,
            DispatchBenchmarkDecisionMode decisionMode,
            String promptFamily,
            ExecutionMode executionMode,
            String machineLabel,
            boolean authorityRun,
            boolean runDeferredXl,
            Path outputRoot) {
    }

    public record AblationRequest(
            AblationComponent component,
            DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
            ScenarioPack scenarioPack,
            ExecutionMode executionMode,
            boolean runDeferredXl,
            Path outputRoot) {
    }

    public enum ExecutionMode {
        CONTROLLED("controlled"),
        LOCAL_REAL("local-real");

        private final String wireName;

        ExecutionMode(String wireName) {
            this.wireName = wireName;
        }

        public String wireName() {
            return wireName;
        }
    }

    public enum ScenarioPack {
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

        public String wireName() {
            return wireName;
        }

        public static ScenarioPack fromWire(String value) {
            return EnumSet.allOf(ScenarioPack.class).stream()
                    .filter(pack -> pack.wireName.equals(value))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("Unknown scenario pack: " + value));
        }
    }

    public enum AblationComponent {
        TABULAR("tabular"),
        ROUTEFINDER("routefinder"),
        GREEDRL("greedrl"),
        FORECAST("forecast"),
        TOMTOM("tomtom"),
        OPEN_METEO("open-meteo"),
        ORTOOLS("ortools"),
        HOT_START("hot-start");

        private final String wireName;

        AblationComponent(String wireName) {
            this.wireName = wireName;
        }

        public String wireName() {
            return wireName;
        }

        public static AblationComponent fromWire(String value) {
            return EnumSet.allOf(AblationComponent.class).stream()
                    .filter(component -> component.wireName.equals(value))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("Unknown ablation component: " + value));
        }
    }

    private interface ScenarioDefinition {
        void configureProperties(RouteChainDispatchV2Properties properties, DispatchPerfBenchmarkHarness.BaselineId baselineId);

        DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                  String traceId,
                                  DispatchPerfBenchmarkHarness.BaselineId baselineId);

        ScenarioDependencies controlledDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId);

        default ScenarioDependencies localRealDependencies(DispatchPerfBenchmarkHarness.BaselineId baselineId,
                                                           RouteChainDispatchV2Properties properties) {
            ScenarioDependencies realDependencies = DispatchQualityBenchmarkHarness.localRealDependencies(properties);
            if (baselineId == DispatchPerfBenchmarkHarness.BaselineId.C) {
                return realDependencies;
            }
            return DispatchQualityBenchmarkHarness.noOps()
                    .withOpenMeteoClient(realDependencies.openMeteoClient())
                    .withTomTomTrafficRefineClient(realDependencies.tomTomTrafficRefineClient());
        }
    }

    private record ScenarioDependencies(
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

    private record ScenarioExecution(
            DispatchV2Result result,
            MlAttachDiagnostics attachDiagnostics,
            List<String> authoritativeStages) {
    }

    private record MlAttachDiagnostics(
            String resolvedModelManifestPath,
            boolean manifestExists,
            Map<String, String> workerBaseUrls,
            Map<String, Boolean> activeMlFlags,
            List<DispatchQualityWorkerStatus> workerStatusSnapshot,
            DispatchQualityMlAttachStatus mlAttachStatus,
            List<String> mlAttachmentFailureReasons) {
    }

    private record ManifestResolution(
            Path path,
            String displayPath,
            boolean exists,
            List<String> failureReasons) {
        boolean valid() {
            return path != null && exists;
        }
    }

}
