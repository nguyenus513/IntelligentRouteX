package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.EtaContext;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.bundle.BoundaryCandidateSelector;
import com.routechain.v2.bundle.BoundaryExpansionEngine;
import com.routechain.v2.bundle.BundleDominancePruner;
import com.routechain.v2.bundle.BundleFamilyEnumerator;
import com.routechain.v2.bundle.BundleScorer;
import com.routechain.v2.bundle.BundleSeedGenerator;
import com.routechain.v2.bundle.BundleValidator;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.bundle.DispatchBundleStageService;
import com.routechain.v2.cluster.DispatchPairClusterService;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.cluster.MicroClusterer;
import com.routechain.v2.cluster.OrderBuffer;
import com.routechain.v2.cluster.PairFeatureBuilder;
import com.routechain.v2.cluster.PairHardGateEvaluator;
import com.routechain.v2.cluster.PairSimilarityGraphBuilder;
import com.routechain.v2.cluster.PairSimilarityScorer;
import com.routechain.v2.context.BaselineTravelTimeEstimator;
import com.routechain.v2.context.EtaFeatureBuilder;
import com.routechain.v2.context.EtaService;
import com.routechain.v2.context.EtaUncertaintyEstimator;
import com.routechain.v2.context.FreshnessMetadata;
import com.routechain.v2.context.TrafficProfileService;
import com.routechain.v2.context.WeatherContextService;
import com.routechain.v2.decision.DecisionStageLogger;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpGreedRlClient;
import com.routechain.v2.integration.NoOpForecastClient;
import com.routechain.v2.integration.NoOpRouteFinderClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.routing.BestPathRouter;
import com.routechain.v2.routing.RouteCostFunction;
import com.routechain.v2.routing.RouteVectorEnricher;
import com.routechain.v2.routing.SyntheticRoadGraphProvider;
import com.routechain.v2.scenario.DispatchScenarioService;
import com.routechain.v2.scenario.DispatchScenarioStage;
import com.routechain.v2.scenario.DemandShiftFeatureBuilder;
import com.routechain.v2.scenario.PostDropShiftFeatureBuilder;
import com.routechain.v2.scenario.RobustUtilityAggregator;
import com.routechain.v2.scenario.ScenarioEvaluator;
import com.routechain.v2.scenario.ScenarioGateEvaluator;
import com.routechain.v2.scenario.ZoneBurstFeatureBuilder;
import com.routechain.v2.executor.DispatchAssignmentBuilder;
import com.routechain.v2.executor.DispatchExecutor;
import com.routechain.v2.executor.DispatchExecutorService;
import com.routechain.v2.executor.DispatchExecutorStage;
import com.routechain.v2.executor.ExecutionConflictValidator;
import com.routechain.v2.executor.SelectedProposalResolver;
import com.routechain.v2.selector.ConflictGraphBuilder;
import com.routechain.v2.selector.DispatchSelectorService;
import com.routechain.v2.selector.DispatchSelectorStage;
import com.routechain.v2.selector.GlobalSelector;
import com.routechain.v2.selector.GreedyRepairSelector;
import com.routechain.v2.selector.OrToolsSetPackingSolver;
import com.routechain.v2.selector.SelectorCandidateBuilder;
import com.routechain.v2.selector.SelectorSolver;

import java.time.Instant;
import java.util.List;

public final class RouteTestFixtures {
    private RouteTestFixtures() {
    }

    public static RouteChainDispatchV2Properties properties() {
        return RouteChainDispatchV2Properties.defaults();
    }

