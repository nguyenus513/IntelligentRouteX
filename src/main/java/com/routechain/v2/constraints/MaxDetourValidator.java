package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class MaxDetourValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "max-detour-exceeded")) {
            return List.of(ConstraintViolation.candidate("max-detour-exceeded", candidate.proposalId(), "max-detour-exceeded"));
        }
        return List.of();
    }
}
