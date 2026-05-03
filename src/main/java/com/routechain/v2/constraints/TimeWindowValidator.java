package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class TimeWindowValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "delivery-window-violation")) {
            return List.of(ConstraintViolation.candidate("delivery-window-violation", candidate.proposalId(), "delivery-window-violation"));
        }
        return List.of();
    }
}
