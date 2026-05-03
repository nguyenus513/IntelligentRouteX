package com.routechain.v2.selector;

import com.routechain.v2.constraints.ConstraintCheckResult;
import com.routechain.v2.constraints.FeasibilityOracle;

import com.routechain.v2.route.RouteProposalSource;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class SelectorPoolReducer {
    private static final int DEFAULT_MAX_POOL_SIZE = 256;
    private static final int MIN_PER_SOURCE = 8;
    private static final int MIN_ACTIVE_REPAIR = 12;
    private static final int MIN_PER_DRIVER = 2;
    private static final int MIN_PER_ORDER = 2;

    private final FeasibilityOracle feasibilityOracle;

    public SelectorPoolReducer() {
        this(new FeasibilityOracle());
    }

    public SelectorPoolReducer(FeasibilityOracle feasibilityOracle) {
        this.feasibilityOracle = feasibilityOracle;
    }

    public SelectorPoolReductionResult reduce(List<SelectorCandidateEnvelope> candidateEnvelopes) {
        return reduce(candidateEnvelopes, DEFAULT_MAX_POOL_SIZE);
    }

    public SelectorPoolReductionResult reduce(List<SelectorCandidateEnvelope> candidateEnvelopes, int maxPoolSize) {
        int effectiveMaxPoolSize = Math.max(1, maxPoolSize);
        Map<String, Integer> violationCountsByCode = new java.util.TreeMap<>();
        List<SelectorCandidateEnvelope> feasible = new ArrayList<>();
        for (SelectorCandidateEnvelope envelope : candidateEnvelopes) {
            ConstraintCheckResult check = feasibilityOracle.check(envelope.candidate());
            if (check.feasible()) {
                feasible.add(envelope);
            } else {
                check.violationCountsByCode().forEach((code, count) -> violationCountsByCode.merge(code, count, Integer::sum));
            }
        }
        feasible = feasible.stream()
                .sorted(SelectorCandidateRanking.comparator())
                .toList();
        double feasibleBestObjectiveUtility = bestObjective(feasible);
        int feasibilityRejectedCount = candidateEnvelopes.size() - feasible.size();
        if (feasible.size() <= effectiveMaxPoolSize) {
            return new SelectorPoolReductionResult(
                    feasible,
                    feasibilityRejectedCount,
                    List.of("selector-pool-feasibility-filter-applied"),
                    candidateEnvelopes.size(),
                    feasible.size(),
                    violationCountsByCode,
                    effectiveMaxPoolSize,
                    false,
                    bestObjective(feasible),
                    feasibleBestObjectiveUtility);
        }

        Map<String, SelectorCandidateEnvelope> retainedByProposalId = new LinkedHashMap<>();
        Map<RouteProposalSource, List<SelectorCandidateEnvelope>> bySource = new LinkedHashMap<>();
        for (SelectorCandidateEnvelope envelope : feasible) {
            bySource.computeIfAbsent(envelope.candidate().source(), ignored -> new ArrayList<>()).add(envelope);
        }
        for (List<SelectorCandidateEnvelope> sourceCandidates : bySource.values()) {
            sourceCandidates.stream()
                    .limit(1)
                    .forEach(envelope -> retainIfRoom(retainedByProposalId, envelope, effectiveMaxPoolSize));
        }
        feasible.stream()
                .filter(envelope -> envelope.candidate().source() == RouteProposalSource.ACTIVE_ROUTE_INSERTION)
                .limit(MIN_ACTIVE_REPAIR)
                .forEach(envelope -> retainIfRoom(retainedByProposalId, envelope, effectiveMaxPoolSize));
        for (List<SelectorCandidateEnvelope> sourceCandidates : bySource.values()) {
            sourceCandidates.stream()
                    .limit(MIN_PER_SOURCE)
                    .forEach(envelope -> retainIfRoom(retainedByProposalId, envelope, effectiveMaxPoolSize));
        }
        retainTopByDriver(feasible, retainedByProposalId, effectiveMaxPoolSize);
        retainTopByOrder(feasible, retainedByProposalId, effectiveMaxPoolSize);
        feasible.stream()
                .sorted(Comparator.comparingDouble((SelectorCandidateEnvelope envelope) -> envelope.candidate().selectionScore()).reversed())
                    .forEach(envelope -> {
                    if (retainedByProposalId.size() < effectiveMaxPoolSize) {
                        retainedByProposalId.putIfAbsent(envelope.candidate().proposalId(), envelope);
                    }
                });
        List<SelectorCandidateEnvelope> reduced = retainedByProposalId.values().stream()
                .sorted(SelectorCandidateRanking.comparator())
                .toList();
        return new SelectorPoolReductionResult(
                reduced,
                feasibilityRejectedCount + feasible.size() - reduced.size(),
                List.of("selector-pool-reduced-before-exact", "selector-pool-feasibility-filter-applied"),
                candidateEnvelopes.size(),
                feasible.size(),
                violationCountsByCode,
                effectiveMaxPoolSize,
                true,
                bestObjective(reduced),
                feasibleBestObjectiveUtility);
    }

    private void retainTopByDriver(List<SelectorCandidateEnvelope> feasible,
                                   Map<String, SelectorCandidateEnvelope> retainedByProposalId,
                                   int maxPoolSize) {
        Map<String, Integer> retainedByDriver = new LinkedHashMap<>();
        for (SelectorCandidateEnvelope envelope : feasible) {
            if (retainedByProposalId.size() >= maxPoolSize) {
                return;
            }
            String driverId = envelope.candidate().driverId();
            int count = retainedByDriver.getOrDefault(driverId, 0);
            if (count < MIN_PER_DRIVER && retainIfRoom(retainedByProposalId, envelope, maxPoolSize)) {
                retainedByDriver.put(driverId, count + 1);
            }
        }
    }

    private void retainTopByOrder(List<SelectorCandidateEnvelope> feasible,
                                  Map<String, SelectorCandidateEnvelope> retainedByProposalId,
                                  int maxPoolSize) {
        Map<String, Integer> retainedByOrder = new LinkedHashMap<>();
        for (SelectorCandidateEnvelope envelope : feasible) {
            if (retainedByProposalId.size() >= maxPoolSize) {
                return;
            }
            for (String orderId : envelope.candidate().orderIds()) {
                int count = retainedByOrder.getOrDefault(orderId, 0);
                if (count < MIN_PER_ORDER && retainIfRoom(retainedByProposalId, envelope, maxPoolSize)) {
                    retainedByOrder.put(orderId, count + 1);
                    break;
                }
            }
        }
    }

    private boolean retainIfRoom(Map<String, SelectorCandidateEnvelope> retainedByProposalId,
                                 SelectorCandidateEnvelope envelope,
                                 int maxPoolSize) {
        if (retainedByProposalId.size() >= maxPoolSize) {
            return false;
        }
        return retainedByProposalId.putIfAbsent(envelope.candidate().proposalId(), envelope) == null;
    }

    private double bestObjective(List<SelectorCandidateEnvelope> candidates) {
        return candidates.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .mapToDouble(SelectorCandidateRanking::objectiveUtility)
                .max()
                .orElse(0.0);
    }
}
