package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.TestRouteFinderClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchRouteProposalServiceAdaptiveComputeTest {

    @Test
    void adaptiveGateCanSkipRouteFinderForSimpleClearCase() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getRoutefinder().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        properties.getCompute().getAdaptive().setRoutefinderStopCountThreshold(99);
        properties.getCompute().getAdaptive().setRoutefinderEtaAmbiguityThresholdMinutes(-1.0);
        properties.getCompute().getAdaptive().setRoutefinderBoundaryCrossEscalationEnabled(false);
        properties.getCompute().getAdaptive().setRoutefinderTrafficEscalationEnabled(false);
        properties.getCompute().getAdaptive().setRoutefinderWeatherEscalationEnabled(false);
        TestRouteFinderClient routeFinderClient = TestRouteFinderClient.applied();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        DispatchRouteProposalService service = RouteTestFixtures.routeProposalService(
                properties,
                new NoOpTabularScoringClient(),
                routeFinderClient);

        DispatchRouteProposalStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage);

        assertEquals(0, routeFinderClient.alternativesInvocations().size());
        assertEquals(0, routeFinderClient.refineInvocations().size());
        assertTrue(stage.routeProposals().stream().noneMatch(proposal ->
                proposal.source() == RouteProposalSource.ML_PROPOSAL || proposal.source() == RouteProposalSource.ML_REFINED));
    }

    @Test
    void adaptiveGateEscalatesRouteFinderWhenAmbiguityThresholdAllowsIt() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getRoutefinder().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        properties.getCompute().getAdaptive().setRoutefinderEtaAmbiguityThresholdMinutes(10.0);
        TestRouteFinderClient routeFinderClient = TestRouteFinderClient.applied();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        DispatchRouteProposalService service = RouteTestFixtures.routeProposalService(
                properties,
                new NoOpTabularScoringClient(),
                routeFinderClient);

        DispatchRouteProposalStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage);

        assertTrue(routeFinderClient.alternativesInvocations().size() > 0);
        assertTrue(routeFinderClient.refineInvocations().size() > 0);
        assertTrue(stage.routeProposals().stream().anyMatch(proposal -> proposal.source() == RouteProposalSource.ML_PROPOSAL));
    }
}
