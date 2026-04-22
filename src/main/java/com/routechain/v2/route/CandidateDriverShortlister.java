package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.v2.EtaContext;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.MlStageMetadataAccumulator;
import com.routechain.v2.integration.TabularScoreResult;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.harvest.HarvestRecorder;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class CandidateDriverShortlister {
    private final RouteChainDispatchV2Properties properties;
    private final DriverRouteFeatureBuilder driverRouteFeatureBuilder;
    private final TabularScoringClient tabularScoringClient;
    private final HarvestRecorder harvestRecorder;

    public CandidateDriverShortlister(RouteChainDispatchV2Properties properties,
                                      DriverRouteFeatureBuilder driverRouteFeatureBuilder,
                                      TabularScoringClient tabularScoringClient,
                                      HarvestRecorder harvestRecorder) {
        this.properties = properties;
        this.driverRouteFeatureBuilder = driverRouteFeatureBuilder;
        this.tabularScoringClient = tabularScoringClient;
        this.harvestRecorder = harvestRecorder;
    }

    public CandidateDriverShortlister(RouteChainDispatchV2Properties properties,
                                      DriverRouteFeatureBuilder driverRouteFeatureBuilder,
                                      TabularScoringClient tabularScoringClient) {
        this(properties, driverRouteFeatureBuilder, tabularScoringClient, null);
    }

    public CandidateDriverShortlister(RouteChainDispatchV2Properties properties,
                                      DriverRouteFeatureBuilder driverRouteFeatureBuilder) {
        this(properties, driverRouteFeatureBuilder, new NoOpTabularScoringClient(), null);
    }

    public DriverShortlistResult shortlist(String traceId,
                                           List<Driver> availableDrivers,
                                           PickupAnchor pickupAnchor,
                                           DispatchCandidateContext context,
                                           EtaContext etaContext,
                                           EtaLegCache etaLegCache) {
        List<DriverRouteFeatures> deterministicRanking = availableDrivers.stream()
                .sorted(Comparator.comparing(Driver::driverId))
                .map(driver -> driverRouteFeatureBuilder.build(driver, pickupAnchor, context, etaContext, etaLegCache))
                .sorted(Comparator.comparingDouble(DriverRouteFeatures::driverFitScore).reversed()
                        .thenComparingDouble(DriverRouteFeatures::pickupEtaMinutes)
                        .thenComparing(DriverRouteFeatures::driverId))
                .toList();
        List<DriverRouteFeatures> boundedShortlist = deterministicRanking.stream()
                .limit(Math.max(1, properties.getCandidate().getMaxDrivers()))
                .toList();
        if (!properties.isMlEnabled() || !properties.getMl().getTabular().isEnabled()) {
            return new DriverShortlistResult(boundedShortlist, List.of(), List.of());
        }
        MlStageMetadataAccumulator mlStageMetadataAccumulator = new MlStageMetadataAccumulator("driver-shortlist/rerank");
        List<String> degradeReasons = new ArrayList<>();
        List<DriverRouteFeatures> rescored = boundedShortlist.stream()
                .map(features -> rescore(traceId, features, mlStageMetadataAccumulator, degradeReasons))
                .sorted(Comparator.comparingDouble(DriverRouteFeatures::driverFitScore).reversed()
                        .thenComparingDouble(DriverRouteFeatures::pickupEtaMinutes)
                        .thenComparing(DriverRouteFeatures::driverId))
                .toList();
        return new DriverShortlistResult(
                rescored,
                List.copyOf(degradeReasons.stream().distinct().toList()),
                mlStageMetadataAccumulator.build().map(List::of).orElse(List.of()));
    }

    public List<DriverRouteFeatures> shortlist(List<Driver> availableDrivers,
                                               PickupAnchor pickupAnchor,
                                               DispatchCandidateContext context,
                                               EtaContext etaContext,
                                               EtaLegCache etaLegCache) {
        return shortlist("driver-shortlist", availableDrivers, pickupAnchor, context, etaContext, etaLegCache).shortlistedFeatures();
    }

    private DriverRouteFeatures rescore(String traceId,
                                        DriverRouteFeatures features,
                                        MlStageMetadataAccumulator mlStageMetadataAccumulator,
                                        List<String> degradeReasons) {
        TabularScoreResult scoreResult = tabularScoringClient.scoreDriverFit(
                new DriverFitFeatureVector(
                        "driver-fit-feature-vector/v1",
                        traceId,
                        features.bundleId(),
                        features.anchorOrderId(),
                        features.driverId(),
                        features.pickupEtaMinutes(),
                        features.etaUncertainty(),
                        features.bundleScore(),
                        features.anchorScore(),
                        features.bundleSupportScore(),
                        features.corridorAffinity(),
                        features.urgencyLift(),
                        features.boundaryPenalty(),
                        features.driverFitScore()),
                properties.getMl().getTabular().getReadTimeout().toMillis());
        mlStageMetadataAccumulator.accept(scoreResult);
        if (harvestRecorder != null) {
            harvestRecorder.recordTabularTeacher(
                    traceId,
                    "driver-shortlist/rerank",
                    "driver:%s:%s".formatted(features.bundleId(), features.driverId()),
                    "driver-fit-score",
                    new DriverFitFeatureVector(
                            "driver-fit-feature-vector/v1",
                            traceId,
                            features.bundleId(),
                            features.anchorOrderId(),
                            features.driverId(),
                            features.pickupEtaMinutes(),
                            features.etaUncertainty(),
                            features.bundleScore(),
                            features.anchorScore(),
                            features.bundleSupportScore(),
                            features.corridorAffinity(),
                            features.urgencyLift(),
                            features.boundaryPenalty(),
                            features.driverFitScore()),
                    scoreResult);
        }
        if (!scoreResult.applied()) {
            degradeReasons.add("driver-fit-ml-unavailable");
            return features;
        }
        return new DriverRouteFeatures(
                features.bundleId(),
                features.anchorOrderId(),
                features.driverId(),
                features.pickupEtaMinutes(),
                features.etaUncertainty(),
                features.bundleScore(),
                features.anchorScore(),
                features.bundleSupportScore(),
                features.corridorAffinity(),
                features.urgencyLift(),
                features.boundaryPenalty(),
                Math.max(0.0, Math.min(1.0, features.driverFitScore() + scoreResult.value())),
                features.reasons(),
                features.degradeReasons());
    }
}
