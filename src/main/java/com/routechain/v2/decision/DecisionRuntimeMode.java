package com.routechain.v2.decision;

import java.util.Locale;

public enum DecisionRuntimeMode {
    LEGACY,
    LLM,
    LLM_SHADOW,
    LLM_AUTHORITATIVE,
    HYBRID,
    STUDENT;

    public static DecisionRuntimeMode fromMode(String rawMode) {
        if (rawMode == null || rawMode.isBlank()) {
            return LEGACY;
        }
        return switch (rawMode.trim().toLowerCase(Locale.ROOT)) {
            case "legacy" -> LEGACY;
            case "llm-shadow" -> LLM_SHADOW;
            case "llm-authoritative" -> LLM_AUTHORITATIVE;
            case "hybrid" -> HYBRID;
            case "student" -> STUDENT;
            case "llm" -> LLM;
            default -> LEGACY;
        };
    }
}
