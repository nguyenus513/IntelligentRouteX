package com.routechain.v2.mladaptive;

public enum AdaptiveMlPolicyMode {
    OFF,
    DIAGNOSTIC,
    TIE_BREAK,
    TOP_K_ASSISTED,
    QUALITY_SEEKING;

    public static AdaptiveMlPolicyMode from(String value) {
        if (value == null || value.isBlank()) {
            return DIAGNOSTIC;
        }
        try {
            return AdaptiveMlPolicyMode.valueOf(value.trim().toUpperCase().replace('-', '_'));
        } catch (IllegalArgumentException ignored) {
            return DIAGNOSTIC;
        }
    }
}
