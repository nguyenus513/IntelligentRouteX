package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GlobalSelectorDegradeTest {

    @Test
    void usesGreedyRepairWhenOrtoolsDisabled() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                SelectorTestFixtures.envelope("proposal-a", "bundle-a", "driver-1", List.of("order-1"), 0.90, 0.85, 0.95, 5.0, true),
                SelectorTestFixtures.envelope("proposal-b", "bundle-b", "driver-2", List.of("order-2"), 0.80, 0.80, 0.88, 6.0, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());

        GlobalSelectionResult greedyResult = new GlobalSelector(
                RouteChainDispatchV2Properties.defaults(),
                new GreedyRepairSelector(),
                unavailable("selector-ortools-failed"))
                .select(candidates, graph)
                .selectionResult();

        assertEquals(SelectionSolverMode.GREEDY_REPAIR, greedyResult.solverMode());
    }

    @Test
    void degradesToGreedyWhenSolverReturnsUnavailableTimeoutOrFailure() {
        assertDegradedReason("selector-ortools-unavailable");
        assertDegradedReason("selector-ortools-timeout");
        assertDegradedReason("selector-ortools-failed");
    }



    @Test
    void doesNotSelectOracleRejectedCandidateWhenReducedPoolIsEmpty() {
        SelectorCandidate badCandidate = new SelectorCandidate(
                "selector-candidate/v1",
                "bad-food",
                "bundle-bad",
                "order-bad",
                "driver-bad",
                List.of("order-bad"),
                0.99,
                0.99,
                com.routechain.v2.route.RouteProposalSource.HEURISTIC_FAST,
                "cluster-bad",
                false,
                0.99,
                true,
                List.of(),
                List.of("food-on-vehicle-hard-limit"));
        List<SelectorCandidateEnvelope> candidates = List.of(new SelectorCandidateEnvelope(badCandidate, 1.0));
        ConflictGraph graph = new ConflictGraphBuilder().build(List.of(badCandidate));

        GlobalSelectionResult result = new GlobalSelector(
                RouteChainDispatchV2Properties.defaults(),
                new GreedyRepairSelector(),
                unavailable("selector-ortools-unavailable"))
                .select(candidates, graph)
                .selectionResult();

        assertTrue(result.selectedProposals().isEmpty());
        assertTrue(result.degradeReasons().contains("selector-feasibility-violation-food-on-vehicle-max-exceeded"));
    }

    @Test
    void timeoutReturnsFeasibleGreedyIncumbentWithTelemetry() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                SelectorTestFixtures.envelope("proposal-a", "bundle-a", "driver-1", List.of("order-1"), 0.90, 0.85, 0.95, 5.0, true),
                SelectorTestFixtures.envelope("proposal-b", "bundle-b", "driver-2", List.of("order-2"), 0.80, 0.80, 0.88, 6.0, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setSelectorOrtoolsEnabled(true);

        GlobalSelectionResult result = new GlobalSelector(
                properties,
                new GreedyRepairSelector(),
                unavailable("selector-ortools-timeout"))
                .select(candidates, graph)
                .selectionResult();

        assertEquals(SelectionSolverMode.CP_SAT_TIMEOUT_INCUMBENT, result.solverMode());
        assertTrue(result.selectorTimedOut());
        assertEquals("CP_SAT_TIMEOUT_INCUMBENT", result.selectorFallbackLevel());
        assertTrue(result.acceptanceGatePassed());
        assertEquals(2, result.selectorPoolInputCount());
        assertEquals(2, result.selectorPoolReducedCount());
        assertEquals(2, result.selectedCount());
    }


    private void assertDegradedReason(String degradeReason) {
        List<SelectorCandidateEnvelope> candidates = List.of(
                SelectorTestFixtures.envelope("proposal-a", "bundle-a", "driver-1", List.of("order-1"), 0.90, 0.85, 0.95, 5.0, true),
                SelectorTestFixtures.envelope("proposal-b", "bundle-b", "driver-2", List.of("order-1"), 0.80, 0.80, 0.88, 6.0, true),
                SelectorTestFixtures.envelope("proposal-c", "bundle-c", "driver-3", List.of("order-2"), 0.75, 0.70, 0.81, 4.0, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setSelectorOrtoolsEnabled(true);

        GlobalSelectionResult degradedResult = new GlobalSelector(
                properties,
                new GreedyRepairSelector(),
                unavailable(degradeReason))
                .select(candidates, graph)
                .selectionResult();

        SelectionSolverMode expectedMode = degradeReason.contains("timeout")
                ? SelectionSolverMode.CP_SAT_TIMEOUT_INCUMBENT
                : SelectionSolverMode.DEGRADED_GREEDY;
        assertEquals(expectedMode, degradedResult.solverMode());
        assertTrue(degradedResult.degradeReasons().contains(degradeReason));
    }

    private SelectorSolver unavailable(String degradeReason) {
        return (selectorCandidates, conflictGraph) -> new SelectorSolverResult(Optional.empty(), List.of(degradeReason));
    }
}
