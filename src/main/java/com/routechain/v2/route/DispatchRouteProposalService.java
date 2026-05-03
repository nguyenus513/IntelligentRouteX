package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.EtaContext;
import com.routechain.v2.HotStartReuseSummary;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.compute.AdaptiveComputeGate;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.feedback.ReuseStateBuilder;
import com.routechain.v2.feedback.RouteProposalTupleReuseEntry;
import com.routechain.v2.integration.MlStageMetadataAccumulator;
import com.routechain.v2.integration.MlWorkerAuditSupport;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.RouteFinderFeatureVector;
import com.routechain.v2.integration.RouteFinderResult;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.routing.RouteVectorEnricher;
import com.routechain.v2.routing.RouteVectorCache;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class DispatchRouteProposalService {
    private final RouteChainDispatchV2Properties properties;
    private final RouteProposalEngine routeProposalEngine;
    private final RouteProposalValidator routeProposalValidator;
    private final RouteValueScorer routeValueScorer;
    private final RouteProposalPruner routeProposalPruner;
    private final EtaLegCacheFactory etaLegCacheFactory;
    private final RouteFinderClient routeFinderClient;
    private final RouteVectorEnricher routeVectorEnricher;
    private final DecisionStageLogger decisionStageLogger;
    private final HarvestRecorder harvestRecorder;
    private final AdaptiveComputeGate adaptiveComputeGate;
    private final RouteProposalBudgetPolicy routeProposalBudgetPolicy;
    private final RouteProposalPrePruner routeProposalPrePruner;

    public DispatchRouteProposalService(RouteChainDispatchV2Properties properties,
                                        RouteProposalEngine routeProposalEngine,
                                        RouteProposalValidator routeProposalValidator,
                                        RouteValueScorer routeValueScorer,
                                        RouteProposalPruner routeProposalPruner,
                                        EtaLegCacheFactory etaLegCacheFactory,
                                        RouteFinderClient routeFinderClient,
                                        RouteVectorEnricher routeVectorEnricher,
                                        DecisionStageLogger decisionStageLogger,
                                        HarvestRecorder harvestRecorder,
                                        AdaptiveComputeGate adaptiveComputeGate) {
        this.properties = properties;
        this.routeProposalEngine = routeProposalEngine;
        this.routeProposalValidator = routeProposalValidator;
        this.routeValueScorer = routeValueScorer;
        this.routeProposalPruner = routeProposalPruner;
        this.etaLegCacheFactory = etaLegCacheFactory;
        this.routeFinderClient = routeFinderClient;
        this.routeVectorEnricher = routeVectorEnricher;
        this.decisionStageLogger = decisionStageLogger;
        this.harvestRecorder = harvestRecorder;
        this.adaptiveComputeGate = adaptiveComputeGate;
        this.routeProposalBudgetPolicy = new RouteProposalBudgetPolicy(properties);
        this.routeProposalPrePruner = new RouteProposalPrePruner();
    }

    public DispatchRouteProposalService(RouteChainDispatchV2Properties properties,
                                        RouteProposalEngine routeProposalEngine,
                                        RouteProposalValidator routeProposalValidator,
                                        RouteValueScorer routeValueScorer,
                                        RouteProposalPruner routeProposalPruner,
                                        EtaLegCacheFactory etaLegCacheFactory,
                                        RouteFinderClient routeFinderClient,
                                        RouteVectorEnricher routeVectorEnricher,
                                        DecisionStageLogger decisionStageLogger,
                                        HarvestRecorder harvestRecorder) {
        this(properties,
                routeProposalEngine,
                routeProposalValidator,
                routeValueScorer,
                routeProposalPruner,
                etaLegCacheFactory,
                routeFinderClient,
                routeVectorEnricher,
                decisionStageLogger,
                harvestRecorder,
                new AdaptiveComputeGate(properties));
    }

    public DispatchRouteProposalService(RouteChainDispatchV2Properties properties,
                                        RouteProposalEngine routeProposalEngine,
                                        RouteProposalValidator routeProposalValidator,
                                        RouteValueScorer routeValueScorer,
                                        RouteProposalPruner routeProposalPruner,
                                        EtaLegCacheFactory etaLegCacheFactory,
                                        RouteFinderClient routeFinderClient,
                                        RouteVectorEnricher routeVectorEnricher,
                                        DecisionStageLogger decisionStageLogger) {
        this(properties,
                routeProposalEngine,
                routeProposalValidator,
                routeValueScorer,
                routeProposalPruner,
                etaLegCacheFactory,
                routeFinderClient,
                routeVectorEnricher,
                decisionStageLogger,
                null,
                new AdaptiveComputeGate(properties));
    }

    public DispatchRouteProposalStage evaluate(DispatchV2Request request,
                                               EtaContext etaContext,
                                               DispatchPairClusterStage pairClusterStage,
                                               DispatchBundleStage bundleStage,
                                               DispatchRouteCandidateStage routeCandidateStage) {
        return evaluate(request, etaContext, pairClusterStage, bundleStage, routeCandidateStage, null);
    }

    public DispatchRouteProposalStage evaluate(DispatchV2Request request,
                                               EtaContext etaContext,
                                               DispatchPairClusterStage pairClusterStage,
                                               DispatchBundleStage bundleStage,
                                               DispatchRouteCandidateStage routeCandidateStage,
                                               RouteProposalReuseInput reuseInput) {
        long routeProposalStartedAt = System.nanoTime();
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                request.availableDrivers(),
                pairClusterStage,
                bundleStage);
        EtaLegCache etaLegCache = etaLegCacheFactory.create(
                request.traceId(),
                request.decisionTime(),
                request.weatherProfile() == null ? WeatherProfile.CLEAR : request.weatherProfile());
        RouteReusePreparation reusePreparation = prepareReuse(bundleStage, routeCandidateStage, reuseInput);
        RouteProposalBudgetDecision budgetDecision = routeProposalBudgetPolicy.decide(
                request,
                etaContext,
                bundleStage.bundleCandidates().size(),
                reusePreparation.freshDriverCandidates().size(),
                0.0);
        RouteProposalPruneResult inputBudget = routeProposalPrePruner.pruneInputs(
                reusePreparation.freshDriverCandidates(),
                routeCandidateStage.pickupAnchors(),
                context,
                budgetDecision);
        List<RouteProposalCandidate> deterministicGenerated = routeProposalEngine.generate(
                inputBudget.driverCandidates(),
                inputBudget.pickupAnchors(),
                context,
                etaLegCache);
        RouteFinderGenerationOutcome routeFinderGeneration = generateRouteFinderProposals(request.traceId(), etaContext, deterministicGenerated, context);
        List<RouteProposalCandidate> generated = new ArrayList<>(reusePreparation.reusedCandidates());
        generated.addAll(deterministicGenerated);
        generated.addAll(routeFinderGeneration.generatedCandidates());
        RouteProposalPruneResult candidateBudget = routeProposalPrePruner.pruneCandidates(
                java.util.stream.Stream.concat(
                                deterministicGenerated.stream(),
                                routeFinderGeneration.generatedCandidates().stream())
                        .toList(),
                context,
                budgetDecision);
        RouteVectorCache routeVectorCache = new RouteVectorCache();
        String weatherBucket = weatherBucket(etaContext);
        String trafficBucket = trafficBucket(etaContext);
        List<RouteProposalCandidate> enrichedReused = reusePreparation.reusedCandidates().stream()
                .map(candidate -> routeProposalValidator.validate(candidate, context))
                .map(candidate -> enrichCandidate(request.traceId(), candidate, context, routeVectorCache, weatherBucket, trafficBucket))
                .toList();
        List<RouteProposalCandidate> validatedFresh = candidateBudget.candidates().stream()
                .map(candidate -> routeProposalValidator.validate(candidate, context))
                .map(candidate -> enrichCandidate(request.traceId(), candidate, context, routeVectorCache, weatherBucket, trafficBucket))
                .toList();
        List<RouteValueScoringOutcome> scoringOutcomes = validatedFresh.stream()
                .map(candidate -> routeValueScorer.score(request.traceId(), candidate, context))
                .toList();
        List<RouteProposalCandidate> scored = new ArrayList<>(enrichedReused);
        scored.addAll(scoringOutcomes.stream()
                .map(RouteValueScoringOutcome::candidate)
                .toList());
        List<RouteProposalCandidate> retained = routeProposalPruner.prune(scored);
        List<RouteProposalCandidate> roadRefined = retained.stream()
                .map(candidate -> enrichCandidate(request.traceId(), candidate, context, null, weatherBucket, trafficBucket, "road-refinement"))
                .map(candidate -> routeValueScorer.score(request.traceId(), candidate, context).candidate())
                .toList();
        retained = routeProposalPruner.prune(roadRefined);
        List<RouteProposal> routeProposals = retained.stream().map(RouteProposalCandidate::proposal).toList();
        decisionStageLogger.writeFamily("route_selection_trace", request.traceId(), "route-proposal-pool", java.util.Map.of(
                "generatedProposalIds", generated.stream().map(candidate -> candidate.proposal().proposalId()).toList(),
                "retainedProposalIds", retained.stream().map(candidate -> candidate.proposal().proposalId()).toList(),
                "budgetMetrics", budgetMetrics(budgetDecision, inputBudget, candidateBudget, routeVectorCache)));
        List<String> degradeReasons = java.util.stream.Stream.of(
                        reusePreparation.degradeReasons().stream(),
                        routeFinderGeneration.degradeReasons().stream(),
                        scored.stream().flatMap(candidate -> candidate.proposal().degradeReasons().stream()),
                        scoringOutcomes.stream().flatMap(outcome -> outcome.degradeReasons().stream()))
                .flatMap(stream -> stream)
                .distinct()
                .toList();
        List<MlStageMetadata> mlStageMetadata = java.util.stream.Stream.of(
                        routeFinderGeneration.mlStageMetadata().stream(),
                        scoringOutcomes.stream().flatMap(outcome -> outcome.mlStageMetadata().stream()))
                .flatMap(stream -> stream)
                .distinct()
                .toList();
        long routeProposalElapsedMs = elapsedMs(routeProposalStartedAt);
        return new DispatchRouteProposalStage(
                "dispatch-route-proposal-stage/v1",
                routeProposals,
                summarize(routeCandidateStage.driverCandidates().size(), generated, retained, degradeReasons,
                        budgetMetrics(budgetDecision, inputBudget, candidateBudget, routeVectorCache)),
                new HotStartReuseSummary(
                        "hot-start-reuse-summary/v1",
                        !reusePreparation.reusedCandidates().isEmpty(),
                        reusePreparation.reusedCandidates().size(),
                        reusePreparation.degradeReasons()),
                List.of(DispatchStageLatency.measured("route-proposal-pool", routeProposalElapsedMs, !reusePreparation.reusedCandidates().isEmpty())),
                mlStageMetadata,
                degradeReasons);
    }

    private RouteReusePreparation prepareReuse(DispatchBundleStage bundleStage,
                                               DispatchRouteCandidateStage routeCandidateStage,
                                               RouteProposalReuseInput reuseInput) {
        if (reuseInput == null || reuseInput.reuseState() == null) {
            return RouteReusePreparation.empty(routeCandidateStage.driverCandidates());
        }
        Map<String, BundleCandidate> bundlesById = bundleStage.bundleCandidates().stream()
                .collect(java.util.stream.Collectors.toMap(BundleCandidate::bundleId, bundle -> bundle, (left, right) -> left));
        Map<String, PickupAnchor> anchorsByKey = routeCandidateStage.pickupAnchors().stream()
                .collect(java.util.stream.Collectors.toMap(
                        anchor -> ReuseStateBuilder.tupleKey(anchor.bundleId(), anchor.anchorOrderId(), null),
                        anchor -> anchor,
                        (left, right) -> left));
        Map<String, RouteProposalTupleReuseEntry> storedByKey = reuseInput.reuseState().routeProposalTuples().stream()
                .collect(java.util.stream.Collectors.toMap(
                        entry -> ReuseStateBuilder.tupleKey(entry.bundleId(), entry.anchorOrderId(), entry.driverId()),
                        entry -> entry,
                        (left, right) -> left,
                        java.util.LinkedHashMap::new));
        List<RouteProposalCandidate> reusedCandidates = new ArrayList<>();
        List<DriverCandidate> freshDriverCandidates = new ArrayList<>();
        List<String> degradeReasons = new ArrayList<>();
        boolean tupleDrift = false;
        for (DriverCandidate driverCandidate : routeCandidateStage.driverCandidates()) {
            String key = ReuseStateBuilder.tupleKey(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), driverCandidate.driverId());
            PickupAnchor pickupAnchor = anchorsByKey.get(ReuseStateBuilder.tupleKey(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), null));
            BundleCandidate bundle = bundlesById.get(driverCandidate.bundleId());
            RouteProposalTupleReuseEntry stored = storedByKey.get(key);
            if (bundle == null || pickupAnchor == null || stored == null) {
                freshDriverCandidates.add(driverCandidate);
                tupleDrift = true;
                continue;
            }
            String currentSignature = ReuseStateBuilder.routeProposalTupleSignature(bundle, pickupAnchor, driverCandidate);
            if (!Objects.equals(currentSignature, stored.tupleSignature())) {
                freshDriverCandidates.add(driverCandidate);
                tupleDrift = true;
                continue;
            }
            reusedCandidates.addAll(stored.routeProposals().stream()
                    .map(proposal -> reusedCandidate(proposal, pickupAnchor, driverCandidate))
                    .toList());
        }
        if (tupleDrift) {
            degradeReasons.add("hot-start-route-tuple-drift");
        }
        return new RouteReusePreparation(
                List.copyOf(reusedCandidates),
                List.copyOf(freshDriverCandidates),
                List.copyOf(degradeReasons));
    }

    private RouteProposalCandidate reusedCandidate(RouteProposal proposal,
                                                   PickupAnchor pickupAnchor,
                                                   DriverCandidate driverCandidate) {
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(proposal.bundleId(), proposal.anchorOrderId(), proposal.driverId());
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(
                        tupleKey,
                        proposal.source(),
                        RouteProposalEngine.stopOrderSignature(proposal.stopOrder()),
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        List.of("hot-start-route-reused")));
    }

    private RouteProposalCandidate enrichCandidate(String traceId,
                                                   RouteProposalCandidate candidate,
                                                   DispatchCandidateContext context,
                                                   RouteVectorCache routeVectorCache,
                                                   String weatherBucket,
                                                   String trafficBucket) {
        return enrichCandidate(traceId, candidate, context, routeVectorCache, weatherBucket, trafficBucket, "pool-enrichment");
    }

    private RouteProposalCandidate enrichCandidate(String traceId,
                                                   RouteProposalCandidate candidate,
                                                   DispatchCandidateContext context,
                                                   RouteVectorCache routeVectorCache,
                                                   String weatherBucket,
                                                   String trafficBucket,
                                                   String routingIntent) {
        RouteProposal enrichedProposal = routeVectorEnricher.enrich(traceId, candidate.proposal(), context, routeVectorCache, weatherBucket, trafficBucket, routingIntent);
        return new RouteProposalCandidate(
                enrichedProposal,
                candidate.tupleKey(),
                candidate.pickupAnchor(),
                candidate.driverCandidate(),
                candidate.trace());
    }

    private RouteFinderGenerationOutcome generateRouteFinderProposals(String traceId,
                                                                      EtaContext etaContext,
                                                                      List<RouteProposalCandidate> deterministicGenerated,
                                                                      DispatchCandidateContext context) {
        if (!properties.isMlEnabled() || !properties.getMl().getRoutefinder().isEnabled()) {
            return RouteFinderGenerationOutcome.empty();
        }
        Map<RouteProposalTupleKey, List<RouteProposalCandidate>> candidatesByTuple = deterministicGenerated.stream()
                .collect(java.util.stream.Collectors.groupingBy(
                        RouteProposalCandidate::tupleKey,
                        java.util.LinkedHashMap::new,
                        java.util.stream.Collectors.toList()));
        MlStageMetadataAccumulator mlStageMetadataAccumulator = new MlStageMetadataAccumulator("route-proposal-pool");
        List<RouteProposalCandidate> generatedCandidates = new ArrayList<>();
        List<String> degradeReasons = new ArrayList<>();
        int tupleOrdinal = 0;
        for (List<RouteProposalCandidate> tupleCandidates : candidatesByTuple.values()) {
            RouteProposalCandidate seed = selectSeed(tupleCandidates);
            if (seed == null) {
                continue;
            }
            if (adaptiveComputeGate.enabled()) {
                AdaptiveComputeGate.GateDecision gateDecision = adaptiveComputeGate.decideRouteFinder(
                        new AdaptiveComputeGate.RouteFinderInputs(
                                tupleOrdinal,
                                tupleCandidates.size(),
                                seed.proposal().stopOrder().size(),
                                topEtaGapMinutes(tupleCandidates),
                                etaContext.weatherBadSignal(),
                                etaContext.trafficBadSignal(),
                                context.bundle(seed.proposal().bundleId()).boundaryCross(),
                                routeFinderClient.readyState().ready(),
                                routeFinderClient.readyState().workerMetadata()));
                logAdaptiveDecision(traceId, seed, tupleCandidates, gateDecision, context);
                tupleOrdinal++;
                if (!gateDecision.escalated()) {
                    continue;
                }
            }
            RouteFinderFeatureVector featureVector = featureVector(traceId, seed, context);
            RouteFinderResult alternatives = routeFinderClient.generateAlternatives(
                    featureVector,
                    properties.getMl().getRoutefinder().getAlternativesTimeout().toMillis());
            mlStageMetadataAccumulator.accept(alternatives);
            if (harvestRecorder != null) {
                harvestRecorder.recordRouteFinderTeacher(traceId, seed.proposal().proposalId(), "alternatives", featureVector, alternatives);
            }
            if (alternatives.applied()) {
                generatedCandidates.addAll(alternatives.routes().stream()
                        .limit(Math.max(1, properties.getMl().getRoutefinder().getMaxAlternativesPerDriverCandidate()))
                        .map(route -> routeProposalEngine.externalCandidate(
                                seed.driverCandidate(),
                                seed.pickupAnchor(),
                                RouteProposalSource.ML_PROPOSAL,
                                route.stopOrder(),
                                route.projectedPickupEtaMinutes(),
                                route.projectedCompletionEtaMinutes(),
                                mergeReasons("routefinder-alternative", route.traceReasons()),
                                List.of()))
                        .toList());
            } else {
                degradeReasons.add("routefinder-ml-unavailable");
            }
            RouteFinderResult refined = routeFinderClient.refineRoute(
                    featureVector,
                    properties.getMl().getRoutefinder().getRefineTimeout().toMillis());
            mlStageMetadataAccumulator.accept(refined);
            if (harvestRecorder != null) {
                harvestRecorder.recordRouteFinderTeacher(traceId, seed.proposal().proposalId(), "refine", featureVector, refined);
            }
            if (refined.applied()) {
                refined.routes().stream().findFirst()
                        .map(route -> routeProposalEngine.externalCandidate(
                                seed.driverCandidate(),
                                seed.pickupAnchor(),
                                RouteProposalSource.ML_REFINED,
                                route.stopOrder(),
                                route.projectedPickupEtaMinutes(),
                                route.projectedCompletionEtaMinutes(),
                                mergeReasons("routefinder-refined", route.traceReasons()),
                                List.of()))
                        .ifPresent(generatedCandidates::add);
            } else {
                degradeReasons.add("routefinder-ml-unavailable");
            }
        }
        return new RouteFinderGenerationOutcome(
                List.copyOf(generatedCandidates),
                mlStageMetadataAccumulator.build().map(List::of).orElse(List.of()),
                List.copyOf(degradeReasons.stream().distinct().toList()));
    }

    private void logAdaptiveDecision(String traceId,
                                     RouteProposalCandidate seed,
                                     List<RouteProposalCandidate> tupleCandidates,
                                     AdaptiveComputeGate.GateDecision gateDecision,
                                     DispatchCandidateContext context) {
        decisionStageLogger.writeFamily("adaptive_compute_trace", traceId, "route-proposal-pool", java.util.Map.ofEntries(
                java.util.Map.entry("stageName", "route-proposal-pool"),
                java.util.Map.entry("workerName", "ml-routefinder-worker"),
                java.util.Map.entry("decision", gateDecision.decision().name()),
                java.util.Map.entry("escalated", gateDecision.escalated()),
                java.util.Map.entry("reason", gateDecision.reason()),
                java.util.Map.entry("deviceUsed", gateDecision.workerMetadata().device()),
                java.util.Map.entry("workerAuditPresent", MlWorkerAuditSupport.auditPresent(gateDecision.workerMetadata())),
                java.util.Map.entry("workerAuditSource", MlWorkerAuditSupport.auditSource(gateDecision.workerMetadata())),
                java.util.Map.entry("workerAuditMissingFields", MlWorkerAuditSupport.missingFields(gateDecision.workerMetadata())),
                java.util.Map.entry("workerReady", routeFinderClient.readyState().ready()),
                java.util.Map.entry("proposalId", seed.proposal().proposalId()),
                java.util.Map.entry("tupleCandidateCount", tupleCandidates.size()),
                java.util.Map.entry("stopCount", seed.proposal().stopOrder().size()),
                java.util.Map.entry("topEtaGapMinutes", topEtaGapMinutes(tupleCandidates)),
                java.util.Map.entry("boundaryCross", context.bundle(seed.proposal().bundleId()).boundaryCross())));
    }

    private double topEtaGapMinutes(List<RouteProposalCandidate> tupleCandidates) {
        List<Double> sortedEtas = tupleCandidates.stream()
                .map(candidate -> candidate.proposal().projectedCompletionEtaMinutes())
                .sorted()
                .toList();
        if (sortedEtas.size() < 2) {
            return -1.0;
        }
        return sortedEtas.get(1) - sortedEtas.getFirst();
    }

    private RouteFinderFeatureVector featureVector(String traceId,
                                                   RouteProposalCandidate seed,
                                                   DispatchCandidateContext context) {
        return new RouteFinderFeatureVector(
                "routefinder-feature-vector/v1",
                traceId,
                seed.proposal().bundleId(),
                seed.proposal().anchorOrderId(),
                seed.proposal().driverId(),
                seed.proposal().source().name(),
                seed.proposal().stopOrder(),
                context.bundle(seed.proposal().bundleId()).orderIds().stream().sorted().toList(),
                seed.proposal().projectedPickupEtaMinutes(),
                seed.proposal().projectedCompletionEtaMinutes(),
                seed.driverCandidate().rerankScore(),
                context.bundleScore(seed.proposal().bundleId()),
                seed.pickupAnchor().score(),
                context.averagePairSupport(context.bundle(seed.proposal().bundleId()).orderIds()),
                context.bundle(seed.proposal().bundleId()).boundaryCross(),
                Math.max(1, properties.getMl().getRoutefinder().getMaxAlternativesPerDriverCandidate()));
    }

    private RouteProposalCandidate selectSeed(List<RouteProposalCandidate> tupleCandidates) {
        return tupleCandidates.stream()
                .sorted(Comparator.comparingInt((RouteProposalCandidate candidate) -> sourcePriority(candidate.proposal().source()))
                        .thenComparingDouble(candidate -> candidate.proposal().projectedPickupEtaMinutes())
                        .thenComparing(candidate -> candidate.proposal().proposalId()))
                .findFirst()
                .orElse(null);
    }

    private int sourcePriority(RouteProposalSource source) {
        return switch (source) {
            case HEURISTIC_FAST -> 0;
            case HEURISTIC_SAFE -> 1;
            case FALLBACK_SIMPLE -> 2;
            case ML_PROPOSAL -> 3;
            case ML_REFINED -> 4;
            case ACTIVE_ROUTE_INSERTION -> 5;
            case BEAUTY_CORRIDOR -> 1;
        };
    }

    private List<String> mergeReasons(String baseReason, List<String> traceReasons) {
        List<String> reasons = new ArrayList<>();
        reasons.add(baseReason);
        if (traceReasons != null) {
            reasons.addAll(traceReasons);
        }
        return List.copyOf(reasons.stream().distinct().toList());
    }

    private record RouteFinderGenerationOutcome(
            List<RouteProposalCandidate> generatedCandidates,
            List<MlStageMetadata> mlStageMetadata,
            List<String> degradeReasons) {

        private static RouteFinderGenerationOutcome empty() {
            return new RouteFinderGenerationOutcome(List.of(), List.of(), List.of());
        }
    }

    private record RouteReusePreparation(
            List<RouteProposalCandidate> reusedCandidates,
            List<DriverCandidate> freshDriverCandidates,
            List<String> degradeReasons) {

        private static RouteReusePreparation empty(List<DriverCandidate> allDrivers) {
            return new RouteReusePreparation(List.of(), List.copyOf(allDrivers), List.of());
        }
    }

    private RouteProposalBudgetMetrics budgetMetrics(RouteProposalBudgetDecision budgetDecision,
                                                     RouteProposalPruneResult inputBudget,
                                                     RouteProposalPruneResult candidateBudget,
                                                     RouteVectorCache routeVectorCache) {
        Map<String, Integer> pruneReasons = new java.util.LinkedHashMap<>();
        inputBudget.pruneReasonCounts().forEach((key, value) -> pruneReasons.merge(key, value, Integer::sum));
        candidateBudget.pruneReasonCounts().forEach((key, value) -> pruneReasons.merge(key, value, Integer::sum));
        return new RouteProposalBudgetMetrics(
                "route-proposal-budget-metrics/v1",
                budgetDecision.enabled(),
                budgetDecision.budgetMode(),
                budgetDecision.maxTotalRouteProposals(),
                inputBudget.candidateCountBeforePrune(),
                inputBudget.candidateCountAfterPrune(),
                candidateBudget.candidateCountBeforePrune(),
                candidateBudget.candidateCountAfterPrune(),
                inputBudget.proposalPrunedBeforeRoutePool() + candidateBudget.proposalPrunedBeforeRoutePool(),
                Map.copyOf(pruneReasons),
                routeVectorCache.computedCount(),
                routeVectorCache.reusedCount(),
                routeVectorCache.hitRate());
    }

    private String weatherBucket(EtaContext etaContext) {
        return etaContext != null && etaContext.weatherBadSignal() ? "weather:bad" : "weather:normal";
    }

    private String trafficBucket(EtaContext etaContext) {
        return etaContext != null && etaContext.trafficBadSignal() ? "traffic:bad" : "traffic:normal";
    }

    private RouteProposalSummary summarize(int driverCandidateCount,
                                          List<RouteProposalCandidate> generated,
                                          List<RouteProposalCandidate> retained,
                                          List<String> degradeReasons,
                                          RouteProposalBudgetMetrics budgetMetrics) {
        Map<RouteProposalSource, Integer> sourceCounts = new EnumMap<>(RouteProposalSource.class);
        generated.forEach(candidate -> sourceCounts.merge(candidate.proposal().source(), 1, Integer::sum));
        int proposalTupleCount = (int) generated.stream().map(RouteProposalCandidate::tupleKey).distinct().count();
        return new RouteProposalSummary(
                "route-proposal-summary/v1",
                driverCandidateCount,
                proposalTupleCount,
                generated.size(),
                retained.size(),
                sourceCounts,
                budgetMetrics,
                List.copyOf(degradeReasons));
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }
}
