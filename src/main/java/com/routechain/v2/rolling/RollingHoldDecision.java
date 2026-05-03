package com.routechain.v2.rolling;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record RollingHoldDecision(
        String schemaVersion,
        String orderId,
        RollingDecisionMode decisionMode,
        long holdSeconds,
        double confidence,
        double bundleOpportunityScore,
        double riskScore,
        List<String> reasonCodes) implements SchemaVersioned {

    public RollingHoldDecision {
        reasonCodes = reasonCodes == null ? List.of() : List.copyOf(reasonCodes);
    }
}
