package com.routechain.v2.benchmark;

public enum BenchmarkMode {
    FAST_GATE,
    QUALITY_BENCHMARK;

    public static BenchmarkMode from(String value) {
        if (value == null || value.isBlank()) {
            return FAST_GATE;
        }
        try {
            return BenchmarkMode.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException ignored) {
            return FAST_GATE;
        }
    }

    public boolean quality() {
        return this == QUALITY_BENCHMARK;
    }
}
