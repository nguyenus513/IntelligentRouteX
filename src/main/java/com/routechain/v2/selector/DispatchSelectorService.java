package com.routechain.v2.selector;

import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.EtaContext;
import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.active.ActiveInsertionSelectorBridge;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.objective.UnifiedObjective;
import com.routechain.v2.repair.ActiveRouteRepairService;
import com.routechain.v2.repair.ActiveRouteRepairResult;
import com.routechain.v2.repair.RepairCandidate;
import com.routechain.v2.repair.RepairContext;
import com.routechain.v2.scenario.DispatchScenarioStage;

import java.time.Duration;
import java.util.List;
import java.util.stream.Stream;

public final class DispatchSelectorService {
    private final RouteChainDispatchV2Properties properties;
    private final SelectorCandidateBuilder selectorCandidateBuilder;
    private final ConflictGraphBuilder conflictGraphBuilder;
    private final GlobalSelector globalSelector;
    private final ActiveInsertionSelectorBridge activeInsertionSelectorBridge;
    private final HybridCandidatePoolBuilder hybridCandidatePoolBuilder;
    private final UnifiedObjective unifiedObjective;
    private final ActiveRouteRepairService activeRouteRepairService;

    public DispatchSelectorService(RouteChainDispatchV2Properties properties,
                                   SelectorCandidateBuilder selectorCandidateBuilder,
                                   ConflictGraphBuilder conflictGraphBuilder,
                                   GlobalSelector globalSelector) {
        this.properties = properties;
        this.selectorCandidateBuilder = selectorCandidateBuilder;
        this.conflictGraphBuilder = conflictGraphBuilder;
        this.globalSelector = globalSelector;
        this.activeInsertionSelectorBridge = new ActiveInsertionSelectorBridge();
        this.hybridCandidatePoolBuilder = new HybridCandidatePoolBuilder();
        this.unifiedObjective = new UnifiedObjective();
        this.activeRouteRepairService = new ActiveRouteRepairService();
    }

    public DispatchSelectorStage evaluate(DispatchV2Request request,
                                         EtaContext etaContext,
                                         DispatchPairClusterStage pairClusterStage,
                                         DispatchBundleStage bundleStage,
                                         DispatchRouteCandidateStage routeCandidateStage,
                                         DispatchRouteProposalStage routeProposalStage,
                                         DispatchScenarioStage scenarioStage) {
        return evaluate(
                request,
                etaContext,
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage,
                List.of());
    }

