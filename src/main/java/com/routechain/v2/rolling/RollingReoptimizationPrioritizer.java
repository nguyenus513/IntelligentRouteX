package com.routechain.v2.rolling;

import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.DriverShortlistSummary;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class RollingReoptimizationPrioritizer {
    private static final String STAGE_REASON = "rolling-horizon-driver-reprioritized";
    private static final String CANDIDATE_REASON = "rolling-active-route-reoptimization-intent";
    private static final double BASE_SCORE_LIFT = 0.10;
    private static final double NEAR_DRIVER_SCORE_LIFT = 0.06;

    public DispatchRouteCandidateStage apply(DispatchRouteCandidateStage stage,
                                             List<BundleCandidate> bundleCandidates,
                                             List<RollingHoldDecision> rollingDecisions) {
        Set<String> reoptimizationOrderIds = rollingDecisions.stream()
                .filter(decision -> decision.decisionMode() == RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE)
                .map(RollingHoldDecision::orderId)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        if (stage == null || reoptimizationOrderIds.isEmpty() || stage.driverCandidates().isEmpty()) {
            return stage;
        }
        Map<String, BundleCandidate> bundleById = bundleCandidates.stream()
                .collect(Collectors.toMap(BundleCandidate::bundleId, bundle -> bundle, (left, right) -> left, LinkedHashMap::new));
        List<DriverCandidate> prioritized = stage.driverCandidates().stream()
                .map(candidate -> prioritize(candidate, bundleById.get(candidate.bundleId()), reoptimizationOrderIds))
                .sorted(Comparator.comparing((DriverCandidate candidate) -> !touchesReoptimizationOrder(candidate, bundleById.get(candidate.bundleId()), reoptimizationOrderIds))
                        .thenComparing(Comparator.comparingDouble(DriverCandidate::rerankScore).reversed())
                        .thenComparingDouble(DriverCandidate::pickupEtaMinutes)
                        .thenComparing(DriverCandidate::bundleId)
                        .thenComparing(DriverCandidate::anchorOrderId)
                        .thenComparing(DriverCandidate::driverId))
                .toList();
        if (prioritized.equals(stage.driverCandidates())) {
            return stage;
        }
        List<String> degradeReasons = appendDistinct(stage.degradeReasons(), STAGE_REASON);
        return new DispatchRouteCandidateStage(
                stage.schemaVersion(),
                stage.pickupAnchors(),
                stage.pickupAnchorSummary(),
                rerank(prioritized),
                summarize(stage.driverShortlistSummary(), degradeReasons),
                stage.stageLatencies(),
                stage.mlStageMetadata(),
                degradeReasons);
    }

    private DriverCandidate prioritize(DriverCandidate candidate,
                                       BundleCandidate bundle,
                                       Set<String> reoptimizationOrderIds) {
        if (!touchesReoptimizationOrder(candidate, bundle, reoptimizationOrderIds)) {
            return candidate;
        }
        double pickupLift = candidate.pickupEtaMinutes() <= 8.0 ? NEAR_DRIVER_SCORE_LIFT : 0.0;
        double rerankScore = clamp01(candidate.rerankScore() + BASE_SCORE_LIFT + pickupLift);
        double driverFitScore = clamp01(candidate.driverFitScore() + 0.5 * (BASE_SCORE_LIFT + pickupLift));
        return new DriverCandidate(
                candidate.schemaVersion(),
                candidate.bundleId(),
                candidate.anchorOrderId(),
                candidate.driverId(),
                candidate.rank(),
                candidate.pickupEtaMinutes(),
                driverFitScore,
                rerankScore,
                appendDistinct(candidate.reasons(), CANDIDATE_REASON),
                candidate.degradeReasons());
    }

    private boolean touchesReoptimizationOrder(DriverCandidate candidate,
                                               BundleCandidate bundle,
                                               Set<String> reoptimizationOrderIds) {
        if (reoptimizationOrderIds.contains(candidate.anchorOrderId())) {
            return true;
        }
        return bundle != null && bundle.orderIds().stream().anyMatch(reoptimizationOrderIds::contains);
    }

    private List<DriverCandidate> rerank(List<DriverCandidate> candidates) {
        java.util.ArrayList<DriverCandidate> ranked = new java.util.ArrayList<>();
        int rank = 1;
        for (DriverCandidate candidate : candidates) {
            ranked.add(new DriverCandidate(
                    candidate.schemaVersion(),
                    candidate.bundleId(),
                    candidate.anchorOrderId(),
                    candidate.driverId(),
                    rank++,
                    candidate.pickupEtaMinutes(),
                    candidate.driverFitScore(),
                    candidate.rerankScore(),
                    candidate.reasons(),
                    candidate.degradeReasons()));
        }
        return List.copyOf(ranked);
    }

    private DriverShortlistSummary summarize(DriverShortlistSummary summary, List<String> degradeReasons) {
        return new DriverShortlistSummary(
                summary.schemaVersion(),
                summary.bundleCount(),
                summary.anchorCount(),
                summary.shortlistedDriverCount(),
                summary.rerankedDriverCount(),
                degradeReasons);
    }

    private List<String> appendDistinct(List<String> values, String value) {
        LinkedHashSet<String> appended = new LinkedHashSet<>(values);
        appended.add(value);
        return List.copyOf(appended);
    }

    private double clamp01(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
