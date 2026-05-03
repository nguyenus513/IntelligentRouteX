package com.routechain.v2.constraints;

import com.routechain.v2.selector.SelectorCandidate;

final class CandidateConstraintSupport {
    private CandidateConstraintSupport() {
    }

    static boolean hasSignal(SelectorCandidate candidate, String signal) {
        return candidate.degradeReasons().contains(signal) || candidate.reasons().contains(signal);
    }
}
