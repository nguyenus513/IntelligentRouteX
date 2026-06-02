package com.routechain.api.bigdata;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LivePdLnsPostSolverImproverGuardTest {

    @Test
    void pre_guard_pass_skips_repair_and_commits_core_incumbent() {
        LivePdLnsPostSolverImprover improver = new LivePdLnsPostSolverImprover();

        LivePdLnsPostSolverImprover.Result result = improver.improve(
                List.of(order("O1", false, 45), order("O2", false, 50)),
                List.of(Map.of("orderId", "O1"), Map.of("orderId", "O2")),
                20.0,
                18.0,
                "CORE_OR_TOOLS_VROOM_PYVRP_DEFAULT_SEED",
                0.05);

        assertTrue(result.accepted());
        assertTrue(result.safetyPassed());
        assertTrue(result.repairSkipped());
        assertFalse(result.rollbackApplied());
        assertEquals("pre-guard-pass-repair-skipped", result.reason());
        assertTrue((Boolean) result.asMap().get("repairSkipped"));
    }

    @Test
    void pre_guard_fail_runs_repair_then_post_guard_blocks_bad_commit() {
        LivePdLnsPostSolverImprover improver = new LivePdLnsPostSolverImprover();

        LivePdLnsPostSolverImprover.Result result = improver.improve(
                List.of(order("BAD", true, 0), order("O2", false, 50)),
                List.of(Map.of("orderId", "BAD"), Map.of("orderId", "O2")),
                20.0,
                18.0,
                "CORE_OR_TOOLS_VROOM_PYVRP_DEFAULT_SEED",
                0.50);

        assertFalse(result.accepted());
        assertFalse(result.safetyPassed());
        assertFalse(result.repairSkipped());
        assertEquals("post-guard-blocked-commit", result.reason());
        assertFalse((Boolean) ((Map<?, ?>) result.asMap().get("preGuard")).get("passed"));
        assertFalse((Boolean) ((Map<?, ?>) result.asMap().get("postGuard")).get("passed"));
    }

    private Map<String, Object> order(String id, boolean urgent, int eta) {
        return Map.of(
                "externalOrderId", id,
                "pickupLat", 10.75,
                "pickupLng", 106.67,
                "dropoffLat", 10.76,
                "dropoffLng", 106.68,
                "urgent", urgent,
                "promisedEtaMinutes", eta,
                "priority", urgent ? 10 : 1);
    }
}
