package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.MlStageMetadataAccumulator;
import com.routechain.v2.integration.NoOpTabularScoringClient;
import com.routechain.v2.integration.TabularScoreResult;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.harvest.HarvestRecorder;
import com.routechain.v2.bundle.BundleCandidate;

import java.util.ArrayList;
import java.util.List;

public final class RouteValueScorer {
    private final RouteChainDispatchV2Properties properties;
    private final TabularScoringClient tabularScoringClient;
    private final HarvestRecorder harvestRecorder;

    public RouteValueScorer(RouteChainDispatchV2Properties properties,
                            TabularScoringClient tabularScoringClient,
                            HarvestRecorder harvestRecorder) {
        this.properties = properties;
        this.tabularScoringClient = tabularScoringClient;
        this.harvestRecorder = harvestRecorder;
    }

    public RouteValueScorer(RouteChainDispatchV2Properties properties, TabularScoringClient tabularScoringClient) {
        this(properties, tabularScoringClient, null);
    }

    public RouteValueScorer() {
        this(RouteChainDispatchV2Properties.defaults(), new NoOpTabularScoringClient(), null);
    }

    public RouteValueScoringOutcome score(String traceId, RouteProposalCandidate candidate, DispatchCandidateContext context) {
        RouteProposal proposal = candidate.proposal();
        if (!proposal.feasible()) {
            return new RouteValueScoringOutcome(new RouteProposalCandidate(
                    new RouteProposal(
                            proposal.schemaVersion(),
                            proposal.proposalId(),
                            proposal.bundleId(),
                            proposal.anchorOrderId(),
                            proposal.driverId(),
                            proposal.source(),
                            proposal.stopOrder(),
                            proposal.projectedPickupEtaMinutes(),
                            proposal.projectedCompletionEtaMinutes(),
                            0.0,
                            false,
                            proposal.reasons(),
                            proposal.degradeReasons(),
                            proposal.legCount(),
                            proposal.totalDistanceMeters(),
                            proposal.totalTravelTimeSeconds(),
                            proposal.routeCost(),
                            proposal.majorRoadRatio(),
                            proposal.minorRoadRatio(),
                            proposal.turnCount(),
                            proposal.uTurnCount(),
                            proposal.congestionScore(),
                            proposal.straightnessScore(),
                            proposal.geometryAvailable(),
                            proposal.legs()),
                    candidate.tupleKey(),
                    candidate.pickupAnchor(),
                    candidate.driverCandidate(),
                    candidate.trace()),
                    List.of(),
                    List.of());
        }
        BundleCandidate bundle = context.bundle(proposal.bundleId());
        double driverContribution = 0.32 * candidate.driverCandidate().rerankScore();
        double bundleContribution = 0.20 * bundle.score();
        double anchorContribution = 0.14 * candidate.pickupAnchor().score();
        double pickupEtaContribution = 0.14 * etaScore(proposal.projectedPickupEtaMinutes(), 25.0);
        double completionEtaContribution = 0.10 * etaScore(proposal.projectedCompletionEtaMinutes(), 75.0);
        double supportContribution = 0.10 * context.averagePairSupport(bundle.orderIds());
        double urgencyLift = bundle.orderIds().stream()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .anyMatch(order -> order.urgent() && proposal.projectedPickupEtaMinutes() <= 12.0) ? 0.05 : 0.0;
        double boundaryPenalty = bundle.boundaryCross() ? Math.max(0.0, 0.08 - context.acceptedBoundarySupport(bundle.bundleId()) * 0.08) : 0.0;
        double fallbackPenalty = proposal.source() == RouteProposalSource.FALLBACK_SIMPLE ? 0.05 : 0.0;
        double score = Math.max(0.0, Math.min(1.0,
                driverContribution
                        + bundleContribution
                        + anchorContribution
                        + pickupEtaContribution
                        + completionEtaContribution
                        + supportContribution
                        + urgencyLift
                        - boundaryPenalty
                        - fallbackPenalty));
        List<String> reasons = new ArrayList<>(proposal.reasons());
        if (urgencyLift > 0.0) {
            reasons.add("urgent-route-lift");
        }
        if (fallbackPenalty > 0.0) {
            reasons.add("fallback-simple-penalty");
        }
        double adjustedScore = score;
        List<String> degradeReasons = new ArrayList<>(proposal.degradeReasons());
        MlStageMetadataAccumulator mlStageMetadataAccumulator = new MlStageMetadataAccumulator("route-proposal-pool");
        if (properties.isMlEnabled() && properties.getMl().getTabular().isEnabled()) {
            RouteValueFeatureVector featureVector = new RouteValueFeatureVector(
                    "route-value-feature-vector/v1",
                    traceId,
                    proposal.proposalId(),
                    proposal.bundleId(),
                    proposal.anchorOrderId(),
                    proposal.driverId(),
                    proposal.source().name(),
                    proposal.projectedPickupEtaMinutes(),
                    proposal.projectedCompletionEtaMinutes(),
                    score,
                    candidate.driverCandidate().rerankScore(),
                    bundle.score(),
                    candidate.pickupAnchor().score(),
                    context.averagePairSupport(bundle.orderIds()),
                    urgencyLift,
                    boundaryPenalty,
                    fallbackPenalty);
            TabularScoreResult scoreResult = tabularScoringClient.scoreRouteValue(
                    featureVector,
                    properties.getMl().getTabular().getReadTimeout().toMillis());
            mlStageMetadataAccumulator.accept(scoreResult);
            if (harvestRecorder != null) {
                harvestRecorder.recordTabularTeacher(
                        traceId,
                        "route-proposal-pool",
                        proposal.proposalId(),
                        "route-value-score",
                        featureVector,
                        scoreResult);
            }
            if (scoreResult.applied()) {
                adjustedScore = Math.max(0.0, Math.min(1.0, score + scoreResult.value()));
            } else {
                degradeReasons.add("route-value-ml-unavailable");
            }
        }
        RouteProposal scored = new RouteProposal(
                proposal.schemaVersion(),
                proposal.proposalId(),
                proposal.bundleId(),
                proposal.anchorOrderId(),
                proposal.driverId(),
                proposal.source(),
                proposal.stopOrder(),
                proposal.projectedPickupEtaMinutes(),
                proposal.projectedCompletionEtaMinutes(),
                adjustedScore,
                true,
                List.copyOf(reasons),
                List.copyOf(degradeReasons.stream().distinct().toList()),
                proposal.legCount(),
                proposal.totalDistanceMeters(),
                proposal.totalTravelTimeSeconds(),
                proposal.routeCost(),
                proposal.majorRoadRatio(),
                proposal.minorRoadRatio(),
                proposal.turnCount(),
                proposal.uTurnCount(),
                proposal.congestionScore(),
                proposal.straightnessScore(),
                proposal.geometryAvailable(),
                proposal.legs());
        return new RouteValueScoringOutcome(new RouteProposalCandidate(
                scored,
                candidate.tupleKey(),
                candidate.pickupAnchor(),
                candidate.driverCandidate(),
                new RouteProposalTrace(
                        candidate.trace().tupleKey(),
                        candidate.trace().source(),
                        candidate.trace().stopOrderSignature(),
                        driverContribution,
                        bundleContribution,
                        anchorContribution,
                        pickupEtaContribution,
                        completionEtaContribution,
                        supportContribution,
                        urgencyLift,
                        boundaryPenalty,
                        fallbackPenalty,
                        candidate.trace().validationReasons())),
                List.copyOf(degradeReasons.stream().distinct().toList()),
                mlStageMetadataAccumulator.build().map(List::of).orElse(List.of()));
    }

    public RouteProposalCandidate score(RouteProposalCandidate candidate, DispatchCandidateContext context) {
        return score("route-value", candidate, context).candidate();
    }

    private double etaScore(double etaMinutes, double ceilingMinutes) {
        return Math.max(0.0, 1.0 - (etaMinutes / ceilingMinutes));
    }
}
