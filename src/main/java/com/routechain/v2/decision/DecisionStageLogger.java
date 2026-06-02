package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DecisionStageLogger {
    private final boolean enabled;
    private final Path baseDirectory;
    private final ObjectMapper objectMapper;

    public DecisionStageLogger(RouteChainDispatchV2Properties properties) {
        this.enabled = properties.getFeedback().isDecisionLogEnabled();
        this.baseDirectory = Path.of(properties.getFeedback().getBaseDir()).resolve("decision-stage");
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
    }

    public void writeFamily(String family, String traceId, String stageKey, Object payload) {
        if (!enabled || traceId == null || traceId.isBlank()) {
            return;
        }
        try {
            String safeFamily = safePathPart(family, 64);
            Files.createDirectories(baseDirectory.resolve(safeFamily));
            String suffix = stageKey == null || stageKey.isBlank() ? "" : "-" + safePathPart(stageKey, 72);
            Path file = baseDirectory.resolve(safeFamily)
                    .resolve(safePathPart(traceId, 72) + suffix + ".json");
            objectMapper.writeValue(file.toFile(), payload);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to write decision trace family " + family, exception);
        }
    }

    private String safePathPart(String raw, int maxLength) {
        String sanitized = raw == null || raw.isBlank()
                ? "unknown"
                : raw.replaceAll("[^a-zA-Z0-9._-]", "_");
        if (sanitized.length() <= maxLength) {
            return sanitized;
        }
        String hash = Integer.toHexString(raw.hashCode());
        int prefixLength = Math.max(8, maxLength - hash.length() - 1);
        return sanitized.substring(0, Math.min(prefixLength, sanitized.length())) + "-" + hash;
    }
}
