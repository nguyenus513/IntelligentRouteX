package com.routechain.v2.harvest;

import java.time.Instant;
import java.util.Map;

public record HarvestRuntimeMetadata(
        String commitSha,
        String machineClass,
        Instant generatedAt,
        Map<String, Object> sourceConfig) {
}
