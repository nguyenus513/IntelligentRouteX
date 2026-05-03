package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

import java.util.ArrayList;
import java.util.List;

public final class FeasibilityOracle {
    private final PickupDropoffPrecedenceValidator pickupDropoffPrecedenceValidator = new PickupDropoffPrecedenceValidator();
    private final FrozenPrefixValidator frozenPrefixValidator = new FrozenPrefixValidator();
    private final FoodFreshnessValidator foodFreshnessValidator = new FoodFreshnessValidator();
    private final CapacityValidator capacityValidator = new CapacityValidator();
    private final RouteChurnValidator routeChurnValidator = new RouteChurnValidator();
    private final ReadyTimeValidator readyTimeValidator = new ReadyTimeValidator();
    private final TimeWindowValidator timeWindowValidator = new TimeWindowValidator();
    private final MaxDetourValidator maxDetourValidator = new MaxDetourValidator();
    private final DriverAvailabilityValidator driverAvailabilityValidator = new DriverAvailabilityValidator();
    private final ShiftEndValidator shiftEndValidator = new ShiftEndValidator();
    private final ActiveRouteCommitmentValidator activeRouteCommitmentValidator = new ActiveRouteCommitmentValidator();
    private final FoodOnVehicleDurationValidator foodOnVehicleDurationValidator = new FoodOnVehicleDurationValidator();

    public ConstraintCheckResult check(SelectorCandidate candidate) {
        List<ConstraintViolation> violations = new ArrayList<>();
        if (!candidate.feasible()) {
            violations.add(ConstraintViolation.candidate("candidate-marked-infeasible", candidate.proposalId(), "candidate marked infeasible upstream"));
        }
        violations.addAll(pickupDropoffPrecedenceValidator.validate(candidate));
        violations.addAll(frozenPrefixValidator.validate(candidate));
        violations.addAll(foodFreshnessValidator.validate(candidate));
        violations.addAll(capacityValidator.validate(candidate));
        violations.addAll(routeChurnValidator.validate(candidate));
        violations.addAll(readyTimeValidator.validate(candidate));
        violations.addAll(timeWindowValidator.validate(candidate));
        violations.addAll(maxDetourValidator.validate(candidate));
        violations.addAll(driverAvailabilityValidator.validate(candidate));
        violations.addAll(shiftEndValidator.validate(candidate));
        violations.addAll(activeRouteCommitmentValidator.validate(candidate));
        violations.addAll(foodOnVehicleDurationValidator.validate(candidate));
        if (violations.isEmpty()) {
            return ConstraintCheckResult.ok();
        }
        return ConstraintCheckResult.infeasible(violations);
    }

    public List<SelectorCandidate> feasibleCandidates(List<SelectorCandidate> candidates) {
        return candidates.stream()
                .filter(candidate -> check(candidate).feasible())
                .toList();
    }
}
