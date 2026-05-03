package com.routechain.v2.benchmark;

import java.util.List;
import java.util.Locale;

public enum DispatchBenchmarkDecisionMode {
    LEGACY("legacy", "legacy", List.of());

    private final String wireName;
    private final String runtimeMode;
    private final List<String> authoritativeStages;

    DispatchBenchmarkDecisionMode(String wireName, String runtimeMode, List<String> authoritativeStages) {
        this.wireName = wireName;
        this.runtimeMode = runtimeMode;
        this.authoritativeStages = List.copyOf(authoritativeStages);
    }

    public String wireName() {
        return wireName;
    }

    public String runtimeMode() {
        return runtimeMode;
    }

    public List<String> authoritativeStages() {
        return authoritativeStages;
    }

    public static DispatchBenchmarkDecisionMode fromWire(String rawValue) {
        if (rawValue == null || rawValue.isBlank()) {
            return LEGACY;
        }
        String normalized = rawValue.trim().toLowerCase(Locale.ROOT);
        for (DispatchBenchmarkDecisionMode value : values()) {
            if (value.wireName.equals(normalized)) {
                return value;
            }
        }
        if (normalized.startsWith("llm") || "hybrid".equals(normalized)) {
            throw new IllegalArgumentException("LLM decision mode is disabled by policy: " + rawValue);
        }
        throw new IllegalArgumentException("Unknown decision mode: " + rawValue);
    }
}
