package com.routechain.v2.mladaptive;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public final class AdaptiveLearningStateStore {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public void load(AdaptiveLearningState state, String statePath) {
        if (state == null || statePath == null || statePath.isBlank()) {
            return;
        }
        Path path = Path.of(statePath);
        if (!Files.exists(path)) {
            return;
        }
        try {
            Map<String, Object> root = MAPPER.readValue(path.toFile(), new TypeReference<>() { });
            state.replace(numberMap(root.get("seedRewards")), numberMap(root.get("operatorRewards")), numberMap(root.get("movePatternRewards")));
        } catch (IOException ignored) {
            // Keep in-memory defaults if persisted state is unreadable.
        }
    }

    public void save(AdaptiveLearningState state, String statePath) {
        if (state == null || statePath == null || statePath.isBlank()) {
            return;
        }
        Path path = Path.of(statePath);
        try {
            if (path.getParent() != null) {
                Files.createDirectories(path.getParent());
            }
            Map<String, Object> root = new LinkedHashMap<>();
            root.put("version", "v1");
            root.put("updatedAt", Instant.now().toString());
            root.put("seedRewards", state.seedRewards());
            root.put("operatorRewards", state.operatorRewards());
            root.put("movePatternRewards", state.movePatternRewards());
            MAPPER.writerWithDefaultPrettyPrinter().writeValue(path.toFile(), root);
        } catch (IOException ignored) {
            // Persistence must never break dispatch.
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Double> numberMap(Object value) {
        Map<String, Double> result = new LinkedHashMap<>();
        if (!(value instanceof Map<?, ?> map)) {
            return result;
        }
        map.forEach((key, raw) -> {
            if (key != null && raw instanceof Number number) {
                result.put(String.valueOf(key), number.doubleValue());
            }
        });
        return result;
    }
}
