package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;
import java.util.Map;

public final class CapacityValidator {
    private static final int DEFAULT_MAX_ORDERS_PER_CANDIDATE = 4;
    private static final String MAX_ORDERS_ENV = "IRX_MAX_ORDERS_PER_ROUTE";

    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        int maxOrders = maxOrdersPerCandidate();
        if (candidate.orderIds().size() > maxOrders) {
            return List.of(ConstraintViolation.withEvidence(
                    "capacity-exceeded",
                    candidate.proposalId(),
                    "candidate exceeds max orders per route",
                    Map.of("maxOrders", maxOrders, "actualOrders", candidate.orderIds().size())));
        }
        return List.of();
    }

    private static int maxOrdersPerCandidate() {
        String configured = System.getenv(MAX_ORDERS_ENV);
        if (configured == null || configured.isBlank()) {
            configured = System.getProperty("routechain.dispatch-v2.constraints.max-orders-per-route");
        }
        if (configured == null || configured.isBlank()) {
            return DEFAULT_MAX_ORDERS_PER_CANDIDATE;
        }
        try {
            return Math.max(1, Integer.parseInt(configured.trim()));
        } catch (NumberFormatException ignored) {
            return DEFAULT_MAX_ORDERS_PER_CANDIDATE;
        }
    }
}
