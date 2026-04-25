package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrToolsSetPackingSolverTest {

    @Test
    void solvesSimpleSetPackingAndKeepsObjectiveEqualToSelectedScoreSum() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getSelector().getOrtools().setTimeout(Duration.ofSeconds(2));
        OrToolsSetPackingSolver solver = new OrToolsSetPackingSolver(properties);
        List<SelectorCandidate> candidates = List.of(
                SelectorTestFixtures.candidate("proposal-a", "bundle-a", "driver-1", List.of("order-1"), 0.90, 0.70, 0.90, true),
                SelectorTestFixtures.candidate("proposal-b", "bundle-b", "driver-2", List.of("order-2"), 0.88, 0.75, 0.89, true),
                SelectorTestFixtures.candidate("proposal-c", "bundle-c", "driver-3", List.of("order-1", "order-2"), 0.95, 0.93, 1.95, true),
                SelectorTestFixtures.candidate("proposal-d", "bundle-a", "driver-4", List.of("order-3"), 0.70, 0.68, 0.70, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates);

        GlobalSelectionResult result = solver.solve(candidates, graph).selectionResult().orElseThrow();
        Map<String, SelectorCandidate> byProposalId = candidates.stream()
                .collect(java.util.stream.Collectors.toMap(SelectorCandidate::proposalId, candidate -> candidate));

        assertEquals(SelectionSolverMode.ORTOOLS, result.solverMode());
        assertEquals(result.selectedProposals().stream().mapToDouble(SelectedProposal::selectionScore).sum(), result.objectiveValue(), 1e-9);
        assertTrue(result.selectedProposals().stream().allMatch(selected -> byProposalId.containsKey(selected.proposalId())));
        assertTrue(result.selectedProposals().stream().allMatch(selected -> graph.edges().stream()
                .filter(edge -> edge.leftProposalId().equals(selected.proposalId()) || edge.rightProposalId().equals(selected.proposalId()))
                .noneMatch(edge -> result.selectedProposals().stream().anyMatch(other ->
                        !other.proposalId().equals(selected.proposalId())
                                && (other.proposalId().equals(edge.leftProposalId()) || other.proposalId().equals(edge.rightProposalId()))))));
        assertTrue(result.selectedProposals().stream().anyMatch(selected -> selected.proposalId().equals("proposal-c")));
        assertTrue(result.selectedProposals().stream().anyMatch(selected -> selected.proposalId().equals("proposal-d")));
        assertTrue(result.selectedProposals().stream().noneMatch(selected -> selected.proposalId().equals("proposal-a")));
        assertTrue(result.selectedProposals().stream().noneMatch(selected -> selected.proposalId().equals("proposal-b")));
    }
    @Test
    void scarcityObjectivePrefersCleanLargerBundleOverBlockingPairs() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getSelector().getOrtools().setTimeout(Duration.ofSeconds(2));
        OrToolsSetPackingSolver solver = new OrToolsSetPackingSolver(properties);
        List<SelectorCandidate> candidates = List.of(
                SelectorTestFixtures.candidate("proposal-big", "bundle-big", "driver-1", List.of("order-1", "order-2", "order-3", "order-4"), 0.82, 0.82, 0.86, true),
                SelectorTestFixtures.candidate("proposal-pair-a", "bundle-pair-a", "driver-1", List.of("order-1", "order-2"), 0.90, 0.90, 0.98, true),
                SelectorTestFixtures.candidate("proposal-pair-b", "bundle-pair-b", "driver-2", List.of("order-3", "order-4"), 0.88, 0.88, 0.96, true),
                SelectorTestFixtures.candidate("proposal-other", "bundle-other", "driver-2", List.of("order-5", "order-6"), 0.80, 0.80, 0.84, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates);

        GlobalSelectionResult result = solver.solve(candidates, graph).selectionResult().orElseThrow();

        assertEquals(List.of("proposal-big", "proposal-other"), result.selectedProposals().stream().map(SelectedProposal::proposalId).toList());
        assertTrue(result.degradeReasons().contains("scarce-bundling-priority-enabled"));
        assertTrue(result.selectedProposals().stream()
                .filter(selected -> selected.proposalId().equals("proposal-big"))
                .findFirst()
                .orElseThrow()
                .reasons()
                .contains("selected-by-ortools-scarce-bundling"));
    }
}
