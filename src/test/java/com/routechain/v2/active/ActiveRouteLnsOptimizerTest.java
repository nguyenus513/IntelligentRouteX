package com.routechain.v2.active;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveRouteLnsOptimizerTest {

    @Test
    void retainsFeasibleCandidatesAndTagsReasons() {
        ActiveRouteLnsOptimizer optimizer = new ActiveRouteLnsOptimizer();

        ActiveRouteLnsRepairResult result = optimizer.improve(List.of(
                candidate("bad", 0.99, false),
                candidate("good", 0.80, true)));

        assertEquals(1, result.candidates().size());
        assertEquals("good", result.candidates().getFirst().candidateId());
        assertTrue(result.candidates().getFirst().reasons().contains("active-lns-bounded-repair-retained"));
        assertTrue(result.operatorNames().contains("bounded-regret-retain"));
    }

    private ActiveRouteInsertionCandidate candidate(String id, double score, boolean feasible) {
        return new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                id,
                "route-1",
                "driver-1",
                "order-1",
                0,
                List.of("order-1"),
                3.0,
                12.0,
                1.0,
                0.05,
                0.05,
                0.05,
                score,
                feasible,
                List.of(),
                List.of());
    }
}
