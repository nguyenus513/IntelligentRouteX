package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MutableSuffixAlnsTest {
    private final MutableSuffixAlns alns = new MutableSuffixAlns();

    @Test
    void preservesInsertedOrderAndAvoidsDuplicates() {
        RepairSolution solution = alns.improve(candidate(List.of("o0", "o1", "o2", "o3"), "o2", 0.60), Duration.ofMillis(100));

        assertTrue(solution.feasible());
        assertTrue(solution.candidate().newStopOrder().contains("o2"));
        assertEquals(solution.candidate().newStopOrder().size(), solution.candidate().newStopOrder().stream().distinct().count());
    }

    @Test
    void recordsDestroyAndReinsertionTrace() {
        RepairSolution solution = alns.improve(candidate(List.of("o0", "o1", "o2", "o3"), "o2", 0.60), Duration.ofMillis(100));

        assertTrue(solution.reasons().stream().anyMatch(reason -> reason.contains("removal")));
        assertTrue(solution.reasons().stream().anyMatch(reason -> reason.contains("reinsertion")));
    }

    @Test
    void improvesScoreWhenSuffixCanBeReordered() {
        RepairSolution solution = alns.improve(candidate(List.of("o0", "o1", "o2", "o3"), "o2", 0.60), Duration.ofMillis(100));

        assertTrue(solution.score() >= 0.60);
    }

    private ActiveRouteInsertionCandidate candidate(List<String> stopOrder, String insertedOrderId, double score) {
        return new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                "candidate-" + insertedOrderId,
                "route-1",
                "driver-1",
                insertedOrderId,
                1,
                stopOrder,
                3.0,
                12.0,
                4.0,
                0.1,
                0.1,
                0.1,
                score,
                true,
                List.of("active-route-regret-insertion"),
                List.of());
    }
}
