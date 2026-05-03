package com.routechain.v2.bundle;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BundleDominancePrunerTest {

    @Test
    void deduplicatesByOrderSetSignatureAndKeepsBestCandidate() {
        BundleDominancePruner pruner = new BundleDominancePruner();
        List<BundleCandidate> retained = pruner.prune(List.of(
                new BundleCandidate("bundle-candidate/v1", "a", BundleProposalSource.DETERMINISTIC_FAMILY, BundleFamily.COMPACT_CLIQUE, "cluster-001", false, List.of(), List.of("order-1", "order-2"), "order-1|order-2", "order-1", "0:0", 0.70, true, List.of()),
                new BundleCandidate("bundle-candidate/v1", "b", BundleProposalSource.DETERMINISTIC_FAMILY, BundleFamily.COMPACT_CLIQUE, "cluster-001", false, List.of(), List.of("order-1", "order-2"), "order-1|order-2", "order-1", "0:0", 0.65, true, List.of()),
                new BundleCandidate("bundle-candidate/v1", "c", BundleProposalSource.GREEDRL_PROPOSAL, BundleFamily.CORRIDOR_CHAIN, "cluster-001", false, List.of(), List.of("order-1", "order-2"), "order-1|order-2", "order-1", "0:0", 0.75, true, List.of())));

        assertEquals(1, retained.size());
        assertEquals("c", retained.getFirst().bundleId());
    }

    @Test
    void preservesFamilyDiversityWhenPoolExceedsCap() {
        BundleDominancePruner pruner = new BundleDominancePruner();
        java.util.ArrayList<BundleCandidate> candidates = new java.util.ArrayList<>();
        for (int index = 0; index < 270; index++) {
            BundleFamily family = index < 260 ? BundleFamily.COMPACT_CLIQUE : BundleFamily.LATE_RISK_RESCUE;
            candidates.add(new BundleCandidate(
                    "bundle-candidate/v1",
                    "candidate-" + index,
                    BundleProposalSource.DETERMINISTIC_FAMILY,
                    family,
                    "cluster-001",
                    false,
                    List.of(),
                    List.of("order-" + index, "order-x" + index),
                    "order-" + index + "|order-x" + index,
                    "order-" + index,
                    "0:0",
                    1000 - index,
                    true,
                    List.of()));
        }

        List<BundleCandidate> retained = pruner.prune(candidates);

        assertEquals(256, retained.size());
        assertTrue(retained.stream().anyMatch(candidate -> candidate.family() == BundleFamily.LATE_RISK_RESCUE));
    }
}
