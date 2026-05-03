package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class FoodOnVehicleDurationValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (CandidateConstraintSupport.hasSignal(candidate, "food-on-vehicle-max-exceeded")) {
            return List.of(ConstraintViolation.candidate("food-on-vehicle-max-exceeded", candidate.proposalId(), "food-on-vehicle-max-exceeded"));
        }
        return List.of();
    }
}
