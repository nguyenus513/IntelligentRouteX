package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.context.BaselineTravelTimeEstimator;
import com.routechain.v2.context.DispatchEtaContextService;
import com.routechain.v2.context.EtaFeatureBuilder;
import com.routechain.v2.context.EtaService;
import com.routechain.v2.context.EtaUncertaintyEstimator;
import com.routechain.v2.context.TrafficProfileService;
import com.routechain.v2.context.WeatherContextService;
import com.routechain.v2.decision.ContextAssembler;
import com.routechain.v2.decision.ContextToolRegistry;
import com.routechain.v2.decision.DecisionBrainResolver;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.decision.LegacyMlBrain;
import com.routechain.v2.decision.LlmBrain;
import com.routechain.v2.decision.LlmStageScheduler;
import com.routechain.v2.decision.NineRouterResponsesClient;
import com.routechain.v2.decision.StudentBrain;
import com.routechain.v2.feedback.DecisionLogAssembler;
import com.routechain.v2.feedback.DecisionLogService;
import com.routechain.v2.feedback.DecisionLogWriter;
import com.routechain.v2.feedback.DispatchReplayComparator;
import com.routechain.v2.feedback.DispatchReplayLoader;
import com.routechain.v2.feedback.DispatchReplayRecorder;
import com.routechain.v2.feedback.DispatchReplayRunner;
import com.routechain.v2.feedback.HotStartManager;
import com.routechain.v2.feedback.PostDispatchHardeningService;
import com.routechain.v2.feedback.ReplayStore;
import com.routechain.v2.feedback.ReuseStateBuilder;
import com.routechain.v2.feedback.ReuseStateService;
import com.routechain.v2.feedback.ReuseStateStore;
import com.routechain.v2.feedback.SnapshotBuilder;
import com.routechain.v2.feedback.SnapshotService;
import com.routechain.v2.feedback.SnapshotStore;
import com.routechain.v2.feedback.WarmStartManager;
import com.routechain.v2.bundle.BoundaryCandidateSelector;
import com.routechain.v2.bundle.BoundaryExpansionEngine;
import com.routechain.v2.bundle.BundleDominancePruner;
import com.routechain.v2.bundle.BundleFamilyEnumerator;
import com.routechain.v2.bundle.BundleScorer;
import com.routechain.v2.bundle.BundleSeedGenerator;
import com.routechain.v2.bundle.BundleValidator;
import com.routechain.v2.bundle.DispatchBundleStageService;
import com.routechain.v2.route.CandidateDriverShortlister;
import com.routechain.v2.route.DispatchRouteCandidateService;
import com.routechain.v2.route.DispatchRouteProposalService;
import com.routechain.v2.route.DriverReranker;
import com.routechain.v2.route.DriverRouteFeatureBuilder;
import com.routechain.v2.route.PickupAnchorSelector;
import com.routechain.v2.route.RouteProposalEngine;
import com.routechain.v2.route.RouteProposalPruner;
import com.routechain.v2.route.RouteProposalValidator;
import com.routechain.v2.route.RouteValueScorer;
import com.routechain.v2.routing.BestPathRouter;
import com.routechain.v2.routing.RoadGraphProvider;
import com.routechain.v2.routing.RouteCostFunction;
import com.routechain.v2.routing.RouteVectorEnricher;
import com.routechain.v2.scenario.DispatchScenarioService;
import com.routechain.v2.scenario.RobustUtilityAggregator;
import com.routechain.v2.scenario.ScenarioEvaluator;
import com.routechain.v2.scenario.ScenarioGateEvaluator;
import com.routechain.v2.executor.DispatchAssignmentBuilder;
import com.routechain.v2.executor.DispatchExecutor;
import com.routechain.v2.executor.DispatchExecutorService;
import com.routechain.v2.executor.ExecutionConflictValidator;
import com.routechain.v2.executor.SelectedProposalResolver;
import com.routechain.v2.selector.ConflictGraphBuilder;
import com.routechain.v2.selector.DispatchSelectorService;
import com.routechain.v2.selector.GlobalSelector;
import com.routechain.v2.selector.GreedyRepairSelector;
import com.routechain.v2.selector.SelectorCandidateBuilder;
import com.routechain.v2.selector.SelectorSolver;
import com.routechain.v2.cluster.DispatchPairClusterService;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.cluster.MicroClusterer;
import com.routechain.v2.cluster.OrderBuffer;
import com.routechain.v2.cluster.PairFeatureBuilder;
import com.routechain.v2.cluster.PairHardGateEvaluator;
import com.routechain.v2.cluster.PairSimilarityGraphBuilder;
import com.routechain.v2.cluster.PairSimilarityScorer;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.OpenMeteoClient;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.TomTomTrafficRefineClient;

