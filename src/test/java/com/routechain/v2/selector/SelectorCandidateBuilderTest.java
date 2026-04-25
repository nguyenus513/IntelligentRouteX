package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteShapeQuality;
import com.routechain.v2.route.RouteTestFixtures;
import com.routechain.v2.scenario.RobustUtility;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SelectorCandidateBuilderTest {

    @Test
    void buildsCandidateFromProposalRobustUtilityAndProvenanceAndComputesSelectionScoreOnce() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                RouteTestFixtures.request().availableDrivers(),
                pairClusterStage,
                bundleStage);
        SelectorCandidateBuilder builder = new SelectorCandidateBuilder(properties);

        SelectorCandidateBuildResult buildResult = builder.build(routeProposalStage, scenarioStage, routeCandidateStage, context);

        assertFalse(buildResult.candidateEnvelopes().isEmpty());
        SelectorCandidate candidate = buildResult.candidateEnvelopes().get(0).candidate();
        BundleCandidate bundleCandidate = context.bundle(candidate.bundleId());
        DriverCandidate driverCandidate = routeCandidateStage.driverCandidates().stream()
                .filter(current -> current.bundleId().equals(candidate.bundleId())
                        && current.anchorOrderId().equals(candidate.anchorOrderId())
                        && current.driverId().equals(candidate.driverId()))
                .findFirst()
                .orElseThrow();
        RobustUtility robustUtility = scenarioStage.robustUtilities().stream()
                .filter(current -> current.proposalId().equals(candidate.proposalId()))
                .findFirst()
                .orElseThrow();
        double expectedSelectionScore = (0.60 * robustUtility.robustUtility())
                + (0.20 * candidate.routeValue())
                + (0.10 * driverCandidate.rerankScore())
                + (0.10 * bundleCandidate.score())
                + bundleSizeLift(routeProposalStage.routeProposals().stream()
                .filter(proposal -> proposal.proposalId().equals(candidate.proposalId()))
                .findFirst()
                .orElseThrow())
                - (bundleCandidate.boundaryCross() && context.acceptedBoundarySupport(candidate.bundleId()) < 0.60 ? 0.03 : 0.0)
                - (candidate.source().name().equals("FALLBACK_SIMPLE") ? properties.getSelector().getFallbackPenalty() : 0.0)
                - RouteShapeQuality.penalty(routeProposalStage.routeProposals().stream()
                .filter(proposal -> proposal.proposalId().equals(candidate.proposalId()))
                .findFirst()
                .orElseThrow());

        assertEquals(bundleCandidate.orderIds(), candidate.orderIds());
        assertEquals(bundleCandidate.clusterId(), candidate.clusterId());
        assertEquals(bundleCandidate.boundaryCross(), candidate.boundaryCross());
        assertEquals(driverCandidate.driverId(), candidate.driverId());
        assertEquals(expectedSelectionScore, candidate.selectionScore(), 1e-9);
    }

    @Test
    void rejectsMultiOrderRoutesWithRejectShapeVerdictBeforeSelection() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                RouteTestFixtures.request().availableDrivers(),
                pairClusterStage,
                bundleStage);
        RouteProposal original = routeProposalStage.routeProposals().stream()
                .filter(proposal -> proposal.stopOrder().size() > 1)
                .findFirst()
                .orElseThrow();
        RouteProposal rejectShape = new RouteProposal(
                original.schemaVersion(),
                original.proposalId(),
                original.bundleId(),
                original.anchorOrderId(),
                original.driverId(),
                RouteProposalSource.HEURISTIC_SAFE,
                original.stopOrder(),
                original.projectedPickupEtaMinutes(),
                original.projectedCompletionEtaMinutes(),
                original.routeValue(),
                original.feasible(),
                original.reasons(),
                original.degradeReasons(),
                original.legCount(),
                original.totalDistanceMeters(),
                original.totalTravelTimeSeconds(),
                original.routeCost(),
                original.majorRoadRatio(),
                original.minorRoadRatio(),
                42,
                original.uTurnCount(),
                1.0,
                0.30,
                true,
                original.legs());
        DispatchRouteProposalStage rejectStage = new DispatchRouteProposalStage(
                routeProposalStage.schemaVersion(),
                java.util.List.of(rejectShape),
                routeProposalStage.routeProposalSummary(),
                routeProposalStage.hotStartReuseSummary(),
                routeProposalStage.stageLatencies(),
                routeProposalStage.mlStageMetadata(),
                routeProposalStage.degradeReasons());
        SelectorCandidateBuilder builder = new SelectorCandidateBuilder(properties);

        SelectorCandidateBuildResult buildResult = builder.build(rejectStage, scenarioStage, routeCandidateStage, context);

        assertTrue(buildResult.candidateEnvelopes().isEmpty());
        assertTrue(buildResult.degradeReasons().contains("selector-reject-zigzag-route"));
    }

    @Test
    void rejectsWeakShapeRoutesBeforeSelection() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                RouteTestFixtures.request().availableDrivers(),
                pairClusterStage,
                bundleStage);
        RouteProposal original = routeProposalStage.routeProposals().stream()
                .filter(proposal -> proposal.stopOrder().size() > 1)
                .findFirst()
                .orElseThrow();
        RouteProposal weakShape = new RouteProposal(
                original.schemaVersion(),
                original.proposalId(),
                original.bundleId(),
                original.anchorOrderId(),
                original.driverId(),
                RouteProposalSource.HEURISTIC_SAFE,
                original.stopOrder(),
                original.projectedPickupEtaMinutes(),
                original.projectedCompletionEtaMinutes(),
                original.routeValue(),
                original.feasible(),
                original.reasons(),
                original.degradeReasons(),
                original.legCount(),
                original.totalDistanceMeters(),
                original.totalTravelTimeSeconds(),
                original.routeCost(),
                original.majorRoadRatio(),
                original.minorRoadRatio(),
                18,
                original.uTurnCount(),
                0.93,
                0.58,
                true,
                original.legs());
        DispatchRouteProposalStage weakStage = new DispatchRouteProposalStage(
                routeProposalStage.schemaVersion(),
                java.util.List.of(weakShape),
                routeProposalStage.routeProposalSummary(),
                routeProposalStage.hotStartReuseSummary(),
                routeProposalStage.stageLatencies(),
                routeProposalStage.mlStageMetadata(),
                routeProposalStage.degradeReasons());
        SelectorCandidateBuilder builder = new SelectorCandidateBuilder(properties);

        SelectorCandidateBuildResult buildResult = builder.build(weakStage, scenarioStage, routeCandidateStage, context);

        assertTrue(buildResult.candidateEnvelopes().isEmpty());
        assertTrue(buildResult.degradeReasons().contains("selector-reject-weak-shape-route"));
    }

    @Test
    void rejectsDominatedSameOrderSetRoutesBeforeSelection() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchCandidateContext context = new DispatchCandidateContext(
                pairClusterStage.bufferedOrderWindow().orders(),
                RouteTestFixtures.request().availableDrivers(),
                pairClusterStage,
                bundleStage);
        RouteProposal original = routeProposalStage.routeProposals().stream()
                .filter(proposal -> proposal.stopOrder().size() > 1)
                .findFirst()
                .orElseThrow();
        RouteProposal dominated = shapedProposal(original, original.proposalId() + "-dominated", original.stopOrder(), 1800.0, 1500.0, 16, 0.62, 0.80);
        RouteProposal dominant = shapedProposal(original, original.proposalId() + "-dominant", original.stopOrder().reversed(), 1400.0, 1200.0, 14, 0.70, 0.70);
        DispatchRouteProposalStage dominatedStage = new DispatchRouteProposalStage(
                routeProposalStage.schemaVersion(),
                java.util.List.of(dominated, dominant),
                routeProposalStage.routeProposalSummary(),
                routeProposalStage.hotStartReuseSummary(),
                routeProposalStage.stageLatencies(),
                routeProposalStage.mlStageMetadata(),
                routeProposalStage.degradeReasons());
        SelectorCandidateBuilder builder = new SelectorCandidateBuilder(properties);

        SelectorCandidateBuildResult buildResult = builder.build(dominatedStage, scenarioStage, routeCandidateStage, context);

        assertTrue(buildResult.candidateEnvelopes().stream()
                .noneMatch(envelope -> envelope.candidate().proposalId().equals(dominated.proposalId())));
        assertTrue(buildResult.degradeReasons().contains("selector-reject-dominated-route-shape"));
    }

    private double bundleSizeLift(RouteProposal proposal) {
        int bundleSize = proposal.stopOrder().size();
        if (bundleSize <= 2) {
            return proposal.straightnessScore() < 0.55 ? -0.04 : 0.0;
        }
        if (proposal.straightnessScore() < 0.60 || proposal.turnCount() > (8 * bundleSize + 6)) {
            return 0.0;
        }
        return Math.min(0.10, 0.035 * (bundleSize - 2));
    }

    private RouteProposal shapedProposal(RouteProposal original,
                                         String proposalId,
                                         java.util.List<String> stopOrder,
                                         double routeCost,
                                         double travelTimeSeconds,
                                         int turnCount,
                                         double straightnessScore,
                                         double congestionScore) {
        return new RouteProposal(
                original.schemaVersion(),
                proposalId,
                original.bundleId(),
                stopOrder.getFirst(),
                original.driverId(),
                RouteProposalSource.HEURISTIC_SAFE,
                stopOrder,
                original.projectedPickupEtaMinutes(),
                original.projectedCompletionEtaMinutes(),
                original.routeValue(),
                original.feasible(),
                original.reasons(),
                original.degradeReasons(),
                original.legCount(),
                routeCost,
                travelTimeSeconds,
                routeCost,
                original.majorRoadRatio(),
                original.minorRoadRatio(),
                turnCount,
                original.uTurnCount(),
                congestionScore,
                straightnessScore,
                true,
                original.legs());
    }
}
