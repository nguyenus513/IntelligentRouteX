package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class ActiveRouteCommitmentValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "active-route-commitment-violation")) {
            return List.of(ConstraintViolation.candidate("active-route-commitment-violation", candidate.proposalId(), "active-route-commitment-violation"));
        }
        return List.of();
    }
}
