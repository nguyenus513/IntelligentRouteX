package com.routechain.v2.optimizer;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidate;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AcceptanceGateTest {
    private final AcceptanceGate gate = new AcceptanceGate();

    @Test
    void acceptsFeasibleChallengerWhenIncumbentMissing() {
        assertTrue(gate.canReplace(null, candidate("challenger", 0.6, true)));
    }

    @Test
    void rejectsInfeasibleChallenger() {
        assertFalse(gate.canReplace(candidate("incumbent", 0.5, true), candidate("challenger", 0.9, false)));
    }

    @Test
    void requiresMinimumScoreImprovement() {
        assertFalse(gate.canReplace(candidate("incumbent", 0.80, true), candidate("tiny", 0.805, true)));
        assertTrue(gate.canReplace(candidate("incumbent", 0.80, true), candidate("better", 0.82, true)));
    }

    private SelectorCandidate candidate(String proposalId, double score, boolean feasible) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                "bundle-" + proposalId,
                "order-" + proposalId,
                "driver-" + proposalId,
                List.of("order-" + proposalId),
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
