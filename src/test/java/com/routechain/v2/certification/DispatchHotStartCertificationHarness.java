package com.routechain.v2.certification;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.OpenMeteoClient;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.TomTomTrafficRefineClient;

import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class DispatchHotStartCertificationHarness {

    public DispatchHotStartCertificationReport certify(String traceFamilyId,
                                                       Path feedbackDirectory,
                                                       DispatchV2Request coldRequest,
                                                       DispatchV2Request warmRequest,
                                                       DispatchV2Request hotRequest,
                                                       RouteChainDispatchV2Properties coldProperties,
                                                       RouteChainDispatchV2Properties warmHotProperties,
                                                       CertificationDependencies coldDependencies,
                                                       CertificationDependencies warmHotDependencies) {
        return certifyDetailed(
                traceFamilyId,
                feedbackDirectory,
                coldRequest,
                warmRequest,
                hotRequest,
                coldProperties,
                warmHotProperties,
                coldDependencies,
                warmHotDependencies).report();
    }

    public DispatchHotStartCertificationRun certifyDetailed(String traceFamilyId,
                                                            Path feedbackDirectory,
                                                            DispatchV2Request coldRequest,
                                                            DispatchV2Request warmRequest,
                                                            DispatchV2Request hotRequest,
                                                            RouteChainDispatchV2Properties coldProperties,
                                                            RouteChainDispatchV2Properties warmHotProperties,
                                                            CertificationDependencies coldDependencies,
                                                            CertificationDependencies warmHotDependencies) {
        TestDispatchV2Factory.TestDispatchRuntimeHarness coldHarness = harness(coldProperties, coldDependencies);
        DispatchV2Result coldResult = coldHarness.core().dispatch(coldRequest);

        java.nio.file.Path ignoredFeedbackDirectory = feedbackDirectory;
        TestDispatchV2Factory.TestDispatchRuntimeHarness seedHarness = harness(warmHotProperties, warmHotDependencies);
        seedHarness.core().dispatch(copyWithTraceId(warmRequest, traceFamilyId + "-seed"));

        TestDispatchV2Factory.TestDispatchRuntimeHarness warmHotHarness = harness(warmHotProperties, warmHotDependencies);
        DispatchV2Result warmResult = warmHotHarness.core().dispatch(warmRequest);
        DispatchV2Result hotResult = warmHotHarness.core().dispatch(hotRequest);

        List<String> correctnessMismatchReasons = correctnessMismatchReasons(coldResult, hotResult);
        DispatchHotStartCertificationReport report = new DispatchHotStartCertificationReport(
                "dispatch-hot-start-certification-report/v1",
                traceFamilyId,
                coldResult.traceId(),
                warmResult.traceId(),
                hotResult.traceId(),
                warmResult.warmStartState().bootMode(),
                hotResult.decisionStages(),
                coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                hotResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                warmResult.latencyBudgetSummary().totalDispatchLatencyMs() - coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                hotResult.latencyBudgetSummary().totalDispatchLatencyMs() - coldResult.latencyBudgetSummary().totalDispatchLatencyMs(),
                hotResult.hotStartState().estimatedSavedMs(),
                hotResult.hotStartState().reuseEligible(),
                hotResult.hotStartState().pairClusterReused(),
                hotResult.hotStartState().bundlePoolReused(),
                hotResult.hotStartState().routeProposalPoolReused(),
                hotResult.hotStartState().reusedStageNames(),
                normalizeReuseFailureReasons(hotResult.hotStartState().degradeReasons(), coldRequest, hotRequest),
                correctnessMismatchReasons,
                coldResult.stageLatencies(),
                hotResult.stageLatencies(),
                hotResult.latencyBudgetSummary().breachedStageNames(),
                hotResult.latencyBudgetSummary().totalBudgetBreached(),
                !correctnessMismatchReasons.contains("selected-proposal-ids-mismatch"),
                !correctnessMismatchReasons.contains("executed-assignment-ids-mismatch"),
                !correctnessMismatchReasons.contains("selected-count-mismatch"),
                !correctnessMismatchReasons.contains("executed-assignment-count-mismatch"),
                !correctnessMismatchReasons.contains("conflict-detected"),
                hotResult.degradeReasons());
        return new DispatchHotStartCertificationRun(report, coldResult, warmResult, hotResult);
    }

    private TestDispatchV2Factory.TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                                     CertificationDependencies dependencies) {
        return TestDispatchV2Factory.harness(
                properties,
                dependencies.tabularScoringClient(),
                dependencies.routeFinderClient(),
                dependencies.greedRlClient(),
                dependencies.forecastClient(),
                dependencies.openMeteoClient(),
                dependencies.tomTomTrafficRefineClient());
    }

    private List<String> correctnessMismatchReasons(DispatchV2Result coldResult, DispatchV2Result hotResult) {
        List<String> reasons = new ArrayList<>();
        if (coldResult.globalSelectionResult().selectedCount() != hotResult.globalSelectionResult().selectedCount()) {
            reasons.add("selected-count-mismatch");
        }
        if (coldResult.dispatchExecutionSummary().executedAssignmentCount() != hotResult.dispatchExecutionSummary().executedAssignmentCount()) {
            reasons.add("executed-assignment-count-mismatch");
        }
        if (!conflictFreeAssignments(hotResult)) {
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

    private List<String> normalizeReuseFailureReasons(List<String> rawReasons,
                                                      DispatchV2Request coldRequest,
                                                      DispatchV2Request hotRequest) {
        LinkedHashSet<String> normalized = new LinkedHashSet<>();
        for (String rawReason : rawReasons) {
            if ("hot-start-no-previous-state".equals(rawReason)) {
                normalized.add(rawReason);
            } else if ("hot-start-route-tuple-drift".equals(rawReason)) {
                normalized.add(rawReason);
            } else if ("hot-start-eta-signature-drift".equals(rawReason)) {
                if (coldRequest.weatherProfile() != hotRequest.weatherProfile()) {
                    normalized.add("hot-start-weather-signature-drift");
                } else if (!trafficBucket(coldRequest.decisionTime()).equals(trafficBucket(hotRequest.decisionTime()))) {
                    normalized.add("hot-start-traffic-signature-drift");
                } else {
                    normalized.add("hot-start-eta-signature-drift");
                }
            } else if (rawReason != null && rawReason.contains("missing")) {
                normalized.add("hot-start-stage-payload-missing");
            }
        }
        return List.copyOf(normalized);
    }

    private String trafficBucket(Instant instant) {
        int hour = (instant == null ? Instant.EPOCH : instant).atZone(ZoneOffset.UTC).getHour();
        if ((hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 19)) {
            return "peak";
        }
        if (hour < 6 || hour >= 22) {
            return "offpeak";
        }
        return "default";
    }

    public static RouteChainDispatchV2Properties coldProperties() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setHotStartEnabled(false);
        properties.getFeedback().setStorageMode(FeedbackStorageMode.IN_MEMORY);
        return properties;
    }

    public static RouteChainDispatchV2Properties warmHotProperties(Path feedbackDirectory) {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
        properties.getFeedback().setBaseDir(feedbackDirectory.toString());
        properties.getWarmHotStart().setLoadLatestSnapshotOnBoot(true);
        return properties;
    }

    public static DispatchV2Request copyWithTraceId(DispatchV2Request request, String traceId) {
        return new DispatchV2Request(
                request.schemaVersion(),
                traceId,
                request.openOrders(),
                request.availableDrivers(),
                request.regions(),
                request.weatherProfile(),
                request.decisionTime());
    }

    public static DispatchV2Request copyWithDecisionTime(DispatchV2Request request, String traceId, Instant decisionTime) {
        return new DispatchV2Request(
                request.schemaVersion(),
                traceId,
                request.openOrders().stream()
                        .map(order -> new Order(
                                order.orderId(),
                                order.pickupPoint(),
                                order.dropoffPoint(),
                                shiftInstant(order.createdAt(), request.decisionTime(), decisionTime),
                                shiftInstant(order.readyAt(), request.decisionTime(), decisionTime),
                                order.promisedEtaMinutes(),
                                order.urgent()))
                        .toList(),
                request.availableDrivers(),
                request.regions(),
                request.weatherProfile(),
                decisionTime);
    }

    private static Instant shiftInstant(Instant value, Instant fromDecisionTime, Instant toDecisionTime) {
        if (value == null || fromDecisionTime == null || toDecisionTime == null) {
            return value;
        }
        return value.plusMillis(toDecisionTime.toEpochMilli() - fromDecisionTime.toEpochMilli());
    }

    public record CertificationDependencies(
            TabularScoringClient tabularScoringClient,
            RouteFinderClient routeFinderClient,
            GreedRlClient greedRlClient,
            ForecastClient forecastClient,
            OpenMeteoClient openMeteoClient,
            TomTomTrafficRefineClient tomTomTrafficRefineClient) {

        public static CertificationDependencies noOps() {
            return new CertificationDependencies(
                    new NoOpTabularScoringClient(),
                    new NoOpRouteFinderClient(),
                    new NoOpGreedRlClient(),
                    new NoOpForecastClient(),
                    new NoOpOpenMeteoClient(),
                    new NoOpTomTomTrafficRefineClient());
        }

        public CertificationDependencies withForecastClient(ForecastClient forecastClient) {
            return new CertificationDependencies(
                    tabularScoringClient,
                    routeFinderClient,
                    greedRlClient,
                    forecastClient,
                    openMeteoClient,
                    tomTomTrafficRefineClient);
        }

        public CertificationDependencies withRouteFinderClient(RouteFinderClient routeFinderClient) {
            return new CertificationDependencies(
                    tabularScoringClient,
                    routeFinderClient,
                    greedRlClient,
                    forecastClient,
                    openMeteoClient,
                    tomTomTrafficRefineClient);
        }

        public CertificationDependencies withGreedRlClient(GreedRlClient greedRlClient) {
            return new CertificationDependencies(
                    tabularScoringClient,
                    routeFinderClient,
                    greedRlClient,
                    forecastClient,
                    openMeteoClient,
                    tomTomTrafficRefineClient);
        }

        public CertificationDependencies withOpenMeteoClient(OpenMeteoClient openMeteoClient) {
            return new CertificationDependencies(
                    tabularScoringClient,
                    routeFinderClient,
                    greedRlClient,
                    forecastClient,
                    openMeteoClient,
                    tomTomTrafficRefineClient);
        }

        public CertificationDependencies withTomTomTrafficRefineClient(TomTomTrafficRefineClient tomTomTrafficRefineClient) {
            return new CertificationDependencies(
                    tabularScoringClient,
                    routeFinderClient,
                    greedRlClient,
                    forecastClient,
                    openMeteoClient,
                    tomTomTrafficRefineClient);
        }
    }
}
