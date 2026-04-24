package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.EtaContext;
import com.routechain.v2.HotStartReuseSummary;
import com.routechain.v2.compute.AdaptiveComputeGate;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.feedback.ReuseStateBuilder;
import com.routechain.v2.integration.GreedRlBundleCandidate;
import com.routechain.v2.integration.GreedRlBundleFeatureVector;
import com.routechain.v2.integration.GreedRlBundleResult;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.MlStageMetadataAccumulator;
import com.routechain.v2.integration.MlWorkerAuditSupport;
import com.routechain.v2.harvest.HarvestRecorder;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class DispatchBundleStageService {
    private final RouteChainDispatchV2Properties properties;
    private final BoundaryCandidateSelector boundaryCandidateSelector;
    private final BoundaryExpansionEngine boundaryExpansionEngine;
    private final BundleSeedGenerator bundleSeedGenerator;
    private final BundleFamilyEnumerator bundleFamilyEnumerator;
    private final BundleValidator bundleValidator;
    private final BundleScorer bundleScorer;
    private final BundleDominancePruner bundleDominancePruner;
    private final GreedRlClient greedRlClient;
    private final HarvestRecorder harvestRecorder;
    private final AdaptiveComputeGate adaptiveComputeGate;
    private final DecisionStageLogger decisionStageLogger;

    public DispatchBundleStageService(RouteChainDispatchV2Properties properties,
                                      BoundaryCandidateSelector boundaryCandidateSelector,
                                      BoundaryExpansionEngine boundaryExpansionEngine,
                                      BundleSeedGenerator bundleSeedGenerator,
                                      BundleFamilyEnumerator bundleFamilyEnumerator,
                                      BundleValidator bundleValidator,
                                      BundleScorer bundleScorer,
                                      BundleDominancePruner bundleDominancePruner,
                                      GreedRlClient greedRlClient,
                                      HarvestRecorder harvestRecorder,
                                      AdaptiveComputeGate adaptiveComputeGate,
                                      DecisionStageLogger decisionStageLogger) {
        this.properties = properties;
        this.boundaryCandidateSelector = boundaryCandidateSelector;
        this.boundaryExpansionEngine = boundaryExpansionEngine;
        this.bundleSeedGenerator = bundleSeedGenerator;
        this.bundleFamilyEnumerator = bundleFamilyEnumerator;
        this.bundleValidator = bundleValidator;
        this.bundleScorer = bundleScorer;
        this.bundleDominancePruner = bundleDominancePruner;
        this.greedRlClient = greedRlClient;
        this.harvestRecorder = harvestRecorder;
        this.adaptiveComputeGate = adaptiveComputeGate;
        this.decisionStageLogger = decisionStageLogger;
    }

    public DispatchBundleStageService(RouteChainDispatchV2Properties properties,
                                      BoundaryCandidateSelector boundaryCandidateSelector,
                                      BoundaryExpansionEngine boundaryExpansionEngine,
                                      BundleSeedGenerator bundleSeedGenerator,
                                      BundleFamilyEnumerator bundleFamilyEnumerator,
                                      BundleValidator bundleValidator,
                                      BundleScorer bundleScorer,
                                      BundleDominancePruner bundleDominancePruner,
                                      GreedRlClient greedRlClient,
                                      HarvestRecorder harvestRecorder) {
        this(properties,
                boundaryCandidateSelector,
                boundaryExpansionEngine,
                bundleSeedGenerator,
                bundleFamilyEnumerator,
                bundleValidator,
                bundleScorer,
                bundleDominancePruner,
                greedRlClient,
                harvestRecorder,
                new AdaptiveComputeGate(properties),
                new DecisionStageLogger(properties));
    }

    public DispatchBundleStageService(RouteChainDispatchV2Properties properties,
                                      BoundaryCandidateSelector boundaryCandidateSelector,
                                      BoundaryExpansionEngine boundaryExpansionEngine,
                                      BundleSeedGenerator bundleSeedGenerator,
                                      BundleFamilyEnumerator bundleFamilyEnumerator,
                                      BundleValidator bundleValidator,
                                      BundleScorer bundleScorer,
                                      BundleDominancePruner bundleDominancePruner,
                                      GreedRlClient greedRlClient) {
        this(properties,
                boundaryCandidateSelector,
                boundaryExpansionEngine,
                bundleSeedGenerator,
                bundleFamilyEnumerator,
                bundleValidator,
                bundleScorer,
                bundleDominancePruner,
                greedRlClient,
                null,
                new AdaptiveComputeGate(properties),
                new DecisionStageLogger(properties));
    }

    public DispatchBundleStage evaluate(EtaContext etaContext, DispatchPairClusterStage pairClusterStage) {
        return evaluate(etaContext, pairClusterStage, null);
    }

    public DispatchBundleStage evaluate(EtaContext etaContext,
                                        DispatchPairClusterStage pairClusterStage,
                                        BundleReuseInput reuseInput) {
        if (reuseInput != null && reuseInput.reuseState() != null) {
            List<String> reuseDegradeReasons = new ArrayList<>();
            if (!ReuseStateBuilder.etaContextSignature(etaContext).equals(reuseInput.reuseState().etaContextSignature())) {
                reuseDegradeReasons.add("hot-start-eta-signature-drift");
            }
            if (!ReuseStateBuilder.clusterSignatures(pairClusterStage.microClusters()).equals(reuseInput.reuseState().clusterSignatures())) {
                reuseDegradeReasons.add("hot-start-cluster-signature-drift");
            }
            if (reuseDegradeReasons.isEmpty()
                    && reuseInput.reuseState().bundleCandidates() != null
                    && reuseInput.reuseState().bundlePoolSummary() != null) {
                long boundaryExpansionStartedAt = System.nanoTime();
                List<BoundaryExpansion> reusedBoundaryExpansions = reuseInput.reuseState().boundaryExpansions();
                BoundaryExpansionSummary reusedBoundaryExpansionSummary = reuseInput.reuseState().boundaryExpansionSummary();
                long boundaryExpansionElapsedMs = elapsedMs(boundaryExpansionStartedAt);
                long bundlePoolStartedAt = System.nanoTime();
                List<BundleCandidate> reusedBundleCandidates = reuseInput.reuseState().bundleCandidates();
                BundlePoolSummary reusedBundlePoolSummary = reuseInput.reuseState().bundlePoolSummary();
                long bundlePoolElapsedMs = elapsedMs(bundlePoolStartedAt);
                return new DispatchBundleStage(
                        "dispatch-bundle-stage/v1",
                        reusedBoundaryExpansions,
                        reusedBoundaryExpansionSummary,
                        reusedBundleCandidates,
                        reusedBundlePoolSummary,
                        HotStartReuseSummary.reused(reuseInput.reuseState().bundleCandidates().size()),
                        List.of(
                                DispatchStageLatency.measured("boundary-expansion", boundaryExpansionElapsedMs, false),
                                DispatchStageLatency.measured("bundle-pool", bundlePoolElapsedMs, true)),
                        reuseInput.reuseState().bundleMlStageMetadata(),
                        reuseInput.reuseState().bundleDegradeReasons());
            }
            DispatchBundleStage freshStage = evaluateFresh(etaContext, pairClusterStage);
            List<String> degradeReasons = new ArrayList<>(freshStage.degradeReasons());
            degradeReasons.addAll(reuseDegradeReasons);
            return new DispatchBundleStage(
                    freshStage.schemaVersion(),
                    freshStage.boundaryExpansions(),
                    freshStage.boundaryExpansionSummary(),
                    freshStage.bundleCandidates(),
                    freshStage.bundlePoolSummary(),
                    HotStartReuseSummary.none().withDegradeReasons(reuseDegradeReasons),
                    freshStage.stageLatencies(),
                    freshStage.mlStageMetadata(),
                    List.copyOf(degradeReasons.stream().distinct().toList()));
        }
        return evaluateFresh(etaContext, pairClusterStage);
    }

    private DispatchBundleStage evaluateFresh(EtaContext etaContext, DispatchPairClusterStage pairClusterStage) {
        long boundaryExpansionStartedAt = System.nanoTime();
        Map<String, List<BoundaryCandidate>> boundaryCandidates = boundaryCandidateSelector.select(
                pairClusterStage.bufferedOrderWindow(),
                pairClusterStage.microClusters(),
                pairClusterStage.pairSimilarityGraph());
        List<BoundaryExpansion> boundaryExpansions = pairClusterStage.microClusters().stream()
                .map(cluster -> boundaryExpansionEngine.expand(
                        cluster,
                        boundaryCandidates.getOrDefault(cluster.clusterId(), List.of()),
                        etaContext))
                .toList();
        long boundaryExpansionElapsedMs = elapsedMs(boundaryExpansionStartedAt);

        long bundlePoolStartedAt = System.nanoTime();
        List<String> degradeReasons = new ArrayList<>();
        BoundaryExpansionSummary boundaryExpansionSummary = summarizeBoundaryExpansions(boundaryExpansions, degradeReasons);
        BundleContext context = new BundleContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                pairClusterStage.pairSimilarityGraph(),
                boundaryExpansions);
        List<BundleSeed> seeds = bundleSeedGenerator.generate(pairClusterStage.microClusters(), context);
        List<BundleCandidate> feasibleCandidates = new ArrayList<>();
        MlStageMetadataAccumulator greedRlMetadata = new MlStageMetadataAccumulator("bundle-pool");
        for (BundleSeed seed : seeds) {
            List<BundleCandidate> generatedCandidates = new ArrayList<>(bundleFamilyEnumerator.enumerate(seed, context));
            GreedRlBundleResult greedRlResult = proposeGreedRlBundles(etaContext.traceId(), seed);
            greedRlMetadata.accept(greedRlResult);
            if (harvestRecorder != null) {
                harvestRecorder.recordGreedRlTeacher(
                        seed.cluster().clusterId(),
                        seed.cluster().clusterId(),
                        new GreedRlBundleFeatureVector(
                                "greedrl-bundle-feature-vector/v1",
                                seed.cluster().clusterId(),
                                seed.cluster().clusterId(),
                                List.copyOf(seed.workingOrderIds()),
                                List.copyOf(seed.prioritizedOrderIds()),
                                List.copyOf(seed.acceptedBoundaryOrderIds()),
                                Map.copyOf(seed.supportScoreByOrder()),
                                properties.getBundle().getMaxSize(),
                                properties.getMl().getGreedrl().getMaxProposalsPerCluster()),
                        greedRlResult);
            }
            if (greedRlResult.applied()) {
                generatedCandidates.addAll(toBundleCandidates(seed, context, greedRlResult.proposals()));
            } else if (!greedRlResult.degradeReason().isBlank() && !"greedrl-client-disabled".equals(greedRlResult.degradeReason())) {
                degradeReasons.add(mapGreedRlDegradeReason(greedRlResult.degradeReason()));
            }
            List<BundleCandidate> familyCandidates = generatedCandidates.stream()
                    .map(candidate -> bundleValidator.validate(candidate, context))
                    .filter(BundleCandidate::feasible)
                    .map(candidate -> bundleScorer.score(candidate, context))
                    .sorted(bundleDominancePruner.bundleComparator())
                    .limit(Math.max(1, properties.getBundle().getBeamWidth()))
                    .toList();
            feasibleCandidates.addAll(familyCandidates);
        }
        Map<BundleFamily, Integer> familyCounts = new EnumMap<>(BundleFamily.class);
        Map<BundleProposalSource, Integer> sourceCounts = new EnumMap<>(BundleProposalSource.class);
        feasibleCandidates.forEach(candidate -> familyCounts.merge(candidate.family(), 1, Integer::sum));
        feasibleCandidates.forEach(candidate -> sourceCounts.merge(candidate.proposalSource(), 1, Integer::sum));
        List<BundleCandidate> retained = bundleDominancePruner.prune(feasibleCandidates);
        long bundlePoolElapsedMs = elapsedMs(bundlePoolStartedAt);
        BundlePoolSummary bundlePoolSummary = new BundlePoolSummary(
                "bundle-pool-summary/v1",
                feasibleCandidates.size(),
                retained.size(),
                familyCounts,
                sourceCounts,
                retained.stream().mapToInt(candidate -> candidate.orderIds().size()).max().orElse(0),
                List.copyOf(degradeReasons));
        return new DispatchBundleStage(
                "dispatch-bundle-stage/v1",
                boundaryExpansions,
                boundaryExpansionSummary,
                retained,
                bundlePoolSummary,
                HotStartReuseSummary.none(),
                List.of(
                        DispatchStageLatency.measured("boundary-expansion", boundaryExpansionElapsedMs, false),
                        DispatchStageLatency.measured("bundle-pool", bundlePoolElapsedMs, false)),
                greedRlMetadata.build().stream().toList(),
                List.copyOf(degradeReasons));
    }

    private GreedRlBundleResult proposeGreedRlBundles(String traceId, BundleSeed seed) {
        if (!properties.isMlEnabled() || !properties.getMl().getGreedrl().isEnabled()) {
            return GreedRlBundleResult.notApplied("greedrl-client-disabled");
        }
        if (adaptiveComputeGate.enabled()) {
            AdaptiveComputeGate.GateDecision gateDecision = adaptiveComputeGate.decideGreedRl(
                    new AdaptiveComputeGate.GreedRlInputs(
                            seed.workingOrderIds().size(),
                            seed.acceptedBoundaryOrderIds().size(),
                            supportSpread(seed.supportScoreByOrder()),
                            properties.getMl().getGreedrl().getMaxOrdersPerRequest(),
                            greedRlClient.readyState().ready(),
                            greedRlClient.readyState().workerMetadata()));
            logAdaptiveDecision(traceId, seed, gateDecision);
            if (!gateDecision.escalated()) {
                return GreedRlBundleResult.notApplied(gateDecision.reason(), gateDecision.workerMetadata());
            }
        }
        if (seed.workingOrderIds().size() > properties.getMl().getGreedrl().getMaxOrdersPerRequest()) {
            return GreedRlBundleResult.notApplied("greedrl-scope-too-large");
        }
        return greedRlClient.proposeBundles(
                new GreedRlBundleFeatureVector(
                        "greedrl-bundle-feature-vector/v1",
                        seed.cluster().clusterId(),
                        seed.cluster().clusterId(),
                        List.copyOf(seed.workingOrderIds()),
                        List.copyOf(seed.prioritizedOrderIds()),
                        List.copyOf(seed.acceptedBoundaryOrderIds()),
                        Map.copyOf(seed.supportScoreByOrder()),
                        properties.getBundle().getMaxSize(),
                        properties.getMl().getGreedrl().getMaxProposalsPerCluster()),
                properties.getMl().getGreedrl().getBundleTimeout().toMillis());
    }

    private void logAdaptiveDecision(String traceId,
                                     BundleSeed seed,
                                     AdaptiveComputeGate.GateDecision gateDecision) {
        decisionStageLogger.writeFamily("adaptive_compute_trace", traceId, "bundle-pool", Map.ofEntries(
                Map.entry("stageName", "bundle-pool"),
                Map.entry("workerName", "ml-greedrl-worker"),
                Map.entry("decision", gateDecision.decision().name()),
                Map.entry("escalated", gateDecision.escalated()),
                Map.entry("reason", gateDecision.reason()),
                Map.entry("deviceUsed", gateDecision.workerMetadata().device()),
                Map.entry("workerAuditPresent", MlWorkerAuditSupport.auditPresent(gateDecision.workerMetadata())),
                Map.entry("workerAuditSource", MlWorkerAuditSupport.auditSource(gateDecision.workerMetadata())),
                Map.entry("workerAuditMissingFields", MlWorkerAuditSupport.missingFields(gateDecision.workerMetadata())),
                Map.entry("workerReady", greedRlClient.readyState().ready()),
                Map.entry("clusterId", seed.cluster().clusterId()),
                Map.entry("workingOrderCount", seed.workingOrderIds().size()),
                Map.entry("acceptedBoundaryOrderCount", seed.acceptedBoundaryOrderIds().size()),
                Map.entry("supportSpread", supportSpread(seed.supportScoreByOrder()))));
    }

    private double supportSpread(Map<String, Double> supportScoreByOrder) {
        if (supportScoreByOrder == null || supportScoreByOrder.isEmpty()) {
            return 0.0;
        }
        double min = supportScoreByOrder.values().stream().mapToDouble(Double::doubleValue).min().orElse(0.0);
        double max = supportScoreByOrder.values().stream().mapToDouble(Double::doubleValue).max().orElse(0.0);
        return max - min;
    }

    private List<BundleCandidate> toBundleCandidates(BundleSeed seed,
                                                     BundleContext context,
                                                     List<GreedRlBundleCandidate> proposals) {
        return proposals.stream()
                .map(proposal -> toBundleCandidate(seed, context, proposal))
                .flatMap(Optional::stream)
                .toList();
    }

    private Optional<BundleCandidate> toBundleCandidate(BundleSeed seed,
                                                        BundleContext context,
                                                        GreedRlBundleCandidate proposal) {
        List<String> distinctOrders = proposal.orderIds().stream()
                .filter(seed.workingOrderIds()::contains)
                .distinct()
                .sorted()
                .limit(properties.getBundle().getMaxSize())
                .toList();
        if (distinctOrders.isEmpty()) {
            return Optional.empty();
        }
        String orderSetSignature = context.orderSetSignature(distinctOrders);
        String seedOrderId = distinctOrders.getFirst();
        String corridorSignature = "%d:%d".formatted(
                Math.round(context.order(seedOrderId).dropoffPoint().latitude() - context.order(seedOrderId).pickupPoint().latitude()),
                Math.round(context.order(seedOrderId).dropoffPoint().longitude() - context.order(seedOrderId).pickupPoint().longitude()));
        List<String> acceptedBoundaryOrderIds = proposal.acceptedBoundaryOrderIds().stream()
                .filter(seed.acceptedBoundaryOrderIds()::contains)
                .distinct()
                .sorted()
                .toList();
        return Optional.of(new BundleCandidate(
                "bundle-candidate/v1",
                "GREEDRL|%s|%s".formatted(orderSetSignature, seed.cluster().clusterId()),
                BundleProposalSource.GREEDRL_PROPOSAL,
                parseFamily(proposal.family()),
                seed.cluster().clusterId(),
                proposal.boundaryCross(),
                acceptedBoundaryOrderIds,
                distinctOrders,
                orderSetSignature,
                seedOrderId,
                corridorSignature,
                0.0,
                false,
                List.of()));
    }

    private BundleFamily parseFamily(String family) {
        if (family == null || family.isBlank()) {
            return BundleFamily.COMPACT_CLIQUE;
        }
        try {
            return BundleFamily.valueOf(family);
        } catch (IllegalArgumentException exception) {
            return BundleFamily.COMPACT_CLIQUE;
        }
    }

    private String mapGreedRlDegradeReason(String greedRlReason) {
        if ("greedrl-scope-too-large".equals(greedRlReason)) {
            return greedRlReason;
        }
        return "greedrl-ml-unavailable";
    }

    private BoundaryExpansionSummary summarizeBoundaryExpansions(List<BoundaryExpansion> expansions, List<String> degradeReasons) {
        int expandedClusterCount = (int) expansions.stream().filter(expansion -> !expansion.acceptedBoundaryOrderIds().isEmpty()).count();
        int acceptedCount = expansions.stream().mapToInt(expansion -> expansion.acceptedBoundaryOrderIds().size()).sum();
        int rejectedCount = expansions.stream().mapToInt(expansion -> expansion.rejectedBoundaryOrderIds().size()).sum();
        degradeReasons.addAll(expansions.stream().flatMap(expansion -> expansion.expansionReasons().stream()).distinct().toList());
        return new BoundaryExpansionSummary(
                "boundary-expansion-summary/v1",
                expansions.size(),
                expandedClusterCount,
                acceptedCount,
                rejectedCount,
                List.copyOf(degradeReasons));
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }
}
