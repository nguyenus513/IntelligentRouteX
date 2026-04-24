package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RouteProposalPrunerTest {

    @Test
    void deduplicatesBySourceAndStopOrderAndRetainsStableTopProposals() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().setMaxRouteAlternatives(2);
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey("bundle-1", "order-1", "driver-1");
        PickupAnchor pickupAnchor = new PickupAnchor("pickup-anchor/v1", "bundle-1", "order-1|order-2", "order-1", 1, 0.7, List.of());
        DriverCandidate driverCandidate = new DriverCandidate("driver-candidate/v1", "bundle-1", "order-1", "driver-1", 1, 5.0, 0.8, 0.8, List.of(), List.of());
        RouteProposalPruner pruner = new RouteProposalPruner(properties);

        List<RouteProposalCandidate> retained = pruner.prune(List.of(
                candidate("proposal-a", tupleKey, pickupAnchor, driverCandidate, RouteProposalSource.HEURISTIC_FAST, List.of("order-1", "order-2"), 0.80),
                candidate("proposal-b", tupleKey, pickupAnchor, driverCandidate, RouteProposalSource.HEURISTIC_FAST, List.of("order-1", "order-2"), 0.75),
                candidate("proposal-c", tupleKey, pickupAnchor, driverCandidate, RouteProposalSource.HEURISTIC_SAFE, List.of("order-1", "order-2"), 0.78)));

        assertEquals(2, retained.size());
        assertEquals("proposal-a", retained.getFirst().proposal().proposalId());
    }

    @Test
    void removesShapeDominatedStopOrderBeforeRetainingAlternatives() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().setMaxRouteAlternatives(4);
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey("bundle-1", "order-1", "driver-1");
        PickupAnchor pickupAnchor = new PickupAnchor("pickup-anchor/v1", "bundle-1", "order-1|order-2", "order-1", 1, 0.7, List.of());
        DriverCandidate driverCandidate = new DriverCandidate("driver-candidate/v1", "bundle-1", "order-1", "driver-1", 1, 5.0, 0.8, 0.8, List.of(), List.of());
        RouteProposalPruner pruner = new RouteProposalPruner(properties);

        List<RouteProposalCandidate> retained = pruner.prune(List.of(
                shapedCandidate("zigzag", tupleKey, pickupAnchor, driverCandidate, List.of("order-1", "order-2"), 0.91, 2800.0, 2300.0, 32, 0.18, 1.0),
                shapedCandidate("clean-reverse", tupleKey, pickupAnchor, driverCandidate, List.of("order-2", "order-1"), 0.88, 2500.0, 2100.0, 28, 0.22, 1.0),
                shapedCandidate("clean", tupleKey, pickupAnchor, driverCandidate, List.of("order-2", "order-1"), 0.86, 2100.0, 1900.0, 18, 0.62, 0.7)));

        assertEquals(1, retained.size());
        assertEquals("clean", retained.getFirst().proposal().proposalId());
    }

    private RouteProposalCandidate candidate(String proposalId,
                                             RouteProposalTupleKey tupleKey,
                                             PickupAnchor pickupAnchor,
                                             DriverCandidate driverCandidate,
                                             RouteProposalSource source,
                                             List<String> stopOrder,
                                             double routeValue) {
        return new RouteProposalCandidate(
                new RouteProposal("route-proposal/v1", proposalId, "bundle-1", "order-1", "driver-1", source, stopOrder, 4.0, 20.0, routeValue, true, List.of(), List.of()),
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(tupleKey, source, RouteProposalEngine.stopOrderSignature(stopOrder), 0, 0, 0, 0, 0, 0, 0, 0, 0, List.of()));
    }

    private RouteProposalCandidate shapedCandidate(String proposalId,
                                                   RouteProposalTupleKey tupleKey,
                                                   PickupAnchor pickupAnchor,
                                                   DriverCandidate driverCandidate,
                                                   List<String> stopOrder,
                                                   double routeValue,
                                                   double routeCost,
                                                   double travelTimeSeconds,
                                                   int turnCount,
                                                   double straightnessScore,
                                                   double congestionScore) {
        RouteProposal proposal = new RouteProposal(
                "route-proposal/v1",
                proposalId,
                "bundle-1",
                "order-1",
                "driver-1",
                RouteProposalSource.HEURISTIC_SAFE,
                stopOrder,
                4.0,
                20.0,
                routeValue,
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
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(tupleKey, proposal.source(), RouteProposalEngine.stopOrderSignature(stopOrder), 0, 0, 0, 0, 0, 0, 0, 0, 0, List.of()));
    }
}
