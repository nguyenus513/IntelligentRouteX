package com.routechain.v2.rolling;

import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.BundleFamily;
import com.routechain.v2.bundle.BundleProposalSource;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.DriverShortlistSummary;
import com.routechain.v2.route.PickupAnchor;
import com.routechain.v2.route.PickupAnchorSummary;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RollingReoptimizationPrioritizerTest {

    private final RollingReoptimizationPrioritizer prioritizer = new RollingReoptimizationPrioritizer();

    @Test
    void reoptimizationIntentPromotesTouchedBundlesBeforeRouteGeneration() {
        DispatchRouteCandidateStage stage = stage(List.of(
                candidate("bundle-normal", "order-normal", "driver-a", 0.85, 4.0),
                candidate("bundle-reopt", "order-reopt", "driver-b", 0.60, 5.0)));
        List<BundleCandidate> bundles = List.of(
                bundle("bundle-normal", List.of("order-normal")),
                bundle("bundle-reopt", List.of("order-reopt")));
        RollingHoldDecision decision = new RollingHoldDecision(
                "rolling-hold-decision/v1",
                "order-reopt",
                RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE,
                0,
                0.72,
                0.64,
                0.28,
                List.of("reoptimize-active-route-low-driver-proximity"));

        DispatchRouteCandidateStage prioritized = prioritizer.apply(stage, bundles, List.of(decision));

        assertEquals("driver-b", prioritized.driverCandidates().getFirst().driverId());
        assertEquals(1, prioritized.driverCandidates().getFirst().rank());
        assertTrue(prioritized.driverCandidates().getFirst().rerankScore() > 0.60);
        assertTrue(prioritized.driverCandidates().getFirst().reasons().contains("rolling-active-route-reoptimization-intent"));
        assertTrue(prioritized.degradeReasons().contains("rolling-horizon-driver-reprioritized"));
        assertTrue(prioritized.driverShortlistSummary().degradeReasons().contains("rolling-horizon-driver-reprioritized"));
    }

    @Test
    void nonReoptimizationDecisionsDoNotChangeCandidateOrder() {
        DispatchRouteCandidateStage stage = stage(List.of(
                candidate("bundle-a", "order-a", "driver-a", 0.85, 4.0),
                candidate("bundle-b", "order-b", "driver-b", 0.60, 5.0)));
        RollingHoldDecision decision = new RollingHoldDecision(
                "rolling-hold-decision/v1",
                "order-b",
                RollingDecisionMode.MICRO_BATCH,
                30,
                0.72,
                0.64,
                0.28,
                List.of("micro-batch-compatible-nearby-orders"));

        DispatchRouteCandidateStage prioritized = prioritizer.apply(stage, List.of(bundle("bundle-b", List.of("order-b"))), List.of(decision));

        assertEquals(stage.driverCandidates(), prioritized.driverCandidates());
        assertEquals(stage.degradeReasons(), prioritized.degradeReasons());
    }

    private DispatchRouteCandidateStage stage(List<DriverCandidate> candidates) {
        return new DispatchRouteCandidateStage(
                "dispatch-route-candidate-stage/v1",
                List.of(new PickupAnchor("pickup-anchor/v1", "bundle-reopt", "order-reopt", "order-reopt", 1, 0.80, List.of())),
                new PickupAnchorSummary("pickup-anchor-summary/v1", 2, 2, 1.0, List.of()),
                candidates,
                new DriverShortlistSummary("driver-shortlist-summary/v1", 2, 2, 2, 2, List.of()),
                List.of(),
                List.of(),
                List.of());
    }

    private DriverCandidate candidate(String bundleId, String orderId, String driverId, double rerankScore, double pickupEta) {
        return new DriverCandidate(
                "driver-candidate/v1",
                bundleId,
                orderId,
                driverId,
                0,
                pickupEta,
                rerankScore,
                rerankScore,
                List.of(),
                List.of());
    }

    private BundleCandidate bundle(String bundleId, List<String> orderIds) {
        return new BundleCandidate(
                "bundle-candidate/v1",
                bundleId,
                BundleProposalSource.DETERMINISTIC_FAMILY,
                BundleFamily.COMPACT_CLIQUE,
                "cluster-1",
                false,
                List.of(),
                orderIds,
                String.join("|", orderIds),
                orderIds.getFirst(),
                "corridor-1",
                0.80,
                true,
                List.of());
    }
}
