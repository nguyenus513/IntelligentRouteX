package com.routechain.v2.streaming;

import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.SchemaVersioned;

import java.time.Instant;
import java.util.Map;

public record DispatchStreamingResultEnvelope(
        String schemaVersion,
        String eventId,
        String traceId,
        String regionKey,
        Instant completedAt,
        DispatchV2Result result,
        Map<String, String> attributes) implements SchemaVersioned {

    public DispatchStreamingResultEnvelope {
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
