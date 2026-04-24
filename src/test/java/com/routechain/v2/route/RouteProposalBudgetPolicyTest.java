package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteProposalBudgetPolicyTest {

    @Test
    void capsFullAdaptiveSmallWorkloadAtConfiguredBudget() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().getRouteProposalBudget().setEnabled(true);
        properties.getCompute().getAdaptive().setProfileName("dispatch-v2-full-adaptive");
        RouteProposalBudgetPolicy policy = new RouteProposalBudgetPolicy(properties);

        RouteProposalBudgetDecision decision = policy.decide(RouteTestFixtures.request(), RouteTestFixtures.etaContext(), 16, 128, 1.0);

        assertTrue(decision.enabled());
        assertEquals("full-adaptive-s", decision.budgetMode());
        assertEquals(256, decision.maxTotalRouteProposals());
        assertEquals(4, decision.maxDriversPerBundle());
        assertEquals(2, decision.maxAnchorsPerBundle());
    }

    @Test
    void labelsLargeWorkloadAsFullAdaptiveMedium() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().getRouteProposalBudget().setEnabled(true);
        properties.getCompute().getAdaptive().setProfileName("dispatch-v2-full-adaptive");
        RouteProposalBudgetPolicy policy = new RouteProposalBudgetPolicy(properties);

        RouteProposalBudgetDecision decision = policy.decide(null, RouteTestFixtures.etaContext(), 16, 128, 1.0);

        assertEquals("full-adaptive-m", decision.budgetMode());
        assertEquals(512, decision.maxTotalRouteProposals());
    }

    @Test
    void explicitSmallWorkloadHintWinsOverCandidateCountInference() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().getRouteProposalBudget().setEnabled(true);
        properties.getCandidate().getRouteProposalBudget().setWorkloadSizeHint("S");
        properties.getCompute().getAdaptive().setProfileName("dispatch-v2-full-adaptive");
        RouteProposalBudgetPolicy policy = new RouteProposalBudgetPolicy(properties);

        RouteProposalBudgetDecision decision = policy.decide(null, RouteTestFixtures.etaContext(), 16, 256, 1.0);

        assertEquals("full-adaptive-s", decision.budgetMode());
        assertEquals(256, decision.maxTotalRouteProposals());
    }

    @Test
    void reducesBreadthWhenPreviousGeometryCoverageIsLow() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().getRouteProposalBudget().setEnabled(true);
        RouteProposalBudgetPolicy policy = new RouteProposalBudgetPolicy(properties);

        RouteProposalBudgetDecision decision = policy.decide(RouteTestFixtures.request(), RouteTestFixtures.etaContext(), 4, 64, 0.70);

        assertEquals(179, decision.maxTotalRouteProposals());
        assertTrue(decision.budgetReasons().contains("low-geometry-coverage-breadth-reduced"));
    }
}
