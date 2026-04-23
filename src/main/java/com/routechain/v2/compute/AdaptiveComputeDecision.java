package com.routechain.v2.compute;

public enum AdaptiveComputeDecision {
    TABULAR_ONLY,
    LLM_PLUS_TABULAR,
    ESCALATE_GREEDRL,
    ESCALATE_ROUTEFINDER,
    ESCALATE_FORECAST
}
