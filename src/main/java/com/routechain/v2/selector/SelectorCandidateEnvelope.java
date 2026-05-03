package com.routechain.v2.selector;

public record SelectorCandidateEnvelope(
        SelectorCandidate candidate,
        double projectedPickupEtaMinutes) {
}
