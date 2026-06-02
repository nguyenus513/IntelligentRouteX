package com.routechain.api.bigdata;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record BigDataLiteKafkaEnvelope(
        String schemaVersion,
        String eventId,
        String jobId,
        String batchId,
        String tenantId,
        String queue,
        String kind,
        int chunkIndex,
        int totalChunks,
        boolean forceFail,
        List<Map<String, Object>> items,
        Instant occurredAt,
        Map<String, String> attributes) {

    public BigDataLiteKafkaEnvelope {
        items = items == null ? List.of() : List.copyOf(items);
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
