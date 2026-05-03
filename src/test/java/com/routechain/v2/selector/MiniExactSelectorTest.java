package com.routechain.v2.selector;

import com.routechain.v2.route.RouteProposalSource;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MiniExactSelectorTest {

    private final ConflictGraphBuilder conflictGraphBuilder = new ConflictGraphBuilder();
    private final MiniExactSelector selector = new MiniExactSelector();

    @Test
    void selectsBestNonConflictingCombinationExactly() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                envelope(candidate("single-a", "bundle-a", "driver-a", List.of("order-a"), 0.62, RouteProposalSource.HEURISTIC_FAST)),
                envelope(candidate("active-ab", "route-a", "driver-a", List.of("order-a", "order-b"), 0.92, RouteProposalSource.ACTIVE_ROUTE_INSERTION)),
                envelope(candidate("single-c", "bundle-c", "driver-c", List.of("order-c"), 0.55, RouteProposalSource.HEURISTIC_FAST)));
        ConflictGraph conflictGraph = conflictGraphBuilder.build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());

        SelectorSelectionOutcome outcome = selector.select(candidates, conflictGraph);

        assertEquals(2, outcome.selectionResult().selectedCount());
        assertEquals(List.of("active-ab", "single-c"), outcome.selectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .sorted()
                .toList());
        assertEquals(SelectionSolverMode.MINI_EXACT, outcome.selectionResult().solverMode());
        assertTrue(outcome.selectionResult().degradeReasons().contains("mini-exact-selector-applied"));
    }

    @Test
    void excludesInfeasibleActiveInsertion() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                envelope(candidate("active-bad", "route-a", "driver-a", List.of("order-a", "order-b"), 0.99, RouteProposalSource.ACTIVE_ROUTE_INSERTION, false)),
                envelope(candidate("single-a", "bundle-a", "driver-a", List.of("order-a"), 0.62, RouteProposalSource.HEURISTIC_FAST)));
        ConflictGraph conflictGraph = conflictGraphBuilder.build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());

        SelectorSelectionOutcome outcome = selector.select(candidates, conflictGraph);

        assertEquals(List.of("single-a"), outcome.selectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .toList());
    }

    @Test
    void keepsOnlyOneMutationPerActiveRoute() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                envelope(candidate("active-a", "active-route-1", "driver-a", List.of("order-a"), 0.91, RouteProposalSource.ACTIVE_ROUTE_INSERTION)),
                envelope(candidate("active-b", "active-route-1", "driver-b", List.of("order-b"), 0.90, RouteProposalSource.ACTIVE_ROUTE_INSERTION)),
                envelope(candidate("single-c", "bundle-c", "driver-c", List.of("order-c"), 0.55, RouteProposalSource.HEURISTIC_FAST)));
        ConflictGraph conflictGraph = conflictGraphBuilder.build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());

        SelectorSelectionOutcome outcome = selector.select(candidates, conflictGraph);

        assertEquals(2, outcome.selectionResult().selectedCount());
        assertTrue(outcome.selectionResult().selectedProposals().stream().map(SelectedProposal::proposalId).toList().contains("single-c"));
        assertEquals(1, outcome.selectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .filter(proposalId -> proposalId.startsWith("active-"))
                .count());
    }

    @Test
    void usesUnifiedObjectiveInsteadOfRawScoreOnly() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                envelope(candidate("high-risk", "bundle-risk", "driver-a", List.of("order-a"), 0.95, RouteProposalSource.HEURISTIC_FAST, true, List.of(), List.of("food-on-vehicle-hard-limit"))),
                envelope(candidate("lower-safe", "bundle-safe", "driver-b", List.of("order-a"), 0.86, RouteProposalSource.HEURISTIC_FAST)));
        ConflictGraph conflictGraph = conflictGraphBuilder.build(candidates.stream().map(SelectorCandidateEnvelope::candidate).toList());

        SelectorSelectionOutcome outcome = selector.select(candidates, conflictGraph);

        assertEquals(List.of("lower-safe"), outcome.selectionResult().selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .toList());
        assertTrue(outcome.selectionResult().objectiveValue() > 0.0);
    }

    private SelectorCandidateEnvelope envelope(SelectorCandidate candidate) {
        return new SelectorCandidateEnvelope(candidate, 3.0);
    }

    private SelectorCandidate candidate(String proposalId,
                                        String bundleId,
                                        String driverId,
                                        List<String> orderIds,
                                        double score,
                                        RouteProposalSource source) {
        return candidate(proposalId, bundleId, driverId, orderIds, score, source, true);
    }

    private SelectorCandidate candidate(String proposalId,
                                        String bundleId,
                                        String driverId,
                                        List<String> orderIds,
                                        double score,
                                        RouteProposalSource source,
                                        boolean feasible) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                bundleId,
                orderIds.getFirst(),
                driverId,
                orderIds,
                score,
                score,
                source,
                source == RouteProposalSource.ACTIVE_ROUTE_INSERTION ? "active-route:" + bundleId : "cluster-1",
                false,
                score,
                feasible,
                List.of(),
                List.of());
    }

    private SelectorCandidate candidate(String proposalId,
                                        String bundleId,
                                        String driverId,
                                        List<String> orderIds,
                                        double score,
                                        RouteProposalSource source,
                                        boolean feasible,
                                        List<String> reasons,
                                        List<String> degradeReasons) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                bundleId,
                orderIds.getFirst(),
                driverId,
                orderIds,
                score,
                score,
                source,
                bundleId,
                false,
                score,
                feasible,
                reasons,
                degradeReasons);
    }
}
