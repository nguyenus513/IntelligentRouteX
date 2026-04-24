package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.NoOpGreedRlClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchBundleStageServiceTest {

    @Test
    void runsBoundaryExpansionBeforeBundleGenerationAndUsesPairClusterOutputs() {
        DispatchBundleStageService service = new DispatchBundleStageService(
                RouteChainDispatchV2Properties.defaults(),
                new BoundaryCandidateSelector(RouteChainDispatchV2Properties.defaults()),
                new BoundaryExpansionEngine(RouteChainDispatchV2Properties.defaults()),
                new BundleSeedGenerator(RouteChainDispatchV2Properties.defaults()),
                new BundleFamilyEnumerator(RouteChainDispatchV2Properties.defaults()),
                new BundleValidator(RouteChainDispatchV2Properties.defaults()),
                new BundleScorer(RouteChainDispatchV2Properties.defaults()),
                new BundleDominancePruner(),
                new NoOpGreedRlClient());

        DispatchBundleStage stage = service.evaluate(
                BundleTestFixtures.clearEtaContext(),
                BundleTestFixtures.pairClusterStage());

        assertFalse(stage.boundaryExpansions().isEmpty());
        assertFalse(stage.bundleCandidates().isEmpty());
        assertTrue(stage.boundaryExpansions().stream().anyMatch(expansion -> !expansion.supportScoreByOrder().isEmpty()));
    }

    @Test
    void emitsSingleOrderRecoveryCandidatesForEveryWorkingOrder() {
        DispatchBundleStageService service = new DispatchBundleStageService(
                RouteChainDispatchV2Properties.defaults(),
                new BoundaryCandidateSelector(RouteChainDispatchV2Properties.defaults()),
                new BoundaryExpansionEngine(RouteChainDispatchV2Properties.defaults()),
                new BundleSeedGenerator(RouteChainDispatchV2Properties.defaults()),
                new BundleFamilyEnumerator(RouteChainDispatchV2Properties.defaults()),
                new BundleValidator(RouteChainDispatchV2Properties.defaults()),
                new BundleScorer(RouteChainDispatchV2Properties.defaults()),
                new BundleDominancePruner(),
                new NoOpGreedRlClient());

        DispatchBundleStage stage = service.evaluate(
                BundleTestFixtures.clearEtaContext(),
                BundleTestFixtures.pairClusterStage());

        assertTrue(stage.bundleCandidates().stream().anyMatch(candidate ->
                candidate.bundleId().startsWith("SINGLE_ORDER_RECOVERY|")
                        && candidate.orderIds().size() == 1
                        && candidate.feasible()));
        assertTrue(stage.bundleCandidates().stream().anyMatch(candidate ->
                candidate.bundleId().equals("SINGLE_ORDER_RECOVERY|order-1|order-1")));
        assertTrue(stage.bundleCandidates().stream().anyMatch(candidate ->
                candidate.bundleId().equals("SINGLE_ORDER_RECOVERY|order-2|order-2")));
        assertTrue(stage.bundleCandidates().stream().anyMatch(candidate ->
                candidate.bundleId().equals("SINGLE_ORDER_RECOVERY|order-3|order-3")));
    }
}
