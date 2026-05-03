package com.routechain.v2.decision;

public enum DecisionBrainType {
    LEGACY,
    LLM,
    STUDENT;

    public static DecisionBrainType fromMode(String rawMode) {
        if (rawMode == null || rawMode.isBlank()) {
            return LEGACY;
        }
        return switch (rawMode.trim().toLowerCase(java.util.Locale.ROOT)) {
            case "legacy" -> LEGACY;
            case "student" -> STUDENT;
            case "llm", "hybrid", "llm-shadow", "llm-authoritative" -> LLM;
            default -> LEGACY;
        };
    }
}
