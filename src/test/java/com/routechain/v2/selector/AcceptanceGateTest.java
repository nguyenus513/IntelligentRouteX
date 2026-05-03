package com.routechain.v2.selector;

import com.routechain.v2.route.RouteProposalSource;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AcceptanceGateTest {

    private final AcceptanceGate acceptanceGate = new AcceptanceGate();

    @Test
    void rejectsHardInfeasibleSelectedCandidate() {
        SelectorCandidateEnvelope bad = envelope(candidate("bad", false, List.of("order-1"), 0.9));

        AcceptanceGateResult result = acceptanceGate.evaluate(null, selection("bad", 0.9), List.of(bad));

        assertFalse(result.accepted());
        assertTrue(result.rejectedReasons().stream().anyMatch(reason -> reason.contains("candidate-marked-infeasible")));
    }

    @Test
    void rejectsObjectiveBelowIncumbent() {
        SelectorCandidateEnvelope low = envelope(candidate("low", true, List.of("order-1"), 0.7));

        AcceptanceGateResult result = acceptanceGate.evaluate(selection("incumbent", 1.0), selection("low", 0.7), List.of(low));

        assertFalse(result.accepted());
        assertTrue(result.rejectedReasons().contains("acceptance-objective-below-incumbent"));
    }

    @Test
    void acceptsFeasibleImprovement() {
        SelectorCandidateEnvelope improved = envelope(candidate("improved", true, List.of("order-1"), 1.2));

        AcceptanceGateResult result = acceptanceGate.evaluate(selection("incumbent", 1.0), selection("improved", 1.2), List.of(improved));

        assertTrue(result.accepted());
    }

    private GlobalSelectionResult selection(String proposalId, double objective) {
        return new GlobalSelectionResult(
                "global-selection-result/v1",
                List.of(new SelectedProposal("selected-proposal/v1", proposalId, 1, objective, List.of("test"))),
                1,
                1,
                SelectionSolverMode.GREEDY_REPAIR,
                objective,
                List.of());
    }

    private SelectorCandidateEnvelope envelope(SelectorCandidate candidate) {
        return new SelectorCandidateEnvelope(candidate, 1.0);
    }

    private SelectorCandidate candidate(String proposalId, boolean feasible, List<String> orderIds, double score) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                "bundle-" + proposalId,
                orderIds.getFirst(),
                "driver-" + proposalId,
                orderIds,
                score,
                score,
                RouteProposalSource.HEURISTIC_FAST,
                "cluster-" + proposalId,
                false,
                score,
                feasible,
                List.of(),
                List.of());
    }
}
