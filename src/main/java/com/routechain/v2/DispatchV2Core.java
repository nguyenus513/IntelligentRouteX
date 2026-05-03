package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.active.ActiveFleetStateStore;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.active.ActiveRouteInsertionGenerator;
import com.routechain.v2.active.ActiveRouteState;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.BundleFamily;
import com.routechain.v2.bundle.BundlePoolSummary;
import com.routechain.v2.bundle.BundleProposalSource;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.bundle.DispatchBundleStageService;
import com.routechain.v2.cluster.DispatchPairClusterService;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.context.DispatchEtaContextService;
import com.routechain.v2.context.DispatchEtaContextStage;
import com.routechain.v2.decision.ContextAssembler;
import com.routechain.v2.decision.DecisionBrain;
import com.routechain.v2.decision.DecisionBrainResolver;
import com.routechain.v2.decision.DecisionStageMetaV1;
import com.routechain.v2.decision.DecisionStageInputV1;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.decision.DecisionStageOutputV1;
import com.routechain.v2.decision.DecisionUsageRecord;
import com.routechain.v2.decision.ResolvedDecisionBrain;
import com.routechain.v2.executor.DispatchExecutorService;
import com.routechain.v2.executor.DispatchExecutorStage;
import com.routechain.v2.feedback.DispatchRuntimeReuseState;
import com.routechain.v2.feedback.HotStartAppliedReuse;
import com.routechain.v2.feedback.HotStartReusePlan;
import com.routechain.v2.feedback.PostDispatchHardeningService;
import com.routechain.v2.feedback.WarmStartManager;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.DispatchRouteCandidateService;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DispatchRouteProposalService;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.route.DriverShortlistSummary;
import com.routechain.v2.route.PickupAnchor;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteProposalSummary;
import com.routechain.v2.route.PickupAnchorSummary;
import com.routechain.v2.rolling.AdaptiveHoldWindowPolicy;
import com.routechain.v2.rolling.RollingDecisionMode;
import com.routechain.v2.rolling.RollingDispatchState;
import com.routechain.v2.rolling.RollingHoldDecision;
import com.routechain.v2.rolling.RollingPendingOrderBuffer;
import com.routechain.v2.rolling.RollingReoptimizationPrioritizer;
import com.routechain.v2.scenario.DispatchScenarioService;
import com.routechain.v2.scenario.DispatchScenarioStage;
import com.routechain.v2.scenario.RobustUtility;
import com.routechain.v2.scenario.ScenarioEvaluation;
import com.routechain.v2.scenario.ScenarioEvaluationSummary;
import com.routechain.v2.selector.DispatchSelectorService;
import com.routechain.v2.selector.DispatchSelectorStage;
import com.routechain.v2.selector.GlobalSelectionResult;
import com.routechain.v2.selector.GlobalSelectorSummary;
import com.routechain.v2.selector.SelectedProposal;
import com.routechain.v2.selector.SelectionSolverMode;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class DispatchV2Core {
    private static final List<String> DECISION_STAGES = List.of(
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

    private final RouteChainDispatchV2Properties properties;
    private final DispatchEtaContextService dispatchEtaContextService;
    private final DispatchPairClusterService dispatchPairClusterService;
    private final DispatchBundleStageService dispatchBundleStageService;
    private final DispatchRouteCandidateService dispatchRouteCandidateService;
    private final DispatchRouteProposalService dispatchRouteProposalService;
    private final DispatchScenarioService dispatchScenarioService;
    private final DispatchSelectorService dispatchSelectorService;
    private final DispatchExecutorService dispatchExecutorService;
    private final EtaLegCacheFactory etaLegCacheFactory;
    private final WarmStartManager warmStartManager;
    private final PostDispatchHardeningService postDispatchHardeningService;
    private final DecisionBrainResolver decisionBrainResolver;
    private final ContextAssembler contextAssembler;
    private final DecisionStageLogger decisionStageLogger;
    private final HarvestRecorder harvestRecorder;
    private final AdaptiveHoldWindowPolicy adaptiveHoldWindowPolicy = new AdaptiveHoldWindowPolicy();
    private final RollingPendingOrderBuffer rollingPendingOrderBuffer;
    private final RollingReoptimizationPrioritizer rollingReoptimizationPrioritizer = new RollingReoptimizationPrioritizer();
    private final ActiveFleetStateStore activeFleetStateStore;
    private final ActiveRouteInsertionGenerator activeRouteInsertionGenerator = new ActiveRouteInsertionGenerator();

    public DispatchV2Core(RouteChainDispatchV2Properties properties,
                          DispatchEtaContextService dispatchEtaContextService,
                          DispatchPairClusterService dispatchPairClusterService,
                          DispatchBundleStageService dispatchBundleStageService,
                          DispatchRouteCandidateService dispatchRouteCandidateService,
                          DispatchRouteProposalService dispatchRouteProposalService,
                          DispatchScenarioService dispatchScenarioService,
                          DispatchSelectorService dispatchSelectorService,
                          DispatchExecutorService dispatchExecutorService,
                          EtaLegCacheFactory etaLegCacheFactory,
                          WarmStartManager warmStartManager,
                          PostDispatchHardeningService postDispatchHardeningService,
                          DecisionBrainResolver decisionBrainResolver,
                          ContextAssembler contextAssembler,
                          DecisionStageLogger decisionStageLogger,
                          HarvestRecorder harvestRecorder) {
        this(properties,
                dispatchEtaContextService,
                dispatchPairClusterService,
                dispatchBundleStageService,
                dispatchRouteCandidateService,
                dispatchRouteProposalService,
                dispatchScenarioService,
                dispatchSelectorService,
                dispatchExecutorService,
                etaLegCacheFactory,
                warmStartManager,
                postDispatchHardeningService,
                decisionBrainResolver,
                contextAssembler,
                decisionStageLogger,
                harvestRecorder,
                new RollingPendingOrderBuffer(),
                new ActiveFleetStateStore());
    }

    public DispatchV2Core(RouteChainDispatchV2Properties properties,
                          DispatchEtaContextService dispatchEtaContextService,
                          DispatchPairClusterService dispatchPairClusterService,
                          DispatchBundleStageService dispatchBundleStageService,
                          DispatchRouteCandidateService dispatchRouteCandidateService,
                          DispatchRouteProposalService dispatchRouteProposalService,
                          DispatchScenarioService dispatchScenarioService,
                          DispatchSelectorService dispatchSelectorService,
                          DispatchExecutorService dispatchExecutorService,
                          EtaLegCacheFactory etaLegCacheFactory,
                          WarmStartManager warmStartManager,
                          PostDispatchHardeningService postDispatchHardeningService,
                          DecisionBrainResolver decisionBrainResolver,
                          ContextAssembler contextAssembler,
                          DecisionStageLogger decisionStageLogger,
                          HarvestRecorder harvestRecorder,
                          RollingPendingOrderBuffer rollingPendingOrderBuffer,
                          ActiveFleetStateStore activeFleetStateStore) {
        this.properties = properties;
        this.dispatchEtaContextService = dispatchEtaContextService;
        this.dispatchPairClusterService = dispatchPairClusterService;
        this.dispatchBundleStageService = dispatchBundleStageService;
        this.dispatchRouteCandidateService = dispatchRouteCandidateService;
        this.dispatchRouteProposalService = dispatchRouteProposalService;
        this.dispatchScenarioService = dispatchScenarioService;
        this.dispatchSelectorService = dispatchSelectorService;
        this.dispatchExecutorService = dispatchExecutorService;
        this.etaLegCacheFactory = etaLegCacheFactory;
        this.warmStartManager = warmStartManager;
        this.postDispatchHardeningService = postDispatchHardeningService;
        this.decisionBrainResolver = decisionBrainResolver;
        this.contextAssembler = contextAssembler;
        this.decisionStageLogger = decisionStageLogger;
        this.harvestRecorder = harvestRecorder;
        this.rollingPendingOrderBuffer = rollingPendingOrderBuffer;
        this.activeFleetStateStore = activeFleetStateStore;
    }

    public DispatchV2Result dispatch(DispatchV2Request request) {
        DispatchPipelineExecution execution = executePipeline(request, true);
        DispatchLatencyBudgetSummary latencyBudgetSummary = execution.result().latencyBudgetSummary();
        List<String> reusedStageNames = execution.result().stageLatencies().stream()
                .filter(DispatchStageLatency::hotStartReused)
                .map(DispatchStageLatency::stageName)
                .toList();
        HotStartAppliedReuse appliedReuse = new HotStartAppliedReuse(
                "hot-start-applied-reuse/v1",
                execution.pairClusterStage().hotStartReuseSummary().reused(),
                execution.bundleStage().hotStartReuseSummary().reused(),
                execution.routeProposalStage().hotStartReuseSummary().reused(),
                execution.bundleStage().hotStartReuseSummary().reusedCount(),
                execution.routeProposalStage().hotStartReuseSummary().reusedCount(),
                latencyBudgetSummary.estimatedHotStartSavedMs(),
                reusedStageNames,
                java.util.stream.Stream.of(
                                execution.pairClusterStage().hotStartReuseSummary().degradeReasons().stream(),
                                execution.bundleStage().hotStartReuseSummary().degradeReasons().stream(),
                                execution.routeProposalStage().hotStartReuseSummary().degradeReasons().stream())
                        .flatMap(stream -> stream)
                        .distinct()
                        .toList());
        return postDispatchHardeningService.apply(
                request,
                execution,
                execution.hotStartReusePlan(),
                appliedReuse);
    }

    public DispatchV2Result dispatchForReplay(DispatchV2Request request) {
        return executePipeline(request, false).result();
    }

    private DispatchPipelineExecution executePipeline(DispatchV2Request request, boolean allowHotStartReuse) {
        long dispatchStartedAt = System.nanoTime();
        DispatchV2Request rollingInputRequest = rollingPendingOrderBuffer.mergeDueOrders(request);
        RollingDispatchState rollingState = RollingDispatchState.fromRequest(rollingInputRequest);
        List<RollingHoldDecision> rollingDecisions = adaptiveHoldWindowPolicy.decide(rollingState);
        rollingPendingOrderBuffer.update(rollingInputRequest, rollingDecisions);
        DispatchV2Request effectiveRequest = applyRollingDecisions(rollingInputRequest, rollingDecisions);
        harvestRecorder.recordRunManifest(effectiveRequest);
        ResolvedDecisionBrain resolvedDecisionBrain = decisionBrainResolver.resolve();
        DecisionStageInputV1 observationInput = contextAssembler.observationInput(effectiveRequest);
        DecisionStageOutputV1 observationOutput = runDecisionSidecar(resolvedDecisionBrain, observationInput);
        writeDecisionJoin(observationInput, effectiveRequest.traceId(), observationOutput, List.of(), List.of(), false, false, List.of());
        decisionStageLogger.writeFamily("rolling_horizon", effectiveRequest.traceId(), "adaptive-hold-window", java.util.Map.of(
                "traceId", effectiveRequest.traceId(),
                "inputOrderCount", request.openOrders().size(),
                "rollingInputOrderCount", rollingInputRequest.openOrders().size(),
                "effectiveOrderCount", effectiveRequest.openOrders().size(),
                "bufferedOrderCount", rollingPendingOrderBuffer.size(),
                "bufferedOrderIds", rollingPendingOrderBuffer.bufferedOrderIds(),
                "decisions", rollingDecisions.stream().map(this::rollingDecisionRow).toList()));
        DispatchEtaContextStage etaStage = dispatchEtaContextService.evaluate(effectiveRequest);
        HotStartReusePlan reusePlan = allowHotStartReuse
                ? postDispatchHardeningService.planHotStartReuse(etaStage.etaContext())
                : HotStartReusePlan.none();
        DispatchPairClusterStage pairClusterStage = dispatchPairClusterService.evaluate(
                effectiveRequest,
                etaStage.etaContext(),
                reusePlan.pairClusterReuseInput());
        DispatchBundleStage bundleStage = dispatchBundleStageService.evaluate(
                etaStage.etaContext(),
                pairClusterStage,
                reusePlan.bundleReuseInput());
        DecisionStageInputV1 pairBundleInput = contextAssembler.pairBundleInput(effectiveRequest, etaStage.etaContext(), pairClusterStage, bundleStage);
        DecisionStageOutputV1 pairBundleOutput = runDecisionSidecar(resolvedDecisionBrain, pairBundleInput);
        StageAuthorityResult<DispatchBundleStage> pairBundleAuthority = applyPairBundleAuthority(bundleStage, pairBundleOutput, resolvedDecisionBrain);
        bundleStage = pairBundleAuthority.value();
        writeDecisionJoin(
                pairBundleInput,
                effectiveRequest.traceId(),
                pairBundleAuthority.output(),
                bundleStage.bundleCandidates().stream().map(BundleCandidate::bundleId).toList(),
                pairBundleAuthority.actualSelectedIds(),
                true,
                pairBundleAuthority.authoritativeApplied(),
                List.of("observation-pack"));
        DispatchRouteCandidateStage routeCandidateStage = dispatchRouteCandidateService.evaluate(
                effectiveRequest,
                etaStage.etaContext(),
                pairClusterStage,
                bundleStage);
        DecisionStageInputV1 anchorInput = contextAssembler.anchorInput(effectiveRequest, etaStage.etaContext(), routeCandidateStage);
        DecisionStageOutputV1 anchorOutput = runDecisionSidecar(resolvedDecisionBrain, anchorInput);
        writeDecisionJoin(
                anchorInput,
                effectiveRequest.traceId(),
                anchorOutput,
                routeCandidateStage.pickupAnchors().stream().map(PickupAnchor::anchorOrderId).toList(),
                routeCandidateStage.pickupAnchors().stream().map(PickupAnchor::anchorOrderId).toList(),
                true,
                false,
                List.of("pair-bundle"));
        DecisionStageInputV1 driverInput = contextAssembler.driverInput(effectiveRequest, etaStage.etaContext(), routeCandidateStage);
        DecisionStageOutputV1 driverOutput = runDecisionSidecar(resolvedDecisionBrain, driverInput);
        StageAuthorityResult<DispatchRouteCandidateStage> driverAuthority = applyDriverAuthority(routeCandidateStage, driverOutput, resolvedDecisionBrain);
        routeCandidateStage = rollingReoptimizationPrioritizer.apply(
                driverAuthority.value(),
                bundleStage.bundleCandidates(),
                rollingDecisions);
        writeDecisionJoin(
                driverInput,
                effectiveRequest.traceId(),
                driverAuthority.output(),
                routeCandidateStage.driverCandidates().stream().map(DriverCandidate::driverId).toList(),
                driverAuthority.actualSelectedIds(),
                true,
                driverAuthority.authoritativeApplied(),
                List.of("anchor"));
        DispatchRouteProposalStage routeProposalStage = dispatchRouteProposalService.evaluate(
                effectiveRequest,
                etaStage.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                reusePlan.routeProposalReuseInput());
        DecisionStageInputV1 routeGenerationInput = contextAssembler.routeGenerationInput(effectiveRequest, etaStage.etaContext(), routeProposalStage);
        DecisionStageOutputV1 routeGenerationOutput = runDecisionSidecar(resolvedDecisionBrain, routeGenerationInput);
        StageAuthorityResult<DispatchRouteProposalStage> routeGenerationAuthority = applyRouteProposalAuthority(routeProposalStage, routeGenerationOutput, resolvedDecisionBrain, "route-generation");
        routeProposalStage = routeGenerationAuthority.value();
        writeDecisionJoin(
                routeGenerationInput,
                effectiveRequest.traceId(),
                routeGenerationAuthority.output(),
                routeProposalStage.routeProposals().stream().map(RouteProposal::proposalId).toList(),
                routeGenerationAuthority.actualSelectedIds(),
                true,
                routeGenerationAuthority.authoritativeApplied(),
                List.of("driver"));
        DecisionStageInputV1 routeCritiqueInput = contextAssembler.routeCritiqueInput(effectiveRequest, etaStage.etaContext(), routeProposalStage);
        DecisionStageOutputV1 routeCritiqueOutput = runDecisionSidecar(resolvedDecisionBrain, routeCritiqueInput);
        StageAuthorityResult<DispatchRouteProposalStage> routeCritiqueAuthority = applyRouteProposalAuthority(routeProposalStage, routeCritiqueOutput, resolvedDecisionBrain, "route-critique");
        routeProposalStage = routeCritiqueAuthority.value();
        writeDecisionJoin(
                routeCritiqueInput,
                effectiveRequest.traceId(),
                routeCritiqueAuthority.output(),
                routeProposalStage.routeProposals().stream().map(RouteProposal::proposalId).toList(),
                routeCritiqueAuthority.actualSelectedIds(),
                true,
                routeCritiqueAuthority.authoritativeApplied(),
                List.of("route-generation"));
        DispatchScenarioStage scenarioStage = dispatchScenarioService.evaluate(
                effectiveRequest,
                etaStage.etaContext(),
                etaStage.freshnessMetadata(),
                etaStage.liveStageMetadata(),
                routeProposalStage,
                routeCandidateStage,
                bundleStage,
                pairClusterStage);
        DecisionStageInputV1 scenarioInput = contextAssembler.scenarioInput(effectiveRequest, etaStage.etaContext(), scenarioStage);
        DecisionStageOutputV1 scenarioOutput = runDecisionSidecar(resolvedDecisionBrain, scenarioInput);
        StageAuthorityResult<DispatchScenarioStage> scenarioAuthority = applyScenarioAuthority(scenarioStage, scenarioOutput, resolvedDecisionBrain);
        scenarioStage = scenarioAuthority.value();
        writeDecisionJoin(
                scenarioInput,
                effectiveRequest.traceId(),
                scenarioAuthority.output(),
                scenarioStage.robustUtilities().stream().map(RobustUtility::proposalId).toList(),
                scenarioAuthority.actualSelectedIds(),
                true,
                scenarioAuthority.authoritativeApplied(),
                List.of("route-critique"));
        List<ActiveRouteInsertionCandidate> activeInsertionCandidates = activeInsertionCandidates(effectiveRequest, rollingDecisions);
        decisionStageLogger.writeFamily("active_route_insertion", effectiveRequest.traceId(), "active-route-insertion", java.util.Map.of(
                "activeRouteCount", activeFleetStateStore.activeRoutes(effectiveRequest).size(),
                "candidateCount", activeInsertionCandidates.size(),
                "candidateIds", activeInsertionCandidates.stream().map(ActiveRouteInsertionCandidate::candidateId).toList(),
                "activeRouteIds", activeFleetStateStore.activeRouteIds()));
        DispatchSelectorStage selectorStage = dispatchSelectorService.evaluate(
                effectiveRequest,
                etaStage.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage,
                activeInsertionCandidates);
        DecisionStageInputV1 finalSelectionInput = contextAssembler.finalSelectionInput(effectiveRequest, etaStage.etaContext(), selectorStage);
        DecisionStageOutputV1 finalSelectionOutput = runDecisionSidecar(
                resolvedDecisionBrain,
                finalSelectionInput);
        StageAuthorityResult<DispatchSelectorStage> finalSelectionAuthority = applyFinalSelectionAuthority(selectorStage, finalSelectionOutput, resolvedDecisionBrain);
        selectorStage = finalSelectionAuthority.value();
        writeDecisionJoin(
                finalSelectionInput,
                effectiveRequest.traceId(),
                finalSelectionAuthority.output(),
                selectorStage.selectorCandidates().stream().map(candidate -> candidate.proposalId()).toList(),
                finalSelectionAuthority.actualSelectedIds(),
                true,
                finalSelectionAuthority.authoritativeApplied(),
                List.of("scenario"));
        DispatchExecutorStage executorStage = dispatchExecutorService.evaluate(
                effectiveRequest,
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                selectorStage);
        activeFleetStateStore.recordAssignments(effectiveRequest, executorStage.assignments());
        DecisionStageInputV1 safetyExecuteInput = contextAssembler.safetyExecuteInput(effectiveRequest, etaStage.etaContext(), executorStage);
        DecisionStageOutputV1 executionOutput = runDecisionSidecar(
                resolvedDecisionBrain,
                safetyExecuteInput);
        writeDecisionJoin(
                safetyExecuteInput,
                effectiveRequest.traceId(),
                executionOutput,
                executorStage.assignments().stream().map(assignment -> assignment.assignmentId()).toList(),
                executorStage.assignments().stream().map(assignment -> assignment.assignmentId()).toList(),
                true,
                false,
                List.of("final-selection"));
        long totalDispatchLatencyMs = elapsedMs(dispatchStartedAt);
        List<DispatchStageLatency> stageLatencies = finalizeStageLatencies(
                mergeStageLatencies(
                        etaStage.stageLatencies(),
                        pairClusterStage.stageLatencies(),
                        bundleStage.stageLatencies(),
                        routeCandidateStage.stageLatencies(),
                        routeProposalStage.stageLatencies(),
                        scenarioStage.stageLatencies(),
                        selectorStage.stageLatencies(),
                        executorStage.stageLatencies()),
                reusePlan,
                totalDispatchLatencyMs);
        DispatchLatencyBudgetSummary latencyBudgetSummary = latencyBudgetSummary(stageLatencies, totalDispatchLatencyMs);
        List<String> budgetDegradeReasons = budgetDegradeReasons(stageLatencies, latencyBudgetSummary);
        List<String> degradeReasons = java.util.stream.Stream.concat(
                        java.util.stream.Stream.concat(
                                java.util.stream.Stream.concat(
                                        java.util.stream.Stream.concat(
                                                java.util.stream.Stream.concat(
                                                        java.util.stream.Stream.concat(
                                                                etaStage.degradeReasons().stream(),
                                                                pairClusterStage.degradeReasons().stream()),
                                                        bundleStage.degradeReasons().stream()),
                                                routeCandidateStage.degradeReasons().stream()),
                                        routeProposalStage.degradeReasons().stream()),
                                scenarioStage.degradeReasons().stream()),
                        java.util.stream.Stream.concat(
                                selectorStage.degradeReasons().stream(),
                                java.util.stream.Stream.concat(
                                        executorStage.degradeReasons().stream(),
                                        budgetDegradeReasons.stream())))
                .distinct()
                .toList();
        List<MlStageMetadata> mlStageMetadata = java.util.stream.Stream.of(
                        etaStage.mlStageMetadata().stream(),
                        pairClusterStage.mlStageMetadata().stream(),
                        bundleStage.mlStageMetadata().stream(),
                        routeCandidateStage.mlStageMetadata().stream(),
                        routeProposalStage.mlStageMetadata().stream(),
                        scenarioStage.mlStageMetadata().stream())
                .flatMap(stream -> stream)
                .distinct()
                .toList();
        List<LiveStageMetadata> liveStageMetadata = java.util.stream.Stream.of(
                        etaStage.liveStageMetadata().stream())
                .flatMap(stream -> stream)
                .distinct()
                .toList();
        List<String> rollingDegradeReasons = rollingDegradeReasons(rollingInputRequest, effectiveRequest, rollingDecisions);
        List<String> finalDegradeReasons = java.util.stream.Stream.concat(degradeReasons.stream(), rollingDegradeReasons.stream())
                .filter(reason -> reason != null && !reason.isBlank())
                .distinct()
                .toList();
        DispatchV2Result result = new DispatchV2Result(
                "dispatch-v2-result/v1",
                effectiveRequest.traceId(),
                false,
                null,
                DECISION_STAGES,
                etaStage.etaContext(),
                etaStage.etaStageTrace(),
                scenarioStage.freshnessMetadata(),
                pairClusterStage.bufferedOrderWindow(),
                pairClusterStage.pairGraphSummary(),
                pairClusterStage.microClusters(),
                pairClusterStage.microClusterSummary(),
                bundleStage.boundaryExpansions(),
                bundleStage.boundaryExpansionSummary(),
                bundleStage.bundleCandidates(),
                bundleStage.bundlePoolSummary(),
                routeCandidateStage.pickupAnchors(),
                routeCandidateStage.pickupAnchorSummary(),
                routeCandidateStage.driverCandidates(),
                routeCandidateStage.driverShortlistSummary(),
                routeProposalStage.routeProposals(),
                routeProposalStage.routeProposalSummary(),
                scenarioStage.scenarioEvaluations(),
                scenarioStage.robustUtilities(),
                scenarioStage.scenarioEvaluationSummary(),
                stageLatencies,
                latencyBudgetSummary,
                mlStageMetadata,
                liveStageMetadata,
                selectorStage.selectorCandidates(),
                selectorStage.conflictGraph(),
                selectorStage.globalSelectionResult(),
                selectorStage.globalSelectorSummary(),
                executorStage.assignments(),
                executorStage.dispatchExecutionSummary(),
                warmStartManager.currentState(),
                new HotStartState(
                        "hot-start-state/v2",
                        reusePlan.previousTraceId(),
                        reusePlan.reuseState() == null ? List.of() : reusePlan.reuseState().clusterSignatures(),
                        reusePlan.reuseState() == null ? List.of() : reusePlan.reuseState().bundleSignatures(),
                        reusePlan.reuseState() == null ? List.of() : reusePlan.reuseState().routeProposals().stream()
                                .map(proposal -> proposal.proposalId()
                                        + "|" + proposal.bundleId()
                                        + "|" + proposal.driverId()
                                        + "|" + String.join(",", proposal.stopOrder()))
                                .sorted()
                                .toList(),
                        List.of(),
                        reusePlan.reuseEligible(),
                        false,
                        false,
                        false,
                        0,
                        0,
                        latencyBudgetSummary.estimatedHotStartSavedMs(),
                        stageLatencies.stream().filter(DispatchStageLatency::hotStartReused).map(DispatchStageLatency::stageName).toList(),
                        reusePlan.degradeReasons()),
                selectorStage.activeRepairTelemetry(),
                finalDegradeReasons);
        decisionStageLogger.writeFamily("dispatch_execution", effectiveRequest.traceId(), "dispatch-executor", executorStage.dispatchExecutionSummary());
        decisionStageLogger.writeFamily("route_outcome_trace", effectiveRequest.traceId(), "dispatch-executor", java.util.Map.of(
                "assignmentIds", executorStage.assignments().stream().map(assignment -> assignment.assignmentId()).toList(),
                "selectedProposalIds", selectorStage.globalSelectionResult().selectedProposals().stream()
                        .map(selectedProposal -> selectedProposal.proposalId())
                        .toList(),
                "executionBrainSelectedIds", executionOutput == null ? List.of() : executionOutput.selectedIds()));
        harvestRecorder.recordDispatchExecution(
                effectiveRequest,
                executorStage,
                executionOutput,
                selectorStage.globalSelectionResult().selectedProposals().stream()
                        .map(SelectedProposal::proposalId)
                        .toList());
        decisionStageLogger.writeFamily("dispatch_outcome", effectiveRequest.traceId(), "dispatch-result", java.util.Map.of(
                "traceId", effectiveRequest.traceId(),
                "assignmentCount", executorStage.assignments().size(),
                "repairMode", selectorStage.activeRepairTelemetry().candidateInputCount() > 0 ? "BOUNDED_ALNS" : "NONE",
                "repairOperatorCounts", selectorStage.activeRepairTelemetry().operatorStats().stream()
                        .collect(java.util.stream.Collectors.toMap(
                                com.routechain.v2.repair.RepairOperatorStat::operatorName,
                                com.routechain.v2.repair.RepairOperatorStat::triedCount,
                                Integer::sum,
                                java.util.LinkedHashMap::new)),
                "repairAcceptedMoves", selectorStage.activeRepairTelemetry().acceptedMoves(),
                "repairRejectedMoves", selectorStage.activeRepairTelemetry().rejectedMoves(),
                "repairImprovementDelta", selectorStage.activeRepairTelemetry().bestImprovementDelta(),
                "repairRuntimeMs", selectorStage.activeRepairTelemetry().runtimeMs(),
                "degradeReasons", finalDegradeReasons));
        harvestRecorder.recordDispatchOutcome(effectiveRequest, executorStage, finalDegradeReasons);
        return new DispatchPipelineExecution(
                result,
                reusePlan,
                etaStage,
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage);
    }

    private DispatchV2Request applyRollingDecisions(DispatchV2Request request, List<RollingHoldDecision> rollingDecisions) {
        Map<String, RollingHoldDecision> decisionByOrderId = rollingDecisions.stream()
                .collect(Collectors.toMap(RollingHoldDecision::orderId, decision -> decision, (left, right) -> left));
        List<Order> dispatchableOrders = request.openOrders().stream()
                .filter(order -> {
                    RollingHoldDecision decision = decisionByOrderId.get(order.orderId());
                    return decision == null
                            || decision.decisionMode() == RollingDecisionMode.DISPATCH_NOW
                            || decision.decisionMode() == RollingDecisionMode.MICRO_BATCH
                            || decision.decisionMode() == RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE;
                })
                .toList();
        if (dispatchableOrders.isEmpty() && !request.openOrders().isEmpty()) {
            Order safestOrder = request.openOrders().stream()
                    .min(Comparator.comparing(order -> {
                        RollingHoldDecision decision = decisionByOrderId.get(order.orderId());
                        return decision == null ? 0L : Math.max(0L, decision.holdSeconds());
                    }))
                    .orElse(request.openOrders().getFirst());
            dispatchableOrders = List.of(safestOrder);
        }
        if (dispatchableOrders.size() == request.openOrders().size()) {
            return request;
        }
        return new DispatchV2Request(
                request.schemaVersion(),
                request.traceId(),
                dispatchableOrders,
                request.availableDrivers(),
                request.regions(),
                request.weatherProfile(),
                request.decisionTime());
    }

    private Map<String, Object> rollingDecisionRow(RollingHoldDecision decision) {
        return java.util.Map.of(
                "orderId", decision.orderId(),
                "decisionMode", decision.decisionMode().name(),
                "holdSeconds", decision.holdSeconds(),
                "confidence", decision.confidence(),
                "bundleOpportunityScore", decision.bundleOpportunityScore(),
                "riskScore", decision.riskScore(),
                "reasonCodes", decision.reasonCodes());
    }

    private List<String> rollingDegradeReasons(DispatchV2Request originalRequest,
                                               DispatchV2Request effectiveRequest,
                                               List<RollingHoldDecision> rollingDecisions) {
        List<String> reasons = new ArrayList<>();
        if (effectiveRequest.openOrders().size() < originalRequest.openOrders().size()) {
            reasons.add("rolling-horizon-held-orders");
        }
        if (rollingDecisions.stream().anyMatch(decision -> decision.decisionMode() == RollingDecisionMode.MICRO_BATCH)) {
            reasons.add("rolling-horizon-micro-batch-enabled");
        }
        if (rollingDecisions.stream().anyMatch(decision -> decision.decisionMode() == RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE)) {
            reasons.add("rolling-horizon-active-route-reoptimize-requested");
        }
        return List.copyOf(reasons);
    }

    private List<ActiveRouteInsertionCandidate> activeInsertionCandidates(DispatchV2Request effectiveRequest,
                                                                          List<RollingHoldDecision> rollingDecisions) {
        if (!properties.getSelector().isActiveRouteRepairEnabled()) {
            return List.of();
        }
        Set<String> reoptimizationOrderIds = rollingDecisions.stream()
                .filter(decision -> decision.decisionMode() == RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE)
                .map(RollingHoldDecision::orderId)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        if (activeFleetStateStore.size() == 0) {
            return List.of();
        }
        if (reoptimizationOrderIds.isEmpty()) {
            reoptimizationOrderIds = effectiveRequest.openOrders().stream()
                    .map(Order::orderId)
                    .collect(Collectors.toCollection(LinkedHashSet::new));
        }
        Set<String> finalReoptimizationOrderIds = reoptimizationOrderIds;
        List<Order> candidateOrders = effectiveRequest.openOrders().stream()
                .filter(order -> finalReoptimizationOrderIds.contains(order.orderId()))
                .toList();
        if (candidateOrders.isEmpty()) {
            return List.of();
        }
        List<ActiveRouteState> activeRoutes = activeFleetStateStore.activeRoutes(effectiveRequest);
        if (activeRoutes.isEmpty()) {
            return List.of();
        }
        List<Order> knownOrders = java.util.stream.Stream.concat(
                        activeFleetStateStore.knownOrders(effectiveRequest).stream(),
                        candidateOrders.stream())
                .collect(Collectors.toMap(Order::orderId, order -> order, (left, right) -> right, LinkedHashMap::new))
                .values()
                .stream()
                .toList();
        EtaLegCache etaLegCache = etaLegCacheFactory.create(
                effectiveRequest.traceId(),
                effectiveRequest.decisionTime(),
                effectiveRequest.weatherProfile() == null ? WeatherProfile.CLEAR : effectiveRequest.weatherProfile());
        Set<String> candidateOrderIds = candidateOrders.stream().map(Order::orderId).collect(Collectors.toSet());
        return activeRouteInsertionGenerator.generate(activeRoutes, knownOrders, effectiveRequest.decisionTime(), etaLegCache).stream()
                .filter(candidate -> candidateOrderIds.contains(candidate.insertedOrderId()))
                .limit(24)
                .toList();
    }

    private DecisionStageOutputV1 runDecisionSidecar(ResolvedDecisionBrain resolvedDecisionBrain, DecisionStageInputV1 input) {
        decisionStageLogger.writeFamily("decision_stage_input", input.traceId(), input.stageName().wireName(), input);
        harvestRecorder.recordDecisionStageInput(input);
        DecisionBrain loggingBrain = resolvedDecisionBrain.loggingBrainForStage(input.stageName());
        DecisionStageOutputV1 output = loggingBrain.evaluateStage(input);
        decisionStageLogger.writeFamily("decision_stage_output", input.traceId(), input.stageName().wireName(), output);
        harvestRecorder.recordDecisionStageOutput(input, output);
        decisionStageLogger.writeFamily("decision_usage", input.traceId(), input.stageName().wireName(), new DecisionUsageRecord(
                "decision-usage/v1",
                input.traceId(),
                input.runId(),
                input.tickId(),
                input.stageName(),
                resolvedDecisionBrain.requestedType(),
                output.brainType(),
                resolvedDecisionBrain.fallbackUsed() || output.meta().fallbackUsed(),
                resolvedDecisionBrain.fallbackUsed() ? resolvedDecisionBrain.fallbackReason() : output.meta().fallbackReason(),
                properties.getDecision().getLlm().getProvider(),
                properties.getDecision().getLlm().getModel(),
                output.providerModel(),
                properties.getDecision().getLlm().getBaseUrl(),
                properties.getDecision().getLlm().getWireApi(),
                output.brainType() == com.routechain.v2.decision.DecisionBrainType.LLM ? "/v1/models" : null));
        return output;
    }

    private void writeDecisionJoin(DecisionStageInputV1 input,
                                   String traceId,
                                   DecisionStageOutputV1 output,
                                   List<String> candidateIds,
                                   List<String> actualSelectedIds,
                                   boolean agreementAvailable,
                                   boolean authoritativeApplied,
                                   List<String> upstreamRefs) {
        List<String> safeCandidateIds = candidateIds == null ? List.of() : List.copyOf(candidateIds);
        Set<String> rejectedIds = new LinkedHashSet<>(safeCandidateIds);
        rejectedIds.removeAll(output.selectedIds());
        Map<String, Object> joinPayload = new LinkedHashMap<>();
        joinPayload.put("schemaVersion", "decision-stage-join/v1");
        joinPayload.put("traceId", output.traceId());
        joinPayload.put("runId", output.runId());
        joinPayload.put("tickId", output.tickId());
        joinPayload.put("stageName", output.stageName());
        joinPayload.put("brainType", output.brainType());
        joinPayload.put("selectedIds", output.selectedIds());
        joinPayload.put("candidateIds", safeCandidateIds);
        joinPayload.put("rejectedIds", List.copyOf(rejectedIds));
        joinPayload.put("actualSelectedIds", actualSelectedIds == null ? List.of() : actualSelectedIds);
        joinPayload.put("agreementAvailable", agreementAvailable);
        joinPayload.put("authoritativeApplied", authoritativeApplied);
        joinPayload.put("authorityMode", properties.getDecision().getMode());
        joinPayload.put("authoritativeStageSet", properties.getDecision().getAuthoritativeStages());
        joinPayload.put("decisionQualityFlags", output.meta().decisionQualityFlags());
        joinPayload.put("contextProfile", output.meta().contextProfile());
        joinPayload.put("overlaySet", output.meta().overlaySet());
        joinPayload.put("candidateUniverseCount", safeCandidateIds.size());
        joinPayload.put("selectedCount", output.selectedIds().size());
        joinPayload.put("effortSelectionReason", output.meta().effortSelectionReason());
        joinPayload.put("upstreamRefs", upstreamRefs == null ? List.of() : upstreamRefs);
        decisionStageLogger.writeFamily("decision_stage_join", traceId, output.stageName().wireName(), joinPayload);
        harvestRecorder.recordDecisionStageJoin(input, output, candidateIds, actualSelectedIds, authoritativeApplied);
    }

    private StageAuthorityResult<DispatchBundleStage> applyPairBundleAuthority(DispatchBundleStage bundleStage,
                                                                               DecisionStageOutputV1 output,
                                                                               ResolvedDecisionBrain resolvedDecisionBrain) {
        List<String> candidateIds = bundleStage.bundleCandidates().stream().map(BundleCandidate::bundleId).toList();
        if (!shouldApplyAuthoritatively(resolvedDecisionBrain, output)) {
            return new StageAuthorityResult<>(bundleStage, output, false, candidateIds);
        }
        List<String> selectedIds = validSelectedIds(output.selectedIds(), candidateIds);
        if (selectedIds.isEmpty()) {
            return new StageAuthorityResult<>(bundleStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, candidateIds);
        }
        List<BundleCandidate> filtered = bundleStage.bundleCandidates().stream()
                .filter(bundle -> selectedIds.contains(bundle.bundleId()))
                .toList();
        return new StageAuthorityResult<>(
                new DispatchBundleStage(
                        bundleStage.schemaVersion(),
                        bundleStage.boundaryExpansions(),
                        bundleStage.boundaryExpansionSummary(),
                        filtered,
                        summarizeBundles(filtered, bundleStage.bundlePoolSummary()),
                        bundleStage.hotStartReuseSummary(),
                        bundleStage.stageLatencies(),
                        bundleStage.mlStageMetadata(),
                        appendDistinct(bundleStage.degradeReasons(), "decision-authority-pair-bundle")),
                output,
                true,
                filtered.stream().map(BundleCandidate::bundleId).toList());
    }

    private StageAuthorityResult<DispatchRouteCandidateStage> applyDriverAuthority(DispatchRouteCandidateStage routeCandidateStage,
                                                                                   DecisionStageOutputV1 output,
                                                                                   ResolvedDecisionBrain resolvedDecisionBrain) {
        List<String> candidateIds = routeCandidateStage.driverCandidates().stream().map(DriverCandidate::driverId).toList();
        if (!shouldApplyAuthoritatively(resolvedDecisionBrain, output)) {
            return new StageAuthorityResult<>(routeCandidateStage, output, false, candidateIds);
        }
        List<String> selectedIds = validSelectedIds(output.selectedIds(), candidateIds);
        if (selectedIds.isEmpty()) {
            return new StageAuthorityResult<>(routeCandidateStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, candidateIds);
        }
        List<DriverCandidate> filtered = routeCandidateStage.driverCandidates().stream()
                .filter(candidate -> selectedIds.contains(candidate.driverId()))
                .toList();
        return new StageAuthorityResult<>(
                new DispatchRouteCandidateStage(
                        routeCandidateStage.schemaVersion(),
                        routeCandidateStage.pickupAnchors(),
                        routeCandidateStage.pickupAnchorSummary(),
                        filtered,
                        summarizeDrivers(filtered, routeCandidateStage.driverShortlistSummary()),
                        routeCandidateStage.stageLatencies(),
                        routeCandidateStage.mlStageMetadata(),
                        appendDistinct(routeCandidateStage.degradeReasons(), "decision-authority-driver")),
                output,
                true,
                filtered.stream().map(DriverCandidate::driverId).toList());
    }

    private StageAuthorityResult<DispatchRouteProposalStage> applyRouteProposalAuthority(DispatchRouteProposalStage routeProposalStage,
                                                                                         DecisionStageOutputV1 output,
                                                                                         ResolvedDecisionBrain resolvedDecisionBrain,
                                                                                         String authorityReason) {
        List<String> candidateIds = routeProposalStage.routeProposals().stream().map(RouteProposal::proposalId).toList();
        if (!shouldApplyAuthoritatively(resolvedDecisionBrain, output)) {
            return new StageAuthorityResult<>(routeProposalStage, output, false, candidateIds);
        }
        List<String> selectedIds = validSelectedIds(output.selectedIds(), candidateIds);
        if (selectedIds.isEmpty()) {
            return new StageAuthorityResult<>(routeProposalStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, candidateIds);
        }
        List<RouteProposal> filtered = routeProposalStage.routeProposals().stream()
                .filter(proposal -> selectedIds.contains(proposal.proposalId()))
                .toList();
        return new StageAuthorityResult<>(
                new DispatchRouteProposalStage(
                        routeProposalStage.schemaVersion(),
                        filtered,
                        summarizeRouteProposals(filtered, routeProposalStage.routeProposalSummary(), authorityReason),
                        routeProposalStage.hotStartReuseSummary(),
                        routeProposalStage.stageLatencies(),
                        routeProposalStage.mlStageMetadata(),
                        appendDistinct(routeProposalStage.degradeReasons(), "decision-authority-" + authorityReason)),
                output,
                true,
                filtered.stream().map(RouteProposal::proposalId).toList());
    }

    private StageAuthorityResult<DispatchScenarioStage> applyScenarioAuthority(DispatchScenarioStage scenarioStage,
                                                                               DecisionStageOutputV1 output,
                                                                               ResolvedDecisionBrain resolvedDecisionBrain) {
        List<String> candidateIds = scenarioStage.robustUtilities().stream().map(RobustUtility::proposalId).toList();
        if (!shouldApplyAuthoritatively(resolvedDecisionBrain, output)) {
            return new StageAuthorityResult<>(scenarioStage, output, false, candidateIds);
        }
        List<String> selectedIds = validSelectedIds(output.selectedIds(), candidateIds);
        if (selectedIds.isEmpty()) {
            return new StageAuthorityResult<>(scenarioStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, candidateIds);
        }
        List<RobustUtility> filteredUtilities = scenarioStage.robustUtilities().stream()
                .filter(utility -> selectedIds.contains(utility.proposalId()))
                .toList();
        List<ScenarioEvaluation> filteredEvaluations = scenarioStage.scenarioEvaluations().stream()
                .filter(evaluation -> selectedIds.contains(evaluation.proposalId()))
                .toList();
        return new StageAuthorityResult<>(
                new DispatchScenarioStage(
                        scenarioStage.schemaVersion(),
                        filteredEvaluations,
                        filteredUtilities,
                        summarizeScenarios(filteredEvaluations, filteredUtilities, scenarioStage.scenarioEvaluationSummary()),
                        scenarioStage.freshnessMetadata(),
                        scenarioStage.stageLatencies(),
                        scenarioStage.mlStageMetadata(),
                        appendDistinct(scenarioStage.degradeReasons(), "decision-authority-scenario")),
                output,
                true,
                filteredUtilities.stream().map(RobustUtility::proposalId).toList());
    }

    private StageAuthorityResult<DispatchSelectorStage> applyFinalSelectionAuthority(DispatchSelectorStage selectorStage,
                                                                                     DecisionStageOutputV1 output,
                                                                                     ResolvedDecisionBrain resolvedDecisionBrain) {
        List<String> selectedIds = selectorStage.globalSelectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .toList();
        List<String> candidateIds = selectorStage.selectorCandidates().stream()
                .map(candidate -> candidate.proposalId())
                .toList();
        if (!shouldApplyAuthoritatively(resolvedDecisionBrain, output)) {
            return new StageAuthorityResult<>(selectorStage, output, false, selectedIds);
        }
        List<String> validSelectedIds = validSelectedIds(output.selectedIds(), candidateIds);
        if (validSelectedIds.isEmpty()) {
            return new StageAuthorityResult<>(selectorStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, selectedIds);
        }
        Map<String, Double> selectionScoreByProposalId = selectorStage.selectorCandidates().stream()
                .collect(Collectors.toMap(candidate -> candidate.proposalId(), candidate -> candidate.selectionScore(), (left, right) -> left));
        List<SelectedProposal> selectedProposals = new ArrayList<>();
        int rank = 1;
        for (String proposalId : validSelectedIds) {
            Double selectionScore = selectionScoreByProposalId.get(proposalId);
            if (selectionScore == null) {
                continue;
            }
            selectedProposals.add(new SelectedProposal(
                    "selected-proposal/v1",
                    proposalId,
                    rank++,
                    selectionScore,
                    List.of("decision-authority-final-selection")));
        }
        if (selectedProposals.isEmpty()) {
            return new StageAuthorityResult<>(selectorStage, withAuthorityFallback(output, "llm-selected-ids-invalid"), false, selectedIds);
        }
        SelectionSolverMode solverMode = selectorStage.globalSelectionResult().solverMode();
        GlobalSelectionResult selectionResult = new GlobalSelectionResult(
                selectorStage.globalSelectionResult().schemaVersion(),
                List.copyOf(selectedProposals),
                selectorStage.globalSelectionResult().retainedCandidateCount(),
                selectedProposals.size(),
                solverMode,
                selectedProposals.stream().mapToDouble(SelectedProposal::selectionScore).sum(),
                selectorStage.globalSelectionResult().selectorPoolInputCount(),
                selectorStage.globalSelectionResult().selectorPoolReducedCount(),
                selectorStage.globalSelectionResult().selectorFeasibleCount(),
                selectorStage.globalSelectionResult().selectorRejectedCount(),
                selectorStage.globalSelectionResult().selectorTimedOut(),
                selectorStage.globalSelectionResult().selectorFallbackLevel(),
                selectorStage.globalSelectionResult().acceptanceGatePassed(),
                selectorStage.globalSelectionResult().acceptanceGateRejectedReasons(),
                selectorStage.globalSelectionResult().selectorMaxPoolSize(),
                selectorStage.globalSelectionResult().selectorPoolCapApplied(),
                selectorStage.globalSelectionResult().selectorRetainedBestObjectiveUtility(),
                selectorStage.globalSelectionResult().selectorFeasibleBestObjectiveUtility(),
                appendDistinct(selectorStage.globalSelectionResult().degradeReasons(), "decision-authority-final-selection"));
        GlobalSelectorSummary selectorSummary = new GlobalSelectorSummary(
                selectorStage.globalSelectorSummary().schemaVersion(),
                selectorStage.globalSelectorSummary().candidateCount(),
                selectorStage.globalSelectorSummary().feasibleCandidateCount(),
                selectorStage.globalSelectorSummary().conflictEdgeCount(),
                selectedProposals.size(),
                solverMode,
                selectorStage.globalSelectorSummary().poolInputCount(),
                selectorStage.globalSelectorSummary().poolReducedCount(),
                selectorStage.globalSelectorSummary().poolRejectedCount(),
                selectorStage.globalSelectorSummary().selectorTimedOut(),
                selectorStage.globalSelectorSummary().selectorFallbackLevel(),
                selectorStage.globalSelectorSummary().acceptanceGatePassed(),
                selectorStage.globalSelectorSummary().acceptanceGateRejectedReasons(),
                selectorStage.globalSelectorSummary().selectorMaxPoolSize(),
                selectorStage.globalSelectorSummary().selectorPoolCapApplied(),
                selectorStage.globalSelectorSummary().selectorPoolCapObjectiveLoss(),
                appendDistinct(selectorStage.globalSelectorSummary().degradeReasons(), "decision-authority-final-selection"));
        return new StageAuthorityResult<>(
                new DispatchSelectorStage(
                        selectorStage.schemaVersion(),
                        selectorStage.selectorCandidates(),
                        selectorStage.conflictGraph(),
                        selectionResult,
                        selectorSummary,
                        selectorStage.trainingTraces(),
                        selectorStage.stageLatencies(),
                        appendDistinct(selectorStage.degradeReasons(), "decision-authority-final-selection")),
                output,
                true,
                selectedProposals.stream().map(SelectedProposal::proposalId).toList());
    }

    private DecisionStageOutputV1 withAuthorityFallback(DecisionStageOutputV1 output, String fallbackReason) {
        DecisionStageMetaV1 meta = output.meta();
        return new DecisionStageOutputV1(
                output.schemaVersion(),
                output.traceId(),
                output.runId(),
                output.tickId(),
                output.stageName(),
                output.brainType(),
                output.providerModel(),
                output.assessments(),
                output.selectedIds(),
                new DecisionStageMetaV1(
                        meta.schemaVersion(),
                        meta.latencyMs(),
                        meta.confidence(),
                        true,
                        fallbackReason,
                        meta.validationPassed(),
                        meta.appliedSource(),
                        meta.requestedEffort(),
                        meta.appliedEffort(),
                        meta.tokenUsage(),
                        meta.retryCount(),
                        meta.rawResponseHash(),
                        meta.authorityMode(),
                        meta.authoritativeStageSet(),
                        appendDistinct(meta.decisionQualityFlags(), "authority-fallback"),
                        meta.contextProfile(),
                        meta.overlaySet(),
                        meta.contextCompressionApplied(),
                        meta.effortSelectionReason()));
    }

    private boolean shouldApplyAuthoritatively(ResolvedDecisionBrain resolvedDecisionBrain,
                                               DecisionStageOutputV1 output) {
        if (output == null || output.stageName() == null || output.meta() == null) {
            return false;
        }
        if (!resolvedDecisionBrain.shouldApplyAuthoritatively(output.stageName())) {
            return false;
        }
        return output.brainType() == com.routechain.v2.decision.DecisionBrainType.LLM
                && !output.meta().fallbackUsed();
    }

    private List<String> validSelectedIds(List<String> selectedIds, List<String> candidateIds) {
        if (selectedIds == null || selectedIds.isEmpty() || candidateIds == null || candidateIds.isEmpty()) {
            return List.of();
        }
        Set<String> candidateSet = new LinkedHashSet<>(candidateIds);
        return selectedIds.stream()
                .filter(candidateSet::contains)
                .distinct()
                .toList();
    }

    private BundlePoolSummary summarizeBundles(List<BundleCandidate> filtered, BundlePoolSummary original) {
        Map<BundleFamily, Integer> familyCounts = new EnumMap<>(BundleFamily.class);
        Map<BundleProposalSource, Integer> sourceCounts = new EnumMap<>(BundleProposalSource.class);
        Map<BundleFamily, Integer> familyRetainedCounts = new EnumMap<>(BundleFamily.class);
        int maxBundleSize = 0;
        int lateRiskRescueCandidateCount = 0;
        int activeRouteAddonCandidateCount = 0;
        for (BundleCandidate bundle : filtered) {
            familyCounts.merge(bundle.family(), 1, Integer::sum);
            familyRetainedCounts.merge(bundle.family(), 1, Integer::sum);
            sourceCounts.merge(bundle.proposalSource(), 1, Integer::sum);
            maxBundleSize = Math.max(maxBundleSize, bundle.orderIds().size());
            if (bundle.family() == BundleFamily.LATE_RISK_RESCUE) {
                lateRiskRescueCandidateCount++;
            }
            if (bundle.family() == BundleFamily.ACTIVE_ROUTE_ADDON) {
                activeRouteAddonCandidateCount++;
            }
        }
        return new BundlePoolSummary(
                original.schemaVersion(),
                original.candidateCount(),
                filtered.size(),
                familyCounts,
                sourceCounts,
                maxBundleSize,
                appendDistinct(original.degradeReasons(), "decision-authority-pair-bundle"),
                original.familyGeneratedCounts(),
                familyRetainedCounts,
                original.rejectedByReasonCounts(),
                diversityRetainedCount(familyRetainedCounts),
                lateRiskRescueCandidateCount,
                activeRouteAddonCandidateCount);
    }

    private int diversityRetainedCount(Map<BundleFamily, Integer> familyRetainedCounts) {
        return (int) familyRetainedCounts.values().stream()
                .filter(count -> count != null && count > 0)
                .count();
    }

    private DriverShortlistSummary summarizeDrivers(List<DriverCandidate> filtered, DriverShortlistSummary original) {
        long anchorCount = filtered.stream().map(candidate -> candidate.bundleId() + "|" + candidate.anchorOrderId()).distinct().count();
        long bundleCount = filtered.stream().map(DriverCandidate::bundleId).distinct().count();
        return new DriverShortlistSummary(
                original.schemaVersion(),
                Math.toIntExact(bundleCount),
                Math.toIntExact(anchorCount),
                filtered.size(),
                filtered.size(),
                appendDistinct(original.degradeReasons(), "decision-authority-driver"));
    }

    private RouteProposalSummary summarizeRouteProposals(List<RouteProposal> filtered,
                                                        RouteProposalSummary original,
                                                        String authorityReason) {
        Map<RouteProposalSource, Integer> sourceCounts = new EnumMap<>(RouteProposalSource.class);
        filtered.forEach(proposal -> sourceCounts.merge(proposal.source(), 1, Integer::sum));
        int proposalTupleCount = Math.toIntExact(filtered.stream()
                .map(proposal -> proposal.bundleId() + "|" + proposal.anchorOrderId() + "|" + proposal.driverId())
                .distinct()
                .count());
        return new RouteProposalSummary(
                original.schemaVersion(),
                original.driverCandidateCount(),
                proposalTupleCount,
                filtered.size(),
                filtered.size(),
                sourceCounts,
                appendDistinct(original.degradeReasons(), "decision-authority-" + authorityReason));
    }

    private ScenarioEvaluationSummary summarizeScenarios(List<ScenarioEvaluation> evaluations,
                                                        List<RobustUtility> utilities,
                                                        ScenarioEvaluationSummary original) {
        Map<com.routechain.v2.scenario.ScenarioType, Integer> scenarioCounts = new EnumMap<>(com.routechain.v2.scenario.ScenarioType.class);
        Map<com.routechain.v2.scenario.ScenarioType, Integer> appliedCounts = new EnumMap<>(com.routechain.v2.scenario.ScenarioType.class);
        int appliedScenarioCount = 0;
        for (ScenarioEvaluation evaluation : evaluations) {
            scenarioCounts.merge(evaluation.scenario(), 1, Integer::sum);
            if (evaluation.applied()) {
                appliedCounts.merge(evaluation.scenario(), 1, Integer::sum);
                appliedScenarioCount++;
            }
        }
        return new ScenarioEvaluationSummary(
                original.schemaVersion(),
                utilities.size(),
                evaluations.size(),
                appliedScenarioCount,
                scenarioCounts,
                appliedCounts,
                appendDistinct(original.degradeReasons(), "decision-authority-scenario"));
    }

    private List<String> appendDistinct(List<String> reasons, String additionalReason) {
        List<String> merged = new ArrayList<>(reasons == null ? List.of() : reasons);
        if (additionalReason != null && !additionalReason.isBlank()) {
            merged.add(additionalReason);
        }
        return merged.stream()
                .filter(reason -> reason != null && !reason.isBlank())
                .distinct()
                .toList();
    }

    private List<DispatchStageLatency> mergeStageLatencies(List<DispatchStageLatency>... stageLatencyLists) {
        Map<String, DispatchStageLatency> byStage = new LinkedHashMap<>();
        for (List<DispatchStageLatency> stageLatencyList : stageLatencyLists) {
            if (stageLatencyList == null) {
                continue;
            }
            for (DispatchStageLatency stageLatency : stageLatencyList) {
                byStage.put(stageLatency.stageName(), stageLatency);
            }
        }
        List<DispatchStageLatency> merged = new ArrayList<>();
        for (String stageName : DECISION_STAGES) {
            DispatchStageLatency stageLatency = byStage.get(stageName);
            if (stageLatency != null) {
                merged.add(stageLatency);
            }
        }
        return List.copyOf(merged);
    }

    private List<DispatchStageLatency> finalizeStageLatencies(List<DispatchStageLatency> rawStageLatencies,
                                                              HotStartReusePlan reusePlan,
                                                              long totalDispatchLatencyMs) {
        if (!properties.getPerformance().isTelemetryEnabled()) {
            return List.of();
        }
        Map<String, DispatchStageLatency> previousByStage = previousStageLatencies(reusePlan.reuseState());
        List<DispatchStageLatency> finalized = new ArrayList<>();
        for (DispatchStageLatency stageLatency : rawStageLatencies) {
            Duration stageBudget = properties.getPerformance().getStageBudgets().get(stageLatency.stageName());
            long budgetMs = stageBudget == null ? 0L : Math.max(0L, stageBudget.toMillis());
            boolean budgetBreached = budgetMs > 0L && stageLatency.elapsedMs() > budgetMs;
            long estimatedSavedMs = 0L;
            if (stageLatency.hotStartReused()) {
                DispatchStageLatency previousStageLatency = previousByStage.get(stageLatency.stageName());
                if (previousStageLatency != null) {
                    estimatedSavedMs = Math.max(0L, previousStageLatency.elapsedMs() - stageLatency.elapsedMs());
                }
            }
            finalized.add(stageLatency
                    .withBudget(budgetMs, budgetBreached)
                    .withEstimatedSavedMs(estimatedSavedMs));
        }
        return List.copyOf(finalized);
    }

    private Map<String, DispatchStageLatency> previousStageLatencies(DispatchRuntimeReuseState reuseState) {
        if (reuseState == null || reuseState.stageLatencies() == null) {
            return Map.of();
        }
        Map<String, DispatchStageLatency> byStage = new LinkedHashMap<>();
        for (DispatchStageLatency stageLatency : reuseState.stageLatencies()) {
            byStage.put(stageLatency.stageName(), stageLatency);
        }
        return byStage;
    }

    private DispatchLatencyBudgetSummary latencyBudgetSummary(List<DispatchStageLatency> stageLatencies,
                                                              long totalDispatchLatencyMs) {
        if (!properties.getPerformance().isTelemetryEnabled()) {
            return DispatchLatencyBudgetSummary.empty();
        }
        long totalBudgetMs = Math.max(0L, properties.getPerformance().getTotalDispatchBudget().toMillis());
        boolean totalBudgetBreached = totalBudgetMs > 0L && totalDispatchLatencyMs > totalBudgetMs;
        List<String> breachedStageNames = stageLatencies.stream()
                .filter(DispatchStageLatency::budgetBreached)
                .map(DispatchStageLatency::stageName)
                .toList();
        long estimatedHotStartSavedMs = stageLatencies.stream()
                .mapToLong(DispatchStageLatency::estimatedSavedMs)
                .sum();
        return new DispatchLatencyBudgetSummary(
                "dispatch-latency-budget-summary/v1",
                totalDispatchLatencyMs,
                totalBudgetMs,
                totalBudgetBreached,
                breachedStageNames,
                estimatedHotStartSavedMs);
    }

    private List<String> budgetDegradeReasons(List<DispatchStageLatency> stageLatencies,
                                              DispatchLatencyBudgetSummary latencyBudgetSummary) {
        if (!properties.getPerformance().isBudgetEnforcementEnabled()) {
            return List.of();
        }
        List<String> reasons = new ArrayList<>();
        for (DispatchStageLatency stageLatency : stageLatencies) {
            if (stageLatency.budgetBreached()) {
                reasons.add("dispatch-stage-budget-breached:" + stageLatency.stageName());
            }
        }
        if (latencyBudgetSummary.totalBudgetBreached()) {
            reasons.add("dispatch-total-budget-breached");
        }
        return List.copyOf(reasons);
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }

    private record StageAuthorityResult<T>(
            T value,
            DecisionStageOutputV1 output,
            boolean authoritativeApplied,
            List<String> actualSelectedIds) {
    }
}