    public DispatchSelectorStage evaluate(DispatchV2Request request,
                                         EtaContext etaContext,
                                         DispatchPairClusterStage pairClusterStage,
                                         DispatchBundleStage bundleStage,
                                         DispatchRouteCandidateStage routeCandidateStage,
                                         DispatchRouteProposalStage routeProposalStage,
                                         DispatchScenarioStage scenarioStage,
                                         List<ActiveRouteInsertionCandidate> activeInsertionCandidates) {
        long selectorStartedAt = System.nanoTime();
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                request.availableDrivers(),
                pairClusterStage,
                bundleStage);
        SelectorCandidateBuildResult buildResult = selectorCandidateBuilder.build(
                routeProposalStage,
                scenarioStage,
                routeCandidateStage,
                context);
        ActiveRouteRepairResult repairResult = properties.getSelector().isActiveRouteRepairEnabled()
                ? activeRouteRepairService.evaluateWithTelemetry(new RepairContext(
                List.of(),
                activeInsertionCandidates,
                Duration.ofMillis(300)))
                : ActiveRouteRepairResult.empty();
        List<RepairCandidate> repairCandidates = repairResult.candidates();
        List<ActiveRouteInsertionCandidate> repairedActiveInsertionCandidates = repairCandidates.isEmpty()
                ? activeInsertionCandidates
                : repairCandidates.stream().map(RepairCandidate::insertionCandidate).toList();
        List<SelectorCandidateEnvelope> activeInsertionEnvelopes = activeInsertionSelectorBridge.bridge(repairedActiveInsertionCandidates);
        HybridCandidatePoolResult poolResult = hybridCandidatePoolBuilder.build(
                buildResult.candidateEnvelopes(),
                activeInsertionEnvelopes);
        List<SelectorCandidateEnvelope> candidateEnvelopes = poolResult.candidateEnvelopes();
        List<SelectorCandidate> selectorCandidates = candidateEnvelopes.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .toList();
        ConflictGraph conflictGraph = conflictGraphBuilder.build(selectorCandidates);
        SelectorSelectionOutcome selectionOutcome = globalSelector.select(candidateEnvelopes, conflictGraph);
        buildResult.decisionTrace().merge(selectionOutcome.decisionTrace());
        List<String> degradeReasons = Stream.concat(
                        buildResult.degradeReasons().stream(),
                        Stream.concat(
                                selectionOutcome.selectionResult().degradeReasons().stream(),
                                Stream.concat(
                                        poolResult.degradeReasons().stream(),
                                        Stream.concat(
                                                repairResult.degradeReasons().stream(),
                                                activeInsertionEnvelopes.isEmpty()
                                                        ? Stream.empty()
                                                        : Stream.of(activeRepairReason(activeInsertionCandidates, repairCandidates), "active-route-insertion-candidates-merged")))))
                .distinct()
                .toList();
        GlobalSelectionResult selectionResult = selectionOutcome.selectionResult().degradeReasons().equals(degradeReasons)
                ? selectionOutcome.selectionResult()
                : new GlobalSelectionResult(
                selectionOutcome.selectionResult().schemaVersion(),
                selectionOutcome.selectionResult().selectedProposals(),
                selectionOutcome.selectionResult().retainedCandidateCount(),
                selectionOutcome.selectionResult().selectedCount(),
                selectionOutcome.selectionResult().solverMode(),
                selectionOutcome.selectionResult().objectiveValue(),
                degradeReasons);
        List<SelectorObjectiveBreakdown> objectiveBreakdowns = objectiveBreakdowns(selectorCandidates);
        List<SelectorTrainingTrace> trainingTraces = trainingTraces(request.traceId(), selectorCandidates, selectionResult);
        return new DispatchSelectorStage(
                "dispatch-selector-stage/v1",
                selectorCandidates,
                conflictGraph,
                selectionResult,
                summarize(selectorCandidates, conflictGraph, selectionResult, degradeReasons),
                objectiveBreakdowns,
                repairResult.telemetry(),
                trainingTraces,
                List.of(DispatchStageLatency.measured("global-selector", elapsedMs(selectorStartedAt), false)),
                degradeReasons);
    }

    private String activeRepairReason(List<ActiveRouteInsertionCandidate> activeInsertionCandidates,
                                      List<RepairCandidate> repairCandidates) {
        if (activeInsertionCandidates == null || activeInsertionCandidates.isEmpty()) {
            return "active-route-repair-no-input";
        }
        return repairCandidates.isEmpty() ? "active-route-repair-fallback-original-candidates" : "active-route-bounded-alns-repair-applied";
    }

    private List<SelectorObjectiveBreakdown> objectiveBreakdowns(List<SelectorCandidate> selectorCandidates) {
        return selectorCandidates.stream()
                .map(candidate -> new SelectorObjectiveBreakdown(
                        candidate.proposalId(),
                        unifiedObjective.scoreSelectorCandidate(candidate)))
                .toList();
    }

    private List<SelectorTrainingTrace> trainingTraces(String traceId,
                                                       List<SelectorCandidate> selectorCandidates,
                                                       GlobalSelectionResult selectionResult) {
        java.util.Set<String> selectedProposalIds = selectionResult.selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .collect(java.util.stream.Collectors.toSet());
        return selectorCandidates.stream()
                .map(candidate -> new SelectorTrainingTrace(
                        "selector-training-trace/v1",
                        traceId,
                        candidate.proposalId(),
                        candidate.source(),
                        candidate.driverId(),
                        candidate.orderIds(),
                        candidate.selectionScore(),
                        candidate.robustUtility(),
                        candidate.routeValue(),
                        candidate.feasible(),
                        selectedProposalIds.contains(candidate.proposalId()),
                        candidate.reasons(),
                        candidate.degradeReasons()))
                .toList();
    }

    private GlobalSelectorSummary summarize(List<SelectorCandidate> selectorCandidates,
                                            ConflictGraph conflictGraph,
                                            GlobalSelectionResult selectionResult,
                                            List<String> degradeReasons) {
        int feasibleCandidateCount = (int) selectorCandidates.stream().filter(SelectorCandidate::feasible).count();
        return new GlobalSelectorSummary(
                "global-selector-summary/v1",
                selectorCandidates.size(),
                feasibleCandidateCount,
                conflictGraph.conflictEdgeCount(),
                selectionResult.selectedCount(),
                selectionResult.solverMode(),
                selectionResult.selectorPoolInputCount(),
                selectionResult.selectorPoolReducedCount(),
                selectionResult.selectorRejectedCount(),
                selectionResult.selectorTimedOut(),
                selectionResult.selectorFallbackLevel(),
                selectionResult.acceptanceGatePassed(),
                selectionResult.acceptanceGateRejectedReasons(),
                selectionResult.selectorMaxPoolSize(),
                selectionResult.selectorPoolCapApplied(),
                selectionResult.selectorPoolCapObjectiveLoss(),
                degradeReasons);
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }
}
