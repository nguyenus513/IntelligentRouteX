package com.routechain.v2.mladaptive;

public record AdaptiveMlPolicyConfig(
        boolean enabled,
        AdaptiveMlPolicyMode requestedMode,
        int topKMoves,
        double explorationRate,
        boolean updateRewards,
        boolean persistenceEnabled,
        String statePath,
        int qualityBudgetMs) {

    public static AdaptiveMlPolicyConfig diagnostic() {
        return new AdaptiveMlPolicyConfig(true, AdaptiveMlPolicyMode.DIAGNOSTIC, 30, 0.10, true, false, "artifacts/adaptive-ml/adaptive-learning-state.json", 0);
    }

    public AdaptiveMlPolicyMode effectiveMode() {
        if (!enabled || requestedMode == AdaptiveMlPolicyMode.OFF) {
            return AdaptiveMlPolicyMode.OFF;
        }
        return requestedMode == null ? AdaptiveMlPolicyMode.DIAGNOSTIC : requestedMode;
    }

    public boolean assistedControl() {
        AdaptiveMlPolicyMode mode = effectiveMode();
        return mode == AdaptiveMlPolicyMode.TOP_K_ASSISTED || mode == AdaptiveMlPolicyMode.QUALITY_SEEKING;
    }

    public boolean qualitySeeking() {
        return effectiveMode() == AdaptiveMlPolicyMode.QUALITY_SEEKING;
    }
}
