package com.routechain.v2.selector;

import com.routechain.v2.route.RouteProposalSource;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public final class HybridCandidatePoolBuilder {
    private static final int MAX_POOL_SIZE = 160;

    public HybridCandidatePoolResult build(List<SelectorCandidateEnvelope> baseCandidates,
                                           List<SelectorCandidateEnvelope> activeInsertionCandidates) {
        List<SelectorCandidateEnvelope> merged = new ArrayList<>();
        if (baseCandidates != null) {
            merged.addAll(baseCandidates);
        }
        if (activeInsertionCandidates != null) {
            merged.addAll(activeInsertionCandidates);
        }
        Map<String, SelectorCandidateEnvelope> bestBySignature = new LinkedHashMap<>();
        for (SelectorCandidateEnvelope envelope : merged) {
            if (envelope == null || envelope.candidate() == null) {
                continue;
            }
            SelectorCandidateEnvelope normalized = normalize(envelope);
            String signature = signature(normalized.candidate());
            SelectorCandidateEnvelope existing = bestBySignature.get(signature);
            if (existing == null || better(normalized, existing)) {
                bestBySignature.put(signature, normalized);
            }
        }
        List<SelectorCandidateEnvelope> retained = bestBySignature.values().stream()
                .sorted(poolComparator())
                .limit(MAX_POOL_SIZE)
                .toList();
        Map<RouteProposalSource, Integer> sourceCounts = retained.stream()
                .collect(Collectors.groupingBy(
                        envelope -> envelope.candidate().source(),
                        () -> new EnumMap<>(RouteProposalSource.class),
                        Collectors.collectingAndThen(Collectors.counting(), Long::intValue)));
        List<String> degradeReasons = new ArrayList<>();
        if (merged.size() > bestBySignature.size()) {
            degradeReasons.add("hybrid-candidate-pool-deduped");
        }
        if (bestBySignature.size() > retained.size()) {
            degradeReasons.add("hybrid-candidate-pool-cap-applied");
        }
        if (sourceCounts.containsKey(RouteProposalSource.ACTIVE_ROUTE_INSERTION)) {
            degradeReasons.add("hybrid-candidate-pool-active-insertion-present");
        }
        return new HybridCandidatePoolResult(
                "hybrid-candidate-pool-result/v1",
                retained,
                merged.size(),
                retained.size(),
                Math.max(0, merged.size() - bestBySignature.size()),
                Map.copyOf(sourceCounts),
                degradeReasons.stream().distinct().toList());
    }

    private SelectorCandidateEnvelope normalize(SelectorCandidateEnvelope envelope) {
        SelectorCandidate candidate = envelope.candidate();
        List<String> reasons = new ArrayList<>(candidate.reasons());
        reasons.add("hybrid-candidate-pool-normalized");
        SelectorCandidate normalized = new SelectorCandidate(
                candidate.schemaVersion(),
                candidate.proposalId(),
                candidate.bundleId(),
                candidate.anchorOrderId(),
                candidate.driverId(),
                candidate.orderIds().stream().distinct().sorted().toList(),
                candidate.robustUtility(),
                candidate.routeValue(),
                candidate.source(),
                candidate.clusterId(),
                candidate.boundaryCross(),
                candidate.selectionScore(),
                candidate.feasible(),
                reasons.stream().distinct().toList(),
                candidate.degradeReasons());
        return new SelectorCandidateEnvelope(normalized, envelope.projectedPickupEtaMinutes());
    }

    private boolean better(SelectorCandidateEnvelope candidate, SelectorCandidateEnvelope existing) {
        if (candidate.candidate().feasible() != existing.candidate().feasible()) {
            return candidate.candidate().feasible();
        }
        if (candidate.candidate().selectionScore() != existing.candidate().selectionScore()) {
            return candidate.candidate().selectionScore() > existing.candidate().selectionScore();
        }
        if (candidate.candidate().robustUtility() != existing.candidate().robustUtility()) {
            return candidate.candidate().robustUtility() > existing.candidate().robustUtility();
        }
        if (candidate.projectedPickupEtaMinutes() != existing.projectedPickupEtaMinutes()) {
            return candidate.projectedPickupEtaMinutes() < existing.projectedPickupEtaMinutes();
        }
        return candidate.candidate().proposalId().compareTo(existing.candidate().proposalId()) < 0;
    }

    private Comparator<SelectorCandidateEnvelope> poolComparator() {
        return Comparator
                .comparing((SelectorCandidateEnvelope envelope) -> envelope.candidate().source() != RouteProposalSource.ACTIVE_ROUTE_INSERTION)
                .thenComparing(SelectorCandidateRanking.comparator());
    }

    private String signature(SelectorCandidate candidate) {
        return candidate.source()
                + "|" + candidate.driverId()
                + "|" + candidate.bundleId()
                + "|" + String.join(",", candidate.orderIds())
                + "|" + candidate.clusterId();
    }
}
