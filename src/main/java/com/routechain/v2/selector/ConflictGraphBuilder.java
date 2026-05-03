package com.routechain.v2.selector;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class ConflictGraphBuilder {

    public ConflictGraph build(List<SelectorCandidate> selectorCandidates) {
        List<SelectorCandidate> sortedCandidates = selectorCandidates.stream()
                .sorted(Comparator.comparing(SelectorCandidate::proposalId))
                .toList();
        List<ConflictEdge> edges = new ArrayList<>();
        Set<String> seenEdges = new HashSet<>();
        for (int leftIndex = 0; leftIndex < sortedCandidates.size(); leftIndex++) {
            SelectorCandidate left = sortedCandidates.get(leftIndex);
            for (int rightIndex = leftIndex + 1; rightIndex < sortedCandidates.size(); rightIndex++) {
                SelectorCandidate right = sortedCandidates.get(rightIndex);
                if (left.driverId().equals(right.driverId())) {
                    addEdge(edges, seenEdges, left.proposalId(), right.proposalId(), ConflictReason.DRIVER_OVERLAP);
                }
                if (!java.util.Collections.disjoint(left.orderIds(), right.orderIds())) {
                    addEdge(edges, seenEdges, left.proposalId(), right.proposalId(), ConflictReason.ORDER_OVERLAP);
                }
                if (left.bundleId().equals(right.bundleId()) && !left.proposalId().equals(right.proposalId())) {
                    addEdge(edges, seenEdges, left.proposalId(), right.proposalId(), ConflictReason.BUNDLE_OVERLAP);
                }
                if (activeRouteMutationOverlap(left, right)) {
                    addEdge(edges, seenEdges, left.proposalId(), right.proposalId(), ConflictReason.ACTIVE_ROUTE_MUTATION_OVERLAP);
                }
            }
        }
        List<ConflictEdge> normalizedEdges = edges.stream()
                .sorted(Comparator
                        .comparing(ConflictEdge::leftProposalId)
                        .thenComparing(ConflictEdge::rightProposalId)
                        .thenComparing(ConflictEdge::reason))
                .toList();
        return new ConflictGraph("conflict-graph/v1", selectorCandidates.size(), normalizedEdges.size(), normalizedEdges);
    }

    private void addEdge(List<ConflictEdge> edges,
                         Set<String> seenEdges,
                         String proposalIdA,
                         String proposalIdB,
                         ConflictReason reason) {
        String leftProposalId = proposalIdA.compareTo(proposalIdB) <= 0 ? proposalIdA : proposalIdB;
        String rightProposalId = proposalIdA.compareTo(proposalIdB) <= 0 ? proposalIdB : proposalIdA;
        String key = leftProposalId + "|" + rightProposalId + "|" + reason.name();
        if (seenEdges.add(key)) {
            edges.add(new ConflictEdge(leftProposalId, rightProposalId, reason));
        }
    }

    private boolean activeRouteMutationOverlap(SelectorCandidate left, SelectorCandidate right) {
        if (left.source() != com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION
                || right.source() != com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION) {
            return false;
        }
        return left.clusterId() != null && left.clusterId().equals(right.clusterId());
    }
}
