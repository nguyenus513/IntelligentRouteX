package com.routechain.v2.selector;

import com.routechain.v2.route.RouteProposalSource;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HybridCandidatePoolBuilderTest {

    private final HybridCandidatePoolBuilder builder = new HybridCandidatePoolBuilder();

    @Test
    void dedupesBySignatureAndKeepsBetterCandidate() {
        SelectorCandidateEnvelope low = envelope(candidate("p-low", 0.50, RouteProposalSource.HEURISTIC_FAST));
        SelectorCandidateEnvelope high = envelope(candidate("p-high", 0.90, RouteProposalSource.HEURISTIC_FAST));

        HybridCandidatePoolResult result = builder.build(List.of(low, high), List.of());

        assertEquals(1, result.candidateEnvelopes().size());
        assertEquals("p-high", result.candidateEnvelopes().getFirst().candidate().proposalId());
        assertTrue(result.degradeReasons().contains("hybrid-candidate-pool-deduped"));
    }

    @Test
    void preservesActiveInsertionSourceAndNormalizesReasons() {
        SelectorCandidateEnvelope active = envelope(candidate("active-1", 0.80, RouteProposalSource.ACTIVE_ROUTE_INSERTION));

        HybridCandidatePoolResult result = builder.build(List.of(), List.of(active));

        assertEquals(1, result.sourceCounts().get(RouteProposalSource.ACTIVE_ROUTE_INSERTION));
        assertTrue(result.degradeReasons().contains("hybrid-candidate-pool-active-insertion-present"));
        assertTrue(result.candidateEnvelopes().getFirst().candidate().reasons().contains("hybrid-candidate-pool-normalized"));
    }

    private SelectorCandidateEnvelope envelope(SelectorCandidate candidate) {
        return new SelectorCandidateEnvelope(candidate, 3.0);
    }

    private SelectorCandidate candidate(String proposalId, double score, RouteProposalSource source) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                proposalId,
                "bundle-1",
                "order-1",
                "driver-1",
                List.of("order-1", "order-2"),
                score,
                score,
                source,
                "cluster-1",
                false,
                score,
                true,
                List.of(),
                List.of());
    }
}
