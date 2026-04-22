package com.routechain.v2.harvest;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class HarvestEventEnvelopeTest {

    @Test
    void toMapIncludesContractFieldsAndPreservesNullPayloadValues() {
        HarvestEventEnvelope envelope = new HarvestEventEnvelope(
                "bronze-candidate-row/v1",
                "candidate",
                "observation",
                "DECISION_SAFE",
                "trace-1",
                "run-1",
                "tick-1",
                "pair-bundle",
                "bundle",
                "bundle-1",
                "bundle:bundle-1",
                Instant.parse("2026-04-23T00:00:00Z"),
                null,
                null,
                new LinkedHashMap<>(Map.of("source", "measured", "fallbackUsed", false)));
        envelope.payload().put("missingReason", null);

        Map<String, Object> row = envelope.toMap();

        assertEquals("observation", row.get("timeLayer"));
        assertEquals("DECISION_SAFE", row.get("antiLeakageClass"));
        assertEquals("bundle:bundle-1", row.get("candidateId"));
        assertEquals("measured", row.get("source"));
        assertEquals(false, row.get("fallbackUsed"));
        assertNull(row.get("missingReason"));
    }
}
