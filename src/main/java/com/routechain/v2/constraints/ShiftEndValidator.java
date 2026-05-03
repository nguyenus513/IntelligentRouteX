package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class ShiftEndValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "shift-end-exceeded")) {
            return List.of(ConstraintViolation.candidate("shift-end-exceeded", candidate.proposalId(), "shift-end-exceeded"));
        }
        return List.of();
    }
}
