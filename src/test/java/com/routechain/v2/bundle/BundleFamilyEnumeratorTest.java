package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class BundleFamilyEnumeratorTest {

    @Test
    void emitsFamiliesOnlyWhenPrerequisitesExist() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        BundleFamilyEnumerator enumerator = new BundleFamilyEnumerator(properties);
        BundleContext context = new BundleContext(
                BundleTestFixtures.window().orders(),
                BundleTestFixtures.graph(),
                List.of(new BoundaryExpansion("boundary-expansion/v1", "cluster-001", List.of("order-1"), List.of("order-3"), List.of(), java.util.Map.of("order-3", 0.82), List.of(), false)));
        BundleSeed seed = new BundleSeed(
                BundleTestFixtures.microClusters().getFirst(),
                List.of("order-1", "order-2", "order-3"),
                List.of("order-3"),
                List.of("order-1", "order-2", "order-3"),
                java.util.Map.of("order-3", 0.82));

        List<BundleCandidate> candidates = enumerator.enumerate(seed, context);

        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.BOUNDARY_CROSS));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.URGENT_COMPANION));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.SAME_RESTAURANT));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.SAME_DELIVERY_ZONE));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.LATE_RISK_RESCUE));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.URGENT_SINGLE_FALLBACK));
        assertTrue(candidates.stream().anyMatch(candidate -> candidate.family() == BundleFamily.DIVERSITY_EXPLORATION));
    }
}
