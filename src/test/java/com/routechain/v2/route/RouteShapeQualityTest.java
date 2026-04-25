package com.routechain.v2.route;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteShapeQualityTest {

    @Test
    void classifiesMultiOrderZigzagAsRejectShape() {
        RouteProposal proposal = proposal("zigzag", List.of("order-1", "order-2"), 3000.0, 2600.0, 41, 0.30, 1.0);

        assertEquals("REJECT_SHAPE", RouteShapeQuality.verdict(proposal));
        assertTrue(RouteShapeQuality.penalty(proposal) > 0.20);
        assertTrue(RouteShapeQuality.reasons(proposal).contains("route-shape-straightness-penalty"));
    }

    @Test
    void rejectsMultiOrderRouteBelowOperationalStraightnessFloor() {
        RouteProposal proposal = proposal("bad-shape", List.of("order-1", "order-2", "order-3"), 2900.0, 2400.0, 33, 0.46, 1.0);

        assertEquals("REJECT_SHAPE", RouteShapeQuality.verdict(proposal));
    }

    @Test
    void classifiesMultiOrderVisualRiskAsWeakShape() {
        RouteProposal proposal = proposal("weak-shape", List.of("order-1", "order-2"), 1800.0, 1500.0, 18, 0.58, 0.93);

        assertEquals("WEAK_SHAPE", RouteShapeQuality.verdict(proposal));
        assertTrue(RouteShapeQuality.reasons(proposal).contains("route-shape-weak-straightness"));
        assertTrue(RouteShapeQuality.reasons(proposal).contains("route-shape-weak-turn-count"));
    }

    @Test
    void cleanerRouteDominatesWorseRouteWithSameOrderSet() {
        RouteProposal clean = proposal("clean", List.of("order-2", "order-1"), 2100.0, 1800.0, 18, 0.64, 0.70);
        RouteProposal zigzag = proposal("zigzag", List.of("order-1", "order-2"), 2500.0, 2100.0, 28, 0.22, 1.0);

        assertTrue(RouteShapeQuality.dominates(clean, zigzag));
    }

    private RouteProposal proposal(String proposalId,
                                   List<String> stopOrder,
                                   double routeCost,
                                   double travelTimeSeconds,
                                   int turnCount,
                                   double straightnessScore,
                                   double congestionScore) {
        return new RouteProposal(
                "route-proposal/v1",
                proposalId,
                "bundle-1",
                stopOrder.getFirst(),
                "driver-1",
                RouteProposalSource.HEURISTIC_SAFE,
                stopOrder,
                4.0,
                20.0,
                0.8,
                true,
                List.of(),
                List.of(),
                2,
                routeCost,
                travelTimeSeconds,
                routeCost,
                0.7,
                0.3,
                turnCount,
                0,
                congestionScore,
                straightnessScore,
                true,
                List.of());
    }
}
