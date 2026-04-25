package com.routechain.v2.selector;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreedyRepairSelectorTest {

    @Test
    void selectsConflictFreeSubsetPrefersHigherScoreAndIsDeterministic() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                SelectorTestFixtures.envelope("proposal-a", "bundle-a", "driver-1", List.of("order-1"), 0.90, 0.85, 0.95, 5.0, true),
                SelectorTestFixtures.envelope("proposal-b", "bundle-b", "driver-2", List.of("order-1"), 0.80, 0.80, 0.88, 6.0, true),
                SelectorTestFixtures.envelope("proposal-c", "bundle-c", "driver-3", List.of("order-2"), 0.75, 0.70, 0.81, 4.0, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());
        GreedyRepairSelector selector = new GreedyRepairSelector();

        SelectorSelectionOutcome first = selector.select(candidates, graph, SelectionSolverMode.GREEDY_REPAIR, true);
        SelectorSelectionOutcome second = selector.select(candidates, graph, SelectionSolverMode.GREEDY_REPAIR, true);

        assertEquals(List.of("proposal-a", "proposal-c"), first.selectionResult().selectedProposals().stream().map(SelectedProposal::proposalId).toList());
        assertEquals(first.selectionResult().selectedProposals(), second.selectionResult().selectedProposals());
        assertTrue(first.selectionResult().selectedProposals().stream().noneMatch(selected -> selected.proposalId().equals("proposal-b")));
    }

    @Test
    void scarceBundlingPrefersLargerCleanBundleWhenPairsWouldBlockCoverage() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                SelectorTestFixtures.envelope("proposal-big", "bundle-big", "driver-1", List.of("order-1", "order-2", "order-3", "order-4"), 0.82, 0.82, 0.86, 6.0, true),
                SelectorTestFixtures.envelope("proposal-pair-a", "bundle-pair-a", "driver-1", List.of("order-1", "order-2"), 0.90, 0.90, 0.98, 4.0, true),
                SelectorTestFixtures.envelope("proposal-pair-b", "bundle-pair-b", "driver-2", List.of("order-3", "order-4"), 0.88, 0.88, 0.96, 5.0, true),
                SelectorTestFixtures.envelope("proposal-other", "bundle-other", "driver-2", List.of("order-5", "order-6"), 0.80, 0.80, 0.84, 4.0, true));
        ConflictGraph graph = new ConflictGraphBuilder().build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());
        GreedyRepairSelector selector = new GreedyRepairSelector();

        SelectorSelectionOutcome outcome = selector.select(candidates, graph, SelectionSolverMode.GREEDY_REPAIR, true);

        assertEquals(List.of("proposal-big", "proposal-other"), outcome.selectionResult().selectedProposals().stream().map(SelectedProposal::proposalId).toList());
        assertTrue(outcome.selectionResult().degradeReasons().contains("scarce-bundling-priority-enabled"));
        assertTrue(outcome.selectionResult().selectedProposals().stream()
                .filter(selected -> selected.proposalId().equals("proposal-big"))
                .findFirst()
                .orElseThrow()
                .reasons()
                .contains("selected-by-scarce-bundling-greedy-pass"));
    }
}