import java.time.Instant;
import java.util.List;

public final class TestDispatchV2Factory {
    private TestDispatchV2Factory() {
    }

    public static DispatchV2CompatibleCore compatibleCore(RouteChainDispatchV2Properties properties) {
        DispatchV2Configuration configuration = new DispatchV2Configuration();
        DispatchV2Core core = harness(properties).core();
        return configuration.dispatchV2CompatibleCore(properties, core);
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties) {
        return harness(properties).core();
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties, TabularScoringClient tabularScoringClient) {
        return harness(properties, tabularScoringClient).core();
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties,
                                      TabularScoringClient tabularScoringClient,
                                      RouteFinderClient routeFinderClient) {
        return harness(properties, tabularScoringClient, routeFinderClient).core();
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties,
                                      TabularScoringClient tabularScoringClient,
                                      RouteFinderClient routeFinderClient,
                                      GreedRlClient greedRlClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, greedRlClient).core();
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties,
                                      TabularScoringClient tabularScoringClient,
                                      RouteFinderClient routeFinderClient,
                                      GreedRlClient greedRlClient,
                                      OpenMeteoClient openMeteoClient,
                                      TomTomTrafficRefineClient tomTomTrafficRefineClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, greedRlClient, openMeteoClient, tomTomTrafficRefineClient).core();
    }

    public static DispatchV2Core core(RouteChainDispatchV2Properties properties,
                                      TabularScoringClient tabularScoringClient,
                                      RouteFinderClient routeFinderClient,
                                      GreedRlClient greedRlClient,
                                      ForecastClient forecastClient,
                                      OpenMeteoClient openMeteoClient,
                                      TomTomTrafficRefineClient tomTomTrafficRefineClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, greedRlClient, forecastClient, openMeteoClient, tomTomTrafficRefineClient).core();
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties) {
        return harness(properties, new NoOpTabularScoringClient());
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties, TabularScoringClient tabularScoringClient) {
        return harness(properties, tabularScoringClient, new NoOpRouteFinderClient());
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                     TabularScoringClient tabularScoringClient,
                                                     RouteFinderClient routeFinderClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, new NoOpGreedRlClient());
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                     TabularScoringClient tabularScoringClient,
                                                     RouteFinderClient routeFinderClient,
                                                     GreedRlClient greedRlClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, greedRlClient, new NoOpForecastClient(), new NoOpOpenMeteoClient(), new NoOpTomTomTrafficRefineClient());
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                     TabularScoringClient tabularScoringClient,
                                                     RouteFinderClient routeFinderClient,
                                                     GreedRlClient greedRlClient,
                                                     OpenMeteoClient openMeteoClient,
                                                     TomTomTrafficRefineClient tomTomTrafficRefineClient) {
        return harness(properties, tabularScoringClient, routeFinderClient, greedRlClient, new NoOpForecastClient(), openMeteoClient, tomTomTrafficRefineClient);
    }

    public static TestDispatchRuntimeHarness harness(RouteChainDispatchV2Properties properties,
                                                     TabularScoringClient tabularScoringClient,
                                                     RouteFinderClient routeFinderClient,
                                                     GreedRlClient greedRlClient,
                                                     ForecastClient forecastClient,
                                                     OpenMeteoClient openMeteoClient,
                                                     TomTomTrafficRefineClient tomTomTrafficRefineClient) {
        DispatchV2Configuration configuration = new DispatchV2Configuration();
        BaselineTravelTimeEstimator baselineTravelTimeEstimator = configuration.baselineTravelTimeEstimator();
        TrafficProfileService trafficProfileService = configuration.trafficProfileService(properties);
        WeatherContextService weatherContextService = configuration.weatherContextService(properties, openMeteoClient);
        EtaFeatureBuilder etaFeatureBuilder = configuration.etaFeatureBuilder();
        EtaUncertaintyEstimator etaUncertaintyEstimator = configuration.etaUncertaintyEstimator();
        EtaService etaService = configuration.etaService(
                properties,
                baselineTravelTimeEstimator,
                trafficProfileService,
                weatherContextService,
                tomTomTrafficRefineClient,
                tabularScoringClient,
                etaFeatureBuilder,
                etaUncertaintyEstimator);
        DispatchEtaContextService dispatchEtaContextService = configuration.dispatchEtaContextService(properties, etaService);
        OrderBuffer orderBuffer = configuration.orderBuffer(properties);
        PairFeatureBuilder pairFeatureBuilder = configuration.pairFeatureBuilder(baselineTravelTimeEstimator);
        PairHardGateEvaluator pairHardGateEvaluator = configuration.pairHardGateEvaluator(properties);
        PairSimilarityScorer pairSimilarityScorer = configuration.pairSimilarityScorer(
                properties,
                pairHardGateEvaluator,
                tabularScoringClient);
        EtaLegCacheFactory etaLegCacheFactory = configuration.etaLegCacheFactory(properties, etaService);
        PairSimilarityGraphBuilder pairSimilarityGraphBuilder = configuration.pairSimilarityGraphBuilder(
                properties,
                pairFeatureBuilder,
                pairSimilarityScorer);
        MicroClusterer microClusterer = configuration.microClusterer(properties);
        DispatchPairClusterService dispatchPairClusterService = configuration.dispatchPairClusterService(
                properties,
                orderBuffer,
                pairSimilarityGraphBuilder,
                etaLegCacheFactory,
                microClusterer);
        BoundaryCandidateSelector boundaryCandidateSelector = configuration.boundaryCandidateSelector(properties);
        BoundaryExpansionEngine boundaryExpansionEngine = configuration.boundaryExpansionEngine(properties);
        BundleSeedGenerator bundleSeedGenerator = configuration.bundleSeedGenerator(properties);
        BundleFamilyEnumerator bundleFamilyEnumerator = configuration.bundleFamilyEnumerator(properties);
        BundleValidator bundleValidator = configuration.bundleValidator(properties);
        BundleScorer bundleScorer = configuration.bundleScorer(properties);
        BundleDominancePruner bundleDominancePruner = configuration.bundleDominancePruner();
        DispatchBundleStageService dispatchBundleStageService = configuration.dispatchBundleStageService(
                properties,
                boundaryCandidateSelector,
                boundaryExpansionEngine,
                bundleSeedGenerator,
                bundleFamilyEnumerator,
                bundleValidator,
                bundleScorer,
                bundleDominancePruner,
                greedRlClient);
        PickupAnchorSelector pickupAnchorSelector = configuration.pickupAnchorSelector(properties);
        DriverRouteFeatureBuilder driverRouteFeatureBuilder = configuration.driverRouteFeatureBuilder();
        CandidateDriverShortlister candidateDriverShortlister = configuration.candidateDriverShortlister(properties, driverRouteFeatureBuilder, tabularScoringClient);
        DriverReranker driverReranker = configuration.driverReranker();
        DispatchRouteCandidateService dispatchRouteCandidateService = configuration.dispatchRouteCandidateService(
                pickupAnchorSelector,
                candidateDriverShortlister,
                driverReranker,
                etaLegCacheFactory);
        RouteProposalEngine routeProposalEngine = configuration.routeProposalEngine();
        RouteProposalValidator routeProposalValidator = configuration.routeProposalValidator();
        RouteValueScorer routeValueScorer = configuration.routeValueScorer(properties, tabularScoringClient);
        RouteProposalPruner routeProposalPruner = configuration.routeProposalPruner(properties);
        DecisionStageLogger decisionStageLogger = configuration.decisionStageLogger(properties);
        RoadGraphProvider roadGraphProvider = configuration.roadGraphProvider();
        RouteCostFunction routeCostFunction = configuration.routeCostFunction();
        BestPathRouter bestPathRouter = configuration.bestPathRouter(roadGraphProvider, routeCostFunction);
        RouteVectorEnricher routeVectorEnricher = configuration.routeVectorEnricher(bestPathRouter, decisionStageLogger);
        DispatchRouteProposalService dispatchRouteProposalService = configuration.dispatchRouteProposalService(
                properties,
                routeProposalEngine,
                routeProposalValidator,
                routeValueScorer,
                routeProposalPruner,
                etaLegCacheFactory,
                routeFinderClient,
                routeVectorEnricher,
                decisionStageLogger);
        ScenarioGateEvaluator scenarioGateEvaluator = configuration.scenarioGateEvaluator(properties);
        ScenarioEvaluator scenarioEvaluator = configuration.scenarioEvaluator(properties);
        var demandShiftFeatureBuilder = configuration.demandShiftFeatureBuilder();
        var zoneBurstFeatureBuilder = configuration.zoneBurstFeatureBuilder();
        var postDropShiftFeatureBuilder = configuration.postDropShiftFeatureBuilder();
        RobustUtilityAggregator robustUtilityAggregator = configuration.robustUtilityAggregator();
        DispatchScenarioService dispatchScenarioService = configuration.dispatchScenarioService(
                properties,
                forecastClient,
                demandShiftFeatureBuilder,
                zoneBurstFeatureBuilder,
                postDropShiftFeatureBuilder,
                scenarioGateEvaluator,
                scenarioEvaluator,
                robustUtilityAggregator);
        SelectorCandidateBuilder selectorCandidateBuilder = configuration.selectorCandidateBuilder(properties);
        ConflictGraphBuilder conflictGraphBuilder = configuration.conflictGraphBuilder();
        GreedyRepairSelector greedyRepairSelector = configuration.greedyRepairSelector();
        SelectorSolver selectorSolver = configuration.selectorSolver(properties);
        GlobalSelector globalSelector = configuration.globalSelector(
                properties,
                greedyRepairSelector,
                selectorSolver);
        DispatchSelectorService dispatchSelectorService = configuration.dispatchSelectorService(
                selectorCandidateBuilder,
                conflictGraphBuilder,
                globalSelector);
        DispatchAssignmentBuilder dispatchAssignmentBuilder = configuration.dispatchAssignmentBuilder();
        SelectedProposalResolver selectedProposalResolver = configuration.selectedProposalResolver();
        ExecutionConflictValidator executionConflictValidator = configuration.executionConflictValidator();
        DispatchExecutor dispatchExecutor = configuration.dispatchExecutor(
                selectedProposalResolver,
                executionConflictValidator,
                dispatchAssignmentBuilder);
        DispatchExecutorService dispatchExecutorService = configuration.dispatchExecutorService(dispatchExecutor);
        DecisionLogAssembler decisionLogAssembler = configuration.decisionLogAssembler();
        DecisionLogWriter decisionLogWriter = configuration.decisionLogWriter(properties);
        DecisionLogService decisionLogService = configuration.decisionLogService(properties, decisionLogAssembler, decisionLogWriter);
        SnapshotBuilder snapshotBuilder = configuration.snapshotBuilder();
        SnapshotStore snapshotStore = configuration.snapshotStore(properties);
        SnapshotService snapshotService = configuration.snapshotService(properties, snapshotBuilder, snapshotStore);
        ReuseStateBuilder reuseStateBuilder = configuration.reuseStateBuilder();
        ReuseStateStore reuseStateStore = configuration.reuseStateStore(properties);
        ReuseStateService reuseStateService = configuration.reuseStateService(properties, reuseStateBuilder, reuseStateStore);
        ReplayStore replayStore = configuration.replayStore(properties);
        DispatchReplayRecorder dispatchReplayRecorder = configuration.dispatchReplayRecorder(properties, replayStore);
        WarmStartManager warmStartManager = configuration.warmStartManager(properties, snapshotService);
        HotStartManager hotStartManager = configuration.hotStartManager(properties, reuseStateService);
        PostDispatchHardeningService postDispatchHardeningService = configuration.postDispatchHardeningService(
                dispatchReplayRecorder,
                decisionLogService,
                snapshotService,
                reuseStateService,
                hotStartManager);
        ContextToolRegistry contextToolRegistry = configuration.contextToolRegistry();
        ContextAssembler contextAssembler = configuration.contextAssembler(properties, contextToolRegistry);
        LegacyMlBrain legacyMlBrain = configuration.legacyMlBrain();
        StudentBrain studentBrain = configuration.studentBrain(legacyMlBrain);
        NineRouterResponsesClient nineRouterResponsesClient = configuration.nineRouterResponsesClient(properties);
        LlmStageScheduler llmStageScheduler = configuration.llmStageScheduler(properties, nineRouterResponsesClient, decisionStageLogger);
        LlmBrain llmBrain = configuration.llmBrain(llmStageScheduler, properties, legacyMlBrain, decisionStageLogger, contextToolRegistry);
        DecisionBrainResolver decisionBrainResolver = configuration.decisionBrainResolver(properties, legacyMlBrain, llmBrain, studentBrain);
        DispatchV2Core core = configuration.dispatchV2Core(
                properties,
                dispatchEtaContextService,
                dispatchPairClusterService,
                dispatchBundleStageService,
                dispatchRouteCandidateService,
                dispatchRouteProposalService,
                dispatchScenarioService,
                dispatchSelectorService,
                dispatchExecutorService,
                warmStartManager,
                postDispatchHardeningService,
                decisionBrainResolver,
                contextAssembler,
                decisionStageLogger);
        DispatchReplayLoader dispatchReplayLoader = configuration.dispatchReplayLoader(
                dispatchReplayRecorder,
                decisionLogService,
                snapshotService);
        DispatchReplayComparator dispatchReplayComparator = configuration.dispatchReplayComparator();
        DispatchReplayRunner dispatchReplayRunner = configuration.dispatchReplayRunner(
                core,
                dispatchReplayLoader,
                dispatchReplayComparator);
        return new TestDispatchRuntimeHarness(
                core,
                decisionLogService,
                decisionLogWriter,
                snapshotService,
                snapshotStore,
                dispatchReplayRecorder,
                replayStore,
                dispatchReplayLoader,
                dispatchReplayRunner,
                warmStartManager,
                hotStartManager,
                reuseStateService,
                reuseStateStore);
    }

    public static DispatchV2Request requestWithOrdersAndDriver() {
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-core",
                List.of(
                        order("order-1", 10.7750, 106.7000, 10.7800, 106.7100, decisionTime, false),
                        order("order-2", 10.7760, 106.7010, 10.7810, 106.7120, decisionTime.plusSeconds(120), false),
                        order("order-3", 10.8200, 106.7600, 10.8300, 106.7700, decisionTime.plusSeconds(300), true)),
                List.of(
                        new Driver("driver-1", new GeoPoint(10.7700, 106.6950)),
                        new Driver("driver-2", new GeoPoint(10.7720, 106.6970)),
                        new Driver("driver-3", new GeoPoint(10.7810, 106.7060))),
                List.of(),
                WeatherProfile.CLEAR,
                decisionTime);
    }

    static Order order(String orderId,
                       double pickupLat,
                       double pickupLon,
                       double dropLat,
                       double dropLon,
                       Instant readyAt,
                       boolean urgent) {
        return new Order(
                orderId,
                new GeoPoint(pickupLat, pickupLon),
                new GeoPoint(dropLat, dropLon),
                readyAt.minusSeconds(300),
                readyAt,
                20,
                urgent);
    }

    public record TestDispatchRuntimeHarness(
            DispatchV2Core core,
            DecisionLogService decisionLogService,
            DecisionLogWriter decisionLogWriter,
            SnapshotService snapshotService,
            SnapshotStore snapshotStore,
            DispatchReplayRecorder dispatchReplayRecorder,
            ReplayStore replayStore,
            DispatchReplayLoader dispatchReplayLoader,
            DispatchReplayRunner dispatchReplayRunner,
            WarmStartManager warmStartManager,
            HotStartManager hotStartManager,
            ReuseStateService reuseStateService,
            ReuseStateStore reuseStateStore) {
    }
}
