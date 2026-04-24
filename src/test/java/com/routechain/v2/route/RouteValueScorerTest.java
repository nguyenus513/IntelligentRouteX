package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteValueScorerTest {

    @Test
    void prefersBetterPickupEtaAndPenalizesFallbackSource() {
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(RouteChainDispatchV2Properties.defaults());
        String bundleId = context.bundleIds().getFirst();
        PickupAnchor pickupAnchor = new PickupAnchor("pickup-anchor/v1", bundleId, context.orderSetSignature(bundleId), context.bundle(bundleId).seedOrderId(), 1, 0.8, List.of());
        DriverCandidate driverCandidate = new DriverCandidate("driver-candidate/v1", bundleId, pickupAnchor.anchorOrderId(), context.availableDrivers().getFirst().driverId(), 1, 5.0, 0.8, 0.8, List.of(), List.of());
        RouteValueScorer scorer = new RouteValueScorer();

        RouteProposalCandidate faster = scorer.score(candidate(bundleId, pickupAnchor, driverCandidate, RouteProposalSource.HEURISTIC_FAST, 4.0, 20.0), context);
        RouteProposalCandidate fallback = scorer.score(candidate(bundleId, pickupAnchor, driverCandidate, RouteProposalSource.FALLBACK_SIMPLE, 4.0, 20.0), context);
        RouteProposalCandidate slower = scorer.score(candidate(bundleId, pickupAnchor, driverCandidate, RouteProposalSource.HEURISTIC_FAST, 8.0, 20.0), context);

        assertTrue(faster.proposal().routeValue() > slower.proposal().routeValue());
        assertTrue(faster.proposal().routeValue() > fallback.proposal().routeValue());
    }

    @Test
    void penalizesZigzagShapeEvenWhenEtaIsAttractive() {
        DispatchCandidateContext context = RouteTestFixtures.candidateContext(RouteChainDispatchV2Properties.defaults());
        String bundleId = context.bundleIds().getFirst();
        PickupAnchor pickupAnchor = new PickupAnchor("pickup-anchor/v1", bundleId, context.orderSetSignature(bundleId), context.bundle(bundleId).seedOrderId(), 1, 0.8, List.of());
        DriverCandidate driverCandidate = new DriverCandidate("driver-candidate/v1", bundleId, pickupAnchor.anchorOrderId(), context.availableDrivers().getFirst().driverId(), 1, 5.0, 0.8, 0.8, List.of(), List.of());
        RouteValueScorer scorer = new RouteValueScorer();

        RouteProposalCandidate clean = scorer.score(candidateWithShape(bundleId, pickupAnchor, driverCandidate, 8.0, 24.0, 0.82, 8, 0.45), context);
        RouteProposalCandidate zigzag = scorer.score(candidateWithShape(bundleId, pickupAnchor, driverCandidate, 4.0, 20.0, 0.18, 32, 1.0), context);

        assertTrue(clean.proposal().routeValue() > zigzag.proposal().routeValue());
        assertTrue(zigzag.proposal().reasons().contains("route-shape-straightness-penalty"));
        assertTrue(zigzag.proposal().reasons().contains("route-shape-turn-penalty"));
    }

    private RouteProposalCandidate candidate(String bundleId,
                                             PickupAnchor pickupAnchor,
                                             DriverCandidate driverCandidate,
                                             RouteProposalSource source,
                                             double projectedPickupEta,
                                             double projectedCompletionEta) {
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                bundleId + "|" + source.name(),
                bundleId,
                pickupAnchor.anchorOrderId(),
                driverCandidate.driverId(),
                source,
                List.copyOf(RouteTestFixtures.candidateContext(RouteChainDispatchV2Properties.defaults()).bundle(bundleId).orderIds()),
                projectedPickupEta,
                projectedCompletionEta,
                0.0,
                true,
                List.of(),
                List.of());
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(bundleId, pickupAnchor.anchorOrderId(), driverCandidate.driverId());
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(tupleKey, source, RouteProposalEngine.stopOrderSignature(proposal.stopOrder()), 0, 0, 0, 0, 0, 0, 0, 0, source == RouteProposalSource.FALLBACK_SIMPLE ? 0.05 : 0.0, List.of()));
    }

    private RouteProposalCandidate candidateWithShape(String bundleId,
                                                      PickupAnchor pickupAnchor,
                                                      DriverCandidate driverCandidate,
                                                      double projectedPickupEta,
                                                      double projectedCompletionEta,
                                                      double straightnessScore,
                                                      int turnCount,
                                                      double congestionScore) {
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                bundleId + "|shape|" + straightnessScore,
                bundleId,
                pickupAnchor.anchorOrderId(),
                driverCandidate.driverId(),
                RouteProposalSource.HEURISTIC_FAST,
                List.copyOf(RouteTestFixtures.candidateContext(RouteChainDispatchV2Properties.defaults()).bundle(bundleId).orderIds()),
                projectedPickupEta,
                projectedCompletionEta,
                0.0,
                true,
                List.of(),
                List.of(),
                2,
                1000.0,
                300.0,
                400.0,
                0.7,
                0.3,
                turnCount,
                0,
                congestionScore,
                straightnessScore,
                true,
                List.of());
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(bundleId, pickupAnchor.anchorOrderId(), driverCandidate.driverId());
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(tupleKey, RouteProposalSource.HEURISTIC_FAST, RouteProposalEngine.stopOrderSignature(proposal.stopOrder()), 0, 0, 0, 0, 0, 0, 0, 0, 0.0, List.of()));
    }
}
