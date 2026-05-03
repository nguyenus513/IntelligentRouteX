package com.routechain.v2.selector;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.route.RouteProposalSource;

import java.util.List;
import java.util.Map;

record HybridCandidatePoolResult(
        String schemaVersion,
        List<SelectorCandidateEnvelope> candidateEnvelopes,
        int inputCandidateCount,
        int retainedCandidateCount,
        int dedupedCandidateCount,
        Map<RouteProposalSource, Integer> sourceCounts,
        List<String> degradeReasons) implements SchemaVersioned {
}
