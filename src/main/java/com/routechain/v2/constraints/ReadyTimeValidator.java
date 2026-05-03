package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class ReadyTimeValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "active-insertion-pickup-before-ready")) {
            return List.of(ConstraintViolation.candidate("pickup-before-ready-time", candidate.proposalId(), "pickup-before-ready-time"));
        }
        return List.of();
    }
}
