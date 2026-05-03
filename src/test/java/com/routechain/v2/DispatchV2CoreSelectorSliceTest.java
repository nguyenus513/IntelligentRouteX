package com.routechain.v2;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.selector.SelectorCandidate;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchV2CoreSelectorSliceTest {

    @Test
    void enabledPathReturnsSelectorOutputsAndSelectedSetHasNoOrderOrDriverConflicts() {
        DispatchV2Core core = TestDispatchV2Factory.core(TestDispatchV2Factory.selectorSmokeProperties());

        DispatchV2Result result = core.dispatch(TestDispatchV2Factory.selectorSmokeRequest());

        assertEquals(List.of("eta/context", "order-buffer", "pair-graph", "micro-cluster", "boundary-expansion", "bundle-pool", "pickup-anchor", "driver-shortlist/rerank", "route-proposal-pool", "scenario-evaluation", "global-selector", "dispatch-executor"), result.decisionStages());
        assertFalse(result.fallbackUsed());
        assertNull(result.selectedRouteId());
        assertFalse(result.selectorCandidates().isEmpty());
        assertTrue(result.globalSelectionResult().selectedCount() > 0);
        assertTrue(result.globalSelectorSummary().selectedCount() > 0);
        assertNotNull(result.activeRepairTelemetry());
        assertFalse(result.assignments().isEmpty());

        Set<String> selectedDrivers = new HashSet<>();
        Set<String> selectedOrders = new HashSet<>();
        for (var selectedProposal : result.globalSelectionResult().selectedProposals()) {
            SelectorCandidate candidate = result.selectorCandidates().stream()
                    .filter(current -> current.proposalId().equals(selectedProposal.proposalId()))
                    .findFirst()
                    .orElseThrow();
            assertTrue(selectedDrivers.add(candidate.driverId()));
            assertTrue(candidate.orderIds().stream().allMatch(selectedOrders::add));
        }
    }
}
