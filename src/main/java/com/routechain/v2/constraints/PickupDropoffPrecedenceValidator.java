package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class PickupDropoffPrecedenceValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (candidate.orderIds() == null || candidate.orderIds().isEmpty()) {
            return List.of(ConstraintViolation.candidate("empty-order-set", candidate.proposalId(), "candidate has no covered orders"));
        }
        if (CandidateConstraintSupport.hasSignal(candidate, "pickup-before-dropoff-violation")) {
            return List.of(ConstraintViolation.candidate("pickup-before-dropoff-violation", candidate.proposalId(), "pickup/dropoff precedence violated"));
        }
        return List.of();
    }
}
