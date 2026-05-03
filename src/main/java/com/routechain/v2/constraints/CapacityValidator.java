package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;
import java.util.Map;

public final class CapacityValidator {
    private static final int DEFAULT_MAX_ORDERS_PER_CANDIDATE = 4;

    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (candidate.orderIds().size() > DEFAULT_MAX_ORDERS_PER_CANDIDATE) {
            return List.of(ConstraintViolation.withEvidence(
                    "capacity-exceeded",
                    candidate.proposalId(),
                    "candidate exceeds max orders per route",
                    Map.of("maxOrders", DEFAULT_MAX_ORDERS_PER_CANDIDATE, "actualOrders", candidate.orderIds().size())));
        }
        return List.of();
    }
}
