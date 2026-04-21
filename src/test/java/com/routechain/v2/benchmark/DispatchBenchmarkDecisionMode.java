package com.routechain.v2.benchmark;

import com.routechain.v2.decision.DecisionStageName;

import java.util.List;
import java.util.Locale;

public enum DispatchBenchmarkDecisionMode {
    LEGACY("legacy", "legacy", List.of()),
    LLM_SHADOW("llm-shadow", "llm-shadow", List.of()),
    LLM_AUTHORITATIVE("llm-authoritative", "llm-authoritative", List.of(
            DecisionStageName.PAIR_BUNDLE.wireName(),
            DecisionStageName.DRIVER.wireName(),
            DecisionStageName.ROUTE_CRITIQUE.wireName(),
            DecisionStageName.SCENARIO.wireName(),
            DecisionStageName.FINAL_SELECTION.wireName()));

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
        throw new IllegalArgumentException("Unknown decision mode: " + rawValue);
    }
}
