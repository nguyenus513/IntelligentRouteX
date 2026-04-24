package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.cluster.EtaLegCacheFactory;
import com.routechain.v2.context.BaselineTravelTimeEstimator;
import com.routechain.v2.context.EtaFeatureBuilder;
import com.routechain.v2.context.EtaService;
import com.routechain.v2.context.EtaUncertaintyEstimator;
import com.routechain.v2.context.TrafficProfileService;
import com.routechain.v2.context.WeatherContextService;
import com.routechain.v2.integration.NoOpOpenMeteoClient;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.NoOpTomTomTrafficRefineClient;
import org.junit.jupiter.api.Test;

import java.util.EnumSet;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteProposalEngineTest {

    @Test
    void emitsAllSourcesDeterministicallyFromExistingDriverCandidates() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(properties);
        DispatchRouteCandidateStage routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        EtaService etaService = new EtaService(
                properties,
                new BaselineTravelTimeEstimator(),
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                new NoOpTabularScoringClient(),
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        var etaLegCache = new EtaLegCacheFactory(properties, etaService)
                .create(RouteTestFixtures.request().traceId(), RouteTestFixtures.request().decisionTime(), RouteTestFixtures.request().weatherProfile());
        RouteProposalEngine engine = new RouteProposalEngine();

        List<RouteProposalCandidate> first = engine.generate(routeCandidateStage.driverCandidates(), routeCandidateStage.pickupAnchors(), context, etaLegCache);
        List<RouteProposalCandidate> second = engine.generate(routeCandidateStage.driverCandidates(), routeCandidateStage.pickupAnchors(), context, etaLegCache);

        assertEquals(first.stream().map(candidate -> candidate.proposal().proposalId()).toList(), second.stream().map(candidate -> candidate.proposal().proposalId()).toList());
        assertEquals(
                EnumSet.of(RouteProposalSource.HEURISTIC_FAST, RouteProposalSource.HEURISTIC_SAFE, RouteProposalSource.FALLBACK_SIMPLE),
                first.stream().map(candidate -> candidate.proposal().source()).collect(java.util.stream.Collectors.toCollection(() -> EnumSet.noneOf(RouteProposalSource.class))));
        assertTrue(first.stream().allMatch(candidate -> routeCandidateStage.driverCandidates().stream().anyMatch(driverCandidate ->
                driverCandidate.bundleId().equals(candidate.proposal().bundleId())
                        && driverCandidate.anchorOrderId().equals(candidate.proposal().anchorOrderId())
                        && driverCandidate.driverId().equals(candidate.proposal().driverId()))));
    }

    @Test
    void emitsBoundedRecoveryStopOrdersForMultiOrderBundles() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(properties);
        DispatchRouteCandidateStage routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        EtaService etaService = new EtaService(
                properties,
                new BaselineTravelTimeEstimator(),
                new TrafficProfileService(properties),
                new WeatherContextService(properties, new NoOpOpenMeteoClient()),
                new NoOpTomTomTrafficRefineClient(),
                new NoOpTabularScoringClient(),
                new EtaFeatureBuilder(),
                new EtaUncertaintyEstimator());
        var etaLegCache = new EtaLegCacheFactory(properties, etaService)
                .create(RouteTestFixtures.request().traceId(), RouteTestFixtures.request().decisionTime(), RouteTestFixtures.request().weatherProfile());
        DriverCandidate multiOrderDriver = routeCandidateStage.driverCandidates().stream()
                .filter(candidate -> context.bundle(candidate.bundleId()).orderIds().size() >= 3)
                .filter(candidate -> context.bundle(candidate.bundleId()).orderIds().size() <= 4)
                .findFirst()
                .orElseThrow();
        PickupAnchor pickupAnchor = routeCandidateStage.pickupAnchors().stream()
                .filter(anchor -> anchor.bundleId().equals(multiOrderDriver.bundleId())
                        && anchor.anchorOrderId().equals(multiOrderDriver.anchorOrderId()))
                .findFirst()
                .orElseThrow();
        RouteProposalEngine engine = new RouteProposalEngine();

        List<RouteProposalCandidate> generated = engine.generate(List.of(multiOrderDriver), List.of(pickupAnchor), context, etaLegCache);

        assertTrue(generated.size() > 3);
        assertTrue(generated.stream().map(candidate -> candidate.proposal().stopOrder()).distinct().count() > 1);
    }
}
