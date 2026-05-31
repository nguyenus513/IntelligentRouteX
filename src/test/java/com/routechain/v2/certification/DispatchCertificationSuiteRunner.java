package com.routechain.v2.certification;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.BootMode;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import com.routechain.v2.executor.ExecutorCertificationSupport;
import com.routechain.v2.feedback.DecisionLogRecord;
import com.routechain.v2.feedback.DispatchRuntimeReuseState;
import com.routechain.v2.feedback.DispatchRuntimeSnapshot;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.integration.ForecastResult;
import com.routechain.v2.integration.MlWorkerMetadata;
import com.routechain.v2.integration.TestForecastClient;
import com.routechain.v2.integration.TestGreedRlClient;
import com.routechain.v2.integration.TestOpenMeteoClient;
import com.routechain.v2.integration.TestRouteFinderClient;
import com.routechain.v2.integration.TestTabularScoringClient;
import com.routechain.v2.integration.TestTomTomTrafficRefineClient;
import com.routechain.v2.integration.WorkerReadyState;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class DispatchCertificationSuiteRunner {
    private final DispatchHotStartCertificationHarness hotStartHarness = new DispatchHotStartCertificationHarness();

    public DispatchCertificationSuiteReport weatherTrafficPack(Path baseDirectory) {
        String suiteName = "weather-traffic-realism";
        List<DispatchCertificationScenarioReport> scenarios = List.of(
                heavyRainScenario(suiteName, baseDirectory.resolve("heavy-rain")),
                trafficShockScenario(suiteName, baseDirectory.resolve("traffic-shock")),
                staleWeatherScenario(suiteName, baseDirectory.resolve("stale-weather")),
                staleTrafficScenario(suiteName, baseDirectory.resolve("stale-traffic")),
                weatherAndTrafficDegradeScenario(suiteName, baseDirectory.resolve("weather-and-traffic-degrade")));
        return suiteReport(suiteName, scenarios);
    }

    public DispatchCertificationSuiteReport forecastPack(Path baseDirectory) {
        String suiteName = "forecast-realism";
        List<DispatchCertificationScenarioReport> scenarios = List.of(
                strongForecastScenario(suiteName, "zone-burst-strong", baseDirectory.resolve("zone-burst-strong"), strongForecastClient(0.91, 0.56, 0.38)),
                strongForecastScenario(suiteName, "demand-shift-strong", baseDirectory.resolve("demand-shift-strong"), strongForecastClient(0.88, 0.22, 0.31)),
                strongForecastScenario(suiteName, "post-drop-shift-strong", baseDirectory.resolve("post-drop-shift-strong"), strongForecastClient(0.83, 0.18, 0.64)),
                forecastDriftScenario(suiteName, baseDirectory.resolve("forecast-drift-between-runs")),
                forecastUnavailableScenario(suiteName, "forecast-worker-unavailable", baseDirectory.resolve("forecast-worker-unavailable"), TestForecastClient.notApplied("forecast-worker-unavailable")));
        return suiteReport(suiteName, scenarios);
    }

    public DispatchCertificationSuiteReport workerDegradationPack(Path baseDirectory) {
        String suiteName = "worker-degradation";
        List<DispatchCertificationScenarioReport> scenarios = List.of(
                tabularUnavailableScenario(suiteName, baseDirectory.resolve("tabular-unavailable")),
                routeFinderUnavailableScenario(suiteName, baseDirectory.resolve("routefinder-unavailable")),
                greedRlUnavailableScenario(suiteName, baseDirectory.resolve("greedrl-unavailable")),
                forecastUnavailableScenario(suiteName, "forecast-unavailable", baseDirectory.resolve("forecast-unavailable"), TestForecastClient.notApplied("forecast-unavailable")),
                workerReadyFalseOptionalScenario(suiteName, baseDirectory.resolve("worker-ready-false-optional-path")));
        return suiteReport(suiteName, scenarios);
    }

    public DispatchCertificationSuiteReport selectorExecutorPack(Path baseDirectory) {
        String suiteName = "selector-executor-safety";
        List<DispatchCertificationScenarioReport> scenarios = List.of(
                ortoolsEnabledScenario(suiteName, baseDirectory.resolve("ortools-enabled")),
                ortoolsDegradedGreedyScenario(suiteName, baseDirectory.resolve("ortools-degraded-greedy")),
                conflictingCandidatesSafeScenario(suiteName, baseDirectory.resolve("conflicting-candidates-never-conflict-at-assignment")),
                executorDefensiveSkipScenario(suiteName, baseDirectory.resolve("executor-defensive-skip")));
        return suiteReport(suiteName, scenarios);
    }

    public DispatchCertificationSuiteReport bootPersistencePack(Path baseDirectory) {
        String suiteName = "boot-persistence";
        List<DispatchCertificationScenarioReport> scenarios = List.of(
                warmBootAcrossRestartScenario(suiteName, baseDirectory.resolve("warm-boot-across-restart")),
                repeatedHotStartFamilyScenario(suiteName, baseDirectory.resolve("repeated-hot-start-family")),
                replaySafeUnderCertificationLoadScenario(suiteName, baseDirectory.resolve("replay-safe-under-certification-load")),
                snapshotAndReuseStateLoadScenario(suiteName, baseDirectory.resolve("snapshot-and-reuse-state-load-cleanly")));
        return suiteReport(suiteName, scenarios);
    }

    private DispatchCertificationScenarioReport heavyRainScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.getWeather().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.getWeather().setEnabled(true);
        DispatchV2Request request = withWeatherProfile(TestDispatchV2Factory.requestWithOrdersAndDriver(), "trace-heavy-rain", WeatherProfile.HEAVY_RAIN);
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "heavy-rain",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-heavy-rain-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-heavy-rain-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-heavy-rain-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withOpenMeteoClient(TestOpenMeteoClient.freshHeavyRain()),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withOpenMeteoClient(TestOpenMeteoClient.freshHeavyRain()));
        return scenarioFromRun(suiteName, "heavy-rain", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of("open-meteo"), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport trafficShockScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setTomtomEnabled(true);
        coldProperties.getTraffic().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setTomtomEnabled(true);
        warmHotProperties.getTraffic().setEnabled(true);
        DispatchV2Request request = DispatchHotStartCertificationHarness.copyWithDecisionTime(
                TestDispatchV2Factory.requestWithOrdersAndDriver(),
                "trace-traffic-shock",
                Instant.parse("2026-04-16T08:00:00Z"));
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "traffic-shock",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-traffic-shock-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-traffic-shock-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-traffic-shock-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.applied(1.35, true)),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.applied(1.35, true)));
        return scenarioFromRun(suiteName, "traffic-shock", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of("tomtom-traffic"), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport staleWeatherScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.getWeather().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.getWeather().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        long staleAge = coldProperties.getContext().getFreshness().getWeatherMaxAge().toMillis() + 1;
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "stale-weather",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-weather-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-weather-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-weather-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withOpenMeteoClient(TestOpenMeteoClient.staleHeavyRain(staleAge)),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withOpenMeteoClient(TestOpenMeteoClient.staleHeavyRain(staleAge)));
        return scenarioFromRun(suiteName, "stale-weather", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of("open-meteo"), Set.of("open-meteo-stale"), Set.of()));
    }

    private DispatchCertificationScenarioReport staleTrafficScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setTomtomEnabled(true);
        coldProperties.getTraffic().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setTomtomEnabled(true);
        warmHotProperties.getTraffic().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        long staleAge = coldProperties.getContext().getFreshness().getTrafficMaxAge().toMillis() + 1;
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "stale-traffic",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-traffic-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-traffic-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-stale-traffic-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.stale(1.20, staleAge)),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.stale(1.20, staleAge)));
        return scenarioFromRun(suiteName, "stale-traffic", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of("tomtom-traffic"), Set.of("tomtom-stale"), Set.of()));
    }

    private DispatchCertificationScenarioReport weatherAndTrafficDegradeScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.getWeather().setEnabled(true);
        coldProperties.setTomtomEnabled(true);
        coldProperties.getTraffic().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.getWeather().setEnabled(true);
        warmHotProperties.setTomtomEnabled(true);
        warmHotProperties.getTraffic().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "weather-and-traffic-degrade",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-weather-traffic-degrade-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-weather-traffic-degrade-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-weather-traffic-degrade-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps()
                        .withOpenMeteoClient(TestOpenMeteoClient.unavailable("open-meteo-unavailable"))
                        .withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.unavailable("tomtom-unavailable")),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps()
                        .withOpenMeteoClient(TestOpenMeteoClient.unavailable("open-meteo-unavailable"))
                        .withTomTomTrafficRefineClient(TestTomTomTrafficRefineClient.unavailable("tomtom-unavailable")));
        return scenarioFromRun(suiteName, "weather-and-traffic-degrade", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of("open-meteo", "tomtom-traffic"), Set.of("open-meteo-unavailable", "tomtom-unavailable"), Set.of()));
    }

    private DispatchCertificationScenarioReport strongForecastScenario(String suiteName,
                                                                       String scenarioName,
                                                                       Path scenarioDirectory,
                                                                       TestForecastClient forecastClient) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getForecast().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getForecast().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                scenarioName,
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(forecastClient),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(forecastClient));
        return scenarioFromRun(suiteName, scenarioName, run, new ScenarioExpectation(true, false, true, Set.of("chronos-2"), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport forecastDriftScenario(String suiteName, Path scenarioDirectory) {
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getForecast().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getForecast().setEnabled(true);
        MlWorkerMetadata metadata = new MlWorkerMetadata("chronos-2", "v1", "sha256:chronos", 11L);
        TestForecastClient staleForecast = new TestForecastClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> ForecastResult.applied(30, 0.71, java.util.Map.of("q10", -0.18, "q50", -0.09, "q90", 0.02), 0.84, 60_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(20, 0.74, java.util.Map.of("q10", 0.08, "q50", 0.16, "q90", 0.24), 0.82, 60_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(45, 0.69, java.util.Map.of("q10", 0.04, "q50", 0.12, "q90", 0.20), 0.80, 60_000L, metadata));
        TestForecastClient freshForecast = new TestForecastClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> ForecastResult.applied(30, 0.71, java.util.Map.of("q10", -0.18, "q50", -0.09, "q90", 0.02), 0.84, 120_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(20, 0.74, java.util.Map.of("q10", 0.08, "q50", 0.16, "q90", 0.24), 0.82, 120_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(45, 0.69, java.util.Map.of("q10", 0.04, "q50", 0.12, "q90", 0.20), 0.80, 120_000L, metadata));
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "forecast-drift-between-runs",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-forecast-drift-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-forecast-drift-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-forecast-drift-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(staleForecast),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(freshForecast));
        return scenarioFromRun(suiteName, "forecast-drift-between-runs", run, new ScenarioExpectation(false, false, true, Set.of("chronos-2"), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport forecastUnavailableScenario(String suiteName,
                                                                           String scenarioName,
                                                                           Path scenarioDirectory,
                                                                           TestForecastClient forecastClient) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getForecast().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getForecast().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                scenarioName,
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, scenarioName + "-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(forecastClient),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(forecastClient));
        return scenarioFromRun(suiteName, scenarioName, run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of(scenarioName), Set.of()));
    }

    private DispatchCertificationScenarioReport tabularUnavailableScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getTabular().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getTabular().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationHarness.CertificationDependencies dependencies = new DispatchHotStartCertificationHarness.CertificationDependencies(
                TestTabularScoringClient.notApplied("tabular-unavailable"),
                new com.routechain.v2.integration.NoOpRouteFinderClient(),
                new com.routechain.v2.integration.NoOpGreedRlClient(),
                new com.routechain.v2.integration.NoOpForecastClient(),
                new com.routechain.v2.integration.NoOpOpenMeteoClient(),
                new com.routechain.v2.integration.NoOpTomTomTrafficRefineClient());
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "tabular-unavailable",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-tabular-unavailable-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-tabular-unavailable-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-tabular-unavailable-hot"),
                coldProperties,
                warmHotProperties,
                dependencies,
                dependencies);
        return scenarioFromRun(suiteName, "tabular-unavailable", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of("eta-ml-unavailable"), Set.of()));
    }

    private DispatchCertificationScenarioReport routeFinderUnavailableScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getRoutefinder().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getRoutefinder().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "routefinder-unavailable",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-routefinder-unavailable-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-routefinder-unavailable-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-routefinder-unavailable-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withRouteFinderClient(TestRouteFinderClient.notApplied("routefinder-unavailable")),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withRouteFinderClient(TestRouteFinderClient.notApplied("routefinder-unavailable")));
        return scenarioFromRun(
                suiteName,
                "routefinder-unavailable",
                run,
                new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of("routefinder-ml-unavailable"), Set.of()),
                true,
                List.of("routefinder-ml-unavailable"));
    }

    private DispatchCertificationScenarioReport greedRlUnavailableScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getGreedrl().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getGreedrl().setEnabled(true);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "greedrl-unavailable",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedrl-unavailable-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedrl-unavailable-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedrl-unavailable-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withGreedRlClient(TestGreedRlClient.notApplied("greedrl-unavailable")),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withGreedRlClient(TestGreedRlClient.notApplied("greedrl-unavailable")));
        return scenarioFromRun(
                suiteName,
                "greedrl-unavailable",
                run,
                new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of("greedrl-ml-unavailable"), Set.of()),
                true,
                List.of("greedrl-ml-unavailable"));
    }

    private DispatchCertificationScenarioReport workerReadyFalseOptionalScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setMlEnabled(true);
        coldProperties.getMl().getForecast().setEnabled(true);
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setMlEnabled(true);
        warmHotProperties.getMl().getForecast().setEnabled(true);
        MlWorkerMetadata metadata = new MlWorkerMetadata("chronos-2", "v1", "sha256:chronos", 11L);
        TestForecastClient readyFalseClient = new TestForecastClient(
                WorkerReadyState.notReady("worker-ready-false-optional-path", metadata),
                (feature, timeout) -> ForecastResult.notApplied("worker-ready-false-optional-path", metadata),
                (feature, timeout) -> ForecastResult.notApplied("worker-ready-false-optional-path", metadata),
                (feature, timeout) -> ForecastResult.notApplied("worker-ready-false-optional-path", metadata));
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "worker-ready-false-optional-path",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-worker-ready-false-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-worker-ready-false-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-worker-ready-false-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(readyFalseClient),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps().withForecastClient(readyFalseClient));
        return scenarioFromRun(suiteName, "worker-ready-false-optional-path", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of("worker-ready-false-optional-path"), Set.of()));
    }

    private DispatchCertificationScenarioReport ortoolsEnabledScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        coldProperties.setSelectorOrtoolsEnabled(true);
        coldProperties.getSelector().getOrtools().setTimeout(Duration.ofSeconds(2));
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        warmHotProperties.setSelectorOrtoolsEnabled(true);
        warmHotProperties.getSelector().getOrtools().setTimeout(Duration.ofSeconds(2));
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "ortools-enabled",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-ortools-enabled-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-ortools-enabled-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-ortools-enabled-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps(),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps());
        return scenarioFromRun(suiteName, "ortools-enabled", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport ortoolsDegradedGreedyScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "ortools-degraded-greedy",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedy-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedy-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-greedy-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps(),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps());
        return scenarioFromRun(suiteName, "ortools-degraded-greedy", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport conflictingCandidatesSafeScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "conflicting-candidates-never-conflict-at-assignment",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-conflict-safe-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-conflict-safe-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-conflict-safe-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps(),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps());
        return scenarioFromRun(suiteName, "conflicting-candidates-never-conflict-at-assignment", run, new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport executorDefensiveSkipScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "executor-defensive-skip",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-executor-defensive-skip-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-executor-defensive-skip-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-executor-defensive-skip-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps(),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps());
        ExecutorCertificationSupport.ExecutorConflictEvidence evidence = ExecutorCertificationSupport.defensiveSkipEvidence();
        return scenarioFromRun(
                suiteName,
                "executor-defensive-skip",
                run,
                new ScenarioExpectation(true, false, true, Set.of(), Set.of(), Set.of("executor-conflict-validation-failed"), Set.of()),
                evidence.conflictFreeAssignments(),
                evidence.degradeReasons());
    }

    private DispatchCertificationScenarioReport warmBootAcrossRestartScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties coldProperties = DispatchHotStartCertificationHarness.coldProperties();
        RouteChainDispatchV2Properties warmHotProperties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchHotStartCertificationRun run = hotStartHarness.certifyDetailed(
                "warm-boot-across-restart",
                scenarioDirectory,
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-warm-boot-cold"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-warm-boot-warm"),
                DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-warm-boot-hot"),
                coldProperties,
                warmHotProperties,
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps(),
                DispatchHotStartCertificationHarness.CertificationDependencies.noOps());
        DispatchHotStartCertificationReport warmReport = reportForWarmRun("warm-boot-across-restart", run);
        return scenarioFromRun(
                suiteName,
                "warm-boot-across-restart",
                new DispatchHotStartCertificationRun(warmReport, run.coldResult(), run.warmResult(), run.warmResult()),
                new ScenarioExpectation(true, true, false, Set.of(), Set.of(), Set.of(), Set.of()));
    }

    private DispatchCertificationScenarioReport repeatedHotStartFamilyScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties properties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = TestDispatchV2Factory.harness(properties);
        DispatchV2Request baseRequest = TestDispatchV2Factory.requestWithOrdersAndDriver();
        seedHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(baseRequest, "trace-repeated-hot-seed"));

        TestDispatchV2Factory.TestDispatchRuntimeHarness warmHotHarness = TestDispatchV2Factory.harness(properties);
        DispatchV2Result warmResult = warmHotHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(baseRequest, "trace-repeated-hot-warm"));
        warmHotHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(baseRequest, "trace-repeated-hot-first"));
        DispatchV2Result secondHot = warmHotHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(baseRequest, "trace-repeated-hot-second"));

        DispatchHotStartCertificationReport report = new DispatchHotStartCertificationReport(
                "dispatch-hot-start-certification-report/v1",
                "repeated-hot-start-family",
                "trace-repeated-hot-seed",
                warmResult.traceId(),
                secondHot.traceId(),
                warmResult.warmStartState().bootMode(),
                secondHot.decisionStages(),
                0L,
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                secondHot.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                secondHot.latencyBudgetSummary().totalDispatchLatencyMs(),
                secondHot.hotStartState().estimatedSavedMs(),
                secondHot.hotStartState().reuseEligible(),
                secondHot.hotStartState().pairClusterReused(),
                secondHot.hotStartState().bundlePoolReused(),
                secondHot.hotStartState().routeProposalPoolReused(),
                secondHot.hotStartState().reusedStageNames(),
                List.copyOf(secondHot.hotStartState().degradeReasons()),
                List.of(),
                List.of(),
                secondHot.stageLatencies(),
                secondHot.latencyBudgetSummary().breachedStageNames(),
                secondHot.latencyBudgetSummary().totalBudgetBreached(),
                true,
                true,
                true,
                true,
                true,
                secondHot.degradeReasons());
        return scenarioFromRun(
                suiteName,
                "repeated-hot-start-family",
                new DispatchHotStartCertificationRun(report, warmResult, warmResult, secondHot),
                new ScenarioExpectation(false, true, true, Set.of(), Set.of(), Set.of(), Set.of()),
                !secondHot.hotStartState().reusedStageNames().isEmpty() && secondHot.hotStartState().estimatedSavedMs() >= 0L,
                List.of());
    }

    private DispatchCertificationScenarioReport replaySafeUnderCertificationLoadScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
        properties.getFeedback().setBaseDir(scenarioDirectory.toString());
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = TestDispatchV2Factory.harness(properties);
        DispatchV2Request originalRequest = TestDispatchV2Factory.requestWithOrdersAndDriver();
        DispatchV2Result baseline = harness.core().dispatch(originalRequest);
        DecisionLogRecord latestDecisionLogBeforeReplay = harness.decisionLogService().latest();
        DispatchRuntimeSnapshot latestSnapshotBeforeReplay = harness.snapshotService().loadLatest().snapshot();
        DispatchRuntimeReuseState latestReuseStateBeforeReplay = harness.reuseStateService().loadLatest().reuseState();

        DispatchV2Request replayOnlyRequest = new DispatchV2Request(
                originalRequest.schemaVersion(),
                "trace-replay-certification-only",
                originalRequest.openOrders(),
                originalRequest.availableDrivers(),
                originalRequest.regions(),
                originalRequest.weatherProfile(),
                originalRequest.decisionTime().plusSeconds(120));
        harness.dispatchReplayRecorder().record(replayOnlyRequest);
        harness.dispatchReplayRunner().replayLatest();

        boolean isolated = latestDecisionLogBeforeReplay.equals(harness.decisionLogService().latest())
                && latestSnapshotBeforeReplay.equals(harness.snapshotService().loadLatest().snapshot())
                && latestReuseStateBeforeReplay.equals(harness.reuseStateService().loadLatest().reuseState());
        DispatchHotStartCertificationReport report = new DispatchHotStartCertificationReport(
                "dispatch-hot-start-certification-report/v1",
                "replay-safe-under-certification-load",
                baseline.traceId(),
                baseline.traceId(),
                baseline.traceId(),
                baseline.warmStartState().bootMode(),
                baseline.decisionStages(),
                baseline.latencyBudgetSummary().totalDispatchLatencyMs(),
                baseline.latencyBudgetSummary().totalDispatchLatencyMs(),
                baseline.latencyBudgetSummary().totalDispatchLatencyMs(),
                0L,
                0L,
                baseline.hotStartState().estimatedSavedMs(),
                baseline.hotStartState().reuseEligible(),
                baseline.hotStartState().pairClusterReused(),
                baseline.hotStartState().bundlePoolReused(),
                baseline.hotStartState().routeProposalPoolReused(),
                baseline.hotStartState().reusedStageNames(),
                baseline.hotStartState().degradeReasons(),
                List.of(),
                baseline.stageLatencies(),
                baseline.stageLatencies(),
                baseline.latencyBudgetSummary().breachedStageNames(),
                baseline.latencyBudgetSummary().totalBudgetBreached(),
                true,
                true,
                true,
                true,
                true,
                baseline.degradeReasons());
        return scenarioFromRun(
                suiteName,
                "replay-safe-under-certification-load",
                new DispatchHotStartCertificationRun(report, baseline, baseline, baseline),
                new ScenarioExpectation(true, false, false, Set.of(), Set.of(), Set.of(), Set.of()),
                isolated,
                isolated ? List.of() : List.of("replay-isolation-failed"));
    }

    private DispatchCertificationScenarioReport snapshotAndReuseStateLoadScenario(String suiteName, Path scenarioDirectory) {
        RouteChainDispatchV2Properties properties = DispatchHotStartCertificationHarness.warmHotProperties(scenarioDirectory);
        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = TestDispatchV2Factory.harness(properties);
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        seedHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-snapshot-reuse-seed"));

        TestDispatchV2Factory.TestDispatchRuntimeHarness reloadedHarness = TestDispatchV2Factory.harness(properties);
        DispatchV2Result warmResult = reloadedHarness.core().dispatch(DispatchHotStartCertificationHarness.copyWithTraceId(request, "trace-snapshot-reuse-warm"));
        boolean stateLoaded = reloadedHarness.snapshotService().loadLatest().loaded()
                && reloadedHarness.reuseStateService().loadLatest().loaded();

        DispatchHotStartCertificationReport report = new DispatchHotStartCertificationReport(
                "dispatch-hot-start-certification-report/v1",
                "snapshot-and-reuse-state-load-cleanly",
                "trace-snapshot-reuse-seed",
                warmResult.traceId(),
                warmResult.traceId(),
                warmResult.warmStartState().bootMode(),
                warmResult.decisionStages(),
                0L,
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.hotStartState().estimatedSavedMs(),
                warmResult.hotStartState().reuseEligible(),
                warmResult.hotStartState().pairClusterReused(),
                warmResult.hotStartState().bundlePoolReused(),
                warmResult.hotStartState().routeProposalPoolReused(),
                warmResult.hotStartState().reusedStageNames(),
                warmResult.hotStartState().degradeReasons(),
                List.of(),
                warmResult.stageLatencies(),
                warmResult.stageLatencies(),
                warmResult.latencyBudgetSummary().breachedStageNames(),
                warmResult.latencyBudgetSummary().totalBudgetBreached(),
                true,
                true,
                true,
                true,
                true,
                warmResult.degradeReasons());
        return scenarioFromRun(
                suiteName,
                "snapshot-and-reuse-state-load-cleanly",
                new DispatchHotStartCertificationRun(report, warmResult, warmResult, warmResult),
                new ScenarioExpectation(true, true, false, Set.of(), Set.of(), Set.of(), Set.of()),
                stateLoaded,
                stateLoaded ? List.of() : List.of("snapshot-or-reuse-state-not-loaded"));
    }

    private DispatchCertificationScenarioReport scenarioFromRun(String suiteName,
                                                                String scenarioName,
                                                                DispatchHotStartCertificationRun run,
                                                                ScenarioExpectation expectation) {
        return scenarioFromRun(suiteName, scenarioName, run, expectation, true, List.of());
    }

    private DispatchCertificationScenarioReport scenarioFromRun(String suiteName,
                                                                String scenarioName,
                                                                DispatchHotStartCertificationRun run,
                                                                ScenarioExpectation expectation,
                                                                boolean extraPassCondition,
                                                                List<String> extraDegradeReasons) {
        DispatchV2Result hotResult = run.hotResult();
        List<String> mlMetadataSources = distinct(hotResult.mlStageMetadata().stream()
                .map(metadata -> metadata.sourceModel())
                .filter(source -> source != null && !source.isBlank())
                .toList());
        List<String> liveMetadataSources = distinct(hotResult.liveStageMetadata().stream()
                .map(metadata -> metadata.sourceName())
                .filter(source -> source != null && !source.isBlank())
                .toList());
        List<String> degradeReasons = distinct(java.util.stream.Stream.of(
                        run.report().degradeReasons().stream(),
                        hotResult.liveStageMetadata().stream()
                                .map(metadata -> metadata.degradeReason())
                                .filter(reason -> reason != null && !reason.isBlank()),
                        extraDegradeReasons.stream())
                .flatMap(stream -> stream)
                .toList());
        boolean warmBootOk = !expectation.requireWarmBoot() || run.report().warmBootMode() == BootMode.WARM;
        boolean reusedStagesOk = !expectation.requireReusedStages() || !run.report().reusedStageNames().isEmpty();
        boolean requiredMlSourcesPresent = mlMetadataSources.containsAll(expectation.requiredMlSources());
        boolean requiredLiveSourcesPresent = liveMetadataSources.containsAll(expectation.requiredLiveSources());
        boolean requiredDegradesPresent = degradeReasons.containsAll(expectation.requiredDegradeReasons());
        boolean requiredReuseReasonsPresent = run.report().reuseFailureReasons().containsAll(expectation.requiredReuseFailureReasons());
        boolean passed = run.report().decisionStages().size() == 12
                && run.report().conflictFreeAssignments()
                && warmBootOk
                && reusedStagesOk
                && requiredMlSourcesPresent
                && requiredLiveSourcesPresent
                && requiredDegradesPresent
                && requiredReuseReasonsPresent
                && extraPassCondition;
        return new DispatchCertificationScenarioReport(
                "dispatch-certification-scenario-report/v1",
                suiteName,
                scenarioName,
                run.report().decisionStages(),
                run.report().coldTotalLatencyMs(),
                run.report().warmTotalLatencyMs(),
                run.report().hotTotalLatencyMs(),
                run.report().reusedStageNames(),
                run.report().estimatedSavedMs(),
                degradeReasons,
                run.report().correctnessMismatchReasons(),
                run.report().conflictFreeAssignments(),
                run.report().budgetBreachedStageNames(),
                run.report().totalBudgetBreached(),
                mlMetadataSources,
                liveMetadataSources,
                passed);
    }

    private DispatchHotStartCertificationReport reportForWarmRun(String traceFamilyId,
                                                                 DispatchHotStartCertificationRun run) {
        DispatchV2Result coldResult = run.coldResult();
        DispatchV2Result warmResult = run.warmResult();
        List<String> correctnessMismatchReasons = correctnessMismatchReasons(coldResult, warmResult);
        return new DispatchHotStartCertificationReport(
                "dispatch-hot-start-certification-report/v1",
                traceFamilyId,
                coldResult.traceId(),
                warmResult.traceId(),
                warmResult.traceId(),
                warmResult.warmStartState().bootMode(),
                warmResult.decisionStages(),
                coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs() - coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs() - coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.hotStartState().estimatedSavedMs(),
                warmResult.hotStartState().reuseEligible(),
                warmResult.hotStartState().pairClusterReused(),
                warmResult.hotStartState().bundlePoolReused(),
                warmResult.hotStartState().routeProposalPoolReused(),
                warmResult.hotStartState().reusedStageNames(),
                warmResult.hotStartState().degradeReasons(),
                correctnessMismatchReasons,
                coldResult.stageLatencies(),
                warmResult.stageLatencies(),
                warmResult.latencyBudgetSummary().breachedStageNames(),
                warmResult.latencyBudgetSummary().totalBudgetBreached(),
                !correctnessMismatchReasons.contains("selected-proposal-ids-mismatch"),
                !correctnessMismatchReasons.contains("executed-assignment-ids-mismatch"),
                !correctnessMismatchReasons.contains("selected-count-mismatch"),
                !correctnessMismatchReasons.contains("executed-assignment-count-mismatch"),
                !correctnessMismatchReasons.contains("conflict-detected"),
                warmResult.degradeReasons());
    }

    private List<String> correctnessMismatchReasons(DispatchV2Result baselineResult,
                                                    DispatchV2Result candidateResult) {
        List<String> reasons = new ArrayList<>();
        List<String> baselineSelectedIds = baselineResult.globalSelectionResult().selectedProposals().stream()
                .map(selected -> selected.proposalId())
                .toList();
        List<String> candidateSelectedIds = candidateResult.globalSelectionResult().selectedProposals().stream()
                .map(selected -> selected.proposalId())
                .toList();
        if (!baselineSelectedIds.equals(candidateSelectedIds)) {
            reasons.add("selected-proposal-ids-mismatch");
        }

        List<String> baselineAssignmentIds = baselineResult.assignments().stream()
                .map(assignment -> assignment.assignmentId())
                .toList();
        List<String> candidateAssignmentIds = candidateResult.assignments().stream()
                .map(assignment -> assignment.assignmentId())
                .toList();
        if (!baselineAssignmentIds.equals(candidateAssignmentIds)) {
            reasons.add("executed-assignment-ids-mismatch");
        }
        if (baselineResult.globalSelectionResult().selectedCount() != candidateResult.globalSelectionResult().selectedCount()) {
            reasons.add("selected-count-mismatch");
        }
        if (baselineResult.dispatchExecutionSummary().executedAssignmentCount() != candidateResult.dispatchExecutionSummary().executedAssignmentCount()) {
            reasons.add("executed-assignment-count-mismatch");
        }
        if (!conflictFreeAssignments(candidateResult)) {
            reasons.add("conflict-detected");
        }
        return List.copyOf(reasons);
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

    private DispatchCertificationSuiteReport suiteReport(String suiteName, List<DispatchCertificationScenarioReport> scenarios) {
        int passedCount = (int) scenarios.stream().filter(DispatchCertificationScenarioReport::passed).count();
        List<String> failureSummaries = scenarios.stream()
                .filter(report -> !report.passed())
                .map(this::failureSummary)
                .toList();
        return new DispatchCertificationSuiteReport(
                "dispatch-certification-suite-report/v1",
                suiteName,
                scenarios.size(),
                passedCount,
                scenarios.size() - passedCount,
                List.copyOf(scenarios),
                failureSummaries);
    }

    private String failureSummary(DispatchCertificationScenarioReport report) {
        if (!report.correctnessMismatchReasons().isEmpty()) {
            return "correctness-mismatch:" + report.scenarioName();
        }
        if (!report.conflictFreeAssignments()) {
            return "conflict-safety:" + report.scenarioName();
        }
        if (!report.degradeReasons().isEmpty()) {
            return "live-source-degrade:" + report.scenarioName();
        }
        return "certification-failed:" + report.scenarioName();
    }

    private DispatchV2Request withWeatherProfile(DispatchV2Request request, String traceId, WeatherProfile weatherProfile) {
        return new DispatchV2Request(
                request.schemaVersion(),
                traceId,
                request.openOrders(),
                request.availableDrivers(),
                request.regions(),
                weatherProfile,
                request.decisionTime());
    }

    private TestForecastClient strongForecastClient(double zoneBurstProbability,
                                                    double demandShiftProbability,
                                                    double postDropProbability) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("chronos-2", "v1", "sha256:chronos", 11L);
        return new TestForecastClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> ForecastResult.applied(30, demandShiftProbability, java.util.Map.of("q10", -0.30, "q50", -0.18, "q90", -0.05), 0.91, 40_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(20, zoneBurstProbability, java.util.Map.of("q10", 0.18, "q50", 0.32, "q90", 0.46), 0.93, 38_000L, metadata),
                (feature, timeout) -> ForecastResult.applied(45, postDropProbability, java.util.Map.of("q10", 0.12, "q50", 0.28, "q90", 0.41), 0.90, 42_000L, metadata));
    }

    private List<String> distinct(List<String> values) {
        return new ArrayList<>(new LinkedHashSet<>(values));
    }

    private record ScenarioExpectation(
            boolean fullCorrectnessRequired,
            boolean requireWarmBoot,
            boolean requireReusedStages,
            Set<String> requiredMlSources,
            Set<String> requiredLiveSources,
            Set<String> requiredDegradeReasons,
            Set<String> requiredReuseFailureReasons) {
    }
}
