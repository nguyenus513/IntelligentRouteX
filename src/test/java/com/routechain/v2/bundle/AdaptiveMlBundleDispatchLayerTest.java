package com.routechain.v2.bundle;

import com.routechain.v2.EtaContext;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdaptiveMlBundleDispatchLayerTest {

    private final AdaptiveMlBundleDispatchLayer layer = new AdaptiveMlBundleDispatchLayer();
    private final BundleContext context = new BundleContext(BundleTestFixtures.window().orders(), BundleTestFixtures.graph(), List.of());

    @Test
    void admissionPriorityUsesAgingLateRiskRegretDriverFitAndBundlePotential() {
        double oldUrgentPriority = layer.admissionPriority(
                BundleTestFixtures.orders().get(2),
                context,
                BundleTestFixtures.weatherBadEtaContext(),
                Instant.parse("2026-04-16T12:30:00Z"));
        double freshPriority = layer.admissionPriority(
                BundleTestFixtures.orders().get(0),
                context,
                BundleTestFixtures.clearEtaContext(),
                Instant.parse("2026-04-16T12:01:00Z"));

        assertTrue(oldUrgentPriority > freshPriority);
    }

    @Test
    void bundleScoringRewardsCompactCompatibleBundlesAndPenalizesLateRisk() {
        BundleCandidate compact = candidate("compact", List.of("order-1", "order-2"), BundleFamily.COMPACT_CLIQUE, 0.0);
        BundleCandidate scoredClear = layer.scoreBundle(
                compact,
                context,
                BundleTestFixtures.clearEtaContext(),
                Instant.parse("2026-04-16T12:05:00Z"),
                0.9);
        BundleCandidate scoredRisky = layer.scoreBundle(
                compact,
                context,
                BundleTestFixtures.weatherBadEtaContext(),
                Instant.parse("2026-04-16T12:45:00Z"),
                0.9);

        assertTrue(scoredClear.score() > scoredRisky.score());
    }

    @Test
    void greedySetPackingSelectsNonOverlappingBundlesOnly() {
        List<BundleCandidate> selected = layer.greedySetPack(List.of(
                candidate("ab", List.of("order-1", "order-2"), BundleFamily.COMPACT_CLIQUE, 0.95),
                candidate("ac", List.of("order-1", "order-3"), BundleFamily.CORRIDOR_CHAIN, 0.90),
                candidate("cd", List.of("order-3", "order-4"), BundleFamily.CORRIDOR_CHAIN, 0.80)));

        assertEquals(List.of("ab", "cd"), selected.stream().map(BundleCandidate::bundleId).toList());
    }

    @Test
    void breakRiskIncreasesForBadWeatherOldBoundaryBundles() {
        BundleCandidate compact = candidate("compact", List.of("order-1", "order-2"), BundleFamily.COMPACT_CLIQUE, 0.7);
        BundleCandidate boundary = new BundleCandidate(
                "bundle-candidate/v1",
                "boundary",
                BundleProposalSource.DETERMINISTIC_FAMILY,
                BundleFamily.BOUNDARY_CROSS,
                "cluster-001",
                true,
                List.of("order-3"),
                List.of("order-2", "order-3", "order-4"),
                "order-2|order-3|order-4",
                "order-2",
                "0:0",
                0.7,
                true,
                List.of());

        double safeRisk = layer.breakRisk(compact, context, BundleTestFixtures.clearEtaContext(), Instant.parse("2026-04-16T12:03:00Z"));
        double breakRisk = layer.breakRisk(boundary, context, BundleTestFixtures.weatherBadEtaContext(), Instant.parse("2026-04-16T12:45:00Z"));

        assertTrue(breakRisk > safeRisk);
    }

    private BundleCandidate candidate(String id, List<String> orderIds, BundleFamily family, double score) {
        return new BundleCandidate(
                "bundle-candidate/v1",
                id,
                BundleProposalSource.DETERMINISTIC_FAMILY,
                family,
                "cluster-001",
                false,
                List.of(),
                orderIds,
                String.join("|", orderIds.stream().sorted().toList()),
                orderIds.getFirst(),
                "0:0",
                score,
                true,
                List.of());
    }
}
