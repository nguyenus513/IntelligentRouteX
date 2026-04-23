package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.TestGreedRlClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchBundleStageServiceAdaptiveComputeTest {

    @Test
    void adaptiveGateCanSkipGreedRlForLowComplexityBundleSeed() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getGreedrl().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        properties.getCompute().getAdaptive().setGreedrlMinWorkingOrders(99);
        properties.getCompute().getAdaptive().setGreedrlMinAcceptedBoundaryOrders(99);
        properties.getCompute().getAdaptive().setGreedrlSupportSpreadThreshold(-1.0);
        TestGreedRlClient greedRlClient = TestGreedRlClient.applied();

        DispatchBundleStage stage = RouteChainBundleFixtures.bundleStage(properties, greedRlClient);

        assertEquals(0, greedRlClient.bundleInvocations().size());
        assertTrue(stage.bundleCandidates().stream().noneMatch(candidate -> candidate.proposalSource() == BundleProposalSource.GREEDRL_PROPOSAL));
    }

    @Test
    void adaptiveGateEscalatesGreedRlWhenThresholdAllowsIt() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getGreedrl().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        properties.getCompute().getAdaptive().setGreedrlMinWorkingOrders(1);
        TestGreedRlClient greedRlClient = TestGreedRlClient.applied();

        DispatchBundleStage stage = RouteChainBundleFixtures.bundleStage(properties, greedRlClient);

        assertTrue(greedRlClient.bundleInvocations().size() > 0);
        assertTrue(stage.bundlePoolSummary().sourceCounts().getOrDefault(BundleProposalSource.GREEDRL_PROPOSAL, 0) > 0);
    }
}
