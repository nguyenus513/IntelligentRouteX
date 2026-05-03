package com.routechain.v2.selector;

import com.routechain.v2.route.RouteProposalSource;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SelectorPoolReducerTest {
    private final SelectorPoolReducer reducer = new SelectorPoolReducer();

    @Test
    void filtersInfeasibleCandidatesBeforeExactSelection() {
        SelectorPoolReductionResult result = reducer.reduce(List.of(
                envelope(candidate("bad", false, 0.99, RouteProposalSource.HEURISTIC_FAST)),
                envelope(candidate("good", true, 0.70, RouteProposalSource.HEURISTIC_FAST))));

        assertEquals(List.of("good"), result.retainedCandidates().stream()
                .map(envelope -> envelope.candidate().proposalId())
                .toList());
        assertTrue(result.reasons().contains("selector-pool-feasibility-filter-applied"));
        assertEquals(2, result.checkedCandidateCount());
        assertEquals(1, result.feasibleCandidateCount());
        assertEquals(1, result.violationCountsByCode().get("candidate-marked-infeasible"));
    }

    @Test
    void keepsSmallFeasiblePoolWithoutReduction() {
        SelectorPoolReductionResult result = reducer.reduce(List.of(
                envelope(candidate("a", true, 0.60, RouteProposalSource.HEURISTIC_FAST)),
                envelope(candidate("b", true, 0.70, RouteProposalSource.BEAUTY_CORRIDOR))));

        assertEquals(2, result.retainedCandidates().size());
        assertEquals(0, result.rejectedCandidateCount());
        assertFalse(result.retainedCandidates().isEmpty());
        assertFalse(result.poolCapApplied());
    }

    @Test
    void capsReducedPoolAndPreservesBestObjectiveCandidate() {
        SelectorPoolReductionResult result = reducer.reduce(List.of(
                envelope(candidate("top", true, 0.99, RouteProposalSource.HEURISTIC_FAST)),
                envelope(candidate("mid", true, 0.80, RouteProposalSource.HEURISTIC_SAFE)),
                envelope(candidate("low", true, 0.10, RouteProposalSource.BEAUTY_CORRIDOR))), 2);

        assertEquals(2, result.retainedCandidates().size());
        assertTrue(result.poolCapApplied());
        assertEquals(2, result.maxPoolSize());
        assertTrue(result.retainedCandidates().stream()
                .anyMatch(envelope -> envelope.candidate().proposalId().equals("top")));
        assertEquals(result.feasibleBestObjectiveUtility(), result.retainedBestObjectiveUtility(), 1e-9);
        assertTrue(result.reasons().contains("selector-pool-reduced-before-exact"));
    }

    @Test
    void preservesActiveRepairAndDriverDiversityWhenPoolIsCapped() {
        List<SelectorCandidateEnvelope> candidates = List.of(
                envelope(candidate("fast-a", true, 0.99, RouteProposalSource.HEURISTIC_FAST, "driver-a", "order-a")),
                envelope(candidate("fast-b", true, 0.98, RouteProposalSource.HEURISTIC_FAST, "driver-a", "order-b")),
                envelope(candidate("fast-c", true, 0.97, RouteProposalSource.HEURISTIC_FAST, "driver-a", "order-c")),
                envelope(candidate("ml-a", true, 0.92, RouteProposalSource.ML_PROPOSAL, "driver-b", "order-d")),
                envelope(candidate("routefinder-a", true, 0.91, RouteProposalSource.ML_REFINED, "driver-c", "order-e")),
                envelope(candidate("active-a", true, 0.70, RouteProposalSource.ACTIVE_ROUTE_INSERTION, "driver-d", "order-f")));

        SelectorPoolReductionResult result = reducer.reduce(candidates, 5);

        List<String> retainedIds = result.retainedCandidates().stream()
                .map(envelope -> envelope.candidate().proposalId())
                .toList();
        assertEquals(5, retainedIds.size());
        assertTrue(retainedIds.contains("active-a"));
        assertTrue(retainedIds.contains("ml-a"));
        assertTrue(retainedIds.contains("routefinder-a"));
    }

    private SelectorCandidateEnvelope envelope(SelectorCandidate candidate) {
        return new SelectorCandidateEnvelope(candidate, 1.0);
    }

    private SelectorCandidate candidate(String proposalId, boolean feasible, double score, RouteProposalSource source) {
        return candidate(proposalId, feasible, score, source, "driver-" + proposalId, "order-" + proposalId);
    }

    private SelectorCandidate candidate(String proposalId,
                                        boolean feasible,
                                        double score,
                                        RouteProposalSource source,
                                        String driverId,
                                        String orderId) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                "bundle-" + proposalId,
                orderId,
                driverId,
                List.of(orderId),
                score,
                score,
                source,
                "cluster-" + proposalId,
                false,
                score,
                feasible,
                List.of(),
                List.of());
    }
}
