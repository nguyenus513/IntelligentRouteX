package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextSelectorTest {

    @Test
    void forcesCompactContextForHeavyLlmStages() {
        RouteChainDispatchV2Properties.Decision decision = RouteChainDispatchV2Properties.defaults().getDecision();
        ContextSelector selector = new ContextSelector(decision);

        ContextSelectionProfile profile = selector.select(
                DecisionStageName.ROUTE_CRITIQUE,
                Map.of("trafficBad", true, "weatherBad", true),
                Map.of("proposalCount", 20, "topIds", List.of("a", "b", "c", "d", "e")),
                List.of("prev-stage"));

        assertEquals("compact-staging", profile.profileName());
        assertTrue(profile.compressed());
        assertTrue(profile.qualityFlags().contains("context-forced-compact"));
        assertEquals(Boolean.TRUE, profile.selectedContext().get("forceCompact"));
    }
}
