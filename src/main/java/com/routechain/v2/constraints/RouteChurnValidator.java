package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class RouteChurnValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "route-churn-limit-exceeded")) {
            return List.of(ConstraintViolation.candidate("route-churn-limit-exceeded", candidate.proposalId(), "route churn limit exceeded"));
        }
        return List.of();
    }
}
