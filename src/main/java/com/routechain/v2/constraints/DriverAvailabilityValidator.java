package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class DriverAvailabilityValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "driver-unavailable")) {
            return List.of(ConstraintViolation.candidate("driver-unavailable", candidate.proposalId(), "driver-unavailable"));
        }
        return List.of();
    }
}