    public static DispatchV2Request request() {
        Instant decisionTime = Instant.parse("2026-04-16T12:00:00Z");
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-route",
                List.of(
                        order("order-1", 10.7750, 106.7000, 10.7800, 106.7100, decisionTime, false),
                        order("order-2", 10.7760, 106.7010, 10.7810, 106.7120, decisionTime.plusSeconds(120), false),
                        order("order-3", 10.7770, 106.7020, 10.7820, 106.7130, decisionTime.plusSeconds(240), true)),
                List.of(
                        new Driver("driver-1", new GeoPoint(10.7700, 106.6950)),
                        new Driver("driver-2", new GeoPoint(10.7720, 106.6970)),
                        new Driver("driver-3", new GeoPoint(10.7780, 106.7040))),
                List.of(),
                WeatherProfile.CLEAR,
                decisionTime);
    }

    public static EtaContext etaContext() {
        return new EtaContext(
                "dispatch-eta-context/v1",
                "trace-route",
                1,
                6.0,
                6.0,
                0.3,
                false,
                false,
                "corridor-a",
                "baseline-profile-weather");
    }

    public static DispatchPairClusterStage pairClusterStage(RouteChainDispatchV2Properties properties) {
        BaselineTravelTimeEstimator estimator = new BaselineTravelTimeEstimator();
        EtaService etaService = new EtaService(
                properties,
                estimator,
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                new NoOpTabularScoringClient(),
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        return new DispatchPairClusterService(
                properties,
                new OrderBuffer(properties),
                new PairSimilarityGraphBuilder(
                        properties,
                        new PairFeatureBuilder(estimator),
                        new PairSimilarityScorer(properties, new PairHardGateEvaluator(properties), new NoOpTabularScoringClient())),
                new EtaLegCacheFactory(properties, etaService),
                new MicroClusterer(properties))
                .evaluate(request(), etaContext());
    }

    public static DispatchBundleStage bundleStage(RouteChainDispatchV2Properties properties, DispatchPairClusterStage pairClusterStage) {
        return bundleStage(properties, pairClusterStage, new NoOpGreedRlClient());
    }

    public static DispatchBundleStage bundleStage(RouteChainDispatchV2Properties properties,
                                                  DispatchPairClusterStage pairClusterStage,
                                                  GreedRlClient greedRlClient) {
        return new DispatchBundleStageService(
                properties,
                new BoundaryCandidateSelector(properties),
                new BoundaryExpansionEngine(properties),
                new BundleSeedGenerator(properties),
                new BundleFamilyEnumerator(properties),
                new BundleValidator(properties),
                new BundleScorer(properties),
                new BundleDominancePruner(),
                greedRlClient)
                .evaluate(etaContext(), pairClusterStage);
    }

    public static DispatchCandidateContext candidateContext(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        return new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                request().availableDrivers(),
                pairClusterStage,
                bundleStage);
    }

    public static DispatchRouteCandidateService routeService(RouteChainDispatchV2Properties properties) {
        return routeService(properties, new NoOpTabularScoringClient());
    }

    public static DispatchRouteCandidateService routeService(RouteChainDispatchV2Properties properties,
                                                             TabularScoringClient tabularScoringClient) {
        EtaService etaService = new EtaService(
                properties,
                new BaselineTravelTimeEstimator(),
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                tabularScoringClient,
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        EtaLegCacheFactory etaLegCacheFactory = new EtaLegCacheFactory(properties, etaService);
        return new DispatchRouteCandidateService(
                new PickupAnchorSelector(properties),
                new CandidateDriverShortlister(properties, new DriverRouteFeatureBuilder(), tabularScoringClient),
                new DriverReranker(),
                etaLegCacheFactory);
    }

    public static DispatchRouteCandidateStage routeCandidateStage(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        return routeService(properties).evaluate(request(), etaContext(), pairClusterStage, bundleStage);
    }

    public static DispatchRouteProposalService routeProposalService(RouteChainDispatchV2Properties properties) {
        return routeProposalService(properties, new NoOpTabularScoringClient(), new NoOpRouteFinderClient());
    }

    public static DispatchRouteProposalService routeProposalService(RouteChainDispatchV2Properties properties,
                                                                    TabularScoringClient tabularScoringClient) {
        return routeProposalService(properties, tabularScoringClient, new NoOpRouteFinderClient());
    }

    public static DispatchRouteProposalService routeProposalService(RouteChainDispatchV2Properties properties,
                                                                    TabularScoringClient tabularScoringClient,
                                                                    RouteFinderClient routeFinderClient) {
        EtaService etaService = new EtaService(
                properties,
                new BaselineTravelTimeEstimator(),
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                tabularScoringClient,
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        EtaLegCacheFactory etaLegCacheFactory = new EtaLegCacheFactory(properties, etaService);
        return new DispatchRouteProposalService(
                properties,
                new RouteProposalEngine(),
                new RouteProposalValidator(),
                new RouteValueScorer(properties, tabularScoringClient),
                new RouteProposalPruner(properties),
                etaLegCacheFactory,
                routeFinderClient,
                new RouteVectorEnricher(
                        new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()),
                        new DecisionStageLogger(properties)),
                new DecisionStageLogger(properties));
    }

    public static DispatchRouteProposalStage routeProposalStage(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        DispatchRouteCandidateStage routeCandidateStage = routeCandidateStage(properties);
        return routeProposalService(properties).evaluate(request(), etaContext(), pairClusterStage, bundleStage, routeCandidateStage);
    }

    public static EtaContext weatherBadEtaContext() {
        return new EtaContext(
                "dispatch-eta-context/v1",
                "trace-route-weather",
                1,
                8.0,
                8.0,
                0.45,
                false,
                true,
                "corridor-a",
                "baseline-profile-weather");
    }

    public static EtaContext trafficBadEtaContext() {
        return new EtaContext(
                "dispatch-eta-context/v1",
                "trace-route-traffic",
                1,
                8.0,
                8.0,
                0.45,
                true,
                false,
                "corridor-a",
                "baseline-profile-weather");
    }

    public static DispatchScenarioService scenarioService(RouteChainDispatchV2Properties properties) {
        return scenarioService(properties, new NoOpForecastClient());
    }

    public static DispatchScenarioService scenarioService(RouteChainDispatchV2Properties properties,
                                                          ForecastClient forecastClient) {
        return new DispatchScenarioService(
                properties,
                forecastClient,
                new DemandShiftFeatureBuilder(),
                new ZoneBurstFeatureBuilder(),
                new PostDropShiftFeatureBuilder(),
                new ScenarioGateEvaluator(properties),
                new ScenarioEvaluator(properties),
                new RobustUtilityAggregator());
    }

    public static DispatchScenarioStage scenarioStage(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        DispatchRouteCandidateStage routeCandidateStage = routeCandidateStage(properties);
        DispatchRouteProposalStage routeProposalStage = routeProposalStage(properties);
        return scenarioService(properties).evaluate(
                request(),
                etaContext(),
                new FreshnessMetadata("freshness-metadata/v1", 0L, 0L, 0L, true, true, false),
                LiveStageMetadata.emptyList(),
                routeProposalStage,
                routeCandidateStage,
                bundleStage,
                pairClusterStage);
    }

    public static DispatchSelectorService selectorService(RouteChainDispatchV2Properties properties) {
        SelectorSolver selectorSolver = new OrToolsSetPackingSolver(properties);
        return new DispatchSelectorService(
                properties,
                new SelectorCandidateBuilder(properties),
                new ConflictGraphBuilder(),
                new GlobalSelector(properties, new GreedyRepairSelector(), selectorSolver));
    }

    public static DispatchSelectorStage selectorStage(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        DispatchRouteCandidateStage routeCandidateStage = routeCandidateStage(properties);
        DispatchRouteProposalStage routeProposalStage = routeProposalStage(properties);
        DispatchScenarioStage scenarioStage = scenarioStage(properties);
        return selectorService(properties).evaluate(
                request(),
                etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage);
    }

    public static DispatchExecutorService executorService(RouteChainDispatchV2Properties properties) {
        return new DispatchExecutorService(new DispatchExecutor(
                new SelectedProposalResolver(),
                new ExecutionConflictValidator(),
                new DispatchAssignmentBuilder()));
    }

    public static DispatchExecutorStage executorStage(RouteChainDispatchV2Properties properties) {
        DispatchPairClusterStage pairClusterStage = pairClusterStage(properties);
        DispatchBundleStage bundleStage = bundleStage(properties, pairClusterStage);
        DispatchRouteCandidateStage routeCandidateStage = routeCandidateStage(properties);
        DispatchRouteProposalStage routeProposalStage = routeProposalStage(properties);
        DispatchSelectorStage selectorStage = selectorStage(properties);
        return executorService(properties).evaluate(
                request(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                selectorStage);
    }

    private static Order order(String orderId,
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
}
