package com.routechain.v2.scenario;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.EtaContext;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.context.FreshnessMetadata;
import com.routechain.v2.integration.DemandShiftFeatureVector;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.ForecastResult;
import com.routechain.v2.integration.MlStageMetadataAccumulator;
import com.routechain.v2.integration.PostDropShiftFeatureVector;
import com.routechain.v2.integration.ZoneBurstFeatureVector;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.RouteProposal;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public final class DispatchScenarioService {
    private final RouteChainDispatchV2Properties properties;
    private final ForecastClient forecastClient;
    private final DemandShiftFeatureBuilder demandShiftFeatureBuilder;
    private final ZoneBurstFeatureBuilder zoneBurstFeatureBuilder;
    private final PostDropShiftFeatureBuilder postDropShiftFeatureBuilder;
    private final ScenarioGateEvaluator scenarioGateEvaluator;
    private final ScenarioEvaluator scenarioEvaluator;
    private final RobustUtilityAggregator robustUtilityAggregator;
    private final HarvestRecorder harvestRecorder;

    public DispatchScenarioService(RouteChainDispatchV2Properties properties,
                                   ForecastClient forecastClient,
                                   DemandShiftFeatureBuilder demandShiftFeatureBuilder,
                                   ZoneBurstFeatureBuilder zoneBurstFeatureBuilder,
                                   PostDropShiftFeatureBuilder postDropShiftFeatureBuilder,
                                   ScenarioGateEvaluator scenarioGateEvaluator,
                                   ScenarioEvaluator scenarioEvaluator,
                                   RobustUtilityAggregator robustUtilityAggregator,
                                   HarvestRecorder harvestRecorder) {
        this.properties = properties;
        this.forecastClient = forecastClient;
        this.demandShiftFeatureBuilder = demandShiftFeatureBuilder;
        this.zoneBurstFeatureBuilder = zoneBurstFeatureBuilder;
        this.postDropShiftFeatureBuilder = postDropShiftFeatureBuilder;
        this.scenarioGateEvaluator = scenarioGateEvaluator;
        this.scenarioEvaluator = scenarioEvaluator;
        this.robustUtilityAggregator = robustUtilityAggregator;
        this.harvestRecorder = harvestRecorder;
    }

    public DispatchScenarioService(RouteChainDispatchV2Properties properties,
                                   ForecastClient forecastClient,
                                   DemandShiftFeatureBuilder demandShiftFeatureBuilder,
                                   ZoneBurstFeatureBuilder zoneBurstFeatureBuilder,
                                   PostDropShiftFeatureBuilder postDropShiftFeatureBuilder,
                                   ScenarioGateEvaluator scenarioGateEvaluator,
                                   ScenarioEvaluator scenarioEvaluator,
                                   RobustUtilityAggregator robustUtilityAggregator) {
        this(properties,
                forecastClient,
                demandShiftFeatureBuilder,
                zoneBurstFeatureBuilder,
                postDropShiftFeatureBuilder,
                scenarioGateEvaluator,
                scenarioEvaluator,
                robustUtilityAggregator,
                null);
    }

    public DispatchScenarioStage evaluate(DispatchV2Request request,
                                          EtaContext etaContext,
                                          FreshnessMetadata freshnessMetadata,
                                          List<LiveStageMetadata> liveStageMetadata,
                                          DispatchRouteProposalStage routeProposalStage,
                                          DispatchRouteCandidateStage routeCandidateStage,
                                          DispatchBundleStage bundleStage,
                                          DispatchPairClusterStage pairClusterStage) {
        long scenarioStartedAt = System.nanoTime();
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                request.availableDrivers(),
                pairClusterStage,
                bundleStage);
        ForecastScenarioContext forecastScenarioContext = forecastContext(
                request,
                etaContext,
                freshnessMetadata,
                context,
                routeProposalStage,
                routeCandidateStage,
                bundleStage);
        Map<String, DriverCandidate> driverCandidateByKey = routeCandidateStage.driverCandidates().stream()
                .collect(java.util.stream.Collectors.toMap(
                        candidate -> key(candidate.bundleId(), candidate.anchorOrderId(), candidate.driverId()),
                        candidate -> candidate,
                        (left, right) -> left));
        List<ScenarioEvaluation> evaluations = new ArrayList<>();
        List<String> degradeReasons = new ArrayList<>();
        for (RouteProposal proposal : routeProposalStage.routeProposals()) {
            DriverCandidate driverCandidate = driverCandidateByKey.get(key(proposal.bundleId(), proposal.anchorOrderId(), proposal.driverId()));
            if (driverCandidate == null) {
                continue;
            }
            List<ScenarioGateDecision> decisions = scenarioGateEvaluator.gate(
                    proposal,
                    driverCandidate,
                    context,
                    etaContext,
                    forecastScenarioContext.freshnessMetadata(),
                    liveStageMetadata,
                    forecastScenarioContext);
            for (ScenarioGateDecision decision : decisions) {
                ScenarioEvaluationResult result = scenarioEvaluator.evaluate(
                        proposal,
                        driverCandidate,
                        context,
                        etaContext,
                        decision,
                        forecastScenarioContext);
                evaluations.add(result.evaluation());
                degradeReasons.addAll(result.evaluation().degradeReasons());
            }
        }
        List<RobustUtility> robustUtilities = routeProposalStage.routeProposals().stream()
                .map(RouteProposal::proposalId)
                .distinct()
                .sorted()
                .map(proposalId -> robustUtilityAggregator.aggregate(proposalId, evaluations))
                .toList();
        List<String> distinctDegradeReasons = degradeReasons.stream().distinct().toList();
        long scenarioElapsedMs = elapsedMs(scenarioStartedAt);
        return new DispatchScenarioStage(
                "dispatch-scenario-stage/v1",
                List.copyOf(evaluations),
                robustUtilities,
                summarize(evaluations, robustUtilities, distinctDegradeReasons),
                forecastScenarioContext.freshnessMetadata(),
                List.of(DispatchStageLatency.measured("scenario-evaluation", scenarioElapsedMs, false)),
                forecastScenarioContext.mlStageMetadata(),
                distinctDegradeReasons);
    }

    private ForecastScenarioContext forecastContext(DispatchV2Request request,
                                                   EtaContext etaContext,
                                                   FreshnessMetadata freshnessMetadata,
                                                   DispatchCandidateContext context,
                                                   DispatchRouteProposalStage routeProposalStage,
                                                   DispatchRouteCandidateStage routeCandidateStage,
                                                   DispatchBundleStage bundleStage) {
        MlStageMetadataAccumulator metadataAccumulator = new MlStageMetadataAccumulator("scenario-evaluation");
        DemandShiftFeatureVector demandShiftFeatures = demandShiftFeatureBuilder.build(request, etaContext, context, routeProposalStage, bundleStage);
        ZoneBurstFeatureVector zoneBurstFeatures = zoneBurstFeatureBuilder.build(request, etaContext, context, routeProposalStage);
        PostDropShiftFeatureVector postDropShiftFeatures = postDropShiftFeatureBuilder.build(request, etaContext, context, routeProposalStage, routeCandidateStage);
        ForecastResult demandShift = forecastClient.forecastDemandShift(demandShiftFeatures, 180L);
        ForecastResult zoneBurst = forecastClient.forecastZoneBurst(zoneBurstFeatures, 180L);
        ForecastResult postDropShift = forecastClient.forecastPostDropShift(postDropShiftFeatures, 180L);
        if (harvestRecorder != null) {
            String traceId = demandShiftFeatures.traceId();
            harvestRecorder.recordForecastTeacher(traceId, demandShiftFeatures.corridorId(), "demand-shift", demandShiftFeatures, demandShift);
            harvestRecorder.recordForecastTeacher(traceId, zoneBurstFeatures.corridorId(), "zone-burst", zoneBurstFeatures, zoneBurst);
            harvestRecorder.recordForecastTeacher(traceId, postDropShiftFeatures.corridorId(), "post-drop-shift", postDropShiftFeatures, postDropShift);
        }
        acceptMetadata(metadataAccumulator, demandShift);
        acceptMetadata(metadataAccumulator, zoneBurst);
        acceptMetadata(metadataAccumulator, postDropShift);
        long maxForecastAgeMs = java.util.stream.LongStream.of(
                        freshnessMetadata == null ? 0L : freshnessMetadata.forecastAgeMs(),
                        demandShift.sourceAgeMs(),
                        zoneBurst.sourceAgeMs(),
                        postDropShift.sourceAgeMs())
                .max()
                .orElse(0L);
        boolean forecastFresh = maxForecastAgeMs > 0L
                && maxForecastAgeMs <= contextFreshnessMaxAgeMs();
        FreshnessMetadata mergedFreshness = new FreshnessMetadata(
                freshnessMetadata == null ? "freshness-metadata/v1" : freshnessMetadata.schemaVersion(),
                freshnessMetadata == null ? 0L : freshnessMetadata.weatherAgeMs(),
                freshnessMetadata == null ? 0L : freshnessMetadata.trafficAgeMs(),
                maxForecastAgeMs,
                freshnessMetadata != null && freshnessMetadata.weatherFresh(),
                freshnessMetadata != null && freshnessMetadata.trafficFresh(),
                forecastFresh);
        List<String> degradeReasons = java.util.stream.Stream.of(
                        demandShift.degradeReason(),
                        zoneBurst.degradeReason(),
                        postDropShift.degradeReason())
                .filter(reason -> reason != null && !reason.isBlank())
                .distinct()
                .toList();
        return new ForecastScenarioContext(
                demandShift,
                zoneBurst,
                postDropShift,
                mergedFreshness,
                metadataAccumulator.build().map(List::of).orElse(List.of()),
                degradeReasons);
    }

    private void acceptMetadata(MlStageMetadataAccumulator accumulator, ForecastResult forecastResult) {
        if (!forecastResult.workerMetadata().sourceModel().isBlank()) {
            accumulator.accept(forecastResult);
        }
    }

    private long contextFreshnessMaxAgeMs() {
        return properties.getContext().getFreshness().getForecastMaxAge().toMillis();
    }

    private ScenarioEvaluationSummary summarize(List<ScenarioEvaluation> evaluations,
                                                List<RobustUtility> robustUtilities,
                                                List<String> degradeReasons) {
        Map<ScenarioType, Integer> scenarioCounts = new EnumMap<>(ScenarioType.class);
        Map<ScenarioType, Integer> appliedScenarioCounts = new EnumMap<>(ScenarioType.class);
        evaluations.forEach(evaluation -> {
            scenarioCounts.merge(evaluation.scenario(), 1, Integer::sum);
            if (evaluation.applied()) {
                appliedScenarioCounts.merge(evaluation.scenario(), 1, Integer::sum);
            }
        });
        int appliedScenarioCount = evaluations.stream().mapToInt(evaluation -> evaluation.applied() ? 1 : 0).sum();
        return new ScenarioEvaluationSummary(
                "scenario-evaluation-summary/v1",
                robustUtilities.size(),
                evaluations.size(),
                appliedScenarioCount,
                scenarioCounts,
                appliedScenarioCounts,
                degradeReasons);
    }

    private String key(String bundleId, String anchorOrderId, String driverId) {
        return bundleId + "|" + anchorOrderId + "|" + driverId;
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }
}
