package com.routechain.v2.harvest;

import com.routechain.v2.SchemaVersioned;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public record HarvestEventEnvelope(
        String schemaVersion,
        String rowType,
        String traceId,
        String runId,
        String tickId,
        String stageName,
        String entityType,
        String entityId,
        String candidateId,
        Instant observationTime,
        Instant decisionTime,
        Instant outcomeTime,
        Map<String, Object> payload) implements SchemaVersioned {

    public HarvestEventEnvelope {
        payload = payload == null ? Map.of() : new LinkedHashMap<>(payload);
    }

    public Map<String, Object> toMap() {
        LinkedHashMap<String, Object> row = new LinkedHashMap<>();
        row.put("schemaVersion", schemaVersion);
        row.put("rowType", rowType);
        row.put("traceId", traceId);
        row.put("runId", runId);
        row.put("tickId", tickId);
        row.put("stageName", stageName);
        row.put("entityType", entityType);
        row.put("entityId", entityId);
        row.put("candidateId", candidateId);
        row.put("observationTime", observationTime);
        row.put("decisionTime", decisionTime);
        row.put("outcomeTime", outcomeTime);
        row.putAll(payload);
        return row;
    }
}
