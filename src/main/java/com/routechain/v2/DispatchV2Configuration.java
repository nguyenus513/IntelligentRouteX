package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.context.BaselineTravelTimeEstimator;
import com.routechain.v2.context.DispatchEtaContextService;
import com.routechain.v2.context.EtaFeatureBuilder;
import com.routechain.v2.context.EtaService;
import com.routechain.v2.context.EtaUncertaintyEstimator;
import com.routechain.v2.compute.AdaptiveComputeGate;
import com.routechain.v2.context.TrafficProfileService;
import com.routechain.v2.context.WeatherContextService;
import com.routechain.v2.decision.ContextAssembler;
import com.routechain.v2.decision.ContextToolRegistry;
import com.routechain.v2.decision.DecisionBrainResolver;
import com.routechain.v2.decision.DecisionSessionStore;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.decision.FileDecisionSessionStore;
import com.routechain.v2.decision.LegacyMlBrain;
import com.routechain.v2.decision.LlmBrain;
import com.routechain.v2.decision.LlmStageScheduler;
import com.routechain.v2.decision.NineRouterResponsesClient;
import com.routechain.v2.decision.NoOpDecisionSessionStore;
import com.routechain.v2.decision.StudentBrain;
import com.routechain.v2.feedback.DecisionLogAssembler;
import com.routechain.v2.feedback.DecisionLogService;
import com.routechain.v2.feedback.DecisionLogWriter;
import com.routechain.v2.feedback.DispatchReplayComparator;
import com.routechain.v2.feedback.DispatchReplayLoader;
import com.routechain.v2.feedback.DispatchReplayRecorder;
import com.routechain.v2.feedback.DispatchReplayRunner;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.feedback.FileDecisionLogWriter;
import com.routechain.v2.feedback.FileReplayStore;
import com.routechain.v2.feedback.FileReuseStateStore;
import com.routechain.v2.feedback.FileSnapshotStore;
import com.routechain.v2.feedback.HotStartManager;
import com.routechain.v2.feedback.InMemoryDecisionLogWriter;
import com.routechain.v2.feedback.InMemoryReplayStore;
import com.routechain.v2.feedback.InMemoryReuseStateStore;
import com.routechain.v2.feedback.InMemorySnapshotStore;
import com.routechain.v2.feedback.PostDispatchHardeningService;
import com.routechain.v2.feedback.ReplayStore;
import com.routechain.v2.feedback.ReuseStateBuilder;
import com.routechain.v2.feedback.ReuseStateService;
import com.routechain.v2.feedback.ReuseStateStore;
import com.routechain.v2.feedback.SnapshotBuilder;
import com.routechain.v2.feedback.SnapshotService;
import com.routechain.v2.feedback.SnapshotStore;
import com.routechain.v2.feedback.WarmStartManager;
import com.routechain.v2.harvest.HarvestRailWriter;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.harvest.HarvestRuntimeMetadataResolver;
import com.routechain.v2.cluster.DispatchPairClusterService;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.cluster.MicroClusterer;
import com.routechain.v2.cluster.OrderBuffer;
import com.routechain.v2.cluster.PairFeatureBuilder;
import com.routechain.v2.cluster.PairHardGateEvaluator;
import com.routechain.v2.cluster.PairSimilarityGraphBuilder;
import com.routechain.v2.cluster.PairSimilarityScorer;
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
import com.routechain.v2.routing.BudgetedRoutingProvider;
import com.routechain.v2.routing.HttpOsrmRoutingProvider;
import com.routechain.v2.routing.HttpTomTomRoutingProvider;
import com.routechain.v2.routing.DurationMatrixCache;
import com.routechain.v2.routing.OsrmTableClient;
import com.routechain.v2.routing.RoadGraphProvider;
import com.routechain.v2.routing.RouteCostFunction;
import com.routechain.v2.routing.RouteVectorEnricher;
import com.routechain.v2.routing.RoutingProvider;
import com.routechain.v2.routing.SyntheticRoadGraphProvider;
import com.routechain.v2.routing.SyntheticRoutingProvider;
import com.routechain.v2.scenario.DispatchScenarioService;
import com.routechain.v2.scenario.DemandShiftFeatureBuilder;
import com.routechain.v2.scenario.PostDropShiftFeatureBuilder;
import com.routechain.v2.scenario.RobustUtilityAggregator;
import com.routechain.v2.scenario.ScenarioEvaluator;
import com.routechain.v2.scenario.ScenarioGateEvaluator;
import com.routechain.v2.scenario.ZoneBurstFeatureBuilder;
import com.routechain.v2.executor.DispatchAssignmentBuilder;
import com.routechain.v2.executor.DispatchExecutor;
import com.routechain.v2.executor.DispatchExecutorService;
import com.routechain.v2.executor.ExecutionConflictValidator;
import com.routechain.v2.executor.SelectedProposalResolver;
import com.routechain.v2.selector.ConflictGraphBuilder;
import com.routechain.v2.selector.DispatchSelectorService;
import com.routechain.v2.selector.GlobalSelector;
import com.routechain.v2.selector.GreedyRepairSelector;
import com.routechain.v2.selector.OrToolsSetPackingSolver;
import com.routechain.v2.selector.SelectorCandidateBuilder;
import com.routechain.v2.selector.SelectorSolver;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.HttpForecastClient;
import com.routechain.v2.integration.HttpOpenMeteoClient;
import com.routechain.v2.integration.HttpTomTomTrafficRefineClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.HttpGreedRlClient;
import com.routechain.v2.integration.HttpRouteFinderClient;
import com.routechain.v2.integration.HttpTabularScoringClient;
import com.routechain.v2.integration.OpenMeteoClient;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.TomTomTrafficRefineClient;
import com.routechain.v2.ops.DispatchOpsInfoContributor;
import com.routechain.v2.ops.DispatchOpsReadinessService;
import com.routechain.v2.ops.DispatchOpsStartupReporter;
import org.springframework.boot.actuate.info.InfoContributor;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DispatchV2Configuration {

    private java.nio.file.Path modelManifestPath(RouteChainDispatchV2Properties properties) {
        return java.nio.file.Path.of(properties.getMl().getModelManifestPath());
    }

    @Bean
    BaselineTravelTimeEstimator baselineTravelTimeEstimator() {
        return new BaselineTravelTimeEstimator();
    }

    @Bean
    TrafficProfileService trafficProfileService(RouteChainDispatchV2Properties properties) {
        return new TrafficProfileService(properties);
    }

    @Bean
    WeatherContextService weatherContextService(RouteChainDispatchV2Properties properties, OpenMeteoClient openMeteoClient) {
        return new WeatherContextService(properties, openMeteoClient);
    }

    @Bean
    OpenMeteoClient openMeteoClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isOpenMeteoEnabled() || !properties.getWeather().isEnabled()) {
            return new NoOpOpenMeteoClient();
        }
        return new HttpOpenMeteoClient(
                properties.getWeather().getBaseUrl(),
                properties.getWeather().getConnectTimeout(),
                properties.getWeather().getReadTimeout(),
                properties);
    }

    @Bean
    TomTomTrafficRefineClient tomTomTrafficRefineClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isTomtomEnabled() || !properties.getTraffic().isEnabled()) {
            return new NoOpTomTomTrafficRefineClient();
        }
        return new HttpTomTomTrafficRefineClient(
                properties.getTraffic().getBaseUrl(),
                properties.getTraffic().getApiKey(),
                properties.getTraffic().getConnectTimeout(),
                properties.getTraffic().getReadTimeout(),
                new com.routechain.v2.context.TrafficRefineMapper());
    }

    @Bean
    TabularScoringClient tabularScoringClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isMlEnabled() || !properties.getMl().getTabular().isEnabled()) {
            return new NoOpTabularScoringClient();
        }
        HttpTabularScoringClient client = new HttpTabularScoringClient(
                properties.getMl().getTabular().getBaseUrl(),
                properties.getMl().getTabular().getConnectTimeout(),
                properties.getMl().getTabular().getReadTimeout(),
                modelManifestPath(properties));
        if (properties.isSidecarRequired() && !client.readyState().ready()) {
            throw new IllegalStateException("Tabular worker is required but not ready: " + client.readyState().reason());
        }
        return client;
    }

    @Bean
    RouteFinderClient routeFinderClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isMlEnabled() || !properties.getMl().getRoutefinder().isEnabled()) {
            return new NoOpRouteFinderClient();
        }
        HttpRouteFinderClient client = new HttpRouteFinderClient(
                properties.getMl().getRoutefinder().getBaseUrl(),
                properties.getMl().getRoutefinder().getConnectTimeout(),
                properties.getMl().getRoutefinder().getReadTimeout(),
                modelManifestPath(properties));
        if (properties.isSidecarRequired() && !client.readyState().ready()) {
            throw new IllegalStateException("RouteFinder worker is required but not ready: " + client.readyState().reason());
        }
        return client;
    }

    @Bean
    GreedRlClient greedRlClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isMlEnabled() || !properties.getMl().getGreedrl().isEnabled()) {
            return new NoOpGreedRlClient();
        }
        HttpGreedRlClient client = new HttpGreedRlClient(
                properties.getMl().getGreedrl().getBaseUrl(),
                properties.getMl().getGreedrl().getConnectTimeout(),
                properties.getMl().getGreedrl().getReadTimeout(),
                modelManifestPath(properties));
        if (properties.isSidecarRequired() && !client.readyState().ready()) {
            throw new IllegalStateException("GreedRL worker is required but not ready: " + client.readyState().reason());
        }
        return client;
    }

    @Bean
    ForecastClient forecastClient(RouteChainDispatchV2Properties properties) {
        if (!properties.isMlEnabled() || !properties.getMl().getForecast().isEnabled()) {
            return new NoOpForecastClient();
        }
        HttpForecastClient client = new HttpForecastClient(
                properties.getMl().getForecast().getBaseUrl(),
                properties.getMl().getForecast().getConnectTimeout(),
                properties.getMl().getForecast().getReadTimeout(),
                modelManifestPath(properties));
        if (properties.isSidecarRequired() && !client.readyState().ready()) {
            throw new IllegalStateException("Forecast worker is required but not ready: " + client.readyState().reason());
        }
        return client;
    }

    @Bean
    EtaFeatureBuilder etaFeatureBuilder() {
        return new EtaFeatureBuilder();
    }

    @Bean
    EtaUncertaintyEstimator etaUncertaintyEstimator() {
        return new EtaUncertaintyEstimator();
    }

    @Bean
    EtaService etaService(RouteChainDispatchV2Properties properties,
                          BaselineTravelTimeEstimator baselineTravelTimeEstimator,
                          TrafficProfileService trafficProfileService,
                          WeatherContextService weatherContextService,
                          TomTomTrafficRefineClient tomTomTrafficRefineClient,
                          TabularScoringClient tabularScoringClient,
                          EtaFeatureBuilder etaFeatureBuilder,
                          EtaUncertaintyEstimator etaUncertaintyEstimator) {
        return new EtaService(
                properties,
                baselineTravelTimeEstimator,
                trafficProfileService,
                weatherContextService,
                tomTomTrafficRefineClient,
                tabularScoringClient,
                etaFeatureBuilder,
                etaUncertaintyEstimator);
    }

    @Bean
    DispatchEtaContextService dispatchEtaContextService(RouteChainDispatchV2Properties properties, EtaService etaService) {
        return new DispatchEtaContextService(properties, etaService);
    }

    @Bean
    OrderBuffer orderBuffer(RouteChainDispatchV2Properties properties) {
        return new OrderBuffer(properties);
    }

    @Bean
    PairFeatureBuilder pairFeatureBuilder(BaselineTravelTimeEstimator baselineTravelTimeEstimator) {
        return new PairFeatureBuilder(baselineTravelTimeEstimator);
    }

    @Bean
    PairHardGateEvaluator pairHardGateEvaluator(RouteChainDispatchV2Properties properties) {
        return new PairHardGateEvaluator(properties);
    }

    @Bean
    PairSimilarityScorer pairSimilarityScorer(RouteChainDispatchV2Properties properties,
                                              PairHardGateEvaluator pairHardGateEvaluator,
                                              TabularScoringClient tabularScoringClient,
                                              HarvestRecorder harvestRecorder) {
        return new PairSimilarityScorer(properties, pairHardGateEvaluator, tabularScoringClient, harvestRecorder);
    }

    @Bean
    EtaLegCacheFactory etaLegCacheFactory(RouteChainDispatchV2Properties properties, EtaService etaService) {
        return new EtaLegCacheFactory(properties, etaService);
    }

    @Bean
    PairSimilarityGraphBuilder pairSimilarityGraphBuilder(RouteChainDispatchV2Properties properties,
                                                          PairFeatureBuilder pairFeatureBuilder,
                                                          PairSimilarityScorer pairSimilarityScorer) {
        return new PairSimilarityGraphBuilder(properties, pairFeatureBuilder, pairSimilarityScorer);
    }

    @Bean
    MicroClusterer microClusterer(RouteChainDispatchV2Properties properties) {
        return new MicroClusterer(properties);
    }

    @Bean
    DispatchPairClusterService dispatchPairClusterService(RouteChainDispatchV2Properties properties,
                                                          OrderBuffer orderBuffer,
                                                          PairSimilarityGraphBuilder pairSimilarityGraphBuilder,
                                                          EtaLegCacheFactory etaLegCacheFactory,
                                                          MicroClusterer microClusterer) {
        return new DispatchPairClusterService(
                properties,
                orderBuffer,
                pairSimilarityGraphBuilder,
                etaLegCacheFactory,
                microClusterer);
    }

    @Bean
    BoundaryCandidateSelector boundaryCandidateSelector(RouteChainDispatchV2Properties properties) {
        return new BoundaryCandidateSelector(properties);
    }

    @Bean
    BoundaryExpansionEngine boundaryExpansionEngine(RouteChainDispatchV2Properties properties) {
        return new BoundaryExpansionEngine(properties);
    }

    @Bean
    BundleSeedGenerator bundleSeedGenerator(RouteChainDispatchV2Properties properties) {
        return new BundleSeedGenerator(properties);
    }

    @Bean
    BundleFamilyEnumerator bundleFamilyEnumerator(RouteChainDispatchV2Properties properties) {
        return new BundleFamilyEnumerator(properties);
    }

    @Bean
    BundleValidator bundleValidator(RouteChainDispatchV2Properties properties) {
        return new BundleValidator(properties);
    }

    @Bean
    BundleScorer bundleScorer(RouteChainDispatchV2Properties properties) {
        return new BundleScorer(properties);
    }

    @Bean
    BundleDominancePruner bundleDominancePruner() {
        return new BundleDominancePruner();
    }

    @Bean
    AdaptiveComputeGate adaptiveComputeGate(RouteChainDispatchV2Properties properties) {
        return new AdaptiveComputeGate(properties);
    }

    @Bean
    DispatchBundleStageService dispatchBundleStageService(RouteChainDispatchV2Properties properties,
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
        return new DispatchBundleStageService(
                properties,
                boundaryCandidateSelector,
                boundaryExpansionEngine,
                bundleSeedGenerator,
                bundleFamilyEnumerator,
                bundleValidator,
                bundleScorer,
                bundleDominancePruner,
                greedRlClient,
                harvestRecorder,
                adaptiveComputeGate,
                decisionStageLogger);
    }

    @Bean
    PickupAnchorSelector pickupAnchorSelector(RouteChainDispatchV2Properties properties) {
        return new PickupAnchorSelector(properties);
    }

    @Bean
    DriverRouteFeatureBuilder driverRouteFeatureBuilder() {
        return new DriverRouteFeatureBuilder();
    }

    @Bean
    CandidateDriverShortlister candidateDriverShortlister(RouteChainDispatchV2Properties properties,
                                                          DriverRouteFeatureBuilder driverRouteFeatureBuilder,
                                                          TabularScoringClient tabularScoringClient,
                                                          HarvestRecorder harvestRecorder) {
        return new CandidateDriverShortlister(properties, driverRouteFeatureBuilder, tabularScoringClient, harvestRecorder);
    }

    @Bean
    DriverReranker driverReranker() {
        return new DriverReranker();
    }

    @Bean
    DispatchRouteCandidateService dispatchRouteCandidateService(PickupAnchorSelector pickupAnchorSelector,
                                                                CandidateDriverShortlister candidateDriverShortlister,
                                                                DriverReranker driverReranker,
                                                                EtaLegCacheFactory etaLegCacheFactory) {
        return new DispatchRouteCandidateService(
                pickupAnchorSelector,
                candidateDriverShortlister,
                driverReranker,
                etaLegCacheFactory);
    }

    @Bean
    RouteProposalEngine routeProposalEngine() {
        return new RouteProposalEngine();
    }

    @Bean
    RouteProposalValidator routeProposalValidator() {
        return new RouteProposalValidator();
    }

    @Bean
    RouteValueScorer routeValueScorer(RouteChainDispatchV2Properties properties,
                                      TabularScoringClient tabularScoringClient,
                                      HarvestRecorder harvestRecorder) {
        return new RouteValueScorer(properties, tabularScoringClient, harvestRecorder);
    }

    @Bean
    RouteProposalPruner routeProposalPruner(RouteChainDispatchV2Properties properties) {
        return new RouteProposalPruner(properties);
    }

    @Bean
    DispatchRouteProposalService dispatchRouteProposalService(RouteChainDispatchV2Properties properties,
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
        return new DispatchRouteProposalService(
                properties,
                routeProposalEngine,
                routeProposalValidator,
                routeValueScorer,
                routeProposalPruner,
                etaLegCacheFactory,
                routeFinderClient,
                routeVectorEnricher,
                decisionStageLogger,
                harvestRecorder,
                adaptiveComputeGate);
    }

    @Bean
    ScenarioGateEvaluator scenarioGateEvaluator(RouteChainDispatchV2Properties properties) {
        return new ScenarioGateEvaluator(properties);
    }

    @Bean
    ScenarioEvaluator scenarioEvaluator(RouteChainDispatchV2Properties properties) {
        return new ScenarioEvaluator(properties);
    }

    @Bean
    DemandShiftFeatureBuilder demandShiftFeatureBuilder() {
        return new DemandShiftFeatureBuilder();
    }

    @Bean
    ZoneBurstFeatureBuilder zoneBurstFeatureBuilder() {
        return new ZoneBurstFeatureBuilder();
    }

    @Bean
    PostDropShiftFeatureBuilder postDropShiftFeatureBuilder() {
        return new PostDropShiftFeatureBuilder();
    }

    @Bean
    RobustUtilityAggregator robustUtilityAggregator() {
        return new RobustUtilityAggregator();
    }

    @Bean
    DispatchScenarioService dispatchScenarioService(RouteChainDispatchV2Properties properties,
                                                    ForecastClient forecastClient,
                                                    DemandShiftFeatureBuilder demandShiftFeatureBuilder,
                                                    ZoneBurstFeatureBuilder zoneBurstFeatureBuilder,
                                                    PostDropShiftFeatureBuilder postDropShiftFeatureBuilder,
                                                    ScenarioGateEvaluator scenarioGateEvaluator,
                                                    ScenarioEvaluator scenarioEvaluator,
                                                    RobustUtilityAggregator robustUtilityAggregator,
                                                    HarvestRecorder harvestRecorder,
                                                    AdaptiveComputeGate adaptiveComputeGate,
                                                    DecisionStageLogger decisionStageLogger) {
        return new DispatchScenarioService(
                properties,
                forecastClient,
                demandShiftFeatureBuilder,
                zoneBurstFeatureBuilder,
                postDropShiftFeatureBuilder,
                scenarioGateEvaluator,
                scenarioEvaluator,
                robustUtilityAggregator,
                harvestRecorder,
                adaptiveComputeGate,
                decisionStageLogger);
    }

    @Bean
    SelectorCandidateBuilder selectorCandidateBuilder(RouteChainDispatchV2Properties properties) {
        return new SelectorCandidateBuilder(properties);
    }

    @Bean
    ConflictGraphBuilder conflictGraphBuilder() {
        return new ConflictGraphBuilder();
    }

    @Bean
    GreedyRepairSelector greedyRepairSelector() {
        return new GreedyRepairSelector();
    }

    @Bean
    SelectorSolver selectorSolver(RouteChainDispatchV2Properties properties) {
        return new OrToolsSetPackingSolver(properties);
    }

    @Bean
    GlobalSelector globalSelector(RouteChainDispatchV2Properties properties,
                                  GreedyRepairSelector greedyRepairSelector,
                                  SelectorSolver selectorSolver) {
        return new GlobalSelector(properties, greedyRepairSelector, selectorSolver);
    }

    @Bean
    DispatchSelectorService dispatchSelectorService(SelectorCandidateBuilder selectorCandidateBuilder,
                                                    ConflictGraphBuilder conflictGraphBuilder,
                                                    GlobalSelector globalSelector,
                                                    RouteChainDispatchV2Properties properties) {
        return new DispatchSelectorService(properties, selectorCandidateBuilder, conflictGraphBuilder, globalSelector);
    }

    @Bean
    DispatchAssignmentBuilder dispatchAssignmentBuilder() {
        return new DispatchAssignmentBuilder();
    }

    @Bean
    SelectedProposalResolver selectedProposalResolver() {
        return new SelectedProposalResolver();
    }

    @Bean
    ExecutionConflictValidator executionConflictValidator() {
        return new ExecutionConflictValidator();
    }

    @Bean
    DispatchExecutor dispatchExecutor(SelectedProposalResolver selectedProposalResolver,
                                      ExecutionConflictValidator executionConflictValidator,
                                      DispatchAssignmentBuilder dispatchAssignmentBuilder) {
        return new DispatchExecutor(selectedProposalResolver, executionConflictValidator, dispatchAssignmentBuilder);
    }

    @Bean
    DispatchExecutorService dispatchExecutorService(DispatchExecutor dispatchExecutor) {
        return new DispatchExecutorService(dispatchExecutor);
    }

    @Bean
    DecisionLogAssembler decisionLogAssembler() {
        return new DecisionLogAssembler();
    }

    @Bean
    DecisionStageLogger decisionStageLogger(RouteChainDispatchV2Properties properties) {
        return new DecisionStageLogger(properties);
    }

    @Bean(destroyMethod = "close")
    DecisionSessionStore decisionSessionStore(RouteChainDispatchV2Properties properties) {
        if (!"v3".equalsIgnoreCase(properties.getDecision().getLlm().getPromptFamily())
                || !properties.getDecision().getLlm().getSessionStore().isEnabled()) {
            return new NoOpDecisionSessionStore();
        }
        return new FileDecisionSessionStore(properties);
    }

    @Bean(destroyMethod = "close")
    HarvestRailWriter harvestRailWriter(RouteChainDispatchV2Properties properties) {
        return new HarvestRailWriter(properties);
    }

    @Bean
    HarvestRuntimeMetadataResolver harvestRuntimeMetadataResolver(RouteChainDispatchV2Properties properties) {
        return new HarvestRuntimeMetadataResolver(properties);
    }

    @Bean
    HarvestRecorder harvestRecorder(RouteChainDispatchV2Properties properties,
                                    HarvestRailWriter harvestRailWriter,
                                    HarvestRuntimeMetadataResolver harvestRuntimeMetadataResolver) {
        return new HarvestRecorder(properties, harvestRailWriter, harvestRuntimeMetadataResolver);
    }

    @Bean
    ContextToolRegistry contextToolRegistry() {
        return new ContextToolRegistry();
    }

    @Bean
    ContextAssembler contextAssembler(RouteChainDispatchV2Properties properties, ContextToolRegistry contextToolRegistry) {
        return new ContextAssembler(properties, contextToolRegistry);
    }

    @Bean
    LegacyMlBrain legacyMlBrain() {
        return new LegacyMlBrain();
    }

    @Bean
    StudentBrain studentBrain(LegacyMlBrain legacyMlBrain) {
        return new StudentBrain(legacyMlBrain);
    }

    @Bean
    NineRouterResponsesClient nineRouterResponsesClient(RouteChainDispatchV2Properties properties,
                                                        DecisionSessionStore decisionSessionStore) {
        return new NineRouterResponsesClient(properties.getDecision().getLlm(), decisionSessionStore);
    }

    @Bean
    LlmStageScheduler llmStageScheduler(RouteChainDispatchV2Properties properties,
                                        NineRouterResponsesClient nineRouterResponsesClient,
                                        DecisionStageLogger decisionStageLogger,
                                        DecisionSessionStore decisionSessionStore) {
        return new LlmStageScheduler(nineRouterResponsesClient, properties.getDecision(), decisionStageLogger, decisionSessionStore);
    }

    @Bean
    LlmBrain llmBrain(LlmStageScheduler llmStageScheduler,
                      RouteChainDispatchV2Properties properties,
                      LegacyMlBrain legacyMlBrain,
                      DecisionStageLogger decisionStageLogger,
                      ContextToolRegistry contextToolRegistry) {
        return new LlmBrain(llmStageScheduler, properties.getDecision().getLlm(), legacyMlBrain, decisionStageLogger, contextToolRegistry);
    }

    @Bean
    DecisionBrainResolver decisionBrainResolver(RouteChainDispatchV2Properties properties,
                                                LegacyMlBrain legacyMlBrain,
                                                LlmBrain llmBrain,
                                                StudentBrain studentBrain) {
        return new DecisionBrainResolver(properties, legacyMlBrain, llmBrain, studentBrain);
    }

    @Bean
    RoadGraphProvider roadGraphProvider() {
        return new SyntheticRoadGraphProvider();
    }

    @Bean
    RouteCostFunction routeCostFunction() {
        return new RouteCostFunction();
    }

    @Bean
    BestPathRouter bestPathRouter(RoadGraphProvider roadGraphProvider, RouteCostFunction routeCostFunction) {
        return new BestPathRouter(roadGraphProvider, routeCostFunction);
    }

    @Bean
    RoutingProvider routingProvider(RouteChainDispatchV2Properties properties,
                                    BestPathRouter bestPathRouter,
                                    RouteCostFunction routeCostFunction) {
        RoutingProvider syntheticProvider = new SyntheticRoutingProvider(bestPathRouter);
        if ("osrm".equalsIgnoreCase(properties.getRouting().getProvider())) {
            RoutingProvider osrmProvider = new HttpOsrmRoutingProvider(
                    properties.getRouting().getBaseUrl(),
                    properties.getRouting().getConnectTimeout(),
                    properties.getRouting().getReadTimeout(),
                    routeCostFunction,
                    syntheticProvider);
            return new BudgetedRoutingProvider(osrmProvider, syntheticProvider, properties.getRouting().getRefineLimitPerTick());
        }
        if ("tomtom".equalsIgnoreCase(properties.getRouting().getProvider())) {
            RoutingProvider tomTomProvider = new HttpTomTomRoutingProvider(
                    properties.getTraffic().getBaseUrl(),
                    properties.getTraffic().getApiKey(),
                    properties.getRouting().getConnectTimeout(),
                    properties.getRouting().getReadTimeout(),
                    routeCostFunction,
                    syntheticProvider);
            return new BudgetedRoutingProvider(tomTomProvider, syntheticProvider, properties.getRouting().getRefineLimitPerTick());
        }
        return syntheticProvider;
    }

    @Bean
    OsrmTableClient osrmTableClient(RouteChainDispatchV2Properties properties) {
        return new OsrmTableClient(
                properties.getRouting().getBaseUrl(),
                properties.getRouting().getConnectTimeout(),
                properties.getRouting().getReadTimeout(),
                new DurationMatrixCache());
    }

    @Bean
    RouteVectorEnricher routeVectorEnricher(RouteChainDispatchV2Properties properties,
                                            RoutingProvider routingProvider,
                                            OsrmTableClient osrmTableClient,
                                            DecisionStageLogger decisionStageLogger,
                                            HarvestRecorder harvestRecorder) {
        OsrmTableClient activeTableClient = "osrm".equalsIgnoreCase(properties.getRouting().getProvider())
                ? osrmTableClient
                : null;
        return new RouteVectorEnricher(routingProvider, activeTableClient, decisionStageLogger, harvestRecorder);
    }

    @Bean
    DecisionLogWriter decisionLogWriter(RouteChainDispatchV2Properties properties) {
        if (properties.getFeedback().getStorageMode() == FeedbackStorageMode.FILE) {
            return new FileDecisionLogWriter(
                    java.nio.file.Path.of(properties.getFeedback().getBaseDir()),
                    properties.getFeedback().getRetention().getMaxFiles());
        }
        return new InMemoryDecisionLogWriter();
    }

    @Bean
    DecisionLogService decisionLogService(RouteChainDispatchV2Properties properties,
                                          DecisionLogAssembler decisionLogAssembler,
                                          DecisionLogWriter decisionLogWriter) {
        return new DecisionLogService(properties, decisionLogAssembler, decisionLogWriter);
    }

    @Bean
    SnapshotBuilder snapshotBuilder() {
        return new SnapshotBuilder();
    }

    @Bean
    SnapshotStore snapshotStore(RouteChainDispatchV2Properties properties) {
        if (properties.getFeedback().getStorageMode() == FeedbackStorageMode.FILE) {
            return new FileSnapshotStore(
                    java.nio.file.Path.of(properties.getFeedback().getBaseDir()),
                    properties.getFeedback().getRetention().getMaxFiles());
        }
        return new InMemorySnapshotStore();
    }

    @Bean
    SnapshotService snapshotService(RouteChainDispatchV2Properties properties,
                                    SnapshotBuilder snapshotBuilder,
                                    SnapshotStore snapshotStore) {
        return new SnapshotService(properties, snapshotBuilder, snapshotStore);
    }

    @Bean
    ReuseStateBuilder reuseStateBuilder() {
        return new ReuseStateBuilder();
    }

    @Bean
    ReuseStateStore reuseStateStore(RouteChainDispatchV2Properties properties) {
        if (properties.getFeedback().getStorageMode() == FeedbackStorageMode.FILE) {
            return new FileReuseStateStore(
                    java.nio.file.Path.of(properties.getFeedback().getBaseDir()),
                    properties.getFeedback().getRetention().getMaxFiles());
        }
        return new InMemoryReuseStateStore();
    }

    @Bean
    ReuseStateService reuseStateService(RouteChainDispatchV2Properties properties,
                                        ReuseStateBuilder reuseStateBuilder,
                                        ReuseStateStore reuseStateStore) {
        return new ReuseStateService(properties, reuseStateBuilder, reuseStateStore);
    }

    @Bean
    ReplayStore replayStore(RouteChainDispatchV2Properties properties) {
        if (properties.getFeedback().getStorageMode() == FeedbackStorageMode.FILE) {
            return new FileReplayStore(
                    java.nio.file.Path.of(properties.getFeedback().getBaseDir()),
                    properties.getFeedback().getRetention().getMaxFiles());
        }
        return new InMemoryReplayStore();
    }

    @Bean
    DispatchReplayRecorder dispatchReplayRecorder(RouteChainDispatchV2Properties properties, ReplayStore replayStore) {
        return new DispatchReplayRecorder(properties, replayStore);
    }

    @Bean
    WarmStartManager warmStartManager(RouteChainDispatchV2Properties properties, SnapshotService snapshotService) {
        return new WarmStartManager(properties, snapshotService);
    }

    @Bean
    HotStartManager hotStartManager(RouteChainDispatchV2Properties properties, ReuseStateService reuseStateService) {
        return new HotStartManager(properties, reuseStateService);
    }

    @Bean
    PostDispatchHardeningService postDispatchHardeningService(DispatchReplayRecorder dispatchReplayRecorder,
                                                              DecisionLogService decisionLogService,
                                                              SnapshotService snapshotService,
                                                              ReuseStateService reuseStateService,
                                                              HotStartManager hotStartManager) {
        return new PostDispatchHardeningService(
                dispatchReplayRecorder,
                decisionLogService,
                snapshotService,
                reuseStateService,
                hotStartManager);
    }

    @Bean
    DispatchV2Core dispatchV2Core(RouteChainDispatchV2Properties properties,
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
        return new DispatchV2Core(
                properties,
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
                harvestRecorder);
    }

    @Bean
    DispatchReplayLoader dispatchReplayLoader(DispatchReplayRecorder dispatchReplayRecorder,
                                              DecisionLogService decisionLogService,
                                              SnapshotService snapshotService) {
        return new DispatchReplayLoader(dispatchReplayRecorder, decisionLogService, snapshotService);
    }

    @Bean
    DispatchReplayComparator dispatchReplayComparator() {
        return new DispatchReplayComparator();
    }

    @Bean
    DispatchReplayRunner dispatchReplayRunner(DispatchV2Core dispatchV2Core,
                                              DispatchReplayLoader dispatchReplayLoader,
                                              DispatchReplayComparator dispatchReplayComparator) {
        return new DispatchReplayRunner(dispatchV2Core, dispatchReplayLoader, dispatchReplayComparator);
    }

    @Bean
    DispatchV2CompatibleCore dispatchV2CompatibleCore(RouteChainDispatchV2Properties properties, DispatchV2Core dispatchV2Core) {
        return new DispatchV2CompatibleCore(properties, dispatchV2Core);
    }

    @Bean
    DispatchOpsReadinessService dispatchOpsReadinessService(RouteChainDispatchV2Properties properties,
                                                            WarmStartManager warmStartManager,
                                                            TabularScoringClient tabularScoringClient,
                                                            RouteFinderClient routeFinderClient,
                                                            GreedRlClient greedRlClient,
                                                            ForecastClient forecastClient) {
        return new DispatchOpsReadinessService(
                properties,
                warmStartManager,
                tabularScoringClient,
                routeFinderClient,
                greedRlClient,
                forecastClient,
                modelManifestPath(properties));
    }

    @Bean
    InfoContributor dispatchOpsInfoContributor(DispatchOpsReadinessService dispatchOpsReadinessService) {
        return new DispatchOpsInfoContributor(dispatchOpsReadinessService);
    }

    @Bean
    ApplicationRunner dispatchOpsStartupReporter(DispatchOpsReadinessService dispatchOpsReadinessService,
                                                 ObjectMapper objectMapper) {
        return new DispatchOpsStartupReporter(dispatchOpsReadinessService, objectMapper);
    }
}
