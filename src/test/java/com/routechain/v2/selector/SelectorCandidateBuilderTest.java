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
import com.routechain.v2.scenario.DispatchScenarioStage;
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


    @Test
    void keepsSameOrderSetAlternativesAcrossDifferentDrivers() {
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
        String alternateDriverId = routeCandidateStage.driverCandidates().stream()
                .filter(candidate -> candidate.bundleId().equals(original.bundleId()))
                .filter(candidate -> candidate.anchorOrderId().equals(original.anchorOrderId()))
                .map(DriverCandidate::driverId)
                .filter(driverId -> !driverId.equals(original.driverId()))
                .findFirst()
                .orElseThrow();
        RouteProposal dominatedSameDriver = shapedProposal(original, original.proposalId() + "-same-driver", original.stopOrder(), 1800.0, 1500.0, 14, 0.72, 0.60);
        RouteProposal betterDifferentDriver = shapedProposal(original, original.proposalId() + "-different-driver", original.stopOrder().reversed(), 1300.0, 1100.0, 10, 0.84, 0.45, alternateDriverId);
        DispatchRouteProposalStage stage = new DispatchRouteProposalStage(
                routeProposalStage.schemaVersion(),
                java.util.List.of(dominatedSameDriver, betterDifferentDriver),
                routeProposalStage.routeProposalSummary(),
                routeProposalStage.hotStartReuseSummary(),
                routeProposalStage.stageLatencies(),
                routeProposalStage.mlStageMetadata(),
                routeProposalStage.degradeReasons());
        DispatchScenarioStage localScenarioStage = new DispatchScenarioStage(
                scenarioStage.schemaVersion(),
                java.util.List.of(),
                java.util.List.of(robustUtility(dominatedSameDriver.proposalId()), robustUtility(betterDifferentDriver.proposalId())),
                scenarioStage.scenarioEvaluationSummary(),
                scenarioStage.freshnessMetadata(),
                scenarioStage.stageLatencies(),
                scenarioStage.mlStageMetadata(),
                scenarioStage.degradeReasons());
        SelectorCandidateBuilder builder = new SelectorCandidateBuilder(properties);

        SelectorCandidateBuildResult buildResult = builder.build(stage, localScenarioStage, routeCandidateStage, context);

        assertTrue(buildResult.candidateEnvelopes().stream()
                .anyMatch(envelope -> envelope.candidate().proposalId().equals(dominatedSameDriver.proposalId())));
        assertTrue(buildResult.candidateEnvelopes().stream()
                .anyMatch(envelope -> envelope.candidate().proposalId().equals(betterDifferentDriver.proposalId())));
    }    private double bundleSizeLift(RouteProposal proposal) {
        int bundleSize = proposal.stopOrder().size();
        var analysis = RouteShapeQuality.analyze(proposal);
        if (bundleSize <= 2) {
            return proposal.straightnessScore() < 0.55 || analysis.detourRatio() > RouteShapeQuality.DETOUR_WEAK_RATIO ? -0.04 : 0.0;
        }
        if (proposal.straightnessScore() < 0.62
                || proposal.turnCount() > (7 * bundleSize + 6)
                || analysis.detourRatio() > 1.55
                || analysis.backtrackCount() > 0) {
            return 0.0;
        }
        double compactShapeBonus = Math.min(0.03, Math.max(0.0, analysis.shapeScore() - 0.65) * 0.08);
        return Math.min(0.14, (0.045 * (bundleSize - 2)) + compactShapeBonus);
    }


    private RobustUtility robustUtility(String proposalId) {
        return new RobustUtility("robust-utility/v1", proposalId, 0.8, 0.7, 0.8, 0.9, 0.82, 3, 3);
    }

    private RouteProposal shapedProposal(RouteProposal original,
                                         String proposalId,
                                         java.util.List<String> stopOrder,
                                         double routeCost,
                                         double travelTimeSeconds,
                                         int turnCount,
                                         double straightnessScore,
                                         double congestionScore) {
        return shapedProposal(original, proposalId, stopOrder, routeCost, travelTimeSeconds, turnCount, straightnessScore, congestionScore, original.driverId());
    }

    private RouteProposal shapedProposal(RouteProposal original,
                                         String proposalId,
                                         java.util.List<String> stopOrder,
                                         double routeCost,
                                         double travelTimeSeconds,
                                         int turnCount,
                                         double straightnessScore,
                                         double congestionScore,
                                         String driverId) {
        return new RouteProposal(
                original.schemaVersion(),
                proposalId,
                original.bundleId(),
                stopOrder.getFirst(),
                driverId,
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
