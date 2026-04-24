package com.routechain.v2.route;

import com.routechain.v2.bundle.BundleCandidate;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RouteProposalPrePruner {

    public RouteProposalPruneResult pruneInputs(List<DriverCandidate> driverCandidates,
                                                List<PickupAnchor> pickupAnchors,
                                                DispatchCandidateContext context,
                                                RouteProposalBudgetDecision budgetDecision) {
        if (!budgetDecision.enabled()) {
            return new RouteProposalPruneResult(
                    List.copyOf(driverCandidates),
                    List.copyOf(pickupAnchors),
                    List.of(),
                    driverCandidates.size(),
                    driverCandidates.size(),
                    0,
                    Map.of());
        }
        Map<String, Integer> reasons = new LinkedHashMap<>();
        Set<String> retainedAnchorKeys = new LinkedHashSet<>();
        Map<String, Integer> anchorCountByBundle = new LinkedHashMap<>();
        for (PickupAnchor anchor : pickupAnchors.stream().sorted(anchorComparator()).toList()) {
            int count = anchorCountByBundle.getOrDefault(anchor.bundleId(), 0);
            if (count >= budgetDecision.maxAnchorsPerBundle()) {
                increment(reasons, "anchor-budget-exceeded");
                continue;
            }
            retainedAnchorKeys.add(anchorKey(anchor.bundleId(), anchor.anchorOrderId()));
            anchorCountByBundle.put(anchor.bundleId(), count + 1);
        }
        List<DriverCandidate> anchorFiltered = driverCandidates.stream()
                .filter(candidate -> retainedAnchorKeys.contains(anchorKey(candidate.bundleId(), candidate.anchorOrderId())))
                .sorted(driverComparator(context))
                .toList();
        int anchorPruned = driverCandidates.size() - anchorFiltered.size();
        if (anchorPruned > 0) {
            reasons.put("anchor-budget-exceeded", reasons.getOrDefault("anchor-budget-exceeded", 0) + anchorPruned);
        }
        Map<String, Integer> driverCountByBundle = new LinkedHashMap<>();
        List<DriverCandidate> retainedDrivers = new ArrayList<>();
        for (DriverCandidate candidate : anchorFiltered) {
            int count = driverCountByBundle.getOrDefault(candidate.bundleId(), 0);
            if (count >= budgetDecision.maxDriversPerBundle()) {
                increment(reasons, "driver-budget-exceeded");
                continue;
            }
            retainedDrivers.add(candidate);
            driverCountByBundle.put(candidate.bundleId(), count + 1);
        }
        int tupleBudget = Math.max(1, budgetDecision.maxTotalRouteProposals());
        if (retainedDrivers.size() > tupleBudget) {
            int dropped = retainedDrivers.size() - tupleBudget;
            retainedDrivers = retainedDrivers.stream().limit(tupleBudget).toList();
            reasons.put("total-proposal-budget-exceeded", reasons.getOrDefault("total-proposal-budget-exceeded", 0) + dropped);
        }
        Set<String> retainedDriverKeys = retainedDrivers.stream()
                .map(candidate -> tupleKey(candidate.bundleId(), candidate.anchorOrderId(), candidate.driverId()))
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        Set<String> retainedAnchorKeysAfterDriverBudget = retainedDrivers.stream()
                .map(candidate -> anchorKey(candidate.bundleId(), candidate.anchorOrderId()))
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        List<PickupAnchor> retainedAnchors = pickupAnchors.stream()
                .filter(anchor -> retainedAnchorKeysAfterDriverBudget.contains(anchorKey(anchor.bundleId(), anchor.anchorOrderId())))
                .toList();
        return new RouteProposalPruneResult(
                List.copyOf(retainedDrivers),
                List.copyOf(retainedAnchors),
                List.of(),
                driverCandidates.size(),
                retainedDriverKeys.size(),
                Math.max(0, driverCandidates.size() - retainedDriverKeys.size()),
                Map.copyOf(reasons));
    }

    public RouteProposalPruneResult pruneCandidates(List<RouteProposalCandidate> candidates,
                                                    DispatchCandidateContext context,
                                                    RouteProposalBudgetDecision budgetDecision) {
        if (!budgetDecision.enabled()) {
            return new RouteProposalPruneResult(List.of(), List.of(), List.copyOf(candidates), candidates.size(), candidates.size(), 0, Map.of());
        }
        Map<String, Integer> reasons = new LinkedHashMap<>();
        Map<RouteProposalTupleKey, List<RouteProposalCandidate>> byTuple = candidates.stream()
                .collect(java.util.stream.Collectors.groupingBy(
                        RouteProposalCandidate::tupleKey,
                        LinkedHashMap::new,
                        java.util.stream.Collectors.toList()));
        List<RouteProposalCandidate> retained = new ArrayList<>();
        for (List<RouteProposalCandidate> tupleCandidates : byTuple.values()) {
            List<RouteProposalCandidate> sorted = tupleCandidates.stream().sorted(candidateComparator(context)).toList();
            int keep = Math.min(sorted.size(), Math.max(1, budgetDecision.maxAlternativesPerTuple()));
            retained.addAll(sorted.subList(0, keep));
            if (sorted.size() > keep) {
                reasons.put("alternative-budget-exceeded", reasons.getOrDefault("alternative-budget-exceeded", 0) + (sorted.size() - keep));
            }
        }
        retained = retained.stream().sorted(candidateComparator(context)).toList();
        if (retained.size() > budgetDecision.maxTotalRouteProposals()) {
            int dropped = retained.size() - budgetDecision.maxTotalRouteProposals();
            retained = retained.subList(0, budgetDecision.maxTotalRouteProposals());
            reasons.put("total-proposal-budget-exceeded", reasons.getOrDefault("total-proposal-budget-exceeded", 0) + dropped);
        }
        return new RouteProposalPruneResult(
                List.of(),
                List.of(),
                List.copyOf(retained),
                candidates.size(),
                retained.size(),
                Math.max(0, candidates.size() - retained.size()),
                Map.copyOf(reasons));
    }

    private Comparator<PickupAnchor> anchorComparator() {
        return Comparator.comparingDouble(PickupAnchor::score).reversed()
                .thenComparing(PickupAnchor::bundleId)
                .thenComparing(PickupAnchor::anchorOrderId);
    }

    private Comparator<DriverCandidate> driverComparator(DispatchCandidateContext context) {
        return Comparator.comparingInt((DriverCandidate candidate) -> geometryPriority(context, candidate.bundleId()))
                .thenComparing(Comparator.comparingDouble((DriverCandidate candidate) -> bundleScore(context, candidate.bundleId())).reversed())
                .thenComparing(Comparator.comparingDouble(DriverCandidate::rerankScore).reversed())
                .thenComparingDouble(DriverCandidate::pickupEtaMinutes)
                .thenComparing(DriverCandidate::bundleId)
                .thenComparing(DriverCandidate::anchorOrderId)
                .thenComparing(DriverCandidate::driverId);
    }

    private Comparator<RouteProposalCandidate> candidateComparator(DispatchCandidateContext context) {
        return Comparator.comparingInt((RouteProposalCandidate candidate) -> geometryPriority(context, candidate.proposal().bundleId()))
                .thenComparing(Comparator.comparingDouble((RouteProposalCandidate candidate) -> candidateQuality(candidate, context)).reversed())
                .thenComparingInt(candidate -> sourcePriority(candidate.proposal().source()))
                .thenComparingDouble(candidate -> candidate.proposal().projectedPickupEtaMinutes())
                .thenComparing(candidate -> candidate.proposal().proposalId());
    }

    private double candidateQuality(RouteProposalCandidate candidate, DispatchCandidateContext context) {
        BundleCandidate bundle = context.bundle(candidate.proposal().bundleId());
        double bundleScore = bundle == null ? 0.0 : bundle.score();
        double support = bundle == null ? 0.0 : context.averagePairSupport(bundle.orderIds());
        double fallbackPenalty = candidate.proposal().source() == RouteProposalSource.FALLBACK_SIMPLE ? 0.03 : 0.0;
        double boundaryPenalty = bundle != null && bundle.boundaryCross() ? 0.05 : 0.0;
        double geometryLift = geometryPriority(context, candidate.proposal().bundleId()) == 0 ? 0.10 : 0.0;
        return 0.34 * candidate.driverCandidate().rerankScore()
                + 0.22 * bundleScore
                + 0.18 * candidate.pickupAnchor().score()
                + 0.14 * etaScore(candidate.proposal().projectedPickupEtaMinutes(), 25.0)
                + 0.08 * etaScore(candidate.proposal().projectedCompletionEtaMinutes(), 75.0)
                + 0.04 * support
                + geometryLift
                - fallbackPenalty
                - boundaryPenalty;
    }

    private int geometryPriority(DispatchCandidateContext context, String bundleId) {
        BundleCandidate bundle = context.bundle(bundleId);
        return bundle != null && bundle.orderIds().size() > 1 ? 0 : 1;
    }

    private double bundleScore(DispatchCandidateContext context, String bundleId) {
        BundleCandidate bundle = context.bundle(bundleId);
        return bundle == null ? 0.0 : bundle.score();
    }

    private double etaScore(double etaMinutes, double ceilingMinutes) {
        return Math.max(0.0, 1.0 - (etaMinutes / ceilingMinutes));
    }

    private int sourcePriority(RouteProposalSource source) {
        return switch (source) {
            case HEURISTIC_FAST -> 0;
            case HEURISTIC_SAFE -> 1;
            case FALLBACK_SIMPLE -> 2;
            case ML_REFINED -> 3;
            case ML_PROPOSAL -> 4;
        };
    }

    private String anchorKey(String bundleId, String anchorOrderId) {
        return bundleId + "|" + anchorOrderId;
    }

    private String tupleKey(String bundleId, String anchorOrderId, String driverId) {
        return bundleId + "|" + anchorOrderId + "|" + driverId;
    }

    private void increment(Map<String, Integer> reasons, String reason) {
        reasons.put(reason, reasons.getOrDefault(reason, 0) + 1);
    }
}
