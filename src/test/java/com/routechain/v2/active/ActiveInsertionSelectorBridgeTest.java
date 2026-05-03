package com.routechain.v2.active;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidateEnvelope;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveInsertionSelectorBridgeTest {

    @Test
    void bridgesActiveInsertionIntoSelectorCandidate() {
        ActiveRouteInsertionCandidate insertion = new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                "route-1:insert:order-2:1",
                "route-1",
                "driver-1",
                "order-2",
                1,
                List.of("order-1", "order-2"),
                3.0,
                18.0,
                2.0,
                0.10,
                0.20,
                0.15,
                0.82,
                true,
                List.of("active-route-regret-insertion"),
                List.of());

        SelectorCandidateEnvelope envelope = new ActiveInsertionSelectorBridge().bridge(insertion);

        assertEquals("route-1:insert:order-2:1", envelope.candidate().proposalId());
        assertEquals(RouteProposalSource.ACTIVE_ROUTE_INSERTION, envelope.candidate().source());
        assertEquals(List.of("order-1", "order-2"), envelope.candidate().orderIds());
        assertTrue(envelope.candidate().feasible());
        assertTrue(envelope.candidate().selectionScore() > insertion.score());
        assertTrue(envelope.candidate().reasons().contains("selector-active-route-insertion-bridge"));
    }
}
