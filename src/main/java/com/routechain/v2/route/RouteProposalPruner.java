package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RouteProposalPruner {
    private final RouteChainDispatchV2Properties properties;

    public RouteProposalPruner(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public List<RouteProposalCandidate> prune(List<RouteProposalCandidate> candidates) {
        return candidates.stream()
                .collect(java.util.stream.Collectors.groupingBy(RouteProposalCandidate::tupleKey, LinkedHashMap::new, java.util.stream.Collectors.toList()))
                .values().stream()
                .flatMap(tupleCandidates -> pruneTuple(tupleCandidates).stream())
                .sorted(comparator())
                .toList();
    }

    Comparator<RouteProposalCandidate> comparator() {
        return Comparator.comparingDouble((RouteProposalCandidate candidate) -> candidate.proposal().routeValue()).reversed()
                .thenComparingDouble(candidate -> candidate.proposal().projectedPickupEtaMinutes())
                .thenComparing(candidate -> candidate.proposal().proposalId());
    }

    private List<RouteProposalCandidate> pruneTuple(List<RouteProposalCandidate> tupleCandidates) {
        List<RouteProposalCandidate> shapePruned = removeShapeDominated(tupleCandidates.stream()
                .filter(candidate -> candidate.proposal().feasible())
                .toList());
        Map<String, RouteProposalCandidate> deduped = new LinkedHashMap<>();
        for (RouteProposalCandidate candidate : shapePruned.stream()
                .sorted(comparator())
                .toList()) {
            String dedupeKey = candidate.proposal().source().name() + "|" + RouteProposalEngine.stopOrderSignature(candidate.proposal().stopOrder());
            deduped.putIfAbsent(dedupeKey, candidate);
        }
        return deduped.values().stream()
                .sorted(comparator())
                .limit(Math.max(1, properties.getCandidate().getMaxRouteAlternatives()))
                .toList();
    }

    private List<RouteProposalCandidate> removeShapeDominated(List<RouteProposalCandidate> candidates) {
        return candidates.stream()
                .filter(candidate -> candidates.stream()
                        .filter(other -> other != candidate)
                        .noneMatch(other -> RouteShapeQuality.dominates(other.proposal(), candidate.proposal())))
                .toList();
    }
}
