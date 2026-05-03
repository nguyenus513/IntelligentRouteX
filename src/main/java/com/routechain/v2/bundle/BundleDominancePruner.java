package com.routechain.v2.bundle;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class BundleDominancePruner {
    private static final int MAX_RETAINED_CANDIDATES = 256;
    private static final int MIN_RETAINED_PER_FAMILY = 8;

    public List<BundleCandidate> prune(List<BundleCandidate> candidates) {
        Map<String, BundleCandidate> bestByFamilyAndSignature = new LinkedHashMap<>();
        for (BundleCandidate candidate : candidates.stream().sorted(bundleComparator()).toList()) {
            String key = candidate.family().name() + "|" + candidate.orderSetSignature();
            bestByFamilyAndSignature.merge(key, candidate, this::better);
        }

        Map<String, BundleCandidate> bestBySignature = new LinkedHashMap<>();
        for (BundleCandidate candidate : bestByFamilyAndSignature.values().stream().sorted(bundleComparator()).toList()) {
            bestBySignature.merge(candidate.orderSetSignature(), candidate, this::better);
        }
        List<BundleCandidate> unique = bestBySignature.values().stream().sorted(bundleComparator()).toList();
        if (unique.size() <= MAX_RETAINED_CANDIDATES) {
            return unique;
        }
        Map<String, BundleCandidate> retainedById = new LinkedHashMap<>();
        for (BundleFamily family : BundleFamily.values()) {
            unique.stream()
                    .filter(candidate -> candidate.family() == family)
                    .limit(MIN_RETAINED_PER_FAMILY)
                    .forEach(candidate -> retainedById.putIfAbsent(candidate.bundleId(), candidate));
        }
        unique.forEach(candidate -> {
            if (retainedById.size() < MAX_RETAINED_CANDIDATES) {
                retainedById.putIfAbsent(candidate.bundleId(), candidate);
            }
        });
        return retainedById.values().stream().sorted(bundleComparator()).toList();
    }

    public Comparator<BundleCandidate> bundleComparator() {
        return Comparator.comparingDouble(BundleCandidate::score).reversed()
                .thenComparing((BundleCandidate candidate) -> candidate.orderIds().size(), Comparator.reverseOrder())
                .thenComparing(BundleCandidate::orderSetSignature)
                .thenComparing(candidate -> candidate.family().name());
    }

    private BundleCandidate better(BundleCandidate left, BundleCandidate right) {
        return bundleComparator().compare(left, right) <= 0 ? left : right;
    }
}
