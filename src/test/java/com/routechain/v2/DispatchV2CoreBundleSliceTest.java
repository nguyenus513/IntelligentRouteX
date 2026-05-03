package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchV2CoreBundleSliceTest {

    @Test
    void enabledPathReturnsBundleStagesAndOutputs() {
        DispatchV2Core core = TestDispatchV2Factory.core(RouteChainDispatchV2Properties.defaults());

        DispatchV2Result result = core.dispatch(TestDispatchV2Factory.requestWithOrdersAndDriver());

        assertEquals(List.of("eta/context", "order-buffer", "pair-graph", "micro-cluster", "boundary-expansion", "bundle-pool", "pickup-anchor", "driver-shortlist/rerank", "route-proposal-pool", "scenario-evaluation", "global-selector", "dispatch-executor"), result.decisionStages());
        assertFalse(result.fallbackUsed());
        assertNull(result.selectedRouteId());
        assertNotNull(result.boundaryExpansionSummary());
        assertNotNull(result.bundlePoolSummary());
        assertNotNull(result.pickupAnchorSummary());
        assertNotNull(result.driverShortlistSummary());
        assertNotNull(result.routeProposalSummary());
        assertNotNull(result.scenarioEvaluationSummary());
        assertNotNull(result.globalSelectorSummary());
        assertNotNull(result.dispatchExecutionSummary());
        assertFalse(result.boundaryExpansions().isEmpty());
        assertFalse(result.bundleCandidates().isEmpty());
        assertFalse(result.routeProposals().isEmpty());
        assertFalse(result.scenarioEvaluations().isEmpty());
        assertFalse(result.assignments().isEmpty());
        assertTrue(result.bundlePoolSummary().retainedCount() > 0);
        assertFalse(result.bundlePoolSummary().familyGeneratedCounts().isEmpty());
        assertFalse(result.bundlePoolSummary().familyRetainedCounts().isEmpty());
        assertTrue(result.bundlePoolSummary().diversityRetainedCount() > 0);
    }
}
