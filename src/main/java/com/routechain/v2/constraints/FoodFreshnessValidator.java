package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class FoodFreshnessValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "food-on-vehicle-hard-limit")) {
            return List.of(ConstraintViolation.candidate("food-on-vehicle-max-exceeded", candidate.proposalId(), "food on vehicle hard limit exceeded"));
        }
        return List.of();
    }
}
