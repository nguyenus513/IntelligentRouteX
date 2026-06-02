package com.routechain.api.bigdata;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LiveExternalSeedOrchestratorTest {

    @Test
    void live_cycle_attempts_vroom_and_pyvrp_even_when_runtimes_are_missing() {
        BigDataLiteCoreProperties properties = new BigDataLiteCoreProperties();
        properties.setSyntheticDriverCount(3);
        LiveExternalSeedOrchestrator orchestrator = new LiveExternalSeedOrchestrator(new BigDataDispatchInputMapper(properties));

        LiveExternalSeedOrchestrator.Result result = orchestrator.run(
                "LIVE-CYC-TEST",
                "R1",
                List.of(order("O1", 10.75, 106.67), order("O2", 10.751, 106.671)),
                true,
                true,
                false,
                200);

        assertTrue(result.enabled());
        assertTrue(result.required());
        assertFalse(result.strict());
        assertTrue(result.requirementPassed());
        assertTrue(result.vroom().attempted());
        assertTrue(result.pyvrp().attempted());
        assertEquals(2, result.orderCount());
        assertTrue(result.driverCount() > 0);
        assertNotNull(result.asMap().get("vroom"));
        assertNotNull(result.asMap().get("pyvrp"));
    }

    @Test
    void strict_required_mode_fails_when_external_seed_is_disabled() {
        BigDataLiteCoreProperties properties = new BigDataLiteCoreProperties();
        LiveExternalSeedOrchestrator orchestrator = new LiveExternalSeedOrchestrator(new BigDataDispatchInputMapper(properties));

        LiveExternalSeedOrchestrator.Result result = orchestrator.run(
                "LIVE-CYC-STRICT",
                "R1",
                List.of(order("O1", 10.75, 106.67)),
                false,
                true,
                true,
                200);

        assertFalse(result.vroom().attempted());
        assertFalse(result.pyvrp().attempted());
        assertFalse(result.requirementPassed());
        assertTrue(result.evidenceGapReason().contains("live-external-seed-disabled"));
    }

    private Map<String, Object> order(String id, double lat, double lng) {
        return Map.of(
                "externalOrderId", id,
                "regionId", "R1",
                "pickupLat", lat,
                "pickupLng", lng,
                "dropoffLat", lat + 0.01,
                "dropoffLng", lng + 0.01,
                "placedAtMs", Instant.now().minusSeconds(60).toEpochMilli(),
                "promisedEtaMinutes", 45);
    }
}
