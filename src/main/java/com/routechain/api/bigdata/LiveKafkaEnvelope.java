package com.routechain.api.bigdata;

import java.time.Instant;
import java.util.Map;

public record LiveKafkaEnvelope(
        String schemaVersion,
        String eventId,
        String type,
        String tenantId,
        String regionId,
        String driverId,
        Instant occurredAt,
        Map<String, Object> payload) {

    public LiveKafkaEnvelope {
        payload = payload == null ? Map.of() : Map.copyOf(payload);
    }
}
