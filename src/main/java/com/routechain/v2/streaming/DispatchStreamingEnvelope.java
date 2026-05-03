package com.routechain.v2.streaming;

import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.SchemaVersioned;

import java.time.Instant;
import java.util.Map;

public record DispatchStreamingEnvelope(
        String schemaVersion,
        String eventId,
        String regionKey,
        Instant occurredAt,
        DispatchV2Request request,
        Map<String, String> attributes) implements SchemaVersioned {

    public DispatchStreamingEnvelope {
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
