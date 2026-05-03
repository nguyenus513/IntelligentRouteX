package com.routechain.v2.constraints;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;

public final class FrozenPrefixValidator {
    public List<ConstraintViolation> validate(SelectorCandidate candidate) {
        if (candidate.source() == RouteProposalSource.ACTIVE_ROUTE_INSERTION
                && CandidateConstraintSupport.hasSignal(candidate, "frozen-prefix-violation")) {
            return List.of(ConstraintViolation.candidate("frozen-prefix-mutated", candidate.proposalId(), "active route frozen prefix mutated"));
        }
        return List.of();
    }
}
